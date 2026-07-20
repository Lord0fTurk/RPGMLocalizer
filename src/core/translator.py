"""
Google Web Translator / Lingva Translator implementation.

v0.7.0 — Segment-based: RPG Maker codes are stripped *before* translation and
re-inserted *after*, so they are NEVER exposed to the translation API.  This
eliminates the fragile token-protection + fuzzy-recovery system entirely.
"""
from __future__ import annotations

import asyncio
import aiohttp
import logging
import re
import time
import random
import urllib.parse
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from abc import ABC, abstractmethod

from src.core.text_segmenter import (
    segment_text,
    reassemble as segmenter_reassemble,
    Segment,
    TEXT_SEGMENT_SEPARATOR,
)
from src.core.constants import (
    TRANSLATOR_MAX_SAFE_CHARS,
    TRANSLATOR_MAX_SLICE_CHARS,
    DEFAULT_USE_MULTI_ENDPOINT,
    DEFAULT_ENABLE_LINGVA_FALLBACK,
    DEFAULT_REQUEST_DELAY_MS,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MIRROR_MAX_FAILURES,
    DEFAULT_MIRROR_BAN_TIME,
    DEFAULT_RACING_ENDPOINTS,
)


class TranslationEngine(Enum):
    GOOGLE = "google"
    DEEPL = "deepl"


@dataclass(slots=True)
class TranslationRequest:
    text: str
    source_lang: str
    target_lang: str
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class TranslationResult:
    original_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    success: bool
    error: str | None = None
    metadata: dict = field(default_factory=dict)


class BaseTranslator(ABC):
    def __init__(self, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self._session: aiohttp.ClientSession | None = None
        self._connector: aiohttp.TCPConnector | None = None
        self.timeout_seconds = timeout_seconds

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._connector = aiohttp.TCPConnector(limit=256, ttl_dns_cache=300)
            timeout = aiohttp.ClientTimeout(
                total=max(45, self.timeout_seconds),
                sock_connect=5,
                sock_read=30,
            )
            _ua = random.choice(self._USER_AGENTS) if hasattr(self, '_USER_AGENTS') else None
            _headers = {"User-Agent": _ua, "Connection": "keep-alive"} if _ua else {}
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=timeout,
                headers=_headers,
            )
        return self._session

    async def close(self):
        if self._session:
            try:
                await self._session.close()
            except Exception as e:
                self.logger.warning(f"Error closing session: {e}")
            finally:
                self._session = None
                self._connector = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    @abstractmethod
    async def translate_batch(self, requests: List[Dict[str, Any]], progress_callback=None) -> List[TranslationResult]:
        pass


class GoogleTranslator(BaseTranslator):
    """
    Multi-endpoint Google Translator with Lingva fallback.

    v0.7.0 changes
    --------------
    - RPG Maker codes are handled via text_segmenter (segment-based)
    - No more token-based protection / 4-phase fuzzy recovery
    - No more HTMLShield fallback
    - The `use_syntax_guard` / `use_html_protection` flags are kept as no-ops
      for settings backward compatibility.
    """

    _USER_AGENTS: list[str] = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    ]

    _GLOBAL_COOLDOWN_IDENTITY_SECS: int = 10
    _GLOBAL_COOLDOWN_429_SECS: int = 20
    _GLOBAL_COOLDOWN_IDENTITY_MAX_SECS: int = 60
    _CIRCUIT_BREAKER_THRESHOLD: int = 5
    _CIRCUIT_BREAKER_COOLDOWN_SECS: int = 45

    google_endpoints = [
        "https://translate.googleapis.com/translate_a/single",
        "https://translate.google.com/translate_a/single",
        "https://translate.google.com.tr/translate_a/single",
        "https://translate.google.co.uk/translate_a/single",
        "https://translate.google.de/translate_a/single",
        "https://translate.google.fr/translate_a/single",
        "https://translate.google.ru/translate_a/single",
        "https://translate.google.jp/translate_a/single",
        "https://translate.google.ca/translate_a/single",
        "https://translate.google.com.au/translate_a/single",
        "https://translate.google.pl/translate_a/single",
        "https://translate.google.es/translate_a/single",
        "https://translate.google.it/translate_a/single",
    ]

    lingva_instances = [
        "https://lingva.ml",
        "https://lingva.lunar.icu",
        "https://translate.plausibility.cloud",
        "https://lingva.garudalinux.org",
    ]

    def __init__(
        self,
        concurrency: int = 16,
        batch_size: int = 15,
        max_slice_chars: int | None = None,
        use_multi_endpoint: bool = DEFAULT_USE_MULTI_ENDPOINT,
        enable_lingva_fallback: bool = DEFAULT_ENABLE_LINGVA_FALLBACK,
        request_delay_ms: int = DEFAULT_REQUEST_DELAY_MS,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        mirror_max_failures: int = DEFAULT_MIRROR_MAX_FAILURES,
        mirror_ban_time: int = DEFAULT_MIRROR_BAN_TIME,
        racing_endpoints: int = DEFAULT_RACING_ENDPOINTS,
        use_syntax_guard: bool = True,
        use_html_protection: bool = False,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds)
        self.concurrency = concurrency
        self.batch_size = batch_size
        self._max_chars = TRANSLATOR_MAX_SAFE_CHARS
        self.max_slice_chars = max_slice_chars or TRANSLATOR_MAX_SLICE_CHARS
        self.use_multi_endpoint = use_multi_endpoint
        self.enable_lingva_fallback = enable_lingva_fallback
        self.request_delay_ms = max(0, request_delay_ms)
        self.max_retries = max(1, max_retries)
        self.mirror_max_failures = max(1, mirror_max_failures)
        self.mirror_ban_time = max(10, mirror_ban_time)
        self.racing_endpoints = max(1, racing_endpoints)
        self._endpoint_health: Dict[str, Dict[str, float]] = {}
        self._endpoint_index = 0
        self._lingva_index = 0
        self._endpoint_semaphores: dict[str, asyncio.Semaphore] = {}
        self._global_cooldown_until: float = 0.0
        self._consecutive_identity_count: int = 0
        self._circuit_breaker_active: bool = False
        self._consecutive_429_count: int = 0

        # Adaptive concurrency (RenLocalizer pattern)
        self.adaptive_enabled = True
        self.max_concurrency_cap = max(64, concurrency * 4)
        self.min_concurrency_floor = 4
        self._recent_metrics: deque = deque(maxlen=500)
        self._adapt_lock = asyncio.Lock()
        self._last_adapt_time = 0.0
        self.adapt_interval_sec = 5.0
        self.aggressive_retry = True

        # v0.7.0: use_syntax_guard/use_html_protection are accepted for
        # settings backward compat but ignored — segmenter is always used.
        self.use_syntax_guard = True
        self.use_html_protection = False
        self.logger.info("GoogleTranslator: using segmenter (v0.7.0) — token protection is removed")

        from .constants import REGEX_BATCH_SPLIT
        self.BATCH_SPLIT_PATTERN = re.compile(REGEX_BATCH_SPLIT, re.IGNORECASE | re.DOTALL)

        for ep in self.google_endpoints:
            self._endpoint_health[ep] = {"fails": 0, "banned_until": 0.0}

    @property
    def max_chars(self) -> int:
        return self._max_chars

    def _get_next_endpoint(self) -> str:
        now = time.time()
        available = []
        for ep in self.google_endpoints:
            health = self._endpoint_health.get(ep, {"fails": 0, "banned_until": 0.0})
            if now > health.get("banned_until", 0.0):
                available.append(ep)
        if not available:
            for ep in self.google_endpoints:
                self._endpoint_health[ep] = {"fails": 0, "banned_until": 0.0}
            available = self.google_endpoints[:]
        self._endpoint_index = (min(self._endpoint_index, len(available) - 1) + 1) % len(available)
        return available[self._endpoint_index]

    def _get_next_lingva(self) -> str:
        self._lingva_index = (self._lingva_index + 1) % len(self.lingva_instances)
        return self.lingva_instances[self._lingva_index]

    async def translate_batch(self, requests: List[Dict[str, Any]], progress_callback=None) -> List['TranslationResult']:
        if not requests:
            return []

        results: List[TranslationResult] = []
        for req in requests:
            original_text = req.get('metadata', {}).get('original_text', req['text'])
            results.append(TranslationResult(
                original_text=original_text,
                translated_text=req['text'],
                source_lang=requests[0].get('metadata', {}).get('source_lang', 'auto'),
                target_lang=requests[0].get('metadata', {}).get('target_lang', 'en'),
                success=False,
                metadata=req.get('metadata', {}),
                error="Processing not started",
            ))

        unique_map: Dict[str, List[int]] = {}
        for i, req in enumerate(requests):
            txt = req['text']
            if txt not in unique_map:
                unique_map[txt] = []
            unique_map[txt].append(i)

        unique_texts = list(unique_map.keys())

        first_metadata_lang = requests[0].get('metadata', {}).get('source_lang', 'auto') if requests else 'auto'
        batches_of_text_slices = self._prepare_slices(unique_texts, source_lang=first_metadata_lang)

        sem = asyncio.Semaphore(self.concurrency)

        async def process_slice(slice_texts: List[str]):
            async with sem:
                try:
                    # --- Phase 1: Segment-based protection ---
                    # For each text, segment it and extract clean text.
                    # Store segments for later reassembly.
                    segment_maps: List[List[Segment]] = []
                    clean_batch: List[str] = []
                    bypass_indices = set()

                    for idx, txt in enumerate(slice_texts):
                        segments = segment_text(txt)
                        segment_maps.append(segments)

                        # Build clean text (only TEXT segments joined by separator)
                        text_parts = [s.content for s in segments if s.type.name == "TEXT"]
                        if not text_parts:
                            # No translatable text (only codes)
                            bypass_indices.add(idx)
                            clean_batch.append(".")  # minimal dummy
                        else:
                            clean_batch.append(TEXT_SEGMENT_SEPARATOR.join(text_parts))

                    # --- Phase 2: Join & translate ---
                    from .constants import SAFE_BATCH_SEPARATOR
                    batch_text = SAFE_BATCH_SEPARATOR.join(clean_batch)

                    first_metadata = requests[0].get('metadata', {}) if requests else {}
                    s_lang = first_metadata.get('source_lang', 'auto')
                    t_lang = first_metadata.get('target_lang', 'en')

                    translated_parts = await self._try_translate(batch_text, s_lang, t_lang, len(clean_batch))

                    if not translated_parts:
                        translated_parts = [None] * len(clean_batch)

                        if self._circuit_breaker_active:
                            self.logger.debug("Circuit breaker active — individual retries will use Lingva only")

                        async def retry_single(idx):
                            try:
                                single_res = await self._try_translate(clean_batch[idx], s_lang, t_lang, 1)
                                if single_res:
                                    translated_parts[idx] = single_res[0]
                            except Exception:
                                pass

                        await asyncio.gather(*(retry_single(i) for i in range(len(clean_batch))))

                    # --- Phase 3: Reassemble codes ---
                    for idx, (original, translated, segments) in enumerate(zip(slice_texts, translated_parts, segment_maps)):
                        indices = unique_map.get(original, [])

                        if idx in bypass_indices:
                            final_text = original
                            success = True
                        elif translated:
                            final_text = segmenter_reassemble(translated, segments)
                            success = True
                        else:
                            final_text = original
                            success = False

                        for i_idx in indices:
                            res = results[i_idx]
                            res.translated_text = final_text
                            res.success = success
                            res.error = None if success else "Translation failed or empty"
                            if success and progress_callback:
                                try:
                                    progress_callback(1)
                                except Exception:
                                    pass

                except Exception as e:
                    self.logger.error(f"Batch processing error: {str(e)}")
                    for txt in slice_texts:
                        for idx in unique_map.get(txt, []):
                            results[idx].error = f"Exception: {str(e)}"

        tasks = [process_slice(batch) for batch in batches_of_text_slices]
        if tasks:
            await asyncio.gather(*tasks)

        # Post-batch identity retry (RenLocalizer pattern):
        # unchanged texts likely hit soft rate-limit → retry individually
        if self.aggressive_retry:
            unchanged = [
                i for i, res in enumerate(results)
                if res.success and res.translated_text.strip() == res.original_text.strip()
            ]
            if unchanged and len(unchanged) <= 200:
                self.logger.info(
                    "Post-batch: %d unchanged texts, retrying individually...",
                    len(unchanged),
                )
                async def retry_one(idx):
                    txt = results[idx].original_text
                    segments = segment_text(txt)
                    text_parts = [s.content for s in segments if s.type.name == "TEXT"]
                    if text_parts:
                        clean_txt = TEXT_SEGMENT_SEPARATOR.join(text_parts)
                    else:
                        clean_txt = txt
                    r = await self._try_translate(
                        clean_txt,
                        results[idx].source_lang,
                        results[idx].target_lang,
                        1,
                    )
                    if r and r[0].strip() != txt.strip():
                        if text_parts:
                            results[idx].translated_text = segmenter_reassemble(r[0], segments)
                        else:
                            results[idx].translated_text = r[0]
                        results[idx].success = True
                        results[idx].error = None
                await asyncio.gather(
                    *(asyncio.create_task(retry_one(i)) for i in unchanged),
                    return_exceptions=True,
                )
                recovered = sum(
                    1 for i in unchanged if results[i].success and results[i].translated_text.strip() != results[i].original_text.strip()
                )
                if recovered:
                    self.logger.info("Post-batch retry recovered %d/%d texts", recovered, len(unchanged))

        return results

    def _prepare_slices(self, texts: List[str], source_lang: str = 'auto') -> List[List[str]]:
        slices = []
        current_batch = []
        current_chars = 0
        from .constants import SAFE_BATCH_SEPARATOR

        sep_len = len(SAFE_BATCH_SEPARATOR)

        _CJK_SOURCE_LANGS = {'ja', 'zh', 'zh-cn', 'zh-tw', 'ko', 'zh-hans', 'zh-hant'}
        cjk_multiplier = 0.25 if source_lang.lower() in _CJK_SOURCE_LANGS else 1.0
        base_limit = min(self.max_chars, self.max_slice_chars)
        cjk_limit = max(200, int(base_limit * cjk_multiplier))

        for text in texts:
            text_len = len(text)
            overhead = sep_len if current_batch else 0
            chars_limit = cjk_limit
            if len(current_batch) >= self.batch_size or (current_chars + text_len + overhead > chars_limit and current_batch):
                slices.append(current_batch)
                current_batch = []
                current_chars = 0
                overhead = 0
            current_batch.append(text)
            current_chars += text_len + overhead

        if current_batch:
            slices.append(current_batch)

        return slices

    def _register_failure(self, endpoint: str, count_failure: bool = True) -> None:
        if not count_failure:
            return
        health = self._endpoint_health.setdefault(endpoint, {"fails": 0, "banned_until": 0.0})
        health["fails"] = health.get("fails", 0) + 1
        if health["fails"] >= self.mirror_max_failures:
            health["banned_until"] = time.time() + self.mirror_ban_time

    def _register_success(self, endpoint: str) -> None:
        health = self._endpoint_health.setdefault(endpoint, {"fails": 0, "banned_until": 0.0})
        health["fails"] = 0

    # ------------------------------------------------------------------
    # Adaptive concurrency (ported from RenLocalizer)
    # ------------------------------------------------------------------

    async def _record_metric(self, dur: float, ok: bool):
        if not self.adaptive_enabled:
            return
        self._recent_metrics.append((dur, ok))
        if len(self._recent_metrics) % 25 == 0:
            await self._maybe_adapt_concurrency()

    async def _maybe_adapt_concurrency(self):
        if not self.adaptive_enabled:
            return
        now = time.time()
        if now - self._last_adapt_time < self.adapt_interval_sec:
            return
        if len(self._recent_metrics) < 20:
            return
        async with self._adapt_lock:
            now2 = time.time()
            if now2 - self._last_adapt_time < self.adapt_interval_sec:
                return
            durations = [d for d, _ in self._recent_metrics]
            successes = [s for _, s in self._recent_metrics]
            avg_latency = sum(durations) / len(durations)
            fail_rate = 1 - (sum(1 for s in successes if s) / len(successes))
            old = self.concurrency
            new = old
            if fail_rate > 0.2 or avg_latency > 1.5:
                new = max(self.min_concurrency_floor, int(old * 0.8))
            elif fail_rate < 0.05 and avg_latency < 0.5:
                new = min(self.max_concurrency_cap, max(old + 1, int(old * 1.1)))
            if new != old:
                self.concurrency = new
                self.logger.info(
                    "Adaptive concurrency %d -> %d (lat=%.3fs fail=%.2f%%)",
                    old, new, avg_latency, fail_rate * 100,
                )
            self._last_adapt_time = now2

    async def _try_translate(self, text: str, source: str, target: str, expected_count: int, racing: bool = True) -> Optional[List[str]]:
        params = {
            "client": "gtx",
            "sl": source,
            "tl": target,
            "dt": "t",
            "q": text,
        }

        query = urllib.parse.urlencode(params)

        use_racing = self.use_multi_endpoint and racing
        n_endpoints = self.racing_endpoints if use_racing else 1
        endpoints = [self._get_next_endpoint() for _ in range(n_endpoints)]

        async def call_endpoint(ep):
            query = urllib.parse.urlencode(params)
            url = f"{ep}?{query}"

            ep_sem = self._endpoint_semaphores.setdefault(ep, asyncio.Semaphore(2))

            for attempt in range(1, self.max_retries + 1):
                try:
                    if self.request_delay_ms:
                        await asyncio.sleep(self.request_delay_ms / 1000.0 + random.uniform(0, 0.05))

                    if self._circuit_breaker_active:
                        if self._global_cooldown_until > time.time():
                            self.logger.debug(f"[circuit-breaker] {ep}: bailing out — breaker active")
                            return None
                        self._circuit_breaker_active = False
                        self._consecutive_identity_count = 0
                        self.logger.info(f"[circuit-breaker] {ep}: cooldown expired — resuming")

                    while True:
                        _wait = self._global_cooldown_until - time.time()
                        if _wait <= 0:
                            break
                        self.logger.debug(f"[cooldown] {ep}: waiting {_wait:.1f}s")
                        await asyncio.sleep(min(_wait, 3.0) + random.uniform(0.1, 0.5))

                    if self._circuit_breaker_active:
                        _cb_wait2 = self._global_cooldown_until - time.time()
                        if _cb_wait2 > 0:
                            self.logger.debug(f"[circuit-breaker] {ep}: bailing out after cooldown re-trigger")
                            return None
                        self._circuit_breaker_active = False
                        self._consecutive_identity_count = 0

                    session = await self._get_session()
                    async with ep_sem:
                        req_start = time.time()
                        async with session.get(
                            url,
                            timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
                        ) as resp:
                            elapsed = time.time() - req_start
                            if resp.status == 200:
                                data = await resp.json(content_type=None)
                                if not data or not data[0]:
                                    self._register_failure(ep)
                                    continue

                                full = ""
                                if isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                                    for seg in data[0]:
                                        if isinstance(seg, list) and len(seg) > 0 and seg[0]:
                                            full += str(seg[0])

                                if not full:
                                    self.logger.warning(f"Empty translation from {ep}")
                                    self._register_failure(ep)
                                    continue

                                if full.strip() == text.strip():
                                    # Identity response: Google returned text unchanged.
                                    # Short/technical terms ("HP", "Exit", "ATK") legitimately
                                    # can't be translated — this is NOT a rate-limit signal.
                                    # Accept as-is and continue; only real HTTP 429 triggers
                                    # backoff.  RenLocalizer uses the same approach.
                                    asyncio.ensure_future(self._record_metric(elapsed, True))
                                    return [full.strip()]

                                self._consecutive_identity_count = 0
                                self._circuit_breaker_active = False
                                self._register_success(ep)
                                if self._consecutive_429_count > 0:
                                    self._consecutive_429_count -= 1
                                asyncio.ensure_future(self._record_metric(elapsed, True))

                                full = re.sub(r'\|\s*\|\s*\|RPGMSEP_S\|\s*\|\s*\|', '|||RPGMSEP_S|||', full)
                                full = re.sub(r'\|\s*\|\s*\|RPGMSEP_M\|\s*\|\s*\|', '|||RPGMSEP_M|||', full)
                                full = re.sub(r'\|\s*\|\s*\|RPGMSEP_I\|\s*\|\s*\|', '|||RPGMSEP_I|||', full)
                                full = re.sub(r'\|\s*\|\s*\|TXTSEG\|\s*\|\s*\|', '|||TXTSEG|||', full)

                                parts = self.BATCH_SPLIT_PATTERN.split(full)
                                parts = [p.strip() for p in parts if p.strip()]
                                if len(parts) > expected_count:
                                    parts = parts[:expected_count]

                                if len(parts) != expected_count:
                                    self.logger.error(f"Batch mismatch from {ep}: Got {len(parts)}, expected {expected_count}")
                                    debug_full = full.replace('\r', '').replace('\n', ' ')
                                    self.logger.error(f"RAW: {debug_full[:250]}...")
                                    self._register_failure(ep)
                                    continue
                                return parts

                            if resp.status == 429:
                                asyncio.ensure_future(self._record_metric(elapsed, False))
                                # Escalating global cooldown: 3s→6s→12s→24s (capped 30s)
                                self._consecutive_429_count += 1
                                global_wait = min(3.0 * (2 ** (self._consecutive_429_count - 1)), 30.0)
                                self._global_cooldown_until = max(
                                    self._global_cooldown_until,
                                    time.time() + global_wait,
                                )
                                self._register_failure(ep)
                                wait_time = global_wait + random.uniform(0.5, 1.5)
                                self.logger.warning(
                                    "Google 429 on %s. Cooldown %.0fs (#%d)",
                                    ep, global_wait, self._consecutive_429_count,
                                )
                                await asyncio.sleep(wait_time)
                                continue

                            asyncio.ensure_future(self._record_metric(elapsed, False))
                            self._register_failure(ep)
                            await asyncio.sleep(0.2)
                except Exception:
                    asyncio.ensure_future(self._record_metric(self.timeout_seconds, False))
                    self._register_failure(ep)
                    wait_time = (1.5 ** (attempt - 1)) * 0.5 + random.uniform(0.1, 0.4)
                    await asyncio.sleep(wait_time)
            return None

        result_found = asyncio.Event()
        final_result = None

        async def call_and_signal(ep: str) -> None:
            nonlocal final_result
            res = await call_endpoint(ep)
            if res and not result_found.is_set():
                result_found.set()
                final_result = res

        try:
            async with asyncio.TaskGroup() as tg:
                tasks = [tg.create_task(call_and_signal(ep)) for ep in endpoints]
                while not result_found.is_set() and any(not t.done() for t in tasks):
                    await asyncio.sleep(0.05)
                if result_found.is_set():
                    for t in tasks:
                        if not t.done():
                            t.cancel()
                    return final_result
        except* Exception:
            pass

        if final_result:
            return final_result

        # Lingva fallback
        if self.enable_lingva_fallback and expected_count == 1:
            n = len(self.lingva_instances)
            for _ in range(n):
                try:
                    instance = self._get_next_lingva()
                    url = f"{instance}/api/v1/{source}/{target}/{urllib.parse.quote(text)}"
                    session = await self._get_session()
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=min(self.timeout_seconds, 15))) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            trans = data.get("translation", "")
                            if trans.strip() == text.strip():
                                self.logger.warning(f"Identity response from Lingva {instance}")
                                continue
                            parts = self.BATCH_SPLIT_PATTERN.split(trans.strip())
                            parts = [p.strip() for p in parts if p.strip()]
                            if len(parts) > expected_count:
                                parts = parts[:expected_count]
                            if len(parts) == expected_count:
                                self._consecutive_identity_count = 0
                                self._circuit_breaker_active = False
                                return parts
                except Exception as exc:
                    self.logger.debug(f"Lingva {instance} failed: {type(exc).__name__}: {exc}")
                    await asyncio.sleep(0.3)
        return None

"""
Google Web Translator / Lingva Translator implementation.
Ported and adapted from RenLocalizer for RPGMLocalizer.
"""
from __future__ import annotations

import asyncio
import aiohttp
import logging
import re
import time
import random
import urllib.parse
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from abc import ABC, abstractmethod

from src.utils.html_shield import HTMLShield
from src.core.syntax_guard_rpgm import (
    protect_for_translation,
    restore_from_translation,
    validate_translation_integrity,
    inject_missing_placeholders,
)
from src.core.constants import (
    TRANSLATOR_MAX_SAFE_CHARS,
    TRANSLATOR_MAX_SLICE_CHARS,
    TRANSLATOR_RECURSION_MAX_DEPTH,
    DEFAULT_USE_MULTI_ENDPOINT,
    DEFAULT_ENABLE_LINGVA_FALLBACK,
    DEFAULT_REQUEST_DELAY_MS,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MIRROR_MAX_FAILURES,
    DEFAULT_MIRROR_BAN_TIME,
    DEFAULT_RACING_ENDPOINTS
)

class TranslationEngine(Enum):
    GOOGLE = "google"
    DEEPL = "deepl" # Stub for future

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
        """
        Get or create an aiohttp ClientSession.
        Reuses the session if it's already open, creates a new one otherwise.
        
        Important: Call close() when done to avoid resource leaks.
        """
        if self._session is None or self._session.closed:
            self._connector = aiohttp.TCPConnector(limit=256, ttl_dns_cache=300)
            # Structured timeout: connect fast, give server up to 30s to respond
            # total cap is 45s (or the user-configured value, whichever is larger)
            timeout = aiohttp.ClientTimeout(
                total=max(45, self.timeout_seconds),
                sock_connect=5,
                sock_read=30,
            )
            # Rotate User-Agent per session to avoid bot fingerprinting.
            # Bare aiohttp UA triggers Google soft-429 (identity responses) almost immediately.
            _ua = random.choice(self._USER_AGENTS) if hasattr(self, '_USER_AGENTS') else None
            _headers = {"User-Agent": _ua, "Connection": "keep-alive"} if _ua else {}
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=timeout,
                headers=_headers,
            )
        return self._session

    async def close(self):
        """
        Close the aiohttp session and connector.
        Call this when the translator is no longer needed to prevent resource leaks.
        """
        if self._session:
            try:
                await self._session.close()
            except Exception as e:
                self.logger.warning(f"Error closing session: {e}")
            finally:
                self._session = None
                self._connector = None

    async def __aenter__(self):
        """Context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - automatically closes session."""
        await self.close()

    @abstractmethod
    async def translate_batch(self, requests: List[Dict[str, Any]], progress_callback=None) -> List[TranslationResult]:
        pass

class GoogleTranslator(BaseTranslator):
    """
    Multi-endpoint Google Translator with Lingva fallback.
    Uses web-based translation endpoints, not official API.
    """

    # Browser User-Agent pool — rotated per session to avoid bot fingerprinting.
    # Google's soft-429 (identity response) is triggered almost immediately by
    # the bare "aiohttp/x.y" default UA. These UAs match real desktop browsers.
    _USER_AGENTS: list[str] = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    ]

    # Seconds all mirrors wait after any identity/429 — prevents cascade bans
    _GLOBAL_COOLDOWN_IDENTITY_SECS: int = 10
    _GLOBAL_COOLDOWN_429_SECS: int = 20

    # 10+ Google mirrors
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

    # Ordered by reliability: Hetzner-hosted first (dedicated), Vercel last (cold-start)
    lingva_instances = [
        "https://translate.plausibility.cloud",   # Hetzner, dedicated — most reliable
        "https://lingva.garudalinux.org",          # Hetzner, Garuda Linux mirror
        "https://translate.dr460nf1r3.org",        # Netcup, secondary
        "https://lingva.ml",                       # Vercel, cold-start — tertiary
        "https://translate.igna.wtf",              # Vercel — tertiary
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
        use_html_protection: bool = False
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
        self._endpoint_semaphores: dict[str, asyncio.Semaphore] = {}  # Per-endpoint rate limiter
        self._global_cooldown_until: float = 0.0  # All mirrors pause until this timestamp
        
        # Motor-aware syntax protection strategy
        self.use_syntax_guard = use_syntax_guard  # Use syntax_guard_rpgm (v0.6.6+)
        self.use_html_protection = use_html_protection  # Use HTML wrapping for HTML-supporting engines
        
        # Fallback: Lexer-based HTML Shield (current v0.6.5 system)
        self.shield_system = HTMLShield()
        
        if use_syntax_guard:
            self.logger.info("GoogleTranslator: Using syntax_guard_rpgm for RPG Maker code protection")
        else:
            self.logger.info("GoogleTranslator: Using HTMLShield for code protection (legacy mode)")
        
        # Import split pattern from constants for consistency
        from .constants import REGEX_BATCH_SPLIT
        self.BATCH_SPLIT_PATTERN = re.compile(REGEX_BATCH_SPLIT, re.IGNORECASE | re.DOTALL)

        for ep in self.google_endpoints:
            self._endpoint_health[ep] = {"fails": 0, "banned_until": 0.0}

    @property
    def max_chars(self) -> int:
        """Returns the safe character limit for a single request batch."""
        return self._max_chars

    def _get_next_endpoint(self) -> str:
        """Round-robin endpoint selection with health checks."""
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

        self._endpoint_index = (self._endpoint_index + 1) % len(available)
        return available[self._endpoint_index]

    def _get_next_lingva(self) -> str:
        self._lingva_index = (self._lingva_index + 1) % len(self.lingva_instances)
        return self.lingva_instances[self._lingva_index]

    async def translate_batch(self, requests: List[Dict[str, Any]], progress_callback=None) -> List['TranslationResult']:
        """
        Translates a batch of requests.
        Each request is a dict with: {'text': str, 'metadata': dict}
        Returns a list of TranslationResult objects (Success/Failure).
        
        IMPORTANT: All requests in a single call should have the same source/target languages.
        The caller (TranslationPipeline) is responsible for grouping requests by language pair.
        """
        if not requests:
            return []
            

        # List to hold final results, initialized with failure state
        results: List[TranslationResult] = []
        for req in requests:
            # Get original unprotected text from metadata if available (set by pipeline for cache consistency)
            original_text = req.get('metadata', {}).get('original_text', req['text'])
            results.append(TranslationResult(
                original_text=original_text,
                translated_text=req['text'],
                source_lang=requests[0].get('metadata', {}).get('source_lang', 'auto'),
                target_lang=requests[0].get('metadata', {}).get('target_lang', 'en'),
                success=False,
                metadata=req.get('metadata', {}),
                error="Processing not started"
            ))

        # 1. Deduplication: Map unique texts to original request indices
        unique_map: Dict[str, List[int]] = {}
        for i, req in enumerate(requests):
            txt = req['text']
            if txt not in unique_map:
                unique_map[txt] = []
            unique_map[txt].append(i)

        unique_texts = list(unique_map.keys())
        
        # 2. Slice texts based on limits (CJK sources need smaller URL-safe chunks)
        first_metadata_lang = requests[0].get('metadata', {}).get('source_lang', 'auto') if requests else 'auto'
        batches_of_text_slices = self._prepare_slices(unique_texts, source_lang=first_metadata_lang)
        
        # 3. Process batches concurrently
        sem = asyncio.Semaphore(self.concurrency)
        
        async def process_slice(slice_texts: List[str]):
            async with sem:
                try:
                    # Protection Phase (Motor-Aware: syntax_guard_rpgm vs HTMLShield)
                    protected_batch = []
                    protection_maps = []
                    bypass_indices = set() # Indices that don't need translation
                    
                    for idx, txt in enumerate(slice_texts):
                        # BRANCHING: Motor-aware protection strategy
                        if self.use_syntax_guard:
                            # NEW (v0.6.6+): RPG Maker-aware syntax_guard_rpgm
                            p_txt, metadata = protect_for_translation(txt, use_html=self.use_html_protection)
                        else:
                            # LEGACY (v0.6.5): HTMLShield token system
                            p_txt, metadata = self.shield_system.shield_with_map(txt)
                        
                        # Remove tokens to check for actual translatable text
                        remaining = re.sub(r'⟦[A-Za-z0-9_]+⟧', '', p_txt)
                        if not re.search(r'[\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', remaining):
                            bypass_indices.add(idx)
                            # Use a minimal dummy for the API call
                            protected_batch.append(".") 
                        else:
                            protected_batch.append(p_txt)
                        
                        protection_maps.append(metadata)
                    
                    # 2. Secure Batch Construction (Obsidian Protocol)
                    from .constants import SAFE_BATCH_SEPARATOR
                    # Using ' _S_ ' as a nonsense anchor that survives stripping
                    batch_text = SAFE_BATCH_SEPARATOR.join(protected_batch)
                    
                    # Extract language codes from first request's metadata
                    # All requests in a batch should have the same source/target languages
                    first_metadata = requests[0].get('metadata', {}) if requests else {}
                    s_lang = first_metadata.get('source_lang', 'auto')
                    t_lang = first_metadata.get('target_lang', 'en')
                    
                    # Attempt translation
                    translated_parts = await self._try_translate(batch_text, s_lang, t_lang, len(protected_batch))
                    
                    if not translated_parts:
                        # Fallback: Parallel Individual Retry
                        translated_parts = [None] * len(protected_batch)
                        
                        async def retry_single(idx):
                            try:
                                single_res = await self._try_translate(protected_batch[idx], s_lang, t_lang, 1)
                                if single_res:
                                    translated_parts[idx] = single_res[0]
                            except Exception:
                                pass
                        
                        await asyncio.gather(*(retry_single(i) for i in range(len(protected_batch))))

                    # Re-map and RESTORE results (Obsidian Protocol v4.3 fix)
                    for idx, (original, translated, token_map) in enumerate(zip(slice_texts, translated_parts, protection_maps)):
                        indices = unique_map.get(original, [])
                        
                        if idx in bypass_indices:
                            # Directly use original text for technical/non-translatable content
                            final_text = original
                            success = True
                        elif translated:
                            # CRITICAL: Motor-aware Restoration (syntax_guard_rpgm vs HTMLShield)
                            if self.use_syntax_guard:
                                # NEW (v0.6.5+): RenLocalizer-style 4-phase recovery
                                final_text = restore_from_translation(translated, protection_maps[idx], use_html=self.use_html_protection)
                                
                                # Validation + Injection fallback using pre-translation protected text
                                missing = validate_translation_integrity(final_text, protection_maps[idx])
                                if missing:
                                    final_text = inject_missing_placeholders(final_text, protected_batch[idx], protection_maps[idx], missing)
                            else:
                                # LEGACY (v0.6.5): HTMLShield token restoration
                                final_text = self.shield_system.unshield_with_map(translated, protection_maps[idx])
                            
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
                    # Results remain as initialized (False) but update error
                    for txt in slice_texts:
                        for idx in unique_map.get(txt, []):
                            results[idx].error = f"Exception: {str(e)}"

        tasks = [process_slice(batch) for batch in batches_of_text_slices]
        if tasks:
            await asyncio.gather(*tasks)
            
        return results

    def _prepare_slices(self, texts: List[str], source_lang: str = 'auto') -> List[List[str]]:
        """Slice list of texts into batches respecting batch_size and max_chars.
        
        CJK languages (ja/zh/ko) require a smaller raw-char limit because every
        character URL-encodes to ~9 bytes (3 UTF-8 × 3 percent-encoding), causing
        414 errors on Lingva and some Google mirrors at the default 2 000-char limit.
        """
        slices = []
        current_batch = []
        current_chars = 0
        from .constants import SAFE_BATCH_SEPARATOR
        
        sep_len = len(SAFE_BATCH_SEPARATOR)
        
        # CJK-aware char limit: each CJK char is ~9 URL bytes vs ~1 for ASCII
        _CJK_SOURCE_LANGS = {'ja', 'zh', 'zh-cn', 'zh-tw', 'ko', 'zh-hans', 'zh-hant'}
        cjk_multiplier = 0.25 if source_lang.lower() in _CJK_SOURCE_LANGS else 1.0
        base_limit = min(self.max_chars, self.max_slice_chars)
        cjk_limit = max(200, int(base_limit * cjk_multiplier))  # floor 200 to avoid empty slices
        
        for text in texts:
            text_len = len(text)
            # Overhead for separator if not first item
            overhead = sep_len if current_batch else 0
            
            # If adding this text exceeds limits, flush (Obsidian v4.4: GET-Safe Slicing)
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
        health["fails"] = max(0, health.get("fails", 0) - 1)

    async def _try_translate(self, text: str, source: str, target: str, expected_count: int, racing: bool = True) -> Optional[List[str]]:
        """Try with Google endpoints, then Lingva."""
        
        params = {
            "client": "gtx",
            "sl": source,
            "tl": target,
            "dt": "t",
            "format": "text",  # Unicode tokens (⟦⟧) use text mode
            "q": text
        }
        
        query = urllib.parse.urlencode(params)
        
        # 1. Google Racing (Parallel)
        use_racing = self.use_multi_endpoint and racing
        n_endpoints = self.racing_endpoints if use_racing else 1
        endpoints = [self._get_next_endpoint() for _ in range(n_endpoints)]
        
        async def call_endpoint(ep):
            # Obsidian Protocol v4.4: Safe GET with URL encoding
            query = urllib.parse.urlencode(params)
            url = f"{ep}?{query}"
            
            # Per-endpoint semaphore: max 2 concurrent requests per Google mirror
            ep_sem = self._endpoint_semaphores.setdefault(ep, asyncio.Semaphore(2))
            
            for attempt in range(1, self.max_retries + 1):
                try:
                    if self.request_delay_ms:
                        await asyncio.sleep(self.request_delay_ms / 1000.0)

                    # Global IP cooldown: when ANY mirror returned an identity/429, all
                    # mirrors pause to avoid a cascade ban across the entire IP.
                    _cooldown_remaining = self._global_cooldown_until - time.time()
                    if _cooldown_remaining > 0:
                        self.logger.debug(f"[cooldown] {ep}: waiting {_cooldown_remaining:.1f}s")
                        await asyncio.sleep(_cooldown_remaining)

                    session = await self._get_session()
                    async with ep_sem:
                        async with session.get(
                            url, 
                            timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json(content_type=None)
                                if not data or not data[0]:
                                    self._register_failure(ep)
                                    continue

                                self._register_success(ep)

                                full = ""
                                if isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                                    for seg in data[0]:
                                        if isinstance(seg, list) and len(seg) > 0 and seg[0]:
                                            full += str(seg[0])

                                if not full:
                                    self.logger.warning(f"Empty translation from {ep}")
                                    self._register_failure(ep)
                                    continue

                                # Soft-429 / identity response detection:
                                # Google sometimes returns 200 OK with the original text unchanged.
                                # Treat this as a failure to trigger retry/fallback.
                                # Also activate the global IP cooldown so all mirrors pause —
                                # this is an IP-level signal, not per-mirror.
                                if full.strip() == text.strip():
                                    self.logger.warning(f"Identity response from {ep} (soft 429 suspect) — retrying")
                                    self._global_cooldown_until = max(
                                        self._global_cooldown_until,
                                        time.time() + self._GLOBAL_COOLDOWN_IDENTITY_SECS,
                                    )
                                    self._register_failure(ep)
                                    continue

                                # Normalize mangled separators back to solid Unicode tokens
                                full = re.sub(r'[\[(\{【]\s*_\s*[sS]\s*_\s*[\])\}】]', '⟦_S_⟧', full)
                                full = re.sub(r'[\[(\{【]\s*_\s*[mM]\s*_\s*[\])\}】]', '⟦_M_⟧', full)
                                full = re.sub(r'[\[(\{【]\s*_\s*[iI]\s*_\s*[\])\}】]', '⟦_I_⟧', full)
                                
                                # Split using hardened regex
                                parts = self.BATCH_SPLIT_PATTERN.split(full)
                                parts = [p.strip() for p in parts if p.strip()]
                                if len(parts) > expected_count and not parts[-1]:
                                    parts = parts[:expected_count]

                                if len(parts) != expected_count:
                                    self.logger.error(f"Batch mismatch (split error) from {ep}: Got {len(parts)}, expected {expected_count}")
                                    # Clean up formatting for log visibility
                                    debug_full = full.replace('\r', '').replace('\n', ' ')
                                    self.logger.error(f"RAW CONTENT SNIPPET: {debug_full[:250]}...")
                                    self._register_failure(ep)
                                    continue
                                return parts

                            if resp.status == 429:
                                wait_time = (2 ** (attempt - 1)) + random.uniform(0.2, 0.8)
                                self.logger.warning(f"Google 429 on {ep}. Backing off {wait_time:.2f}s...")
                                self._global_cooldown_until = max(
                                    self._global_cooldown_until,
                                    time.time() + self._GLOBAL_COOLDOWN_429_SECS,
                                )
                                await asyncio.sleep(wait_time)
                                continue

                            self._register_failure(ep)
                            await asyncio.sleep(0.2)
                except Exception:
                    self._register_failure(ep)
                    wait_time = (1.5 ** (attempt - 1)) * 0.5 + random.uniform(0.1, 0.4)
                    await asyncio.sleep(wait_time)
            return None

        # Run multiple requests in parallel and take the first one that succeeds
        result_found = asyncio.Event()
        final_result = None

        async def call_and_signal(ep: str) -> None:
            nonlocal final_result
            res = await call_endpoint(ep)
            if res and not result_found.is_set():
                result_found.set()  # Set FIRST to block other coroutines
                final_result = res

        try:
            async with asyncio.TaskGroup() as tg:
                tasks = [tg.create_task(call_and_signal(ep)) for ep in endpoints]
                
                # Wait for any success or all failures
                while not result_found.is_set() and any(not t.done() for t in tasks):
                    await asyncio.sleep(0.05)
                
                if result_found.is_set():
                    for t in tasks:
                        if not t.done():
                            t.cancel()
                    return final_result
        except* Exception:
            # TaskGroup may raise ExceptionGroup (except*)
            pass
            
        if final_result:
            return final_result
            
        # 2. Lingva Fallback
        if self.enable_lingva_fallback:
            for _ in range(2):
                try:
                    instance = self._get_next_lingva()
                    url = f"{instance}/api/v1/{source}/{target}/{urllib.parse.quote(text)}"
                    session = await self._get_session()
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            trans = data.get("translation", "")
                            parts = self.BATCH_SPLIT_PATTERN.split(trans.strip())
                            parts = [p.strip() for p in parts if p.strip()]
                            if len(parts) > expected_count and not parts[-1]:
                                parts = parts[:expected_count]
                            if len(parts) == expected_count:
                                return parts
                except Exception:
                    await asyncio.sleep(0.3)
            
        return None

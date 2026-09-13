"""
Google Web and RPC Translation Engine
=====================================

Provides high-performance concurrent Google translation using:
- Primary Google web endpoints (translate_a/single)
- Google batchexecute RPC endpoint
- Google clients5 alternate endpoint (translate_a/t)
- Lingva fallback mirrors
- Multi-endpoint racing and automatic circuit breaker
"""
from __future__ import annotations

import asyncio
import aiohttp
import json
import logging
import random
import re
import time
import urllib.parse
from collections import Counter, deque
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.core.constants import (
    DEFAULT_ENABLE_LINGVA_FALLBACK,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MIRROR_BAN_TIME,
    DEFAULT_MIRROR_MAX_FAILURES,
    DEFAULT_RACING_ENDPOINTS,
    DEFAULT_REQUEST_DELAY_MS,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_USE_MULTI_ENDPOINT,
    GOOGLE_BATCHEXECUTE_ENDPOINT,
    GOOGLE_BROWSER_HEADERS,
    GOOGLE_CLIENTS5_ENDPOINT,
    RATE_LIMIT_CIRCUIT_BREAKER_THRESHOLD,
    RATE_LIMIT_LONG_COOLDOWN,
    RATE_LIMIT_PRIMARY_PROBE_INTERVAL,
    TRANSLATOR_MAX_SAFE_CHARS,
    TRANSLATOR_MAX_SLICE_CHARS,
)
from src.core.syntax_guard_rpgm import protect_rpgm_syntax, restore_rpgm_syntax
from .base import BaseTranslator, TranslationRequest, TranslationResult
from .router import EndpointRouter

logger = logging.getLogger("GoogleTranslator")


class GoogleTranslator(BaseTranslator):
    """Multi-endpoint Google Translator with automated failover and SyntaxGuard protection."""

    _USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    ]

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
        "https://translate.plausibility.cloud",
        "https://lingva.lunar.icu",
        "https://translate.projectsegfau.lt",
        "https://lingva.garudalinux.org",
    ]

    BATCH_SEPARATOR = " |||RPGMSEP_S||| "
    BATCH_SPLIT_PATTERN = re.compile(r'\|{3}\s*RPGMSEP_S\s*\|{3}')

    def __init__(
        self,
        concurrency: int = 16,
        batch_size: int = 15,
        max_slice_chars: Optional[int] = None,
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
        self._endpoint_health: Dict[str, Dict[str, Any]] = {
            ep: {"fails": 0, "banned_until": 0.0} for ep in self.google_endpoints
        }
        self._endpoint_index = 0
        self._lingva_index = 0
        self._endpoint_semaphores: Dict[str, asyncio.Semaphore] = {}
        self._global_cooldown_until: float = 0.0
        self._consecutive_identity_count: int = 0
        self._circuit_breaker_active: bool = False
        self._consecutive_429_count: int = 0
        self._primary_probe_at: float = 0.0
        self._alternate_rescues: int = 0

        self._router = EndpointRouter()
        self._router._do_probe = self._probe_primary_endpoint

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

    def _get_next_endpoint(self) -> str:
        """Select next active Google endpoint in round-robin fashion."""
        if not self.use_multi_endpoint:
            return self.google_endpoints[0]
        now = time.time()
        available = [
            ep for ep in self.google_endpoints
            if now >= self._endpoint_health.get(ep, {}).get("banned_until", 0.0)
        ]
        if not available:
            for ep in self.google_endpoints:
                self._endpoint_health[ep] = {"fails": 0, "banned_until": 0.0}
            available = self.google_endpoints[:]

        self._endpoint_index = (self._endpoint_index + 1) % len(available)
        return available[self._endpoint_index]

    def _get_next_lingva(self) -> str:
        instance = self.lingva_instances[self._lingva_index % len(self.lingva_instances)]
        self._lingva_index += 1
        return instance

    def _compute_global_cooldown(self) -> float:
        if self._consecutive_429_count >= RATE_LIMIT_CIRCUIT_BREAKER_THRESHOLD:
            return float(RATE_LIMIT_LONG_COOLDOWN)
        return 3.0 * (2 ** (self._consecutive_429_count - 1)) if self._consecutive_429_count > 0 else 0.0

    def _apply_global_cooldown(self) -> float:
        self._consecutive_429_count += 1
        cooldown = self._compute_global_cooldown()
        self._global_cooldown_until = time.time() + cooldown
        if self._consecutive_429_count >= RATE_LIMIT_CIRCUIT_BREAKER_THRESHOLD:
            if self._primary_probe_at <= time.time():
                self._primary_probe_at = time.time() + RATE_LIMIT_PRIMARY_PROBE_INTERVAL
        return cooldown

    async def _wait_out_global_cooldown(self) -> None:
        now = time.time()
        if self._global_cooldown_until > now:
            sleep_dur = min(25.0, self._global_cooldown_until - now)
            if sleep_dur > 0:
                await asyncio.sleep(sleep_dur)

    @staticmethod
    def _extract_clients5_text(data: Any) -> Optional[str]:
        if not data or not isinstance(data, list):
            return None
        res = []
        for item in data:
            if isinstance(item, str):
                res.append(item)
            elif isinstance(item, list) and item and isinstance(item[0], str):
                res.append(item[0])
        return "".join(res) if res else None

    @staticmethod
    def _iter_batchexecute_inner(raw: Optional[str]):
        if not raw or not isinstance(raw, str):
            return
        for line in raw.splitlines():
            line = line.strip()
            if not line or not line.startswith("["):
                continue
            try:
                parsed = json.loads(line)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, list) and len(item) > 2 and item[1] == "MkEWBc":
                            inner_json = item[2]
                            if isinstance(inner_json, str):
                                yield json.loads(inner_json)
            except Exception:
                continue

    @classmethod
    def _parse_batchexecute_text(cls, raw: Optional[str]) -> Optional[str]:
        if not raw or not isinstance(raw, str):
            return None
        for inner in cls._iter_batchexecute_inner(raw):
            try:
                root = inner[1][0][0]
                if isinstance(root, list):
                    if len(root) > 5 and isinstance(root[5], list):
                        sentences = root[5]
                        parts = [s[0] for s in sentences if isinstance(s, list) and s and s[0]]
                        if parts:
                            return "".join(parts)
                    if len(root) > 0 and isinstance(root[0], str):
                        return root[0]
                elif isinstance(root, str):
                    return root
            except Exception:
                continue
        return None

    async def _probe_primary_endpoint(self) -> bool:
        """Background health check probe for primary endpoints."""
        probe_url = self.google_endpoints[0]
        params = {"client": "gtx", "sl": "en", "tl": "es", "dt": "t", "q": "ok"}
        try:
            session = await self._get_session()
            async with session.get(probe_url, params=params, headers=GOOGLE_BROWSER_HEADERS, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if isinstance(data, list) and data:
                        return True
        except Exception:
            pass
        return False

    async def _translate_via_clients5(self, text: str, source: str, target: str) -> Optional[str]:
        """Fallback via clients5.google.com /translate_a/t (Chrome dictionary client)."""
        params = {
            "client": "dict-chrome-ex",
            "sl": source or "auto",
            "tl": target,
            "q": text,
        }
        try:
            session = await self._get_session()
            async with session.get(
                GOOGLE_CLIENTS5_ENDPOINT,
                params=params,
                headers=GOOGLE_BROWSER_HEADERS,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    return self._extract_clients5_text(data)
        except Exception as e:
            self.logger.debug("clients5 fallback failed: %s", e)
        return None

    async def _post_batchexecute(self, inner_args: str) -> Optional[str]:
        """POST one MkEWBc RPC to TranslateWebserverUi and return raw envelope body."""
        freq = json.dumps(
            [[["MkEWBc", inner_args, None, "generic"]]], separators=(",", ":")
        )
        params = {
            "rpcids": "MkEWBc",
            "source-path": "/",
            "f.sid": "",
            "bl": "",
            "hl": "en-US",
            "soc-app": "1",
            "soc-platform": "1",
            "soc-device": "1",
            "_reqid": str(random.randint(1000, 9999)),
            "rt": "c",
        }
        headers = dict(GOOGLE_BROWSER_HEADERS)
        headers["Content-Type"] = "application/x-www-form-urlencoded;charset=UTF-8"
        try:
            session = await self._get_session()
            async with session.post(
                GOOGLE_BATCHEXECUTE_ENDPOINT,
                params=params,
                data=f"f.req={urllib.parse.quote(freq)}&",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=12),
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.text()
        except Exception as e:
            self.logger.debug("batchexecute request failed: %s", e)
            return None

    async def _translate_via_batchexecute(self, text: str, source: str, target: str) -> Optional[str]:
        """Translate single text via batchexecute RPC."""
        args = json.dumps([[text, source or "auto", target, True], [None]], separators=(",", ":"))
        raw = await self._post_batchexecute(args)
        return self._parse_batchexecute_text(raw)

    async def _translate_via_batchexecute_batch(
        self, texts: List[str], source: str = "auto", target: str = "en"
    ) -> Optional[List[str]]:
        """Multi-item batch via TranslateWebserverUi RPC layer (MkEWBc)."""
        if not texts:
            return None

        rpc_items = [
            ["MkEWBc", json.dumps([[t, source or "auto", target, True], [None]], separators=(",", ":")), None, str(i)]
            for i, t in enumerate(texts)
        ]
        freq = json.dumps([rpc_items], separators=(",", ":"))

        params = {
            "rpcids": "MkEWBc",
            "source-path": "/",
            "f.sid": "",
            "bl": "",
            "hl": "en-US",
            "soc-app": "1",
            "soc-platform": "1",
            "soc-device": "1",
            "_reqid": str(random.randint(1000, 9999)),
            "rt": "c",
        }
        headers = dict(GOOGLE_BROWSER_HEADERS)
        headers["Content-Type"] = "application/x-www-form-urlencoded;charset=UTF-8"

        try:
            session = await self._get_session()
            async with session.post(
                GOOGLE_BATCHEXECUTE_ENDPOINT,
                params=params,
                data=f"f.req={urllib.parse.quote(freq)}&",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status != 200:
                    self.logger.debug("batchexecute batch HTTP %d for %d items", resp.status, len(texts))
                    return None
                raw = await resp.text()
        except Exception as exc:
            self.logger.debug("batchexecute batch request failed: %s", exc)
            return None

        results: List[Optional[str]] = [None] * len(texts)
        for line in raw.splitlines():
            line = line.strip()
            if not line.startswith("[") or "wrb.fr" not in line:
                continue
            try:
                env = json.loads(line)
                for entry in env:
                    if isinstance(entry, list) and len(entry) >= 4 and entry[0] == "wrb.fr":
                        try:
                            item_id = int(entry[-1])
                        except (ValueError, TypeError):
                            continue
                        if not (0 <= item_id < len(texts)):
                            continue
                        if not entry[2]:
                            continue
                        inner = json.loads(entry[2])
                        try:
                            node = inner[1][0][0]
                        except (TypeError, IndexError):
                            continue

                        if isinstance(node, str) and node:
                            results[item_id] = node
                        elif isinstance(node, list) and len(node) > 5 and isinstance(node[5], list):
                            text_out = "".join(s[0] for s in node[5] if s and s[0])
                            results[item_id] = text_out or None
                        elif isinstance(node, list) and node and isinstance(node[0], str) and node[0]:
                            results[item_id] = node[0]
            except (ValueError, TypeError):
                continue

        if any(r is None for r in results):
            received = sum(1 for r in results if r is not None)
            self.logger.debug("batchexecute batch incomplete: received %d/%d items", received, len(texts))
            return None

        return [r for r in results if r is not None]

    async def _translate_via_clients5_parallel(
        self, texts: List[str], source: str = "auto", target: str = "en"
    ) -> Optional[List[str]]:
        """Translate a batch using clients5 single-item calls in parallel with bounded concurrency."""
        sem = asyncio.Semaphore(min(self.concurrency, 8))

        async def single(txt: str) -> Optional[str]:
            async with sem:
                res = await self._translate_via_clients5(txt, source, target)
                if res:
                    self._router.record_family_success(EndpointRouter.FAMILY_CLIENTS5)
                    return res
                self._router.record_family_failure(EndpointRouter.FAMILY_CLIENTS5, block_for=0.0)
                return None

        results = await asyncio.gather(*[single(t) for t in texts])
        if all(r is not None for r in results):
            return [r for r in results if r is not None]
        return None

    def _extract_primary_endpoint_parts(self, data: Any, expected_count: int) -> Optional[List[str]]:
        if not data or not data[0] or not isinstance(data[0], list):
            return None
        full = "".join(str(seg[0]) for seg in data[0] if isinstance(seg, list) and len(seg) > 0 and seg[0])
        if not full:
            return None
        parts = [p.strip() for p in self.BATCH_SPLIT_PATTERN.split(full)]
        if len(parts) > expected_count and not parts[-1]:
            parts = parts[:expected_count]
        return parts if len(parts) == expected_count else None

    async def _call_primary_endpoint(
        self, ep: str, query: str, expected_count: int, use_post: bool = False
    ) -> Optional[List[str]]:
        for _ in range(1, self.max_retries + 1):
            try:
                if self.request_delay_ms:
                    await asyncio.sleep(self.request_delay_ms / 1000.0)
                session = await self._get_session()
                headers = dict(GOOGLE_BROWSER_HEADERS)
                if use_post:
                    headers["Content-Type"] = "application/x-www-form-urlencoded;charset=utf-8"
                    req_ctx = session.post(
                        ep,
                        data=query,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
                    )
                else:
                    url = f"{ep}?{query}"
                    req_ctx = session.get(
                        url,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
                    )
                async with req_ctx as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        parts = self._extract_primary_endpoint_parts(data, expected_count)
                        if parts is not None:
                            self._register_success(ep)
                            self._router.record_family_success(EndpointRouter.FAMILY_PRIMARY)
                            return parts
                        self._register_failure(ep)
                        continue

                    if resp.status == 429:
                        self._register_failure(ep)
                        self._router.record_primary_429()
                        self._apply_global_cooldown()
                        continue

                    self._register_failure(ep)
            except Exception:
                self._register_failure(ep)
        return None

    async def _race_primary_endpoints(
        self, query: str, expected_count: int, endpoints: List[str], use_post: bool = False
    ) -> Optional[List[str]]:
        tasks = [
            asyncio.create_task(self._call_primary_endpoint(ep, query, expected_count, use_post=use_post))
            for ep in endpoints
        ]
        for completed in asyncio.as_completed(tasks):
            res = await completed
            if res:
                for t in tasks:
                    if not t.done():
                        t.cancel()
                return res
        return None

    async def _rescue_single_translation(
        self, text: str, source: str, target: str
    ) -> Optional[List[str]]:
        res_c5 = await self._translate_via_clients5(text, source, target)
        if res_c5:
            self._alternate_rescues += 1
            return [res_c5]

        res_batch = await self._translate_via_batchexecute(text, source, target)
        if res_batch:
            self._alternate_rescues += 1
            return [res_batch]

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
                            if trans:
                                self._alternate_rescues += 1
                                return [trans.strip()]
                except Exception:
                    pass
        return None

    async def _try_translate(
        self, text: str, source: str, target: str, expected_count: int, racing: bool = True
    ) -> Optional[List[str]]:
        """Try with Google endpoints, then rescue chain (clients5 -> batchexecute -> Lingva)."""
        if self._router.primary_blocked:
            if expected_count == 1:
                return await self._rescue_single_translation(text, source, target)
            return None

        await self._wait_out_global_cooldown()

        use_racing = self.use_multi_endpoint and racing
        n_endpoints = self.racing_endpoints if use_racing else 1
        endpoints = [self._get_next_endpoint() for _ in range(n_endpoints)]

        params = {
            "client": "gtx",
            "sl": source,
            "tl": target,
            "dt": "t",
            "format": "text",
            "q": text,
        }
        query = urllib.parse.urlencode(params)

        if expected_count > 1:
            res = await self._race_primary_endpoints(query, expected_count, endpoints, use_post=True)
            if res:
                return res
            res = await self._race_primary_endpoints(query, expected_count, endpoints, use_post=False)
            if res:
                return res
        else:
            res = await self._race_primary_endpoints(query, expected_count, endpoints, use_post=False)
            if res:
                return res

        if expected_count == 1:
            return await self._rescue_single_translation(text, source, target)
        return None

    @staticmethod
    def _extract_req_text(req: Any) -> str:
        if hasattr(req, "text") and isinstance(req.text, str):
            return req.text
        if isinstance(req, dict):
            return req.get("text", "")
        return str(req)

    @staticmethod
    def _extract_meta(req: Any) -> Dict[str, Any]:
        if hasattr(req, "metadata") and isinstance(req.metadata, dict):
            return req.metadata
        if isinstance(req, dict):
            meta = req.get("metadata")
            if isinstance(meta, dict):
                return meta
        return {}

    @staticmethod
    def _extract_src(req: Any, default: str = "auto") -> str:
        if hasattr(req, "source_lang") and req.source_lang:
            return req.source_lang
        if isinstance(req, dict):
            meta = req.get("metadata")
            meta_src = meta.get("source_lang") if isinstance(meta, dict) else None
            return req.get("source_lang") or meta_src or default
        return default

    @staticmethod
    def _extract_tgt(req: Any, default: str = "en") -> str:
        if hasattr(req, "target_lang") and req.target_lang:
            return req.target_lang
        if isinstance(req, dict):
            meta = req.get("metadata")
            meta_tgt = meta.get("target_lang") if isinstance(meta, dict) else None
            return req.get("target_lang") or meta_tgt or default
        return default

    async def _try_batch_separator(
        self, requests: Sequence[Any]
    ) -> Optional[List[TranslationResult]]:
        """Attempt to translate a slice together using BATCH_SEPARATOR on primary endpoints."""
        if not requests or self._router.primary_blocked:
            return None

        raw_texts = [self._extract_req_text(r) for r in requests]
        protected_texts: List[str] = []
        maps_list: List[Dict[str, str]] = []
        for txt in raw_texts:
            p_txt, p_map = protect_rpgm_syntax(txt)
            protected_texts.append(p_txt)
            maps_list.append(p_map)

        src = self._extract_src(requests[0])
        tgt = self._extract_tgt(requests[0])

        combined = self.BATCH_SEPARATOR.join(protected_texts)
        translated_parts = await self._try_translate(
            combined, src, tgt, expected_count=len(protected_texts)
        )
        if not translated_parts or len(translated_parts) != len(protected_texts):
            return None

        # RenLocalizer Separator Bleeding & Remnant Guard
        for part in translated_parts:
            if any(sep in part for sep in ("|||", "RPGMSEP", "SEP777", "TXTSEG", "ТХЦЭГ", "THCEG")):
                self.logger.debug("Batch-sep: separator remnant found in translated part, discarding batch")
                return None

        results: List[TranslationResult] = []
        for req, orig, trans, p_map in zip(requests, raw_texts, translated_parts, maps_list):
            restored = restore_rpgm_syntax(trans, p_map, original_text=orig)
            results.append(TranslationResult(
                original_text=orig,
                translated_text=restored,
                source_lang=src,
                target_lang=tgt,
                success=True,
                metadata=self._extract_meta(req),
            ))
        return results

    async def _translate_batch_alternate(
        self, requests: Sequence[Any], progress_callback: Optional[Any] = None
    ) -> Optional[List[TranslationResult]]:
        if not requests:
            return []
        raw_texts = [self._extract_req_text(r) for r in requests]
        src = self._extract_src(requests[0])
        tgt = self._extract_tgt(requests[0])

        protected_texts: List[str] = []
        maps_list: List[Dict[str, str]] = []
        for txt in raw_texts:
            p_txt, p_map = protect_rpgm_syntax(txt)
            protected_texts.append(p_txt)
            maps_list.append(p_map)

        translations = None
        if not self._router._health[EndpointRouter.FAMILY_BATCHEXECUTE].is_blocked():
            translations = await self._translate_via_batchexecute_batch(protected_texts, src, tgt)
            if translations:
                self._router.record_family_success(EndpointRouter.FAMILY_BATCHEXECUTE)
            else:
                self._router.record_family_failure(EndpointRouter.FAMILY_BATCHEXECUTE, block_for=120.0)

        if not translations and not self._router._health[EndpointRouter.FAMILY_CLIENTS5].is_blocked():
            translations = await self._translate_via_clients5_parallel(protected_texts, src, tgt)

        if translations and len(translations) == len(raw_texts):
            # RenLocalizer Separator Bleeding & Remnant Guard
            for part in translations:
                if any(sep in part for sep in ("|||", "RPGMSEP", "SEP777", "TXTSEG", "ТХЦЭГ", "THCEG")):
                    self.logger.debug("Batch-alternate: separator remnant found in translated part, discarding batch")
                    return None

            results = []
            for orig, trans, p_map, req in zip(raw_texts, translations, maps_list, requests):
                restored = restore_rpgm_syntax(trans, p_map, original_text=orig)
                results.append(TranslationResult(
                    original_text=orig,
                    translated_text=restored,
                    source_lang=src,
                    target_lang=tgt,
                    success=True,
                    metadata=self._extract_meta(req),
                ))
            if progress_callback:
                BaseTranslator.notify_progress(progress_callback, len(results))
            return results
        return None

    async def _translate_single_request(self, req: Any) -> TranslationResult:
        meta = self._extract_meta(req)
        src = self._extract_src(req)
        tgt = self._extract_tgt(req)
        orig = meta.get("original_text", self._extract_req_text(req))

        p_text, p_map = protect_rpgm_syntax(orig)
        trans_list = await self._try_translate(p_text, src, tgt, expected_count=1)
        if trans_list and trans_list[0]:
            final_text = restore_rpgm_syntax(trans_list[0], p_map, original_text=orig)
            return TranslationResult(
                original_text=orig,
                translated_text=final_text,
                source_lang=src,
                target_lang=tgt,
                success=True,
                metadata=meta,
            )
        return TranslationResult(
            original_text=orig,
            translated_text=orig,
            source_lang=src,
            target_lang=tgt,
            success=False,
            error="Translation failed",
            metadata=meta,
        )

    async def translate_single(self, req: Any) -> TranslationResult:
        """Public entrypoint for translating an individual request."""
        return await self._translate_single_request(req)

    async def translate_batch(
        self,
        requests: Sequence[Any],
        progress_callback: Optional[Any] = None,
    ) -> List[TranslationResult]:
        """Translate requests using Google endpoints with deduplication, slicing, and failover.

        Ported and optimized from RenLocalizer:
        1. Deduplicates texts to reduce redundant network calls.
        2. Slices unique texts into safe chunk sizes (max_slice_chars / batch_size).
        3. Executes slices concurrently using an asyncio.Semaphore.
        4. Routes slices via primary batch separator -> batchexecute/clients5 -> single requests.
        5. Rebuilds final results preserved in original order.
        """
        if not requests:
            return []

        # 1. Deduplication
        indexed = list(enumerate(requests))
        unique_map: Dict[str, int] = {}
        unique_list: List[Tuple[int, Any]] = []
        dup_links: Dict[int, int] = {}

        for idx, req in indexed:
            text = self._extract_req_text(req)
            if text in unique_map:
                dup_links[idx] = unique_map[text]
            else:
                u_idx = len(unique_list)
                unique_map[text] = u_idx
                unique_list.append((idx, req))
                dup_links[idx] = u_idx

        dup_counts = Counter(dup_links.values())

        # 2. Slice creation
        max_slice_chars = self.max_slice_chars or 1800
        max_texts = min(max(self.batch_size * 2, 10), 40) if self.batch_size else 30
        slices: List[List[Tuple[int, Any]]] = []
        cur_slice: List[Tuple[int, Any]] = []
        cur_chars = 0

        for item in unique_list:
            t = self._extract_req_text(item[1])
            t_len = len(t)
            if cur_slice and (cur_chars + t_len > max_slice_chars or len(cur_slice) >= max_texts):
                slices.append(cur_slice)
                cur_slice = []
                cur_chars = 0
            cur_slice.append(item)
            cur_chars += t_len
        if cur_slice:
            slices.append(cur_slice)

        # 3. Concurrency limiter (4 workers for unproxied connections)
        concurrency_limit = min(max(self.concurrency, 1), 4)
        sem = asyncio.Semaphore(concurrency_limit)

        async def translate_slice(slice_items: List[Tuple[int, Any]]) -> List[Tuple[int, TranslationResult]]:
            async with sem:
                slice_reqs = [item[1] for item in slice_items]
                slice_u_indices = [unique_map[self._extract_req_text(r)] for r in slice_reqs]
                resolved_count = sum(dup_counts.get(u_i, 1) for u_i in slice_u_indices)

                # Primary blocked -> alternate families directly
                if self._router.primary_blocked:
                    alt_res = await self._translate_batch_alternate(slice_reqs)
                    if alt_res and len(alt_res) == len(slice_reqs):
                        BaseTranslator.notify_progress(progress_callback, resolved_count)
                        return [(slice_items[i][0], alt_res[i]) for i in range(len(alt_res))]
                else:
                    # Primary batch separator attempt
                    sep_res = await self._try_batch_separator(slice_reqs)
                    if sep_res and len(sep_res) == len(slice_reqs):
                        BaseTranslator.notify_progress(progress_callback, resolved_count)
                        return [(slice_items[i][0], sep_res[i]) for i in range(len(sep_res))]

                    # Alternate batch failover
                    alt_res = await self._translate_batch_alternate(slice_reqs)
                    if alt_res and len(alt_res) == len(slice_reqs):
                        BaseTranslator.notify_progress(progress_callback, resolved_count)
                        return [(slice_items[i][0], alt_res[i]) for i in range(len(alt_res))]

                # Individual fallback per request
                indiv_results: List[Tuple[int, TranslationResult]] = []
                for orig_idx, req in slice_items:
                    res = await self._translate_single_request(req)
                    indiv_results.append((orig_idx, res))
                    u_i = unique_map[self._extract_req_text(req)]
                    BaseTranslator.notify_progress(progress_callback, dup_counts.get(u_i, 1))
                return indiv_results

        # 4. Gather slice executions
        tasks = [asyncio.create_task(translate_slice(s)) for s in slices]
        gathered: List[List[Tuple[int, TranslationResult]]] = await asyncio.gather(*tasks)

        # 5. Map results by original index of unique items
        global_to_result: Dict[int, TranslationResult] = {}
        for slice_results in gathered:
            for orig_idx, res in slice_results:
                global_to_result[orig_idx] = res

        # 6. Rebuild full list matching original request order
        final_results: List[TranslationResult] = [None] * len(requests)  # type: ignore
        for orig_idx, req in indexed:
            unique_idx = dup_links[orig_idx]
            unique_global_idx = unique_list[unique_idx][0]
            base_res = global_to_result.get(unique_global_idx)
            req_text = self._extract_req_text(req)
            req_src = self._extract_src(req)
            req_tgt = self._extract_tgt(req)
            req_meta = self._extract_meta(req)

            if base_res is None:
                final_results[orig_idx] = TranslationResult(
                    original_text=req_text,
                    translated_text=req_text,
                    source_lang=req_src,
                    target_lang=req_tgt,
                    success=False,
                    error="Missing batch translation result",
                    metadata=req_meta,
                )
            else:
                final_results[orig_idx] = TranslationResult(
                    original_text=req_text,
                    translated_text=base_res.translated_text,
                    source_lang=base_res.source_lang,
                    target_lang=base_res.target_lang,
                    success=base_res.success,
                    error=base_res.error,
                    metadata=req_meta,
                )

        return final_results



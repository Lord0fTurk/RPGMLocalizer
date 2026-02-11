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

from src.utils.placeholder import protect_rpgm_syntax, restore_rpgm_syntax, validate_restoration
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

@dataclass
class TranslationRequest:
    text: str
    source_lang: str
    target_lang: str
    metadata: Dict = field(default_factory=dict)

@dataclass
class TranslationResult:
    original_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    success: bool
    error: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

class BaseTranslator(ABC):
    def __init__(self, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector] = None
        self.timeout_seconds = timeout_seconds

    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Get or create an aiohttp ClientSession.
        Reuses the session if it's already open, creates a new one otherwise.
        
        Important: Call close() when done to avoid resource leaks.
        """
        if self._session is None or self._session.closed:
            self._connector = aiohttp.TCPConnector(limit=256, ttl_dns_cache=300)
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            self._session = aiohttp.ClientSession(connector=self._connector, timeout=timeout)
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

    lingva_instances = [
        "https://lingva.ml",
        "https://lingva.lunar.icu",
        "https://lingva.garudalinux.org",
    ]

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
        racing_endpoints: int = DEFAULT_RACING_ENDPOINTS
    ):
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
        
        # 2. Slice texts based on limits
        batches_of_text_slices = self._prepare_slices(unique_texts)
        
        # 3. Process batches concurrently
        sem = asyncio.Semaphore(self.concurrency)
        
        async def process_slice(slice_texts: List[str]):
            async with sem:
                try:
                    # Protection Phase
                    protected_batch = []
                    protection_maps = []
                    
                    for txt in slice_texts:
                        p_txt, p_map = protect_rpgm_syntax(txt)
                        protected_batch.append(p_txt)
                        protection_maps.append(p_map)
                    
                    # API Call
                    # JOIN using the special token from constants
                    from .constants import TOKEN_BATCH_SEPARATOR, REGEX_BATCH_SPLIT
                    
                    batch_text = TOKEN_BATCH_SEPARATOR.join(protected_batch)
                    
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
                            except:
                                pass
                        
                        await asyncio.gather(*(retry_single(i) for i in range(len(protected_batch))))

                    # Re-map results
                    for original, translated, p_map in zip(slice_texts, translated_parts, protection_maps):
                        indices = unique_map.get(original, [])
                        
                        final_text = original
                        is_success = False
                        err_msg = "Translation failed"
                        
                        if translated:
                            # Restoration Phase
                            restored = restore_rpgm_syntax(translated, p_map)
                            is_valid, missing = validate_restoration(original, restored, p_map)
                            
                            if is_valid:
                                final_text = restored
                                is_success = True
                                err_msg = None
                            else:
                                err_msg = f"Validation Failed: Missing {missing}"
                        
                        # Update all original requests pointing to this text
                        for idx in indices:
                            res = results[idx]
                            res.translated_text = final_text
                            res.success = is_success
                            res.error = err_msg
                            
                            if is_success:
                                if progress_callback:
                                    try: progress_callback(1)
                                    except: pass
                                    
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

    def _prepare_slices(self, texts: List[str]) -> List[List[str]]:
        """Slice list of texts into batches respecting batch_size and max_chars."""
        slices = []
        current_batch = []
        current_chars = 0
        from .constants import TOKEN_BATCH_SEPARATOR
        
        sep_len = len(TOKEN_BATCH_SEPARATOR)
        
        for text in texts:
            text_len = len(text)
            # Overhead for separator if not first item
            overhead = sep_len if current_batch else 0
            
            # If adding this text exceeds limits, flush
            if len(current_batch) >= self.batch_size or \
               (current_chars + text_len + overhead > self.max_chars and current_batch):
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
            "format": "text",  # Use plain text mode
            "q": text
        }
        
        query = urllib.parse.urlencode(params)
        
        # 1. Google Racing (Parallel)
        use_racing = self.use_multi_endpoint and racing
        n_endpoints = self.racing_endpoints if use_racing else 1
        endpoints = [self._get_next_endpoint() for _ in range(n_endpoints)]
        
        async def call_endpoint(ep):
            for attempt in range(1, self.max_retries + 1):
                try:
                    if self.request_delay_ms:
                        await asyncio.sleep(self.request_delay_ms / 1000.0)
                    url = f"{ep}?{query}"
                    session = await self._get_session()
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)) as resp:
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

                            parts = self.BATCH_SPLIT_PATTERN.split(full)
                            parts = [p.strip() for p in parts]
                            if len(parts) > expected_count and not parts[-1]:
                                parts = parts[:expected_count]

                            if len(parts) != expected_count:
                                self.logger.debug(f"Batch mismatch from {ep}: Got {len(parts)}, expected {expected_count}")
                                snippet = full[:100].replace('\n', ' ')
                                self.logger.debug(f"Snippet: {snippet}...")
                                self._register_failure(ep)
                                continue
                            return parts

                        if resp.status == 429:
                            wait_time = (2 ** (attempt - 1)) + random.uniform(0.2, 0.8)
                            self.logger.warning(f"Google 429 on {ep}. Backing off {wait_time:.2f}s...")
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
        pending = [asyncio.create_task(call_endpoint(ep)) for ep in endpoints]
        
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                res = task.result()
                if res:
                    # Cancel remaining tasks
                    for p in pending: p.cancel()
                    return res
            
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
                            parts = [p.strip() for p in parts]
                            if len(parts) > expected_count and not parts[-1]:
                                parts = parts[:expected_count]
                            if len(parts) == expected_count:
                                return parts
                except Exception:
                    await asyncio.sleep(0.3)
            
        return None

"""
Google Web Translator / Lingva Translator implementation.
Ported and adapted from RenLocalizer for RPGMLocalizer.
"""
from __future__ import annotations

import asyncio
import aiohttp
import logging
import urllib.parse
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from abc import ABC, abstractmethod

from src.utils.placeholder import protect_rpgm_syntax, restore_rpgm_syntax

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
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._connector = aiohttp.TCPConnector(limit=256, ttl_dns_cache=300)
            timeout = aiohttp.ClientTimeout(total=15)
            self._session = aiohttp.ClientSession(connector=self._connector, timeout=timeout)
        return self._session

    async def close(self):
        if self._session:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None
            self._connector = None

    @abstractmethod
    async def translate_batch(self, requests: List[TranslationRequest], progress_callback=None) -> List[TranslationResult]:
        pass

class GoogleTranslator(BaseTranslator):
    """
    Multi-endpoint Google Translator with Lingva fallback.
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

    BATCH_SEPARATOR = " ||| " 

    def __init__(self, concurrency=16, batch_size=50, max_slice_chars=4500):
        super().__init__()
        self.concurrency = concurrency
        self.batch_size = batch_size
        self.max_slice_chars = max_slice_chars
        self._endpoint_failures: Dict[str, int] = {}
        self._endpoint_index = 0
        self._lingva_index = 0

    def _get_next_endpoint(self) -> str:
        """Round-robin endpoint selection with failure tracking."""
        min_failures = min(self._endpoint_failures.get(ep, 0) for ep in self.google_endpoints)
        available = [ep for ep in self.google_endpoints 
                     if self._endpoint_failures.get(ep, 0) <= min_failures + 2]

        if not available:
            self._endpoint_failures.clear()
            available = self.google_endpoints

        self._endpoint_index = (self._endpoint_index + 1) % len(available)
        return available[self._endpoint_index]

    def _get_next_lingva(self) -> str:
        self._lingva_index = (self._lingva_index + 1) % len(self.lingva_instances)
        return self.lingva_instances[self._lingva_index]

    async def translate_batch(self, requests: List[TranslationRequest], progress_callback=None) -> List[TranslationResult]:
        """Translate a list of requests with deduplication and batching."""
        if not requests: return []
        
        # 1. Deduplication and indexing
        indexed = list(enumerate(requests))
        unique_reqs: Dict[str, int] = {} # text -> first_index
        dup_links: Dict[int, int] = {} # original_index -> unique_first_index
        
        unique_list = []
        for idx, req in indexed:
            if req.text not in unique_reqs:
                unique_reqs[req.text] = idx
                unique_list.append((idx, req))
            dup_links[idx] = unique_reqs[req.text]

        # 2. Protection
        unique_protected = []
        for u_idx, req in unique_list:
            p_text, p_map = protect_rpgm_syntax(req.text)
            unique_protected.append((u_idx, p_text, p_map, req))

        # 3. Create slices based on length and batch size
        final_slices = []
        cur_batch = []
        cur_len = 0
        
        for i, (u_idx, p_text, p_map, req) in enumerate(unique_protected):
             l = len(p_text)
             overhead = len(self.BATCH_SEPARATOR) if cur_batch else 0
             
             if cur_batch and (cur_len + overhead + l > self.max_slice_chars or len(cur_batch) >= self.batch_size):
                 final_slices.append(cur_batch)
                 cur_batch = []
                 cur_len = 0
                 overhead = 0
             
             cur_batch.append(i) 
             cur_len += l + overhead
             
        if cur_batch:
            final_slices.append(cur_batch)

        # 3. Process slices
        unique_results: Dict[int, TranslationResult] = {}
        sem = asyncio.Semaphore(self.concurrency)

        async def process_slice(indices: List[int]):
            async with sem:
                s_lang = unique_protected[indices[0]][3].source_lang
                t_lang = unique_protected[indices[0]][3].target_lang
                
                # Construct batch text
                batch_texts = [unique_protected[i][1] for i in indices]
                joined_text = self.BATCH_SEPARATOR.join(batch_texts)
                
                translated_parts = await self._try_translate(joined_text, s_lang, t_lang, len(batch_texts))
                
                if not translated_parts:
                    # Retry items individually without racing to be gentle on Google
                    for i in indices:
                        if self._session is None: break # Closed
                        u_idx = unique_protected[i][0]
                        p_text, p_map, req = unique_protected[i][1], unique_protected[i][2], unique_protected[i][3]
                        
                        single_res = await self._try_translate(p_text, s_lang, t_lang, 1, racing=False)
                        
                        if single_res and single_res[0]:
                            final_val = restore_rpgm_syntax(single_res[0], p_map)
                            unique_results[u_idx] = TranslationResult(
                                req.text, final_val, s_lang, t_lang, True, "", metadata=req.metadata
                            )
                        else:
                            unique_results[u_idx] = TranslationResult(
                                req.text, "", s_lang, t_lang, False, "Translation failed", metadata=req.metadata
                            )
                        
                        # Report progress for each individual item during retry
                        if progress_callback:
                            progress_callback(1)
                    return

                # Map back successful batch
                for i, t_text in zip(indices, translated_parts):
                    u_idx = unique_protected[i][0]
                    p_map = unique_protected[i][2]
                    req = unique_protected[i][3]
                    
                    final_text = restore_rpgm_syntax(t_text.strip(), p_map)
                    unique_results[u_idx] = TranslationResult(
                        req.text, final_text, s_lang, t_lang, True, metadata=req.metadata
                    )

                # Report progress for the whole batch
                if progress_callback:
                    progress_callback(len(indices))

        tasks = [process_slice(sl) for sl in final_slices]
        await asyncio.gather(*tasks)

        # 4. Reconstruct full list
        results = []
        for idx, req in indexed:
            u_idx = dup_links[idx]
            if u_idx in unique_results:
                results.append(unique_results[u_idx])
            else:
                 results.append(TranslationResult(req.text, "", req.source_lang, req.target_lang, False, "Missing result", metadata=req.metadata))
                 
        return results

    async def _try_translate(self, text: str, source: str, target: str, expected_count: int, racing: bool = True) -> Optional[List[str]]:
        """Try with Google endpoints, then Lingva."""
        
        params = {
            "client": "gtx",
            "sl": source,
            "tl": target,
            "dt": "t",
            "q": text
        }
        
        # 1. Google Racing (Parallel) - Use 3 endpoints if racing, else only 1
        n_endpoints = 3 if racing else 1
        endpoints = [self._get_next_endpoint() for _ in range(n_endpoints)]
        
        async def call_endpoint(ep):
            try:
                url = f"{ep}?{query}"
                session = await self._get_session()
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200: 
                        self._endpoint_failures[ep] = self._endpoint_failures.get(ep, 0) + 1
                        return None
                    
                    data = await resp.json(content_type=None)
                    if not data or not data[0]: return None
                    
                    self._endpoint_failures[ep] = max(0, self._endpoint_failures.get(ep, 0) - 1)
                    
                    # Join segments
                    full = ""
                    for seg in data[0]:
                        if seg and seg[0]: full += seg[0]
                    
                    parts = full.split(self.BATCH_SEPARATOR)
                    if len(parts) != expected_count: return None 
                    return parts
            except Exception:
                self._endpoint_failures[ep] = self._endpoint_failures.get(ep, 0) + 1
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
        # lingva format: /api/v1/source/target/text
        try:
            instance = self._get_next_lingva()
            # Lingva usually takes single text, batching might be tricky if separator is not handled.
            # Lingva might not support " ||| " separator logic same as Google.
            # So if batching, we might skip Lingva or try unbatched? 
            # For now, let's try assuming it passes text through Google backend.
            url = f"{instance}/api/v1/{source}/{target}/{urllib.parse.quote(text)}"
            session = await self._get_session()
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                 if resp.status == 200:
                     data = await resp.json()
                     # {"translation": "..."}
                     trans = data.get("translation", "")
                     parts = trans.split(self.BATCH_SEPARATOR)
                     if len(parts) == expected_count:
                         return parts
        except Exception:
            pass
            
        return None

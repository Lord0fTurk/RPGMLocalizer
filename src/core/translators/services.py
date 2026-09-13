"""
AI and LLM Translation Adapters
================================
Provides integration for OpenAI-compatible LLM endpoints, DeepSeek,
and local servers (Ollama / LM Studio).
"""
from __future__ import annotations

import asyncio
import aiohttp
import json
import logging
import random
import re
import time
from abc import abstractmethod
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.core.constants import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_REQUEST_DELAY_MS,
    DEFAULT_TIMEOUT_SECONDS,
    TRANSLATOR_MAX_SAFE_CHARS,
    TRANSLATOR_MAX_SLICE_CHARS,
    USER_AGENTS,
)
from src.core.exceptions import (
    NetworkConnectionError,
    QuotaExceededError,
    RateLimitError,
)
from src.core.llm_repair import parse_llm_array
from src.core.syntax_guard_rpgm import (
    inject_missing_placeholders,
    protect_rpgm_syntax,
    restore_rpgm_syntax,
    validate_translation_integrity,
)
from src.core.text_segmenter import clean_text as segmenter_clean, reassemble as segmenter_reassemble
from .base import BaseTranslator, TranslationEngine, TranslationRequest, TranslationResult

try:
    from version import VERSION as _APP_VERSION
except ImportError:
    _APP_VERSION = "0.8.0"

logger = logging.getLogger("LLMServices")



class SegmentBatchTranslator(BaseTranslator):
    """Base class for translators consuming structured text batches with segment protection."""

    def __init__(
        self,
        concurrency: int = 8,
        batch_size: int = 15,
        max_slice_chars: Optional[int] = None,
        request_delay_ms: int = DEFAULT_REQUEST_DELAY_MS,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds)
        self.concurrency = concurrency
        self.batch_size = batch_size
        self._max_chars = TRANSLATOR_MAX_SAFE_CHARS
        self.max_slice_chars = max_slice_chars or TRANSLATOR_MAX_SLICE_CHARS
        self.request_delay_ms = max(0, request_delay_ms)
        self.max_retries = max(1, max_retries)

    @abstractmethod
    async def _translate_clean_texts(
        self,
        clean_texts: List[str],
        source_lang: str,
        target_lang: str,
    ) -> List[Optional[str]]:
        """Translate a batch of clean text segments."""
        pass

    def _populate_code_only(
        self,
        cleaned_info: List[Tuple[str, str, Any]],
        unique_map: Dict[str, List[int]],
        requests: List[Dict[str, Any]],
        results: List[Optional[TranslationResult]],
    ) -> List[int]:
        needs_trans = []
        for i, (orig, clean, _) in enumerate(cleaned_info):
            if not clean.strip():
                for req_idx in unique_map[orig]:
                    req = requests[req_idx]
                    results[req_idx] = TranslationResult(
                        original_text=orig,
                        translated_text=orig,
                        source_lang=req.get("source_lang", "auto"),
                        target_lang=req.get("target_lang", "en"),
                        success=True,
                        metadata=req.get("metadata", {}),
                    )
            else:
                needs_trans.append(i)
        return needs_trans

    async def _translate_with_retry_and_fallback(
        self, clean_batch: List[str], src: str, tgt: str
    ) -> Optional[List[Optional[str]]]:
        translated_clean: Optional[List[Optional[str]]] = None
        for attempt in range(2):
            translated_clean = await self._translate_clean_texts(clean_batch, src, tgt)
            if not translated_clean or len(translated_clean) != len(clean_batch):
                if len(clean_batch) > 1:
                    indiv_res: List[Optional[str]] = []
                    for single_txt in clean_batch:
                        sub = await self._translate_clean_texts([single_txt], src, tgt)
                        indiv_res.append(sub[0] if sub and sub[0] else None)
                    return indiv_res
                break

            is_identity = all(
                not (c_out and c_in.strip().lower() != c_out.strip().lower())
                for c_in, c_out in zip(clean_batch, translated_clean)
            )
            if not is_identity or attempt == 1:
                break
        return translated_clean

    def _populate_translated_results(
        self,
        needs_indices: List[int],
        cleaned_info: List[Tuple[str, str, Any]],
        translated_clean: Optional[List[Optional[str]]],
        unique_map: Dict[str, List[int]],
        requests: List[Dict[str, Any]],
        src: str,
        tgt: str,
        results: List[Optional[TranslationResult]],
    ) -> None:
        for idx_in_trans, orig_idx in enumerate(needs_indices):
            orig, _, segs = cleaned_info[orig_idx]
            t_str = translated_clean[idx_in_trans] if translated_clean and idx_in_trans < len(translated_clean) else None
            success = t_str is not None
            final_text = segmenter_reassemble(t_str, segs) if success else orig

            for req_idx in unique_map[orig]:
                req = requests[req_idx]
                results[req_idx] = TranslationResult(
                    original_text=orig,
                    translated_text=final_text,
                    source_lang=src,
                    target_lang=tgt,
                    success=success,
                    metadata=req.get("metadata", {}),
                )

    async def translate_batch(
        self,
        requests: List[Dict[str, Any]],
        progress_callback: Optional[Any] = None,
    ) -> List[TranslationResult]:
        """Translate requests via LLM with segment protection and deduplication."""
        if not requests:
            return []

        results: List[Optional[TranslationResult]] = [None] * len(requests)
        unique_map: Dict[str, List[int]] = {}
        for i, req in enumerate(requests):
            unique_map.setdefault(req.get("text", ""), []).append(i)

        cleaned_info = [(txt, *segmenter_clean(txt)) for txt in unique_map.keys()]
        needs_indices = self._populate_code_only(cleaned_info, unique_map, requests, results)

        if needs_indices:
            clean_batch = [cleaned_info[idx][1] for idx in needs_indices]
            req0 = requests[unique_map[cleaned_info[needs_indices[0]][0]][0]]
            meta0 = req0.get("metadata", {})
            src = req0.get("source_lang") or meta0.get("source_lang") or "auto"
            tgt = req0.get("target_lang") or meta0.get("target_lang") or "en"

            translated_clean = await self._translate_with_retry_and_fallback(clean_batch, src, tgt)
            self._populate_translated_results(
                needs_indices, cleaned_info, translated_clean, unique_map, requests, src, tgt, results
            )

        BaseTranslator.notify_progress(progress_callback, len(results))

        return [r for r in results if r is not None]


class OpenAICompatibleTranslator(SegmentBatchTranslator):
    """Translator for OpenAI-compatible chat completion endpoints."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        concurrency: int = 8,
        batch_size: int = 15,
        max_slice_chars: Optional[int] = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        request_delay_ms: int = DEFAULT_REQUEST_DELAY_MS,
    ) -> None:
        super().__init__(
            concurrency=concurrency,
            batch_size=batch_size,
            max_slice_chars=max_slice_chars,
            request_delay_ms=request_delay_ms,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.endpoint = base_url.rstrip("/") + "/chat/completions"

    @staticmethod
    def _parse_translations(content: Optional[str]) -> Optional[List[str]]:
        """Parse raw model output into a list of translation strings."""
        if not content or not isinstance(content, str) or not content.strip():
            return None

        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            parsed = json.loads(text)
        except Exception:
            outcome = parse_llm_array(text)
            if not outcome or not outcome.items:
                return None
            parsed = outcome.items

        if isinstance(parsed, dict):
            if "translations" in parsed and isinstance(parsed["translations"], list):
                parsed = parsed["translations"]
            else:
                return None
        elif not isinstance(parsed, list):
            return None

        return [str(item) for item in parsed]

    def _build_system_prompt(self, target_lang: str) -> str:
        return (
            f"You are an expert game localizer. Translate each input string into {target_lang}. "
            "Return strictly a JSON array with the exact same number of items in identical order. "
            "Preserve all special format tokens and delimiters."
        )

    async def _translate_clean_texts(
        self,
        clean_texts: List[str],
        source_lang: str,
        target_lang: str,
    ) -> List[Optional[str]]:
        if not clean_texts:
            return []

        system_prompt = self._build_system_prompt(target_lang)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(clean_texts, ensure_ascii=False)},
            ],
            "temperature": 0.2,
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                session = await self._get_session()
                async with session.post(
                    self.endpoint,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        choices = data.get("choices", [])
                        if choices:
                            content = choices[0].get("message", {}).get("content", "")
                            parsed = self._parse_translations(content)
                            if parsed is not None:
                                return parsed
                    elif resp.status in (429, 500, 502, 503):
                        await asyncio.sleep((2 ** (attempt - 1)) * 0.5 + random.uniform(0.1, 0.3))
            except Exception:
                await asyncio.sleep(0.3)

        return [None] * len(clean_texts)


class DeepSeekTranslator(OpenAICompatibleTranslator):
    """DeepSeek Chat / Coder translation adapter."""

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key=api_key, model=model, base_url=base_url, **kwargs)


class LocalLLMTranslator(OpenAICompatibleTranslator):
    """Local LLM adapter for Ollama and LM Studio servers."""

    def __init__(
        self,
        model: str = "llama3",
        base_url: str = "http://localhost:11434/v1",
        api_key: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key=api_key, model=model, base_url=base_url, **kwargs)


class PseudoTranslator(BaseTranslator):
    """
    Pseudo-Localization Engine for testing UI bounds and font compatibility.

    Transforms text locally without calling any external API:
    - 'expand': Adds [!!! ... !!!] markers to test UI bounds and length.
    - 'accent': Replaces vowels with accented versions to test font compatibility.
    - 'both': Combines expansion and accenting (default).
    """

    ACCENT_MAP = str.maketrans("aeiouAEIOUyY", "àéîõüÀÉÎÕÜýÝ")
    EXTENDED_ACCENT_MAP = str.maketrans(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "àḃċḋéḟġḣíjḳĺṁńöṗqŕśṫûṿẁẍÿźÀḂĊḊÉḞĠḢÍJḲĹṀŃÖṖQŔŚṪÛṾẀẌŸŹ",
    )

    def __init__(
        self,
        *args: Any,
        mode: str = "both",
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds)
        self.mode = mode  # 'expand', 'accent', or 'both'

    def _apply_accents(self, text: str) -> str:
        return text.translate(self.ACCENT_MAP)

    def _apply_expansion(self, text: str) -> str:
        return f"[!!! {text} !!!]"

    def _pseudo_transform(self, text: str) -> str:
        if not text or not text.strip():
            return text
        result = text
        if self.mode in ("accent", "both"):
            result = self._apply_accents(result)
        if self.mode in ("expand", "both"):
            result = self._apply_expansion(result)
        return result

    async def translate_single(self, request: TranslationRequest | Dict[str, Any]) -> TranslationResult:
        if isinstance(request, dict):
            orig_text = request.get("text", "")
            meta = request.get("metadata", {})
            src_lang = request.get("source_lang") or meta.get("source_lang", "auto")
            tgt_lang = request.get("target_lang") or meta.get("target_lang", "en")
        else:
            orig_text = request.text
            meta = request.metadata if isinstance(request.metadata, dict) else {}
            src_lang = request.source_lang
            tgt_lang = request.target_lang

        if not orig_text:
            return TranslationResult(
                original_text=orig_text,
                translated_text=orig_text,
                source_lang=src_lang,
                target_lang=tgt_lang,
                engine=TranslationEngine.PSEUDO,
                success=True,
                metadata=meta,
            )

        protected_text, placeholders = protect_rpgm_syntax(orig_text)
        parts = re.split(r'(\u27e6RLPH[A-F0-9]{6}_\d+\u27e7|__PH_\d+__|<ph\b[^>]*>.*?</ph>)', protected_text)
        new_parts: List[str] = []
        for part in parts:
            if not part:
                continue
            if part.startswith('\u27e6RLPH') or part.startswith('__PH_') or part.startswith('<ph'):
                new_parts.append(part)
            else:
                new_parts.append(self._pseudo_transform(part))

        pseudo_text = "".join(new_parts)
        final_text = restore_rpgm_syntax(pseudo_text, placeholders, orig_text)

        return TranslationResult(
            original_text=orig_text,
            translated_text=final_text,
            source_lang=src_lang,
            target_lang=tgt_lang,
            engine=TranslationEngine.PSEUDO,
            success=True,
            metadata={**meta, "pseudo_mode": self.mode},
        )

    async def translate_batch(
        self,
        requests: Sequence[TranslationRequest | Dict[str, Any]],
        progress_callback: Optional[Any] = None,
    ) -> List[TranslationResult]:
        results: List[TranslationResult] = []
        for r in requests:
            res = await self.translate_single(r)
            results.append(res)
            self.notify_progress(progress_callback, 1)
        return results

    def get_supported_languages(self) -> Dict[str, str]:
        return {
            "pseudo": "Pseudo-Localization (Test)",
            "expand": "Expansion Test [!!! !!!]",
            "accent": "Accent Test (àccénts)",
        }


class DeepLTranslator(BaseTranslator):
    """DeepL translation service adapter with XML placeholder protection and formality support."""

    base_url_paid = "https://api.deepl.com/v2/translate"
    base_url_free = "https://api-free.deepl.com/v2/translate"

    MAX_RETRIES = 3
    RETRY_DELAYS = [1.0, 2.0, 4.0]

    FORMALITY_OPTIONS = {
        "default": None,
        "formal": "more",
        "informal": "less",
    }

    FORMALITY_LANGUAGES = {
        "de", "fr", "it", "es", "nl", "pl", "pt", "ru", "ja", "tr",
    }

    def __init__(
        self,
        api_key: str = "",
        proxy_manager: Any = None,
        config_manager: Any = None,
        formality: str = "default",
        timeout_seconds: int = 45,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds)
        self.api_key = api_key.strip()
        self.proxy_manager = proxy_manager
        self.config_manager = config_manager
        self.formality = formality
        self._engine = TranslationEngine.DEEPL

    def _map_lang(self, lang: str, is_target: bool = True) -> str:
        if not lang:
            return "EN-US" if is_target else "EN"
        l = lang.lower().strip()
        if is_target:
            if l == "en":
                return "EN-US"
            if l == "pt":
                return "PT-PT"
            if l in ("zh", "zh-cn", "zh-tw"):
                return "ZH"
            return l.upper()
        if l == "en":
            return "EN"
        if l == "ja":
            return "JA"
        if l == "ko":
            return "KO"
        if l in ("zh", "zh-cn", "zh-tw"):
            return "ZH"
        return l.upper()

    @staticmethod
    def _clean_deepl_rpgm_codes(text: str) -> str:
        """Fix whitespace that DeepL may insert inside RPG Maker escape sequences."""
        if not text:
            return text
        text = re.sub(
            r'\\\s*([cCiIpPfFwWvVnNoOaAhHxXyY]|fs|fn|oc|ow|hc|ac|px|py|wc|tt|bg)\s*\[\s*([^\[\]]+?)\s*\]',
            r'\\\1[\2]',
            text,
        )
        text = re.sub(r'\\\s*([Nn][Cc]?)\s*<\s*([^>]+?)\s*>', r'\\\1<\2>', text)
        text = re.sub(r'\\\s*([{}<>.!gG$|\^;])', r'\\\1', text)
        text = re.sub(r'<\s*/?\s*([a-zA-Z][a-zA-Z0-9_\s:-]*?)\s*>', r'<\1>', text)
        return text

    async def translate_single(self, request: TranslationRequest | Dict[str, Any]) -> TranslationResult:
        res = await self.translate_batch([request])
        return res[0] if res else TranslationResult(
            original_text="", translated_text="", source_lang="auto", target_lang="en",
            engine=TranslationEngine.DEEPL, success=False, error="Empty batch response",
        )

    async def translate_batch(
        self,
        requests: Sequence[TranslationRequest | Dict[str, Any]],
        progress_callback: Optional[Any] = None,
    ) -> List[TranslationResult]:
        if not requests:
            return []

        if not self.api_key:
            fail_results: List[TranslationResult] = []
            for r in requests:
                orig = r.get("text", "") if isinstance(r, dict) else r.text
                meta = r.get("metadata", {}) if isinstance(r, dict) else (r.metadata or {})
                sl = r.get("source_lang", "auto") if isinstance(r, dict) else r.source_lang
                tl = r.get("target_lang", "en") if isinstance(r, dict) else r.target_lang
                fail_results.append(
                    TranslationResult(
                        original_text=orig,
                        translated_text="",
                        source_lang=sl,
                        target_lang=tl,
                        engine=TranslationEngine.DEEPL,
                        success=False,
                        error="DeepL API key required",
                        metadata=meta,
                    )
                )
            self.notify_progress(progress_callback, len(fail_results))
            return fail_results

        source_texts: List[str] = []
        meta_list: List[Dict[str, Any]] = []
        sl_list: List[str] = []
        tl_list: List[str] = []

        for r in requests:
            if isinstance(r, dict):
                st = r.get("text", "")
                m = r.get("metadata", {})
                sl = r.get("source_lang") or m.get("source_lang", "auto")
                tl = r.get("target_lang") or m.get("target_lang", "en")
            else:
                st = r.text
                m = r.metadata if isinstance(r.metadata, dict) else {}
                sl = r.source_lang
                tl = r.target_lang
            source_texts.append(st)
            meta_list.append(m)
            sl_list.append(sl)
            tl_list.append(tl)

        target_lang = self._map_lang(tl_list[0], is_target=True)
        source_lang = self._map_lang(sl_list[0], is_target=False) if sl_list[0] and sl_list[0] != "auto" else None

        xml_protected_texts: List[str] = []
        all_placeholders: List[Dict[str, str]] = []

        for st in source_texts:
            p_text, p_holders = protect_rpgm_syntax(st)
            temp_text = p_text
            for idx, ph in enumerate(p_holders.keys()):
                xml_tag = f'<x i="{idx}"/>'
                temp_text = temp_text.replace(ph, xml_tag)
            xml_protected_texts.append(temp_text)
            all_placeholders.append(p_holders)

        headers = {
            "Authorization": f"DeepL-Auth-Key {self.api_key}",
            "User-Agent": f"RPGMLocalizer/{_APP_VERSION}",
        }

        data: Dict[str, Any] = {
            "target_lang": target_lang,
            "text": xml_protected_texts,
            "tag_handling": "xml",
            "ignore_tags": "x",
        }
        if source_lang:
            data["source_lang"] = source_lang

        formality_val = self.FORMALITY_OPTIONS.get(self.formality)
        if formality_val and target_lang.lower()[:2] in self.FORMALITY_LANGUAGES:
            data["formality"] = formality_val

        base_url = (
            self.base_url_free
            if ":fx" in self.api_key or self.api_key.startswith("free:")
            else self.base_url_paid
        )

        last_error = ""
        is_quota = False

        for attempt in range(self.MAX_RETRIES):
            try:
                session = await self._get_session()
                async with session.post(
                    base_url,
                    data=data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
                ) as resp:
                    if resp.status != 200:
                        try:
                            err_data = await resp.json()
                            msg = err_data.get("message", f"HTTP {resp.status}")
                        except Exception:
                            msg = await resp.text()
                        is_quota = resp.status == 456
                        last_error = f"HTTP {resp.status}: {msg[:100]}"
                        if is_quota:
                            self.logger.error("DeepL API quota exceeded (HTTP 456)")
                            break
                        if attempt < self.MAX_RETRIES - 1:
                            await asyncio.sleep(self.RETRY_DELAYS[attempt])
                            continue
                        break

                    payload = await resp.json(content_type=None)
                    translations = payload.get("translations", [])
                    results: List[TranslationResult] = []

                    for i, orig_text in enumerate(source_texts):
                        if i < len(translations):
                            trans_val = translations[i].get("text", "")
                            for j, ph in enumerate(all_placeholders[i].keys()):
                                trans_val = trans_val.replace(f'<x i="{j}"/>', ph)
                                trans_val = re.sub(rf'<x\s+i\s*=\s*"{j}"\s*/>', ph, trans_val, flags=re.IGNORECASE)

                            final_text = restore_rpgm_syntax(trans_val, all_placeholders[i], orig_text)
                            final_text = self._clean_deepl_rpgm_codes(final_text)

                            results.append(
                                TranslationResult(
                                    original_text=orig_text,
                                    translated_text=final_text,
                                    source_lang=sl_list[i],
                                    target_lang=tl_list[i],
                                    engine=TranslationEngine.DEEPL,
                                    success=True,
                                    metadata=meta_list[i],
                                )
                            )
                        else:
                            results.append(
                                TranslationResult(
                                    original_text=orig_text,
                                    translated_text=orig_text,
                                    source_lang=sl_list[i],
                                    target_lang=tl_list[i],
                                    engine=TranslationEngine.DEEPL,
                                    success=False,
                                    error="Missing item in DeepL response",
                                    metadata=meta_list[i],
                                )
                            )

                    self.notify_progress(progress_callback, len(results))
                    return results

            except Exception as e:
                last_error = str(e)
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAYS[attempt])
                    continue

        fail_res = [
            TranslationResult(
                original_text=source_texts[i],
                translated_text="",
                source_lang=sl_list[i],
                target_lang=tl_list[i],
                engine=TranslationEngine.DEEPL,
                success=False,
                error=last_error or "DeepL request failed",
                quota_exceeded=is_quota,
                metadata=meta_list[i],
            )
            for i in range(len(source_texts))
        ]
        self.notify_progress(progress_callback, len(fail_res))
        return fail_res

    def get_supported_languages(self) -> Dict[str, str]:
        return {
            "bg": "Bulgarian", "cs": "Czech", "da": "Danish", "de": "German",
            "el": "Greek", "en": "English", "es": "Spanish", "et": "Estonian",
            "fi": "Finnish", "fr": "French", "hu": "Hungarian", "id": "Indonesian",
            "it": "Italian", "ja": "Japanese", "ko": "Korean", "lt": "Lithuanian",
            "lv": "Latvian", "nb": "Norwegian", "nl": "Dutch", "pl": "Polish",
            "pt": "Portuguese", "ro": "Romanian", "ru": "Russian", "sk": "Slovak",
            "sl": "Slovenian", "sv": "Swedish", "tr": "Turkish", "uk": "Ukrainian",
            "zh": "Chinese",
        }


class LibreTranslateTranslator(BaseTranslator):
    """Local or public LibreTranslate API translator with rate-limit and placeholder shielding."""

    MAX_RETRIES = 3
    RETRY_DELAYS = [2.0, 4.0, 8.0]

    def __init__(
        self,
        base_url: str = "http://localhost:5000",
        api_key: str = "",
        proxy_manager: Any = None,
        config_manager: Any = None,
        timeout_seconds: int = 45,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds)
        clean_url = base_url.strip().rstrip("/")
        if clean_url and not (clean_url.startswith("http://") or clean_url.startswith("https://")):
            clean_url = f"http://{clean_url}"
        self.base_url = clean_url
        self.api_key = api_key.strip()
        self.proxy_manager = proxy_manager
        self.config_manager = config_manager
        self.is_local = "localhost" in self.base_url or "127.0.0.1" in self.base_url
        self._engine = TranslationEngine.LIBRETRANSLATE

    @staticmethod
    def _get_lang_code(raw: str) -> str:
        raw = raw.lower().strip()
        if raw == "auto":
            return "auto"
        if "-" in raw or len(raw) <= 3:
            return raw
        return raw[:2]

    async def translate_single(self, request: TranslationRequest | Dict[str, Any]) -> TranslationResult:
        res = await self.translate_batch([request])
        return res[0] if res else TranslationResult(
            original_text="", translated_text="", source_lang="auto", target_lang="en",
            engine=TranslationEngine.LIBRETRANSLATE, success=False, error="Batch failed",
        )

    async def translate_batch(
        self,
        requests: Sequence[TranslationRequest | Dict[str, Any]],
        progress_callback: Optional[Any] = None,
    ) -> List[TranslationResult]:
        if not requests:
            return []

        source_texts: List[str] = []
        meta_list: List[Dict[str, Any]] = []
        sl_list: List[str] = []
        tl_list: List[str] = []

        for r in requests:
            if isinstance(r, dict):
                st = r.get("text", "")
                m = r.get("metadata", {})
                sl = r.get("source_lang") or m.get("source_lang", "auto")
                tl = r.get("target_lang") or m.get("target_lang", "en")
            else:
                st = r.text
                m = r.metadata if isinstance(r.metadata, dict) else {}
                sl = r.source_lang
                tl = r.target_lang
            source_texts.append(st)
            meta_list.append(m)
            sl_list.append(sl)
            tl_list.append(tl)

        src_lang = self._get_lang_code(sl_list[0])
        tgt_lang = self._get_lang_code(tl_list[0])

        texts_to_translate: List[str] = []
        all_placeholders: List[Dict[str, str]] = []

        for st in source_texts:
            p_text, p_holders = protect_rpgm_syntax(st)
            html_text = (
                p_text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            for ph in sorted(p_holders.keys(), key=len, reverse=True):
                html_text = html_text.replace(ph, f'<span translate="no">{ph}</span>')
            texts_to_translate.append(html_text)
            all_placeholders.append(p_holders)

        payload: Dict[str, Any] = {
            "q": texts_to_translate,
            "source": src_lang,
            "target": tgt_lang,
            "format": "html",
        }
        if self.api_key:
            payload["api_key"] = self.api_key

        url = f"{self.base_url}/translate"
        last_error = ""
        is_quota = False

        headers = {
            "Content-Type": "application/json",
            "User-Agent": random.choice(USER_AGENTS) if not self.is_local else f"RPGMLocalizer/{_APP_VERSION}",
        }

        for attempt in range(self.MAX_RETRIES):
            try:
                session = await self._get_session()
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
                ) as resp:
                    if resp.status != 200:
                        try:
                            err_data = await resp.json()
                            msg = err_data.get("error", f"HTTP {resp.status}")
                        except Exception:
                            msg = await resp.text()

                        if resp.status == 429:
                            last_error = "Rate Limit Exceeded (429)"
                            is_quota = True
                            if attempt < self.MAX_RETRIES - 1:
                                await asyncio.sleep(self.RETRY_DELAYS[attempt])
                                continue
                            break
                        elif resp.status in (401, 403):
                            last_error = f"API Error ({resp.status}): {msg[:100]}"
                            break
                        else:
                            last_error = f"HTTP {resp.status}: {msg[:100]}"
                            if attempt < self.MAX_RETRIES - 1:
                                await asyncio.sleep(self.RETRY_DELAYS[attempt])
                                continue
                            break

                    resp_data = await resp.json(content_type=None)
                    translated_list = resp_data.get("translatedText", [])
                    if isinstance(translated_list, str):
                        translated_list = [translated_list]

                    results: List[TranslationResult] = []
                    for i, orig_text in enumerate(source_texts):
                        if i < len(translated_list):
                            raw_tr = translated_list[i]
                            raw_tr = re.sub(r'<span[^>]*translate=["\']no["\'][^>]*>(.*?)</span>', r'\1', raw_tr, flags=re.IGNORECASE | re.DOTALL)
                            raw_tr = (
                                raw_tr.replace("&amp;", "&")
                                .replace("&lt;", "<")
                                .replace("&gt;", ">")
                                .replace("&quot;", '"')
                                .replace("&#39;", "'")
                            )
                            final_text = restore_rpgm_syntax(raw_tr.strip(), all_placeholders[i], orig_text)
                            results.append(
                                TranslationResult(
                                    original_text=orig_text,
                                    translated_text=final_text,
                                    source_lang=sl_list[i],
                                    target_lang=tl_list[i],
                                    engine=TranslationEngine.LIBRETRANSLATE,
                                    success=True,
                                    metadata=meta_list[i],
                                )
                            )
                        else:
                            results.append(
                                TranslationResult(
                                    original_text=orig_text,
                                    translated_text=orig_text,
                                    source_lang=sl_list[i],
                                    target_lang=tl_list[i],
                                    engine=TranslationEngine.LIBRETRANSLATE,
                                    success=False,
                                    error="Missing item in LibreTranslate response",
                                    metadata=meta_list[i],
                                )
                            )

                    self.notify_progress(progress_callback, len(results))
                    return results

            except Exception as e:
                last_error = str(e)
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAYS[attempt])
                    continue

        fail_res = [
            TranslationResult(
                original_text=source_texts[i],
                translated_text="",
                source_lang=sl_list[i],
                target_lang=tl_list[i],
                engine=TranslationEngine.LIBRETRANSLATE,
                success=False,
                error=last_error or "LibreTranslate request failed",
                quota_exceeded=is_quota,
                metadata=meta_list[i],
            )
            for i in range(len(source_texts))
        ]
        self.notify_progress(progress_callback, len(fail_res))
        return fail_res

    def get_supported_languages(self) -> Dict[str, str]:
        return {
            "en": "English", "ar": "Arabic", "az": "Azerbaijani", "bg": "Bulgarian",
            "bn": "Bengali", "ca": "Catalan", "cs": "Czech", "da": "Danish",
            "de": "German", "el": "Greek", "eo": "Esperanto", "es": "Spanish",
            "et": "Estonian", "fa": "Persian", "fi": "Finnish", "fr": "French",
            "ga": "Irish", "he": "Hebrew", "hi": "Hindi", "hu": "Hungarian",
            "id": "Indonesian", "it": "Italian", "ja": "Japanese", "ko": "Korean",
            "lt": "Lithuanian", "lv": "Latvian", "ms": "Malay", "nb": "Norwegian Bokmål",
            "nl": "Dutch", "pl": "Polish", "pt": "Portuguese", "ro": "Romanian",
            "ru": "Russian", "sk": "Slovak", "sl": "Slovenian", "sq": "Albanian",
            "sr": "Serbian", "sv": "Swedish", "th": "Thai", "tl": "Filipino",
            "tr": "Turkish", "uk": "Ukrainian", "ur": "Urdu", "vi": "Vietnamese",
            "zh": "Chinese",
        }


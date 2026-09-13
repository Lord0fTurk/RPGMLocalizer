# -*- coding: utf-8 -*-
"""
AI Translator Implementations for RPGMLocalizer
================================================
Supports OpenAI, DeepSeek, Local LLM (Ollama / LM Studio), and Google Gemini.

All engines share a resilient, unified base that handles:
  - RPG Maker escape code and tag protection via syntax_guard_rpgm
  - Screenplay / scene batching with speaker context attribution
  - Token-efficient XML and structured JSON Schema batching
  - Tokenizer-friendly ASCII placeholder mapping (__PH_N__) for Unicode brackets
  - Tencent Hy-MT / Hunyuan-MT translation model family sampling & instruction profile
  - Layered 400 error fallback for local servers (LM Studio / Ollama)
  - Levenshtein-based placeholder recovery and orphan token cleanup
  - Exponential backoff with jitter and retry-after support
  - Content-filter safety recovery (returns original text gracefully)
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.core.constants import (
    AI_DEFAULT_MAX_TOKENS,
    AI_DEFAULT_TEMPERATURE,
    AI_DEFAULT_TIMEOUT,
    AI_LOCAL_TIMEOUT,
    AI_LOCAL_URL,
    AI_MAX_RETRIES,
)
from src.core.syntax_guard_rpgm import (
    inject_missing_placeholders,
    protect_rpgm_syntax,
    protect_rpgm_syntax_xml,
    restore_rpgm_syntax,
    restore_rpgm_syntax_xml,
    validate_translation_integrity,
)
from src.core.translators.base import (
    BaseTranslator,
    TranslationEngine,
    TranslationRequest,
    TranslationResult,
)

logger = logging.getLogger(__name__)

# ── Optional dependency guards ─────────────────────────────────────────────────
try:
    from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    AsyncOpenAI = None  # type: ignore[assignment, misc]
    APIStatusError = None  # type: ignore[assignment, misc]
    APITimeoutError = None  # type: ignore[assignment, misc]
    APIConnectionError = None  # type: ignore[assignment, misc]
    _OPENAI_AVAILABLE = False

_GEMINI_MODE: Optional[str] = None
try:
    import google.genai as genai
    if hasattr(genai, "Client"):
        _GEMINI_AVAILABLE = True
        _GEMINI_MODE = "google_genai"
    elif hasattr(genai, "GenerativeModel"):
        _GEMINI_AVAILABLE = True
        _GEMINI_MODE = "legacy_generativeai"
    else:
        _GEMINI_AVAILABLE = False
        genai = None  # type: ignore[assignment]
except ImportError:
    try:
        import google.generativeai as genai  # type: ignore[no-redef]
        _GEMINI_AVAILABLE = True
        _GEMINI_MODE = "legacy_generativeai"
    except ImportError:
        _GEMINI_AVAILABLE = False
        genai = None  # type: ignore[assignment]

# ─────────────────────────────────────────────────────────────────────────────
# Languages & Profiles
# ─────────────────────────────────────────────────────────────────────────────
_XML_ITEM_RE = re.compile(r'<item\s+id="(\d+)">(.*?)</item>', re.DOTALL)

_SUPPORTED_LANGUAGES: Dict[str, str] = {
    "auto": "Auto-detect",
    "en": "English", "tr": "Turkish", "de": "German", "fr": "French",
    "es": "Spanish", "it": "Italian", "pt": "Portuguese", "ru": "Russian",
    "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "ar": "Arabic",
    "pl": "Polish", "nl": "Dutch", "sv": "Swedish", "no": "Norwegian",
    "da": "Danish", "fi": "Finnish", "hu": "Hungarian", "cs": "Czech",
    "ro": "Romanian", "uk": "Ukrainian", "vi": "Vietnamese", "th": "Thai",
}

_HY_MT2_EXTRA_LANGUAGES: Dict[str, str] = {
    "he": "Hebrew", "hi": "Hindi", "bn": "Bengali", "fa": "Persian",
    "fil": "Filipino", "ms": "Malay", "id": "Indonesian",
    "ta": "Tamil", "te": "Telugu", "ur": "Urdu", "my": "Burmese",
    "km": "Khmer", "lo": "Lao", "mn": "Mongolian", "kk": "Kazakh",
    "ug": "Uyghur", "bo": "Tibetan",
    "zh-CN": "Chinese", "zh-TW": "Traditional Chinese", "yue": "Cantonese",
}

_HY_MT2_RE = re.compile(r"(?:hy|hunyuan)[-_ ]?mt", re.IGNORECASE)


def detect_model_profile(model_name: Optional[str]) -> Optional[str]:
    """Return 'hy_mt2' when the model name belongs to Tencent Hy-MT, else None."""
    if not model_name:
        return None
    return "hy_mt2" if _HY_MT2_RE.search(model_name) else None


def _resolve_language_name(code: Optional[str]) -> str:
    """Map a language code to full English name for AI prompt instructions."""
    if not code or code == "auto":
        return "the original language"
    name = _SUPPORTED_LANGUAGES.get(code)
    if name and name != "Auto-detect":
        return name
    name = _HY_MT2_EXTRA_LANGUAGES.get(code)
    if name:
        return name
    return code


def resolve_model_profile(config_manager: Any, model_name: Optional[str]) -> Optional[str]:
    """Resolve the effective model profile from configuration + autodetection."""
    cfg_profile = "auto"
    if config_manager and hasattr(config_manager, "translation_settings"):
        cfg_profile = (
            getattr(config_manager.translation_settings, "ai_model_profile", "auto")
            or "auto"
        )
    cfg_profile = str(cfg_profile).strip().lower()
    if cfg_profile == "generic":
        return None
    if cfg_profile == "hy_mt2":
        return "hy_mt2"
    return detect_model_profile(model_name)


# ─────────────────────────────────────────────────────────────────────────────
# Batch Builders & Parsers
# ─────────────────────────────────────────────────────────────────────────────
def _build_xml_batch(texts: List[str]) -> str:
    """Wrap texts in an XML structure for token-efficient batching."""
    parts = ["<translations>"]
    for i, text in enumerate(texts):
        safe = (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
        )
        parts.append(f'  <item id="{i}">{safe}</item>')
    parts.append("</translations>")
    return "\n".join(parts)


AI_BATCH_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "translated_text": {"type": "string"},
                },
                "required": ["id", "translated_text"],
            },
        }
    },
    "required": ["translations"],
}


def _build_json_batch(texts: List[str]) -> str:
    """Wrap texts in a JSON structure matching the schema."""
    items = [{"id": i, "text": text} for i, text in enumerate(texts)]
    return json.dumps({"items_to_translate": items}, ensure_ascii=False)


def _parse_json_batch(json_text: str, count: int) -> List[Optional[str]]:
    """Parse structured JSON response with tolerance for 1-based indexing."""
    results: List[Optional[str]] = [None] * count
    if not json_text:
        return results

    try:
        clean_text = json_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()

        data = json.loads(clean_text)
        translations = data.get("translations", [])

        extracted_ids: List[int] = []
        for item in translations:
            if isinstance(item, dict) and item.get("id") is not None:
                try:
                    extracted_ids.append(int(item["id"]))
                except (ValueError, TypeError):
                    pass

        is_1_based = bool(
            extracted_ids
            and 0 not in extracted_ids
            and min(extracted_ids) == 1
            and max(extracted_ids) <= count
        )

        unassigned_items: List[str] = []
        for item in translations:
            if not isinstance(item, dict):
                continue
            idx = item.get("id")
            val = item.get("translated_text")
            if val is None or not isinstance(val, str):
                continue

            assigned = False
            if idx is not None:
                try:
                    int_idx = int(idx) - 1 if is_1_based else int(idx)
                    if 0 <= int_idx < count and results[int_idx] is None:
                        results[int_idx] = val
                        assigned = True
                except (ValueError, TypeError):
                    pass
            if not assigned:
                unassigned_items.append(val)

        if unassigned_items and any(r is None for r in results):
            for val in unassigned_items:
                try:
                    first_empty = results.index(None)
                    results[first_empty] = val
                except ValueError:
                    break
    except Exception as exc:
        preview = (json_text or "").strip().replace("\n", " ")[:200]
        logger.warning(
            "Failed to parse AI JSON batch response (%s): %s | preview=%r",
            type(exc).__name__, exc, preview,
        )
    return results


_SCENE_LINE_RE = re.compile(r"^\s*(?:\[|\()?(\d+)(?:\]|\))?[\.\:\-\s]+\s*(.*)$")


def _build_scene_batch(
    texts: List[str], speakers: Optional[List[Optional[str]]] = None
) -> str:
    """Wrap dialogue lines into a screenplay format with character attribution."""
    lines = ["### SCENE START ###"]
    for i, text in enumerate(texts):
        spk = (
            speakers[i].strip()
            if speakers and i < len(speakers) and speakers[i]
            else None
        )
        if spk:
            lines.append(f"[{i}] {spk}: {text}")
        else:
            lines.append(f"[{i}] {text}")
    lines.append("### SCENE END ###")
    return "\n".join(lines)


def _parse_scene_batch(
    response_text: str,
    count: int,
    expected_speakers: Optional[List[Optional[str]]] = None,
) -> List[Optional[str]]:
    """Parse screenplay dialogue lines from model output, stripping speaker prefixes."""
    results: List[Optional[str]] = [None] * count
    if not response_text:
        return results

    clean = response_text.strip()
    if clean.startswith("```"):
        lines_raw = clean.splitlines()
        if len(lines_raw) >= 2 and lines_raw[0].startswith("```"):
            lines_raw = lines_raw[1:]
        if lines_raw and lines_raw[-1].startswith("```"):
            lines_raw = lines_raw[:-1]
        clean = "\n".join(lines_raw)

    for line in clean.splitlines():
        line = line.strip()
        if not line or line.startswith("###"):
            continue
        m = _SCENE_LINE_RE.match(line)
        if not m:
            continue
        try:
            idx = int(m.group(1))
            if not (0 <= idx < count):
                continue
            content = m.group(2).strip()

            spk = (
                expected_speakers[idx].strip()
                if expected_speakers
                and idx < len(expected_speakers)
                and expected_speakers[idx]
                else None
            )
            if spk and content.lower().startswith(f"{spk.lower()}:"):
                content = content[len(spk) + 1:].strip()
            elif ":" in content and spk:
                parts = content.split(":", 1)
                if len(parts) == 2 and len(parts[0].strip()) <= 30 and not any(p in parts[0] for p in ("⟦", "<", "[", "{", "\\")):
                    content = parts[1].strip()

            results[idx] = content
        except (ValueError, IndexError):
            continue

    return results


def _parse_xml_batch(xml_text: str, count: int) -> List[Optional[str]]:
    """Parse XML batch response (<translations><item id="N">...</item></translations>)."""
    results: List[Optional[str]] = [None] * count
    if not xml_text:
        return results

    try:
        start = xml_text.find("<translations>")
        end = xml_text.find("</translations>")
        if start != -1 and end != -1:
            xml_block = xml_text[start:end + len("</translations>")]
            root = ET.fromstring(xml_block)
            for item in root.findall("item"):
                idx_str = item.get("id")
                if idx_str is not None and item.text is not None:
                    try:
                        results[int(idx_str)] = item.text
                    except (ValueError, IndexError):
                        pass
            return results
    except ET.ParseError:
        pass

    for m in _XML_ITEM_RE.finditer(xml_text):
        try:
            idx = int(m.group(1))
            if 0 <= idx < count:
                results[idx] = m.group(2)
        except (ValueError, IndexError):
            pass
    return results


def _clean_orphaned_placeholders(text: str) -> str:
    """Remove mangled or orphaned placeholder residues like RLPHxxxx_y, ⟦, ⟧ etc."""
    if not text:
        return text
    text = re.sub(r'⟦?\s*(?:R[A-Z]{0,6}LPH|PH)[0-9A-F]{3,}(?:\s*_\s*\d+|\s*\d+)?\s*⟧?', '', text, flags=re.IGNORECASE)
    valid_tokens = re.findall(r'⟦\d+⟧', text)
    for i, token in enumerate(valid_tokens):
        text = text.replace(token, f"__VALID_PH_{i}__")
    text = text.replace('\u27e6', '').replace('\u27e7', '')
    for i, token in enumerate(valid_tokens):
        text = text.replace(f"__VALID_PH_{i}__", token)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _recover_placeholders_levenshtein(source_text: str, translated_text: str, placeholders: Dict[str, str]) -> str:
    """Attempt to recover missing placeholders by aligning relative to neighbor anchor words."""
    if not placeholders or not translated_text:
        return translated_text

    src_words = source_text.split()
    tr_words = translated_text.split()
    if not tr_words:
        return translated_text

    def edit_distance(s1: str, s2: str) -> int:
        if len(s1) > len(s2):
            s1, s2 = s2, s1
        distances = list(range(len(s1) + 1))
        for i2, c2 in enumerate(s2):
            distances_ = [i2 + 1]
            for i1, c1 in enumerate(s1):
                if c1 == c2:
                    distances_.append(distances[i1])
                else:
                    distances_.append(1 + min((distances[i1], distances[i1 + 1], distances_[-1])))
            distances = distances_
        return distances[-1]

    def clean_punct(w: str) -> str:
        return re.sub(r'[^\w\s\u0080-\uffff]', '', w).lower()

    for token, _ in placeholders.items():
        if token in translated_text:
            continue

        token_idx = -1
        for idx, w in enumerate(src_words):
            if token in w:
                token_idx = idx
                break
        if token_idx == -1:
            continue

        left_anchor = src_words[token_idx - 1] if token_idx > 0 else None
        right_anchor = src_words[token_idx + 1] if token_idx < len(src_words) - 1 else None

        best_left_idx, best_left_val = -1, 9999
        best_right_idx, best_right_val = -1, 9999

        for idx, w in enumerate(tr_words):
            w_clean = clean_punct(w)
            if not w_clean:
                continue
            if left_anchor:
                la_clean = clean_punct(left_anchor)
                dist = edit_distance(w_clean, la_clean)
                if dist < best_left_val and dist < max(3, len(la_clean) // 2):
                    best_left_val = dist
                    best_left_idx = idx
            if right_anchor:
                ra_clean = clean_punct(right_anchor)
                dist = edit_distance(w_clean, ra_clean)
                if dist < best_right_val and dist < max(3, len(ra_clean) // 2):
                    best_right_val = dist
                    best_right_idx = idx

        insert_idx = -1
        if best_left_idx != -1 and best_right_idx != -1:
            insert_idx = best_left_idx + 1 if best_left_idx < best_right_idx else best_right_idx
        elif best_left_idx != -1:
            insert_idx = best_left_idx + 1
        elif best_right_idx != -1:
            insert_idx = best_right_idx
        else:
            insert_idx = len(tr_words)

        if insert_idx != -1:
            tr_words.insert(insert_idx, token)

    return _clean_orphaned_placeholders(" ".join(tr_words))


def _jitter_sleep(base: float, attempt: int, cap: float = 60.0) -> float:
    """Return wait time with full jitter."""
    return random.uniform(0, min(cap, base * (2 ** attempt)))


# ─────────────────────────────────────────────────────────────────────────────
# AsyncBaseAITranslator
# ─────────────────────────────────────────────────────────────────────────────
class AsyncBaseAITranslator(BaseTranslator):
    """
    Shared async base for OpenAI-compatible LLM translation engines.
    """

    HY_MT2_TEMPERATURE = 0.7
    HY_MT2_TOP_P = 0.6
    HY_MT2_EXTRA_BODY: Dict[str, Any] = {"top_k": 20, "repetition_penalty": 1.05}

    def __init__(
        self,
        api_key: Optional[str] = None,
        proxy_manager: Any = None,
        config_manager: Any = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        batch_size: Optional[int] = None,
        semaphore_count: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout_seconds=int(timeout or AI_DEFAULT_TIMEOUT))
        if not _OPENAI_AVAILABLE:
            raise ImportError(
                "The 'openai' package is required for AI translation engines. "
                "Install it with: pip install openai>=1.50.0"
            )

        self.api_key: str = api_key or "none"
        self.proxy_manager = proxy_manager
        self.config_manager = config_manager
        self._model: str = model or "gpt-4o-mini"
        self._base_url: Optional[str] = base_url
        self._timeout: float = timeout or AI_DEFAULT_TIMEOUT
        self._batch_size: int = batch_size or 20
        self._semaphore_count: int = semaphore_count or 5
        self._engine: TranslationEngine = TranslationEngine.OPENAI
        self._client: Optional[Any] = None
        self._semaphore: Optional[asyncio.Semaphore] = None

        # Interface compatibility attributes
        self.endpoint = (self._base_url.rstrip("/") + "/chat/completions") if self._base_url else "https://api.openai.com/v1/chat/completions"
        self.model = self._model

        self._model_profile: Optional[str] = resolve_model_profile(config_manager, self._model)
        if self._model_profile == "hy_mt2":
            self.logger.info(
                f"[{self.__class__.__name__}] Hy-MT model profile active for '{self._model}'"
            )

    def _get_client(self) -> Any:
        if self._client is None:
            kwargs: Dict[str, Any] = {
                "api_key": self.api_key or "none",
                "timeout": self._timeout,
                "max_retries": 0,
            }
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._semaphore_count)
        return self._semaphore

    def _is_hy_mt2(self) -> bool:
        return self._model_profile == "hy_mt2"

    def _get_sampling_kwargs(self) -> Dict[str, Any]:
        if self._is_hy_mt2():
            return {
                "top_p": self.HY_MT2_TOP_P,
                "extra_body": dict(self.HY_MT2_EXTRA_BODY),
            }
        return {}

    def _get_temperature(self) -> float:
        if self._is_hy_mt2():
            cfg_val = None
            if self.config_manager and hasattr(self.config_manager, "translation_settings"):
                cfg_val = getattr(self.config_manager.translation_settings, "ai_temperature", None)
            if cfg_val is not None and float(cfg_val) != AI_DEFAULT_TEMPERATURE:
                return float(cfg_val)
            return self.HY_MT2_TEMPERATURE
        if self.config_manager and hasattr(self.config_manager, "translation_settings"):
            return float(getattr(self.config_manager.translation_settings, "ai_temperature", AI_DEFAULT_TEMPERATURE))
        return AI_DEFAULT_TEMPERATURE

    def _get_max_tokens(self) -> int:
        if self.config_manager and hasattr(self.config_manager, "translation_settings"):
            return int(getattr(self.config_manager.translation_settings, "ai_max_tokens", AI_DEFAULT_MAX_TOKENS))
        return AI_DEFAULT_MAX_TOKENS

    def _get_retry_count(self) -> int:
        if self.config_manager and hasattr(self.config_manager, "translation_settings"):
            return int(getattr(self.config_manager.translation_settings, "ai_retry_count", AI_MAX_RETRIES))
        return AI_MAX_RETRIES

    def _map_unicode_to_ascii_placeholders(
        self, text: str, placeholders: Dict[str, str]
    ) -> Tuple[str, Dict[str, str]]:
        """Map namespaced Unicode tokens (⟦RLPHxxxx_0⟧) to tokenizer-friendly ASCII (__PH_0__)."""
        if not text or not placeholders:
            return text, {}

        ascii_map: Dict[str, str] = {}
        mapped_text = text
        for i, unicode_token in enumerate(placeholders.keys()):
            ascii_token = f"__PH_{i}__"
            ascii_map[ascii_token] = unicode_token
            mapped_text = mapped_text.replace(unicode_token, ascii_token)

        return mapped_text, ascii_map

    def _map_ascii_to_unicode_placeholders(
        self, text: str, ascii_map: Dict[str, str]
    ) -> str:
        """Revert tokenizer-friendly ASCII placeholders (__PH_0__) back to original tokens."""
        if not text or not ascii_map:
            return text

        ph_pattern = re.compile(r'(?i)__\s*PH\s*_\s*(\d+)\s*__')

        def _replace_ph(m: re.Match) -> str:
            try:
                idx = int(m.group(1))
                ascii_key = f"__PH_{idx}__"
                return ascii_map.get(ascii_key, m.group(0))
            except (ValueError, IndexError):
                return m.group(0)

        return ph_pattern.sub(_replace_ph, text)

    def _build_hy_mt2_single_prompt(
        self,
        tgt_lang_name: str,
        protected_text: str,
        placeholders: Dict[str, str],
        xml_mode: bool = True,
    ) -> str:
        instruction = (
            f"Translate the following text into {tgt_lang_name}. Note that you "
            "should only output the translated result without any additional explanation"
        )
        if placeholders:
            if xml_mode:
                tokens = [f'<ph id="{k}">' for k in sorted(placeholders.keys())][:6]
            else:
                tokens = sorted(set(placeholders.keys()))[:6]
            token_list = ", ".join(tokens)
            instruction += (
                ". You must retain the exact same number of delimiters and "
                f"placeholder tokens ({token_list}) in the translated output; "
                "never omit, escape, translate, or reorder them"
            )
        return instruction + ":\n\n" + protected_text

    def _build_hy_mt2_batch_prompt(self, src_lang_name: str, tgt_lang_name: str) -> str:
        return (
            f"The following is structured data containing text segments to "
            f"translate from {src_lang_name} into {tgt_lang_name}. Translate "
            'only the visible user-facing text inside the "text" field of '
            "each item. Preserve the data structure exactly: keep all keys and "
            '"id" values unchanged; never translate or modify placeholders '
            'like <ph id="N">...</ph>, __PH_N__, \\V[n], \\N[n], \\C[n], '
            "\\I[n], <WordWrap>. Keep the exact same number of items.\n"
            "Return a JSON object with this exact structure, nothing else:\n"
            '{"translations": [{"id": integer, "translated_text": string}]}'
        )

    async def _call_api(
        self,
        system_prompt: Optional[str],
        user_content: str,
        use_json_schema: bool = False,
        top_p: Optional[float] = None,
        extra_body: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Execute API request with retry, jitter backoff, and layered 400 fallbacks."""
        client = self._get_client()
        retries = self._get_retry_count()

        for attempt in range(retries + 1):
            try:
                messages: List[Dict[str, str]] = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": user_content})

                kwargs: Dict[str, Any] = {
                    "model": self._model,
                    "messages": messages,
                    "temperature": self._get_temperature(),
                    "max_tokens": self._get_max_tokens(),
                }
                if top_p is not None:
                    kwargs["top_p"] = top_p
                if extra_body is not None:
                    kwargs["extra_body"] = extra_body
                if use_json_schema:
                    kwargs["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "translation_response",
                            "strict": True,
                            "schema": AI_BATCH_SCHEMA,
                        },
                    }

                response = await client.chat.completions.create(**kwargs)
                finish_reason = response.choices[0].finish_reason
                if finish_reason == "content_filter":
                    self.logger.warning(
                        f"[{self.__class__.__name__}] Content filter triggered. Returning original text."
                    )
                content = response.choices[0].message.content or None
                return content

            except Exception as exc:
                if _OPENAI_AVAILABLE and APIStatusError and isinstance(exc, APIStatusError) and exc.status_code == 400:
                    if extra_body is not None:
                        self.logger.warning(
                            f"[{self.__class__.__name__}] Server rejected extra_body fields (400). Retrying without extra_body."
                        )
                        return await self._call_api(
                            system_prompt, user_content,
                            use_json_schema=use_json_schema,
                            top_p=top_p, extra_body=None,
                        )
                    if use_json_schema:
                        self.logger.warning(
                            f"[{self.__class__.__name__}] Engine failed on response_format json_schema (400). Retrying without schema."
                        )
                        return await self._call_api(
                            system_prompt, user_content,
                            use_json_schema=False, top_p=top_p,
                        )

                is_quota = False
                is_retryable = False
                retry_after: Optional[float] = None

                if _OPENAI_AVAILABLE:
                    if APIStatusError and isinstance(exc, APIStatusError):
                        status = exc.status_code
                        try:
                            ra = exc.response.headers.get("retry-after")
                            if ra:
                                retry_after = float(ra)
                        except Exception:
                            pass
                        if status == 429:
                            is_quota = True
                            is_retryable = True
                        elif status in (500, 502, 503, 504):
                            is_retryable = True
                    elif APITimeoutError and isinstance(exc, (APITimeoutError, APIConnectionError)):
                        is_retryable = True

                if not is_retryable and not is_quota:
                    self.logger.error(f"[{self.__class__.__name__}] Non-retryable error: {exc}")
                    return None

                if attempt >= retries:
                    self.logger.warning(f"[{self.__class__.__name__}] Exhausted retries ({retries}): {exc}")
                    return None

                wait = retry_after if retry_after else _jitter_sleep(2.0, attempt)
                await asyncio.sleep(wait)

        return None

    async def translate_single(self, request: TranslationRequest | Dict[str, Any]) -> TranslationResult:
        """Translate a single segment with syntax protection and recovery."""
        if isinstance(request, dict):
            source_text = request.get("text", "").strip()
            metadata = request.get("metadata", {})
            src_lang = request.get("source_lang") or metadata.get("source_lang", "auto")
            tgt_lang = request.get("target_lang") or metadata.get("target_lang", "en")
        else:
            source_text = request.text.strip()
            metadata = request.metadata if isinstance(request.metadata, dict) else {}
            src_lang = request.source_lang
            tgt_lang = request.target_lang

        if not source_text:
            return TranslationResult(
                original_text=source_text,
                translated_text=source_text,
                source_lang=src_lang,
                target_lang=tgt_lang,
                engine=self._engine,
                success=True,
                metadata=metadata,
            )

        preprotected = bool(metadata.get("preprotected"))
        xml_mode = bool(metadata.get("xml_mode", True))

        if preprotected:
            protected = source_text
            placeholders = metadata.get("placeholders", {})
        else:
            if xml_mode:
                protected, placeholders = protect_rpgm_syntax_xml(source_text)
            else:
                protected, placeholders = protect_rpgm_syntax(source_text)

        if xml_mode:
            mapped_protected = protected
            ascii_map: Dict[str, str] = {}
        else:
            mapped_protected, ascii_map = self._map_unicode_to_ascii_placeholders(protected, placeholders)

        if self._is_hy_mt2():
            tgt_name = _resolve_language_name(tgt_lang)
            system_prompt = None
            delimiter_map = placeholders if xml_mode else (dict(ascii_map) if ascii_map else placeholders)
            user_content = self._build_hy_mt2_single_prompt(tgt_name, mapped_protected, delimiter_map, xml_mode=xml_mode)
        else:
            src_name = _SUPPORTED_LANGUAGES.get(src_lang, src_lang)
            if src_lang == "auto":
                src_name = "the original language"
            tgt_name = _SUPPORTED_LANGUAGES.get(tgt_lang, tgt_lang)

            custom_prompt = None
            if self.config_manager and hasattr(self.config_manager, "translation_settings"):
                custom_prompt = getattr(self.config_manager.translation_settings, "ai_custom_system_prompt", None)

            if custom_prompt and custom_prompt.strip():
                system_prompt = (
                    custom_prompt.strip()
                    + "\n\nImportant: You must strictly preserve all placeholders like __PH_0__, <ph id=\"N\">...</ph>, \\V[n], \\C[n] exactly."
                )
            else:
                system_prompt = (
                    "You are a professional RPG Maker video game translator. "
                    f"Translate dialogue and UI text from {src_name} to {tgt_name}. "
                    "Strictly preserve ALL escape codes, control codes, and placeholders exactly: "
                    '<ph id="N">...</ph>, __PH_0__, \\V[n], \\N[n], \\C[n], \\I[n], \\G, <WordWrap>. '
                    "Maintain the tone, style, and character voice of the original. "
                    "Return only the translated text without explanations."
                )
            user_content = mapped_protected

        async with self._get_semaphore():
            response = await self._call_api(system_prompt, user_content, **self._get_sampling_kwargs())

        if response is None:
            return TranslationResult(
                original_text=source_text,
                translated_text=source_text,
                source_lang=src_lang,
                target_lang=tgt_lang,
                engine=self._engine,
                success=True,
                metadata={**metadata, "skipped": True},
            )

        if xml_mode:
            translated = restore_rpgm_syntax_xml(response.strip(), placeholders, source_text)
            missing = validate_translation_integrity(translated, placeholders)
            if missing:
                translated = source_text
        else:
            unmapped = self._map_ascii_to_unicode_placeholders(response.strip(), ascii_map)
            translated = restore_rpgm_syntax(unmapped, placeholders, source_text)
            missing = validate_translation_integrity(translated, placeholders)
            if missing:
                recovered_lev = _recover_placeholders_levenshtein(source_text, translated, placeholders)
                recovered_lev = restore_rpgm_syntax(recovered_lev, placeholders, source_text)
                if not validate_translation_integrity(recovered_lev, placeholders):
                    translated = recovered_lev
                else:
                    injected = inject_missing_placeholders(translated, protected, placeholders, missing)
                    injected = restore_rpgm_syntax(injected, placeholders, source_text)
                    translated = injected if not validate_translation_integrity(injected, placeholders) else source_text

        translated = _clean_orphaned_placeholders(translated)

        return TranslationResult(
            original_text=source_text,
            translated_text=translated,
            source_lang=src_lang,
            target_lang=tgt_lang,
            engine=self._engine,
            success=True,
            metadata=metadata,
        )

    async def translate_batch(
        self,
        requests: Sequence[TranslationRequest | Dict[str, Any]],
        progress_callback: Optional[Any] = None,
    ) -> List[TranslationResult]:
        """Translate a batch using Screenplay Scene mode, XML grouping, or structured JSON Schema."""
        if not requests:
            return []
        if len(requests) == 1:
            res = await self.translate_single(requests[0])
            self.notify_progress(progress_callback, 1)
            return [res]

        batch_format = "scene"
        effective_chunk_size = self._batch_size
        if self.config_manager and hasattr(self.config_manager, "translation_settings"):
            ts = self.config_manager.translation_settings
            batch_format = getattr(ts, "ai_batch_format", "scene") or "scene"
            if batch_format == "scene":
                effective_chunk_size = getattr(ts, "ai_scene_batch_size", 15) or 15
            else:
                effective_chunk_size = getattr(ts, "ai_batch_size", self._batch_size) or self._batch_size

        chunks: List[List[Tuple[int, Any]]] = []
        cur_chunk: List[Tuple[int, Any]] = []
        for i, req in enumerate(requests):
            cur_chunk.append((i, req))
            if len(cur_chunk) >= effective_chunk_size:
                chunks.append(cur_chunk)
                cur_chunk = []
        if cur_chunk:
            chunks.append(cur_chunk)

        results: List[Optional[TranslationResult]] = [None] * len(requests)
        sem = self._get_semaphore()

        async def process_chunk(chunk: List[Tuple[int, Any]]) -> None:
            protected_list: List[str] = []
            placeholder_list: List[Dict[str, str]] = []
            source_list: List[str] = []
            ascii_maps_list: List[Dict[str, str]] = []
            speakers_list: List[Optional[str]] = []
            meta_list: List[Dict[str, Any]] = []
            sl_list: List[str] = []
            tl_list: List[str] = []

            for _, req in chunk:
                if isinstance(req, dict):
                    src_text = req.get("text", "").strip()
                    meta = req.get("metadata", {})
                    sl = req.get("source_lang") or meta.get("source_lang", "auto")
                    tl = req.get("target_lang") or meta.get("target_lang", "en")
                else:
                    src_text = req.text.strip()
                    meta = req.metadata if isinstance(req.metadata, dict) else {}
                    sl = req.source_lang
                    tl = req.target_lang

                source_list.append(src_text)
                meta_list.append(meta)
                sl_list.append(sl)
                tl_list.append(tl)

                # Extract character / speaker if present in RPG Maker metadata
                spk = (
                    meta.get("character")
                    or meta.get("speaker")
                    or meta.get("actor")
                    or meta.get("name")
                    or meta.get("who")
                )
                speakers_list.append(str(spk) if spk else None)

                preprotected = bool(meta.get("preprotected"))
                xml_mode = bool(meta.get("xml_mode", True))

                if preprotected:
                    prot = src_text
                    ph = meta.get("placeholders", {})
                else:
                    if xml_mode:
                        prot, ph = protect_rpgm_syntax_xml(src_text)
                    else:
                        prot, ph = protect_rpgm_syntax(src_text)

                if xml_mode:
                    mapped_prot = prot
                    ascii_map: Dict[str, str] = {}
                else:
                    mapped_prot, ascii_map = self._map_unicode_to_ascii_placeholders(prot, ph)

                protected_list.append(mapped_prot)
                placeholder_list.append(ph)
                ascii_maps_list.append(ascii_map)

            src_lang = sl_list[0]
            tgt_lang_code = tl_list[0]
            first_meta = meta_list[0]
            chunk_xml_mode = bool(first_meta.get("xml_mode", True))

            use_json = True
            if batch_format == "scene":
                use_json = False
                src_label = _resolve_language_name(src_lang) if self._is_hy_mt2() else _SUPPORTED_LANGUAGES.get(src_lang, src_lang)
                tgt_label = _resolve_language_name(tgt_lang_code) if self._is_hy_mt2() else _SUPPORTED_LANGUAGES.get(tgt_lang_code, tgt_lang_code)

                if self._is_hy_mt2():
                    system_prompt = None
                    instruction = (
                        f"Translate the following scene dialogue into {tgt_label}. "
                        "Keep each line formatted strictly as: [ID] Translated text. "
                        "Do not include the speaker name in the output line. "
                        "Retain the exact same number of lines, and preserve all special escape codes "
                        "(__PH_N__, \\V[n], \\C[n], \\I[n]) exactly:\n\n"
                    )
                    user_content = instruction + _build_scene_batch(protected_list, speakers_list)
                else:
                    system_prompt = (
                        "You are an expert RPG Maker video game translator. "
                        f"Translate the following scene dialogue from {src_label} to {tgt_label}. "
                        "Maintain character voice, emotional context, and natural dialogue flow.\n\n"
                        "Strict Rules:\n"
                        "1) Preserve ALL escape codes and placeholders (\\V[n], \\C[n], \\I[n], <WordWrap>, __PH_0__) exactly.\n"
                        "2) Return each line with its exact index tag matching input: [0] Translated text\n"
                        "3) Do NOT translate or include the speaker's name in your output line.\n"
                        "4) Do NOT skip any lines or merge lines.\n"
                        "5) Do NOT add commentary or code fences."
                    )
                    user_content = _build_scene_batch(protected_list, speakers_list)
            elif batch_format == "xml":
                use_json = False
                src_label = _resolve_language_name(src_lang) if self._is_hy_mt2() else _SUPPORTED_LANGUAGES.get(src_lang, src_lang)
                tgt_label = _resolve_language_name(tgt_lang_code) if self._is_hy_mt2() else _SUPPORTED_LANGUAGES.get(tgt_lang_code, tgt_lang_code)

                if self._is_hy_mt2():
                    system_prompt = None
                    instruction = (
                        f'Translate the text inside each <item id="N"> element into {tgt_label}. '
                        'Keep the exact same <translations> and <item id="N"> XML structure. '
                        "Preserve all special escape codes and placeholders exactly:\n\n"
                    )
                    user_content = instruction + _build_xml_batch(protected_list)
                else:
                    system_prompt = (
                        "You are a professional RPG Maker game translator. "
                        f"Translate each text item from {src_label} to {tgt_label}. "
                        "Strict Rules:\n"
                        '1) Preserve the exact XML structure: <translations><item id="N">Translated text</item></translations>\n'
                        "2) Preserve ALL escape codes and placeholders (\\V[n], \\C[n], \\I[n], <WordWrap>, __PH_0__) exactly.\n"
                        "3) Do NOT add commentary or code fences."
                    )
                    user_content = _build_xml_batch(protected_list)
            else:
                # Structured JSON schema
                src_label = _resolve_language_name(src_lang) if self._is_hy_mt2() else _SUPPORTED_LANGUAGES.get(src_lang, src_lang)
                tgt_label = _resolve_language_name(tgt_lang_code) if self._is_hy_mt2() else _SUPPORTED_LANGUAGES.get(tgt_lang_code, tgt_lang_code)

                if self._is_hy_mt2():
                    system_prompt = None
                    user_content = self._build_hy_mt2_batch_prompt(src_label, tgt_label) + "\n\n" + _build_json_batch(protected_list)
                else:
                    system_prompt = (
                        "You are a professional RPG Maker video game translator. "
                        f"Translate text segments from {src_label} to {tgt_label}. "
                        "Preserve all control codes, variables, and placeholders (\\V[n], \\C[n], \\I[n], __PH_0__) exactly. "
                        'Respond strictly with JSON matching: {"translations": [{"id": integer, "translated_text": string}]}.'
                    )
                    user_content = _build_json_batch(protected_list)

            async with sem:
                response = await self._call_api(
                    system_prompt, user_content,
                    use_json_schema=use_json,
                    **self._get_sampling_kwargs(),
                )

            if response is None:
                for idx_in_chunk, (orig_idx, req) in enumerate(chunk):
                    orig = source_list[idx_in_chunk]
                    results[orig_idx] = TranslationResult(
                        original_text=orig,
                        translated_text=orig,
                        source_lang=sl_list[idx_in_chunk],
                        target_lang=tl_list[idx_in_chunk],
                        engine=self._engine,
                        success=True,
                        metadata={**meta_list[idx_in_chunk], "skipped": True},
                    )
                return

            if batch_format == "scene":
                parsed = _parse_scene_batch(response, len(chunk), speakers_list)
                if all(x is None for x in parsed):
                    parsed = _parse_json_batch(response, len(chunk))
                    if all(x is None for x in parsed):
                        parsed = _parse_xml_batch(response, len(chunk))
            elif batch_format == "xml":
                parsed = _parse_xml_batch(response, len(chunk))
                if all(x is None for x in parsed):
                    parsed = _parse_json_batch(response, len(chunk))
                    if all(x is None for x in parsed):
                        parsed = _parse_scene_batch(response, len(chunk), speakers_list)
            else:
                parsed = _parse_json_batch(response, len(chunk))
                if all(x is None for x in parsed):
                    parsed = _parse_xml_batch(response, len(chunk))
                    if all(x is None for x in parsed):
                        parsed = _parse_scene_batch(response, len(chunk), speakers_list)

            for idx_in_chunk, (orig_idx, req) in enumerate(chunk):
                src_text = source_list[idx_in_chunk]
                translated_raw = parsed[idx_in_chunk]
                if translated_raw is None:
                    results[orig_idx] = await self.translate_single(req)
                    continue

                if chunk_xml_mode:
                    translated = restore_rpgm_syntax_xml(translated_raw.strip(), placeholder_list[idx_in_chunk], src_text)
                    missing = validate_translation_integrity(translated, placeholder_list[idx_in_chunk])
                    if missing:
                        translated = src_text
                else:
                    unmapped = self._map_ascii_to_unicode_placeholders(translated_raw.strip(), ascii_maps_list[idx_in_chunk])
                    translated = restore_rpgm_syntax(unmapped, placeholder_list[idx_in_chunk], src_text)
                    missing = validate_translation_integrity(translated, placeholder_list[idx_in_chunk])
                    if missing:
                        recovered_lev = _recover_placeholders_levenshtein(src_text, translated, placeholder_list[idx_in_chunk])
                        recovered_lev = restore_rpgm_syntax(recovered_lev, placeholder_list[idx_in_chunk], src_text)
                        if not validate_translation_integrity(recovered_lev, placeholder_list[idx_in_chunk]):
                            translated = recovered_lev
                        else:
                            injected = inject_missing_placeholders(
                                translated, protected_list[idx_in_chunk], placeholder_list[idx_in_chunk], missing
                            )
                            injected = restore_rpgm_syntax(injected, placeholder_list[idx_in_chunk], src_text)
                            translated = injected if not validate_translation_integrity(injected, placeholder_list[idx_in_chunk]) else src_text

                translated = _clean_orphaned_placeholders(translated)
                results[orig_idx] = TranslationResult(
                    original_text=src_text,
                    translated_text=translated,
                    source_lang=sl_list[idx_in_chunk],
                    target_lang=tl_list[idx_in_chunk],
                    engine=self._engine,
                    success=True,
                    metadata=meta_list[idx_in_chunk],
                )

        await asyncio.gather(*(process_chunk(ch) for ch in chunks))

        for i, req in enumerate(requests):
            if results[i] is None:
                orig = req.get("text", "") if isinstance(req, dict) else req.text
                meta = req.get("metadata", {}) if isinstance(req, dict) else (req.metadata or {})
                sl = req.get("source_lang", "auto") if isinstance(req, dict) else req.source_lang
                tl = req.get("target_lang", "en") if isinstance(req, dict) else req.target_lang
                results[i] = TranslationResult(
                    original_text=orig,
                    translated_text=orig,
                    source_lang=sl,
                    target_lang=tl,
                    engine=self._engine,
                    success=True,
                    metadata=meta,
                )

        self.notify_progress(progress_callback, len(results))
        return [r for r in results if r is not None]

    def get_supported_languages(self) -> Dict[str, str]:
        return _SUPPORTED_LANGUAGES

    async def close(self) -> None:
        await super().close()
        if self._client and hasattr(self._client, "close"):
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None


# ─────────────────────────────────────────────────────────────────────────────
# Specialized Translators
# ─────────────────────────────────────────────────────────────────────────────
class OpenAITranslator(AsyncBaseAITranslator):
    """OpenAI GPT-4o-mini / custom model translator."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        proxy_manager: Any = None,
        config_manager: Any = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        resolved_model = model
        if not resolved_model and config_manager and hasattr(config_manager, "translation_settings"):
            resolved_model = getattr(config_manager.translation_settings, "openai_model", "gpt-4o-mini")
        resolved_model = resolved_model or "gpt-4o-mini"

        resolved_base_url = base_url
        if not resolved_base_url and config_manager and hasattr(config_manager, "translation_settings"):
            resolved_base_url = getattr(config_manager.translation_settings, "openai_base_url", None)

        timeout = kwargs.get("timeout") or AI_DEFAULT_TIMEOUT
        batch_size = kwargs.get("batch_size", 20)

        super().__init__(
            api_key=api_key,
            proxy_manager=proxy_manager,
            config_manager=config_manager,
            model=resolved_model,
            base_url=resolved_base_url,
            timeout=timeout,
            batch_size=batch_size,
            semaphore_count=5,
            **kwargs,
        )
        self._engine = TranslationEngine.OPENAI


class DeepSeekTranslator(OpenAITranslator):
    """DeepSeek Chat / Coder translation adapter via OpenAI-compatible API."""

    _DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
    _DEEPSEEK_DEFAULT_MODEL = "deepseek-chat"

    def __init__(
        self,
        api_key: Optional[str] = None,
        proxy_manager: Any = None,
        config_manager: Any = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            api_key=api_key,
            proxy_manager=proxy_manager,
            config_manager=config_manager,
            model=model or self._DEEPSEEK_DEFAULT_MODEL,
            base_url=base_url or self._DEEPSEEK_BASE_URL,
            **kwargs,
        )
        self._semaphore_count = 12
        self._semaphore = None
        self._timeout = 120.0
        self._engine = TranslationEngine.DEEPSEEK


class LocalLLMTranslator(OpenAITranslator):
    """Local LLM translator for Ollama and LM Studio servers."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        proxy_manager: Any = None,
        config_manager: Any = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        resolved_base_url = base_url or AI_LOCAL_URL
        resolved_model = model or "llama3.2"

        if config_manager and hasattr(config_manager, "translation_settings"):
            ts = config_manager.translation_settings
            resolved_base_url = getattr(ts, "local_llm_url", None) or resolved_base_url
            resolved_model = getattr(ts, "local_llm_model", None) or resolved_model

        super().__init__(
            api_key=api_key or "none",
            proxy_manager=proxy_manager,
            config_manager=config_manager,
            model=resolved_model,
            base_url=resolved_base_url,
            **kwargs,
        )
        concurrency = 2
        if config_manager and hasattr(config_manager, "translation_settings"):
            concurrency = getattr(config_manager.translation_settings, "ai_concurrency", 2) or 2
        self._semaphore_count = max(1, int(concurrency))
        self._semaphore = None
        self._timeout = AI_LOCAL_TIMEOUT
        self._batch_size = 10
        self._engine = TranslationEngine.LOCAL_LLM


class GeminiTranslator(BaseTranslator):
    """Google Gemini translator supporting official google.genai and legacy SDKs."""

    def __init__(self, *args: Any, api_key: Optional[str] = None, **kwargs: Any) -> None:
        if not _GEMINI_AVAILABLE:
            raise ImportError(
                "google-genai is required for Gemini translation. "
                "Install it with: pip install google-genai"
            )

        resolved_key = api_key
        config_manager = kwargs.get("config_manager")
        if not resolved_key and config_manager and hasattr(config_manager, "api_keys"):
            resolved_key = getattr(config_manager.api_keys, "gemini_api_key", "")
        resolved_key = resolved_key or "none"

        model_name = "gemini-2.0-flash"
        if config_manager and hasattr(config_manager, "translation_settings"):
            model_name = getattr(config_manager.translation_settings, "gemini_model", None) or model_name

        super().__init__(timeout_seconds=int(kwargs.get("timeout", AI_DEFAULT_TIMEOUT)))
        self.api_key = resolved_key
        self._model = model_name
        self._engine = TranslationEngine.GEMINI

        if _GEMINI_MODE == "google_genai":
            client_kwargs: Dict[str, Any] = {}
            if resolved_key and resolved_key != "none":
                client_kwargs["api_key"] = resolved_key
            self._client = genai.Client(**client_kwargs) if genai else None
        else:
            if resolved_key and resolved_key != "none" and hasattr(genai, "configure"):
                genai.configure(api_key=resolved_key)
            if hasattr(genai, "GenerativeModel"):
                self._client = genai.GenerativeModel(model_name) if genai else None
            else:
                self._client = None

    async def translate_single(self, request: TranslationRequest | Dict[str, Any]) -> TranslationResult:
        if isinstance(request, dict):
            src_text = request.get("text", "")
            meta = request.get("metadata", {})
            src_lang = request.get("source_lang") or meta.get("source_lang", "auto")
            tgt_lang = request.get("target_lang") or meta.get("target_lang", "en")
        else:
            src_text = request.text
            meta = request.metadata if isinstance(request.metadata, dict) else {}
            src_lang = request.source_lang
            tgt_lang = request.target_lang

        if not src_text:
            return TranslationResult(
                original_text=src_text,
                translated_text=src_text,
                source_lang=src_lang,
                target_lang=tgt_lang,
                engine=TranslationEngine.GEMINI,
                success=True,
                metadata=meta,
            )

        protected, placeholders = protect_rpgm_syntax(src_text)

        prompt = (
            f"Translate the following RPG Maker game dialogue/text from {src_lang} to {tgt_lang}. "
            f"Only return the translation, without any commentary or explanations. "
            f"Do NOT modify or translate any control codes, variables, or placeholders: "
            f"{protected}"
        )

        try:
            if _GEMINI_MODE == "google_genai" and self._client:
                config_kwargs = {"temperature": 0.3, "max_output_tokens": 2048}
                config = (
                    genai.types.GenerateContentConfig(**config_kwargs)
                    if hasattr(genai, "types") and hasattr(genai.types, "GenerateContentConfig")
                    else None
                )
                response = await self._client.aio.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=config,
                )
                translated_raw = response.text.strip() if response and getattr(response, "text", None) else protected
            elif self._client:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self._client.generate_content(prompt),
                )
                translated_raw = response.text.strip() if response and getattr(response, "text", None) else protected
            else:
                translated_raw = protected

            final_text = restore_rpgm_syntax(translated_raw, placeholders, src_text)

            return TranslationResult(
                original_text=src_text,
                translated_text=final_text,
                source_lang=src_lang,
                target_lang=tgt_lang,
                engine=TranslationEngine.GEMINI,
                success=bool(final_text and final_text != src_text),
                metadata=meta,
            )

        except Exception as exc:
            error_msg = str(exc)
            if "SAFETY" in error_msg.upper() or "blocked" in error_msg.lower():
                return TranslationResult(
                    original_text=src_text,
                    translated_text=src_text,
                    source_lang=src_lang,
                    target_lang=tgt_lang,
                    engine=TranslationEngine.GEMINI,
                    success=False,
                    error="Content blocked by safety filter - original text returned",
                    metadata=meta,
                )
            return TranslationResult(
                original_text=src_text,
                translated_text=src_text,
                source_lang=src_lang,
                target_lang=tgt_lang,
                engine=TranslationEngine.GEMINI,
                success=False,
                error=error_msg,
                metadata=meta,
            )

    async def translate_batch(
        self,
        requests: Sequence[TranslationRequest | Dict[str, Any]],
        progress_callback: Optional[Any] = None,
    ) -> List[TranslationResult]:
        results: List[TranslationResult] = []
        for req in requests:
            res = await self.translate_single(req)
            results.append(res)
            self.notify_progress(progress_callback, 1)
        return results

    async def close(self) -> None:
        await super().close()
        if hasattr(self, "_client") and self._client and hasattr(self._client, "close"):
            try:
                self._client.close()
            except Exception:
                pass

    def get_supported_languages(self) -> Dict[str, str]:
        return _SUPPORTED_LANGUAGES

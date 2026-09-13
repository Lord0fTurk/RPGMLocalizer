"""
Translation Manager and Engine Factory
=======================================
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .base import BaseTranslator, TranslationEngine
from .google import GoogleTranslator
from .services import (
    DeepLTranslator,
    DeepSeekTranslator,
    LibreTranslateTranslator,
    LocalLLMTranslator,
    OpenAICompatibleTranslator,
    PseudoTranslator,
)

logger = logging.getLogger("TranslatorFactory")


def _build_deepl_translator(settings: Dict[str, Any], timeout: int) -> DeepLTranslator:
    api_key = str(settings.get("deepl_api_key", "") or settings.get("api_key", ""))
    formality = str(settings.get("deepl_formality", "default"))
    return DeepLTranslator(
        api_key=api_key,
        formality=formality,
        timeout_seconds=timeout,
    )


def _build_libretranslate_translator(settings: Dict[str, Any], timeout: int) -> LibreTranslateTranslator:
    api_key = str(settings.get("libretranslate_api_key", "") or settings.get("api_key", ""))
    base_url = str(settings.get("libretranslate_url", "http://localhost:5000"))
    return LibreTranslateTranslator(
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=timeout,
    )


def _build_pseudo_translator(settings: Dict[str, Any]) -> PseudoTranslator:
    mode = str(settings.get("pseudo_mode", "both"))
    return PseudoTranslator(mode=mode)


def _build_google_translator(
    settings: Dict[str, Any], concurrency: int, batch_size: int, timeout: int, engine_name: str
) -> GoogleTranslator:
    return GoogleTranslator(
        concurrency=concurrency,
        batch_size=batch_size,
        timeout_seconds=timeout,
        use_multi_endpoint=bool(settings.get("use_multi_endpoint", True)),
        enable_lingva_fallback=bool(settings.get("enable_lingva_fallback", engine_name == "lingva")),
    )


def _build_deepseek_translator(
    settings: Dict[str, Any], concurrency: int, batch_size: int, timeout: int
) -> DeepSeekTranslator:
    api_key = str(settings.get("deepseek_api_key", "") or settings.get("api_key", ""))
    model = str(settings.get("deepseek_model", "deepseek-chat"))
    base_url = str(settings.get("deepseek_base_url", "https://api.deepseek.com/v1"))
    return DeepSeekTranslator(
        api_key=api_key,
        model=model,
        base_url=base_url,
        concurrency=concurrency,
        batch_size=batch_size,
        timeout_seconds=timeout,
    )


def _build_openai_translator(
    settings: Dict[str, Any], concurrency: int, batch_size: int, timeout: int
) -> OpenAICompatibleTranslator:
    api_key = str(settings.get("openai_api_key", "") or settings.get("api_key", ""))
    if not api_key:
        logger.warning("No API key configured for OpenAI engine; requests will fail unless unauthenticated.")
    model = str(settings.get("openai_model", "gpt-4o-mini"))
    base_url = str(settings.get("openai_base_url", "https://api.openai.com/v1"))
    return OpenAICompatibleTranslator(
        api_key=api_key,
        model=model,
        base_url=base_url,
        concurrency=concurrency,
        batch_size=batch_size,
        timeout_seconds=timeout,
    )


def _build_gemini_translator(
    settings: Dict[str, Any], concurrency: int, batch_size: int, timeout: int
) -> OpenAICompatibleTranslator:
    api_key = str(settings.get("gemini_api_key", "") or settings.get("api_key", ""))
    if not api_key:
        logger.warning("No API key configured for Gemini engine; requests will fail unless unauthenticated.")
    model = str(settings.get("gemini_model", "gemini-2.0-flash"))
    base_url = str(settings.get("gemini_base_url", "https://generativelanguage.googleapis.com/v1beta/openai"))
    return OpenAICompatibleTranslator(
        api_key=api_key,
        model=model,
        base_url=base_url,
        concurrency=concurrency,
        batch_size=batch_size,
        timeout_seconds=timeout,
    )


def _build_local_llm_translator(
    settings: Dict[str, Any], concurrency: int, batch_size: int, timeout: int
) -> LocalLLMTranslator:
    api_key = str(settings.get("local_llm_api_key", "") or settings.get("api_key", ""))
    model = str(settings.get("local_llm_model", "") or settings.get("local_model", "llama3"))
    base_url = str(settings.get("local_llm_base_url", "") or settings.get("local_base_url", "http://localhost:11434/v1"))
    return LocalLLMTranslator(
        model=model,
        base_url=base_url,
        api_key=api_key,
        concurrency=concurrency,
        batch_size=batch_size,
        timeout_seconds=timeout,
    )


def create_translator(settings: Dict[str, Any]) -> BaseTranslator:
    """Factory function: construct the configured translation engine instance."""
    engine_name = str(settings.get("engine", "google")).lower().strip()
    concurrency = int(settings.get("concurrent_requests", 12))
    batch_size = int(settings.get("batch_size", 15))
    timeout = int(settings.get("timeout_seconds", 30))

    match engine_name:
        case "deepl":
            return _build_deepl_translator(settings, timeout)
        case "libretranslate":
            return _build_libretranslate_translator(settings, timeout)
        case "pseudo":
            return _build_pseudo_translator(settings)
        case "deepseek":
            return _build_deepseek_translator(settings, concurrency, batch_size, timeout)
        case "openai":
            return _build_openai_translator(settings, concurrency, batch_size, timeout)
        case "gemini":
            return _build_gemini_translator(settings, concurrency, batch_size, timeout)
        case "local_llm" | "ollama" | "local" | "lmstudio":
            return _build_local_llm_translator(settings, concurrency, batch_size, timeout)
        case _:
            return _build_google_translator(settings, concurrency, batch_size, timeout, engine_name)



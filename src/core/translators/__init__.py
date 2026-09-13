"""
Translators Subsystem for RPGMLocalizer
========================================
Modular, SOLID-compliant translation architecture.
"""
from .base import (
    BaseTranslator,
    TranslationEngine,
    TranslationRequest,
    TranslationResult,
)
from .google import GoogleTranslator
from .manager import create_translator
from .router import EndpointRouter, _FamilyHealth
from .services import (
    DeepLTranslator,
    DeepSeekTranslator,
    LibreTranslateTranslator,
    LocalLLMTranslator,
    OpenAICompatibleTranslator,
    PseudoTranslator,
    SegmentBatchTranslator,
)

__all__ = [
    "BaseTranslator",
    "TranslationEngine",
    "TranslationRequest",
    "TranslationResult",
    "GoogleTranslator",
    "EndpointRouter",
    "_FamilyHealth",
    "DeepLTranslator",
    "LibreTranslateTranslator",
    "PseudoTranslator",
    "OpenAICompatibleTranslator",
    "DeepSeekTranslator",
    "LocalLLMTranslator",
    "SegmentBatchTranslator",
    "create_translator",
]


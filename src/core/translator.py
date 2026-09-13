"""
Translator Subsystem Shim (v0.8.0 Modular Architecture)
========================================================

Backward compatibility wrapper. The monolithic translator has been refactored
into the `src.core.translators` package following the Single Responsibility Principle:

- `src.core.translators.base`: Data classes and abstract BaseTranslator.
- `src.core.translators.router`: EndpointRouter and health tracker.
- `src.core.translators.google`: Google Web client, batchexecute RPC, and Lingva.
- `src.core.translators.services`: OpenAI, DeepSeek, and Local LLM adapters.
- `src.core.translators.manager`: Engine factory and orchestration.
"""
from src.core.translators import (
    BaseTranslator,
    DeepLTranslator,
    DeepSeekTranslator,
    EndpointRouter,
    GoogleTranslator,
    LibreTranslateTranslator,
    LocalLLMTranslator,
    OpenAICompatibleTranslator,
    PseudoTranslator,
    SegmentBatchTranslator,
    TranslationEngine,
    TranslationRequest,
    TranslationResult,
    _FamilyHealth,
    create_translator,
)

try:
    from src.core.ai_translator import (
        AsyncBaseAITranslator,
        GeminiTranslator,
        OpenAITranslator,
    )
except ImportError:
    AsyncBaseAITranslator = None  # type: ignore[assignment, misc]
    GeminiTranslator = None  # type: ignore[assignment, misc]
    OpenAITranslator = None  # type: ignore[assignment, misc]

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
    "AsyncBaseAITranslator",
    "OpenAITranslator",
    "GeminiTranslator",
]


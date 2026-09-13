# -*- coding: utf-8 -*-
"""
Custom Exceptions for RPGMLocalizer
===================================
Standardized exception hierarchy for translation, network, and parser operations.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class RPGMLocalizerError(Exception):
    """Base exception for RPGMLocalizer with optional error code and context data."""

    def __init__(
        self,
        message: str = "",
        code: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        solution_hint: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.context = context or {}
        self.solution_hint = solution_hint

    def get_user_friendly_message(self) -> str:
        """Return human-readable message with optional solution hint."""
        msg = self.message
        if self.solution_hint:
            msg += f" (Çözüm ipucu: {self.solution_hint})"
        return msg

    def __str__(self) -> str:
        parts = [self.message] if self.message else [self.__class__.__name__]
        if self.code is not None:
            parts.append(f"[code={self.code}]")
        if self.solution_hint:
            parts.append(f"[ipucu={self.solution_hint}]")
        if self.context:
            parts.append(str(self.context))
        return " ".join(parts)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r}, code={self.code!r}, context={self.context!r})"


class ProxyError(RPGMLocalizerError):
    """Raised when proxy-related errors occur."""


class TranslationError(RPGMLocalizerError):
    """Raised when translation-related errors occur."""


class RateLimitError(TranslationError):
    """Raised when rate limits (HTTP 429) are exceeded."""

    def __init__(self, message: str = "Rate limit aşıldı (HTTP 429)", **kwargs: Any) -> None:
        kwargs.setdefault("solution_hint", "Lütfen istek gecikmesini artırın veya proxy rotasyonunu etkinleştirin.")
        super().__init__(message=message, **kwargs)


class QuotaExceededError(TranslationError):
    """Raised when API quota or credit limit is reached."""

    def __init__(self, message: str = "API kotası tükendi", **kwargs: Any) -> None:
        kwargs.setdefault("solution_hint", "API anahtarınızı ve sağlayıcı bakiyenizi kontrol edin.")
        super().__init__(message=message, **kwargs)


class NetworkConnectionError(TranslationError):
    """Raised when network connectivity issues occur during translation."""

    def __init__(self, message: str = "Ağ bağlantısı hatası", **kwargs: Any) -> None:
        kwargs.setdefault("solution_hint", "İnternet bağlantınızı veya ayarlanmış proxy bağlantısını kontrol edin.")
        super().__init__(message=message, **kwargs)


class ParseError(RPGMLocalizerError):
    """Raised when parsing-related errors occur."""


class ConfigError(RPGMLocalizerError):
    """Raised when configuration-related errors occur."""


class GuiError(RPGMLocalizerError):
    """Raised when GUI-related errors occur."""

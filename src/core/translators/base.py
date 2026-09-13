"""
Base Models and Abstract Classes for Translation Subsystem
===========================================================
"""
from __future__ import annotations

import asyncio
import aiohttp
import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from src.core.constants import DEFAULT_TIMEOUT_SECONDS


class TranslationEngine(Enum):
    """Supported translation engines."""
    GOOGLE = "google"
    DEEPL = "deepl"
    OPENAI = "openai"
    GEMINI = "gemini"
    LOCAL_LLM = "local_llm"
    OLLAMA = "ollama"
    DEEPSEEK = "deepseek"
    LIBRETRANSLATE = "libretranslate"
    PSEUDO = "pseudo"


@dataclass(slots=True)
class TranslationRequest:
    """Represents an individual text translation task."""
    text: str
    source_lang: str
    target_lang: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    engine: Optional[TranslationEngine] = None


@dataclass(slots=True)
class TranslationResult:
    """Represents the outcome of a translation task."""
    original_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    success: bool
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    engine: Optional[TranslationEngine] = None
    quota_exceeded: bool = False


class BaseTranslator(ABC):
    """Abstract base class for all translation engines."""

    _USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]

    def __init__(self, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector] = None
        self._session_lock = asyncio.Lock()
        self.timeout_seconds = timeout_seconds

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session and not self._session.closed:
            return self._session
        async with self._session_lock:
            if self._session and not self._session.closed:
                return self._session
            self._connector = aiohttp.TCPConnector(limit=256, ttl_dns_cache=300)
            timeout = aiohttp.ClientTimeout(
                total=max(45, self.timeout_seconds),
                sock_connect=5,
                sock_read=30,
            )
            ua = random.choice(self._USER_AGENTS)
            headers = {"User-Agent": ua, "Connection": "keep-alive"}
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=timeout,
                headers=headers,
            )
            return self._session

    async def close(self) -> None:
        """Close active ClientSession cleanly."""
        if self._session:
            try:
                await self._session.close()
            except Exception as e:
                self.logger.warning(f"Error closing session: {e}")
            finally:
                self._session = None
                self._connector = None

    async def __aenter__(self) -> BaseTranslator:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    @staticmethod
    def notify_progress(callback: Optional[Callable[..., Any]], count: int = 1) -> None:
        """Safely invoke progress_callback supporting both 0-arg and 1-arg signatures."""
        if not callback:
            return
        try:
            callback(count)
        except TypeError:
            try:
                callback()
            except Exception:
                pass
        except Exception:
            pass

    @abstractmethod
    async def translate_batch(
        self,
        requests: List[Dict[str, Any]],
        progress_callback: Optional[Any] = None,
    ) -> List[TranslationResult]:
        """Translate a batch of text requests."""
        pass


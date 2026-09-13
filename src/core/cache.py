"""
Translation cache for avoiding redundant translations.
Caches previously translated text to speed up subsequent runs.
Supports RenLocalizer-grade project-level and language-level isolation.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from typing import Dict, Optional, Tuple

from src.utils.app_paths import get_cache_dir, get_data_dir
from src.utils.file_ops import safe_write

logger = logging.getLogger(__name__)


def _resolve_default_cache_dir(
    project_id: Optional[str] = None,
    target_lang: Optional[str] = None,
) -> str:
    """Resolve the default cache directory in a deterministic location."""
    return os.fspath(get_cache_dir(project_id=project_id, target_lang=target_lang))


class TranslationCache:
    """
    Persistent cache for storing completed translations.
    Uses file hash + text hash as key to detect unchanged content.
    Supports project-level and language-level isolation.
    """

    CACHE_VERSION = "1.0"

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        project_id: Optional[str] = None,
        target_lang: Optional[str] = None,
    ) -> None:
        """
        Initialize translation cache.

        Args:
            cache_dir: Explicit directory to store cache files.
            project_id: Optional project identifier for project-isolated cache.
            target_lang: Optional target language code for language-isolated cache.
        """
        resolved_cache_dir = cache_dir or _resolve_default_cache_dir(
            project_id=project_id, target_lang=target_lang
        )
        self.cache_dir = os.path.abspath(resolved_cache_dir)
        self.project_id = project_id
        self.target_lang = target_lang
        self.cache: Dict[str, Dict] = {}  # text_hash -> entry metadata
        self.hits = 0
        self.misses = 0
        self._modified = False
        self._pending_writes = 0

        self._ensure_cache_dir()
        self._load_cache()

    def _ensure_cache_dir(self) -> None:
        """Create cache directory if it doesn't exist."""
        os.makedirs(self.cache_dir, exist_ok=True)

    def _get_cache_file(self) -> str:
        """Get path to the cache file."""
        return os.path.join(self.cache_dir, "translation_cache.json")

    def _load_legacy_cache(self) -> Optional[Dict[str, Dict]]:
        """Attempt to load and migrate entries from legacy flat cache files."""
        candidates = [
            os.path.join(os.fspath(get_cache_dir()), "translation_cache.json"),
            os.path.join(os.fspath(get_data_dir()), ".rpgm_cache", "translation_cache.json"),
        ]
        for candidate in candidates:
            if os.path.isfile(candidate) and os.path.abspath(candidate) != os.path.abspath(self._get_cache_file()):
                try:
                    with open(candidate, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("version") == self.CACHE_VERSION:
                        raw_entries = data.get("entries", {})
                        reindexed: Dict[str, Dict] = {}
                        for k, v in raw_entries.items():
                            if not isinstance(v, dict):
                                continue
                            t_lang = v.get("target_lang")
                            if self.target_lang and t_lang and t_lang != self.target_lang:
                                continue
                            orig = v.get("original")
                            s_lang = v.get("source_lang", "auto")
                            if orig and s_lang and t_lang:
                                h = self._hash_text(orig, s_lang, t_lang)
                                reindexed[h] = v
                            else:
                                reindexed[k] = v
                        if reindexed:
                            return reindexed
                except Exception:
                    pass
        return None

    def _load_cache(self) -> None:
        """Load cache from disk, falling back to legacy cache if empty."""
        cache_file = self._get_cache_file()

        if not os.path.exists(cache_file):
            legacy_entries = self._load_legacy_cache()
            if legacy_entries:
                self.cache = legacy_entries
                self._modified = True
                logger.info(
                    f"Imported {len(self.cache)} entries from legacy cache for project [{self.project_id}]"
                )
            else:
                self.cache = {}
            return

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if data.get("version") != self.CACHE_VERSION:
                logger.warning("Cache version mismatch, starting fresh")
                self.cache = {}
                return

            self.cache = data.get("entries", {})
            logger.info(f"Loaded {len(self.cache)} entries from cache")

        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            self.cache = {}

    def save(self) -> None:
        """Save cache to disk atomically."""
        if not self._modified:
            return

        cache_file = self._get_cache_file()

        try:
            data = {
                "version": self.CACHE_VERSION,
                "last_updated": datetime.now().isoformat(),
                "entries": self.cache,
            }

            with safe_write(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)

            self._modified = False
            self._pending_writes = 0
            logger.info(f"Saved {len(self.cache)} entries to cache")

        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def _hash_text(self, text: str, source_lang: str, target_lang: str) -> str:
        """Create a unique hash for a text + language pair."""
        key_str = f"{source_lang}:{target_lang}:{text}"
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()[:32]

    def get(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        """
        Get cached translation if available.

        Returns:
            Cached translation or None if not found
        """
        text_hash = self._hash_text(text, source_lang, target_lang)

        entry = self.cache.get(text_hash)
        if entry:
            self.hits += 1
            return entry.get("translation")

        self.misses += 1
        return None

    def set(self, text: str, translation: str, source_lang: str, target_lang: str) -> None:
        """Store a translation in the cache."""
        if not text or not text.strip() or not translation or not translation.strip():
            return

        text_hash = self._hash_text(text, source_lang, target_lang)

        self.cache[text_hash] = {
            "original": text[:200],  # Store truncated original for debugging
            "translation": translation,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "timestamp": datetime.now().isoformat(),
        }
        self._modified = True
        self._pending_writes += 1
        if self._pending_writes >= 50:
            self.save()

    def get_or_translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        translate_func,
    ) -> Tuple[Optional[str], bool]:
        """
        Get from cache or return None to signal translation needed.

        Returns:
            Tuple of (translation, was_cached)
        """
        cached = self.get(text, source_lang, target_lang)
        if cached:
            return cached, True

        return None, False

    def clear(self) -> None:
        """Clear all cached entries."""
        self.cache = {}
        self._modified = True
        self.hits = 0
        self.misses = 0

    def clear_for_language(self, target_lang: str) -> None:
        """Clear cached entries for a specific target language."""
        to_remove = [
            key for key, entry in self.cache.items()
            if entry.get("target_lang") == target_lang
        ]

        for key in to_remove:
            del self.cache[key]

        self._modified = True
        logger.info(f"Cleared {len(to_remove)} entries for language {target_lang}")

    def get_stats(self) -> dict:
        """Get cache statistics."""
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0.0

        return {
            "total_entries": len(self.cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{hit_rate:.1%}",
            "cache_dir": self.cache_dir,
            "project_id": self.project_id,
        }

    def cleanup_old_entries(self, max_age_days: int = 30) -> None:
        """Remove entries older than specified days."""
        now = datetime.now()
        to_remove = []

        for key, entry in self.cache.items():
            try:
                timestamp = datetime.fromisoformat(entry.get("timestamp", ""))
                age = (now - timestamp).days
                if age > max_age_days:
                    to_remove.append(key)
            except (ValueError, TypeError):
                pass

        for key in to_remove:
            del self.cache[key]

        if to_remove:
            self._modified = True
            logger.info(f"Cleaned up {len(to_remove)} old cache entries")

    def __enter__(self) -> TranslationCache:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.save()


# Global cache instance
_cache: Optional[TranslationCache] = None


def get_cache(
    cache_dir: Optional[str] = None,
    project_id: Optional[str] = None,
    target_lang: Optional[str] = None,
) -> TranslationCache:
    """Get or create the active translation cache instance."""
    global _cache
    if cache_dir:
        requested_dir = os.path.normcase(os.path.abspath(cache_dir))
    else:
        requested_dir = os.path.normcase(
            os.path.abspath(_resolve_default_cache_dir(project_id=project_id, target_lang=target_lang))
        )

    if _cache is None:
        _cache = TranslationCache(cache_dir=cache_dir, project_id=project_id, target_lang=target_lang)
    else:
        current_dir = os.path.normcase(os.path.abspath(_cache.cache_dir))
        if requested_dir != current_dir:
            _cache.save()
            _cache = TranslationCache(cache_dir=cache_dir, project_id=project_id, target_lang=target_lang)

    return _cache


def reset_cache() -> None:
    """Reset the global cache singleton. Call between different project runs."""
    global _cache
    if _cache is not None:
        _cache.save()
    _cache = None

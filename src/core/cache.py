"""
Translation cache for avoiding redundant translations.
Caches previously translated text to speed up subsequent runs.
"""
import json
import hashlib
import os
from typing import Dict, Optional, Tuple
from pathlib import Path
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class TranslationCache:
    """
    Persistent cache for storing completed translations.
    Uses file hash + text hash as key to detect unchanged content.
    """
    
    CACHE_VERSION = "1.0"
    
    def __init__(self, cache_dir: Optional[str] = None):
        """
        Initialize translation cache.
        
        Args:
            cache_dir: Directory to store cache files. 
                      If None, uses .rpgm_cache in current directory.
        """
        self.cache_dir = cache_dir or ".rpgm_cache"
        self.cache: Dict[str, Dict] = {}  # text_hash -> {translation, source_lang, target_lang, timestamp}
        self.hits = 0
        self.misses = 0
        self._modified = False
        
        self._ensure_cache_dir()
        self._load_cache()
    
    def _ensure_cache_dir(self):
        """Create cache directory if it doesn't exist."""
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def _get_cache_file(self) -> str:
        """Get path to the cache file."""
        return os.path.join(self.cache_dir, "translation_cache.json")
    
    def _load_cache(self):
        """Load cache from disk."""
        cache_file = self._get_cache_file()
        
        if not os.path.exists(cache_file):
            self.cache = {}
            return
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check version compatibility
            if data.get('version') != self.CACHE_VERSION:
                logger.warning("Cache version mismatch, starting fresh")
                self.cache = {}
                return
            
            self.cache = data.get('entries', {})
            logger.info(f"Loaded {len(self.cache)} entries from cache")
            
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            self.cache = {}
    
    def save(self):
        """Save cache to disk."""
        if not self._modified:
            return
        
        cache_file = self._get_cache_file()
        
        try:
            data = {
                'version': self.CACHE_VERSION,
                'last_updated': datetime.now().isoformat(),
                'entries': self.cache
            }
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            
            self._modified = False
            logger.info(f"Saved {len(self.cache)} entries to cache")
            
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
    
    def _hash_text(self, text: str, source_lang: str, target_lang: str) -> str:
        """Create a unique hash for a text + language pair."""
        key_str = f"{source_lang}:{target_lang}:{text}"
        return hashlib.sha256(key_str.encode('utf-8')).hexdigest()[:32]
    
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
            return entry.get('translation')
        
        self.misses += 1
        return None
    
    def set(self, text: str, translation: str, source_lang: str, target_lang: str):
        """Store a translation in the cache."""
        text_hash = self._hash_text(text, source_lang, target_lang)
        
        self.cache[text_hash] = {
            'original': text[:100],  # Store truncated original for debugging
            'translation': translation,
            'source_lang': source_lang,
            'target_lang': target_lang,
            'timestamp': datetime.now().isoformat()
        }
        self._modified = True
    
    def get_or_translate(self, text: str, source_lang: str, target_lang: str,
                         translate_func) -> Tuple[str, bool]:
        """
        Get from cache or translate and cache.
        
        Args:
            text: Text to translate
            source_lang: Source language code
            target_lang: Target language code
            translate_func: Async function that translates text
            
        Returns:
            Tuple of (translation, was_cached)
        """
        cached = self.get(text, source_lang, target_lang)
        if cached:
            return cached, True
        
        # Not in cache, need to translate
        # Note: caller must handle async if translate_func is async
        return None, False
    
    def clear(self):
        """Clear all cached entries."""
        self.cache = {}
        self._modified = True
        self.hits = 0
        self.misses = 0
    
    def clear_for_language(self, target_lang: str):
        """Clear cached entries for a specific target language."""
        to_remove = []
        for key, entry in self.cache.items():
            if entry.get('target_lang') == target_lang:
                to_remove.append(key)
        
        for key in to_remove:
            del self.cache[key]
        
        self._modified = True
        logger.info(f"Cleared {len(to_remove)} entries for language {target_lang}")
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        hit_rate = self.hits / (self.hits + self.misses) if (self.hits + self.misses) > 0 else 0
        
        return {
            'total_entries': len(self.cache),
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': f"{hit_rate:.1%}",
            'cache_dir': self.cache_dir
        }
    
    def cleanup_old_entries(self, max_age_days: int = 30):
        """Remove entries older than specified days."""
        now = datetime.now()
        to_remove = []
        
        for key, entry in self.cache.items():
            try:
                timestamp = datetime.fromisoformat(entry.get('timestamp', ''))
                age = (now - timestamp).days
                if age > max_age_days:
                    to_remove.append(key)
            except (ValueError, TypeError):
                # Invalid timestamp, keep the entry
                pass
        
        for key in to_remove:
            del self.cache[key]
        
        if to_remove:
            self._modified = True
            logger.info(f"Cleaned up {len(to_remove)} old cache entries")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.save()


# Global cache instance
_cache: Optional[TranslationCache] = None


def get_cache(cache_dir: Optional[str] = None) -> TranslationCache:
    """Get or create the global translation cache."""
    global _cache
    if _cache is None:
        _cache = TranslationCache(cache_dir)
    return _cache


def reset_cache():
    """Reset the global cache singleton. Call between different project runs."""
    global _cache
    if _cache is not None:
        _cache.save()  # Save before resetting
    _cache = None

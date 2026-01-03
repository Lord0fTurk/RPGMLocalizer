"""
Glossary system for consistent term translation.
Ensures specific terms (character names, items, etc.) are translated consistently.
"""
import json
import re
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class Glossary:
    """
    Manages a glossary of terms for consistent translation.
    Terms in the glossary are protected during translation and replaced with
    their pre-defined translations afterward.
    """
    
    def __init__(self, glossary_path: Optional[str] = None):
        """
        Initialize glossary.
        
        Args:
            glossary_path: Optional path to a JSON glossary file.
        """
        self.terms: Dict[str, str] = {}
        self.case_sensitive: bool = False
        self._pattern: Optional[re.Pattern] = None
        
        if glossary_path:
            self.load(glossary_path)
    
    def load(self, file_path: str) -> bool:
        """
        Load glossary from a JSON file.
        
        Expected format:
        {
            "terms": {
                "Potion": "İksir",
                "Hero": "Kahraman"
            },
            "case_sensitive": false
        }
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, dict):
                self.terms = data.get('terms', data)  # Support both formats
                self.case_sensitive = data.get('case_sensitive', False)
            else:
                logger.warning(f"Invalid glossary format in {file_path}")
                return False
            
            self._build_pattern()
            logger.info(f"Loaded {len(self.terms)} glossary terms from {file_path}")
            return True
            
        except FileNotFoundError:
            logger.warning(f"Glossary file not found: {file_path}")
            return False
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in glossary file: {e}")
            return False
    
    def save(self, file_path: str) -> bool:
        """Save glossary to a JSON file."""
        try:
            data = {
                'terms': self.terms,
                'case_sensitive': self.case_sensitive
            }
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save glossary: {e}")
            return False
    
    def add_term(self, original: str, translation: str):
        """Add a term to the glossary."""
        self.terms[original] = translation
        self._build_pattern()
    
    def remove_term(self, original: str):
        """Remove a term from the glossary."""
        self.terms.pop(original, None)
        self._build_pattern()
    
    def _build_pattern(self):
        """Build regex pattern for matching glossary terms."""
        if not self.terms:
            self._pattern = None
            return
        
        # Sort by length (longest first) to match longer terms first
        sorted_terms = sorted(self.terms.keys(), key=len, reverse=True)
        
        # Escape special regex characters
        escaped = [re.escape(term) for term in sorted_terms]
        
        # Build pattern with word boundaries
        pattern_str = r'\b(' + '|'.join(escaped) + r')\b'
        
        flags = 0 if self.case_sensitive else re.IGNORECASE
        self._pattern = re.compile(pattern_str, flags)
    
    def protect_terms(self, text: str) -> Tuple[str, Dict[str, str]]:
        """
        Protect glossary terms in text with placeholders.
        
        Returns:
            Tuple of (protected_text, placeholder_map)
        """
        if not self._pattern or not self.terms:
            return text, {}
        
        placeholders: Dict[str, str] = {}
        counter = [0]  # Use list for mutability in nested function
        
        def replacer(match):
            original = match.group(0)
            key = f"〈TERM_{counter[0]}〉"
            # Store both original and its translation
            placeholders[key] = (original, self._get_translation(original))
            counter[0] += 1
            return key
        
        protected = self._pattern.sub(replacer, text)
        return protected, placeholders
    
    def restore_terms(self, text: str, placeholders: Dict[str, Tuple[str, str]], 
                      use_translation: bool = True) -> str:
        """
        Restore glossary terms in text.
        
        Args:
            text: Text with placeholders
            placeholders: Map from placeholder to (original, translation)
            use_translation: If True, use translation; if False, restore original
        """
        result = text
        
        for key, (original, translation) in placeholders.items():
            replacement = translation if use_translation else original
            result = result.replace(key, replacement)
        
        return result
    
    def _get_translation(self, term: str) -> str:
        """Get translation for a term, handling case sensitivity."""
        if self.case_sensitive:
            return self.terms.get(term, term)
        
        # Case-insensitive lookup
        term_lower = term.lower()
        for key, value in self.terms.items():
            if key.lower() == term_lower:
                return value
        return term
    
    def apply_to_text(self, text: str) -> str:
        """
        Directly apply glossary translations to text.
        Useful for post-processing or when not using protect/restore flow.
        """
        if not self._pattern or not self.terms:
            return text
        
        def replacer(match):
            return self._get_translation(match.group(0))
        
        return self._pattern.sub(replacer, text)
    
    def __len__(self) -> int:
        return len(self.terms)
    
    def __contains__(self, term: str) -> bool:
        if self.case_sensitive:
            return term in self.terms
        return term.lower() in {k.lower() for k in self.terms}


def create_sample_glossary(output_path: str):
    """Create a sample glossary file for the user."""
    sample = {
        "terms": {
            "Potion": "İksir",
            "Hi-Potion": "Güçlü İksir",
            "Ether": "Ether",
            "Phoenix Down": "Anka Tüyü",
            "Hero": "Kahraman",
            "Attack": "Saldırı",
            "Defense": "Savunma",
            "Magic": "Büyü",
            "HP": "HP",
            "MP": "MP",
            "Gold": "Altın"
        },
        "case_sensitive": False
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Created sample glossary at {output_path}")

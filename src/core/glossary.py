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
        self.terms: Dict[str, Dict[str, Any]] = {}  # { original: { 'translation': str, 'is_regex': bool } }
        self.case_sensitive: bool = False
        self._pattern: Optional[re.Pattern] = None
        self._regex_rules: List[Tuple[re.Pattern, str]] = []  # List of (compiled_pattern, translation_template)
        
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
                raw_terms = data.get('terms', {})
                # Normalize terms to new structure
                for key, val in raw_terms.items():
                    if isinstance(val, str):
                        self.terms[key] = {'translation': val, 'is_regex': False}
                    elif isinstance(val, dict):
                        self.terms[key] = val
                
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
    
    def add_term(self, original: str, translation: str, is_regex: bool = False):
        """Add a term to the glossary."""
        self.terms[original] = {'translation': translation, 'is_regex': is_regex}
        self._build_pattern()
    
    def remove_term(self, original: str):
        """Remove a term from the glossary."""
        self.terms.pop(original, None)
        self._build_pattern()
    
    def _build_pattern(self):
        """Build regex pattern for matching glossary terms."""
        self._pattern = None
        self._regex_rules = []
        
        if not self.terms:
            return
        
        # Split into normal and regex terms
        normal_terms = []
        
        for key, data in self.terms.items():
            if data.get('is_regex'):
                try:
                    flags = 0 if self.case_sensitive else re.IGNORECASE
                    self._regex_rules.append((re.compile(key, flags), data['translation']))
                except re.error as e:
                    logger.error(f"Invalid regex glossary term '{key}': {e}")
            else:
                normal_terms.append(key)
        
        # Build normal pattern
        if normal_terms:
            # Sort by length (longest first)
            normal_terms.sort(key=len, reverse=True)
            escaped = [re.escape(term) for term in normal_terms]
            pattern_str = r'\b(' + '|'.join(escaped) + r')\b'
            flags = 0 if self.case_sensitive else re.IGNORECASE
            self._pattern = re.compile(pattern_str, flags)
    
    def protect_terms(self, text: str) -> Tuple[str, Dict[str, str]]:
        """
        Protect glossary terms in text with placeholders.
        """
        placeholders: Dict[str, str] = {}
        counter = [0]
        protected_text = text

        def get_placeholder(original, translation):
            key = f"〈TERM_{counter[0]}〉"
            placeholders[key] = (original, translation)
            counter[0] += 1
            return key

        # 1. Apply Regex Rules First (Higher priority for patterns like "Potion (S)")
        for pattern, replacement_template in self._regex_rules:
            
            def regex_replacer(match):
                original = match.group(0)
                # Apply template substitution (e.g. \1 for groups)
                try:
                    translation = match.expand(replacement_template)
                except Exception:
                    translation = replacement_template # Fallback
                return get_placeholder(original, translation)
            
            protected_text = pattern.sub(regex_replacer, protected_text)

        # 2. Apply Normal Terms
        if self._pattern:
            def normal_replacer(match):
                original = match.group(0)
                translation = self._get_translation(original)
                return get_placeholder(original, translation)
            
            protected_text = self._pattern.sub(normal_replacer, protected_text)

        return protected_text, placeholders
    
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
            data = self.terms.get(term)
            return data['translation'] if data else term
        
        # Case-insensitive lookup
        term_lower = term.lower()
        term_lower = term.lower()
        for key, val in self.terms.items():
            if key.lower() == term_lower:
                return val['translation']
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

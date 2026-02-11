"""
Note Tag Parser for RPG Maker Note Fields.

RPG Maker note fields (Actor/Enemy/Item/Skill/State/etc.) contain free-form text
that often mixes natural language with custom markup tags used by plugins.

Example note field content:
    <SType: Magic>
    <Element: Fire>
    This is a custom description that should be translated.
    <Custom Death Message>
    %1 has been slain!
    </Custom Death Message>
    <Price: 100>

This parser identifies which parts of note fields are translatable text
and which are structural tags that should be preserved.
"""
import re
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


class NoteTagParser:
    """
    Parser for RPG Maker plugin note tags.
    
    Recognizes common tag formats:
    - Self-closing value tags: <TagName: value>
    - Multi-line block tags: <TagName>\\n...content...\\n</TagName>
    - Single tags: <TagName>
    
    Can extract translatable text from both tag values and free text between tags.
    """
    
    # Common plugin tags that contain translatable text values
    TEXT_VALUE_TAGS = frozenset({
        # VisuStella / Yanfly
        'description', 'help description', 'message',
        'custom death message', 'custom collapse effect',
        'on death', 'on revive', 'on escape',
        'menu text', 'help text', 'info text',
        'display name', 'display text',
        # MOG
        'name', 'title', 'description text',
        # Galv
        'popup text', 'battle text',
    })
    
    # Tags whose values are NOT translatable (numbers, formulas, identifiers)
    SKIP_VALUE_TAGS = frozenset({
        'stype', 'element', 'price', 'hp', 'mp', 'tp', 'atk', 'def',
        'mat', 'mdf', 'agi', 'luk', 'hit', 'eva', 'cri', 'cnt',
        'hrg', 'mrg', 'trg', 'tgr', 'grd', 'rec', 'pha', 'mcr',
        'tcr', 'pdr', 'mdr', 'fdr', 'exr',
        'icon', 'icon index', 'animation', 'animation id',
        'skill', 'skill id', 'state', 'state id',
        'type', 'category', 'target', 'scope',
        'eval', 'custom', 'formula', 'condition',
        'priority', 'speed', 'motion', 'overlay',
        'notetag', 'meta', 'flag', 'trait', 'effect',
        'resistance', 'weakness', 'immunity', 'absorb',
    })
    
    # Regex patterns
    # <TagName: value>
    _VALUE_TAG = re.compile(
        r'<\s*([^<>:]+?)\s*:\s*([^<>]+?)\s*>', re.IGNORECASE
    )
    # <TagName> ... </TagName>  (multiline)
    _BLOCK_TAG = re.compile(
        r'<\s*([^<>/]+?)\s*>(.*?)</\s*\1\s*>', 
        re.IGNORECASE | re.DOTALL
    )
    # <TagName>  (single, self-closing)
    _SINGLE_TAG = re.compile(
        r'<\s*([^<>:]+?)\s*>', re.IGNORECASE
    )
    
    def parse_note(self, note_text: str) -> List[Tuple[str, str, bool]]:
        """
        Parse a note field into segments.
        
        Args:
            note_text: Raw note field content
            
        Returns:
            List of (segment_text, segment_type, is_translatable) tuples.
            segment_type is one of: 'value_tag', 'block_tag', 'single_tag', 'free_text'
        """
        if not note_text or not note_text.strip():
            return []
        
        segments = []
        
        # First pass: find all block tags and their positions
        used_ranges = []
        
        for m in self._BLOCK_TAG.finditer(note_text):
            tag_name = m.group(1).strip()
            content = m.group(2)
            tag_lower = tag_name.lower()
            
            is_text = tag_lower in self.TEXT_VALUE_TAGS
            # If content has natural language (spaces, non-ASCII), likely translatable
            if not is_text and content.strip():
                is_text = self._looks_like_text(content.strip())
            
            segments.append((m.start(), m.end(), tag_name, content.strip(), 
                           'block_tag', is_text))
            used_ranges.append((m.start(), m.end()))
        
        # Second pass: find value tags not inside block tags
        for m in self._VALUE_TAG.finditer(note_text):
            if self._in_ranges(m.start(), used_ranges):
                continue
            
            tag_name = m.group(1).strip()
            value = m.group(2).strip()
            tag_lower = tag_name.lower()
            
            is_text = tag_lower in self.TEXT_VALUE_TAGS
            if not is_text and tag_lower not in self.SKIP_VALUE_TAGS:
                is_text = self._looks_like_text(value)
            
            segments.append((m.start(), m.end(), tag_name, value, 
                           'value_tag', is_text))
            used_ranges.append((m.start(), m.end()))
        
        # Third pass: find single tags
        for m in self._SINGLE_TAG.finditer(note_text):
            if self._in_ranges(m.start(), used_ranges):
                continue
            # Check it's not already matched as value tag
            if any(s <= m.start() < e for s, e in used_ranges):
                continue
            used_ranges.append((m.start(), m.end()))
        
        # Fourth pass: extract free text between tags
        used_ranges.sort()
        pos = 0
        free_texts = []
        for start, end in used_ranges:
            if pos < start:
                text = note_text[pos:start].strip()
                if text:
                    free_texts.append((pos, start, '', text, 'free_text', 
                                      self._looks_like_text(text)))
            pos = end
        if pos < len(note_text):
            text = note_text[pos:].strip()
            if text:
                free_texts.append((pos, len(note_text), '', text, 'free_text',
                                  self._looks_like_text(text)))
        
        segments.extend(free_texts)
        segments.sort(key=lambda x: x[0])
        
        return [(s[3], s[4], s[5]) for s in segments]
    
    def extract_translatable(self, note_text: str) -> List[str]:
        """
        Extract only the translatable text segments from a note field.
        
        Returns:
            List of translatable text strings
        """
        parsed = self.parse_note(note_text)
        return [text for text, seg_type, is_trans in parsed if is_trans and text]
    
    def rebuild_note(self, note_text: str, translations: dict) -> str:
        """
        Rebuild a note field by replacing translatable segments with translations.
        
        Args:
            note_text: Original note field
            translations: Dict mapping original text -> translated text
            
        Returns:
            Note field with translatable parts replaced
        """
        if not translations:
            return note_text
        
        result = note_text
        
        # Replace block tag contents
        for m in self._BLOCK_TAG.finditer(note_text):
            content = m.group(2).strip()
            if content in translations:
                tag_name = m.group(1).strip()
                old = m.group(0)
                new = f'<{tag_name}>\n{translations[content]}\n</{tag_name}>'
                result = result.replace(old, new, 1)
        
        # Replace value tag contents
        for m in self._VALUE_TAG.finditer(note_text):
            value = m.group(2).strip()
            if value in translations:
                tag_name = m.group(1).strip()
                old = m.group(0)
                new = f'<{tag_name}: {translations[value]}>'
                result = result.replace(old, new, 1)
        
        # Replace free text — simple replacement
        for orig, translated in translations.items():
            if orig in result and orig not in [m.group(2).strip() for m in self._BLOCK_TAG.finditer(note_text)]:
                result = result.replace(orig, translated, 1)
        
        return result
    
    def _looks_like_text(self, value: str) -> bool:
        """Check if a value looks like natural language text."""
        if not value:
            return False
        
        # Has spaces -> likely text
        if ' ' in value and len(value) > 3:
            return True
        
        # Has non-ASCII characters -> likely CJK or other translatable text
        if any(ord(c) > 127 for c in value):
            return True
        
        # Contains common text indicators
        if any(c in value for c in '!?.,:;'):
            return len(value) > 2
        
        # Sentence-like pattern
        if value[0].isupper() and len(value) > 5:
            return True
        
        return False
    
    def _in_ranges(self, pos: int, ranges: List[Tuple[int, int]]) -> bool:
        """Check if a position falls within any of the given ranges."""
        return any(s <= pos < e for s, e in ranges)

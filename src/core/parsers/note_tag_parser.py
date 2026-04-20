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
    
    # Common plugin tags that contain translatable text values.
    # Research confirmed (VisuStella/YEP docs): these tags are player-visible in menus/profiles.
    TEXT_VALUE_TAGS = frozenset({
        # VisuStella / Yanfly — confirmed player-visible
        'description', 'help description', 'help', 'message',
        'biography', 'profile', 'actor description', 'character description',
        'custom death message', 'custom collapse effect',
        'on death', 'on revive', 'on escape',
        'menu text', 'help text', 'info text',
        'display name', 'display text',
        'quest name', 'quest title', 'quest objective', 'quest description',
        'quest reward', 'objective text', 'reward text', 'summary',
        'trait description', 'flavor text', 'lore',
        # MOG
        'name', 'title', 'description text',
        # Galv
        'popup text', 'battle text',
    })

    # Tag name KEYWORDS that indicate a code/script block — never translate content.
    # Research confirmed (VisuStella/YEP docs): these contain JS/Ruby code.
    CODE_BLOCK_TAG_KEYWORDS = frozenset({
        'eval', 'js', 'script', 'code', 'formula',
        'custom apply effect', 'custom damage effect', 'custom execute effect',
        'custom failure condition', 'custom confirm effect', 'custom regenerate effect',
        'custom action end effect', 'custom turn end effect', 'custom battle end effect',
        'custom requirement', 'custom condition', 'custom cost',
        'custom show eval', 'custom enable eval', 'custom trigger eval',
        'apply effect', 'execute effect', 'action sequence',
        'action end', 'turn end', 'battle end', 'phase start', 'phase end',
        'pre-damage', 'post-damage', 'pre-apply', 'post-apply',
        'on erased', 'on expire',
    })

    # Tag name SUBSTRINGS that strongly indicate a non-translatable technical block.
    # Keep only unambiguous code indicators — broad words like 'custom', 'effect',
    # 'action', 'condition' are intentionally excluded to avoid FP on player-visible
    # tags like <Custom Death Message> or <Action Text>.
    # Specific compound tags that use these words are handled by CODE_BLOCK_TAG_KEYWORDS.
    _CODE_TAG_SUBWORDS = frozenset({
        'eval', 'js', 'script', 'formula', 'sequence',
    })

    # Tags whose VALUES are NOT translatable (numbers, formulas, identifiers)
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
        # FP-19: Additional RPG Maker plugin parameter identifiers (never player-visible)
        'param', 'xparam', 'sparam',         # stat parameter identifiers
        'learn', 'cost', 'buff', 'debuff',   # skill/state mechanics
        'level', 'class', 'equip',           # DB reference identifiers
        'passive state', 'require',          # passive/requirement tags
        'trigger', 'map id', 'region id', 'terrain tag',  # spatial/event identifiers
        'bypass', 'stencil',                 # rendering flags
        'switch', 'variable', 'timer',       # control flow
        'mode', 'blend', 'opacity',          # visual config
        'x', 'y', 'z', 'angle', 'scale', 'zoom',  # transform params
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
    
    def _is_code_block_tag(self, tag_lower: str) -> bool:
        """Return True when a tag name indicates JS/Ruby code content (never translatable).

        Research confirmed (VisuStella/YEP docs): tag names matching these patterns
        always contain script code that must not be sent to a translation engine.
        """
        if tag_lower in self.CODE_BLOCK_TAG_KEYWORDS:
            return True
        # Check if any code subword appears as a whole word or prefix within the tag name
        for subword in self._CODE_TAG_SUBWORDS:
            if subword in tag_lower:
                return True
        return False

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
            
            # Code block tags MUST never be translated regardless of content
            if self._is_code_block_tag(tag_lower):
                segments.append((m.start(), m.end(), tag_name, content.strip(),
                                  'block_tag', False))
                used_ranges.append((m.start(), m.end()))
                continue

            is_text = tag_lower in self.TEXT_VALUE_TAGS
            # If content has natural language (spaces, non-ASCII), likely translatable
            if not is_text and content.strip():
                is_text = self._looks_like_text(content.strip())
            if is_text and self._is_technical_value(content.strip()):
                is_text = False
            
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
                # FP-18: value-tag context is stricter than free-text context
                is_text = self._looks_like_text(value, in_value_tag=True)
            if is_text and self._is_technical_value(value):
                is_text = False
            
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
                                      self._looks_like_text(text) and not self._is_technical_value(text)))
            pos = end
        if pos < len(note_text):
            text = note_text[pos:].strip()
            if text:
                free_texts.append((pos, len(note_text), '', text, 'free_text',
                                  self._looks_like_text(text) and not self._is_technical_value(text)))
        
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
        
        # Replace free text — use original note_text to identify safe positions,
        # then apply to result. Guard: skip any orig that is already a tag content
        # to avoid double-replacing. Operate on result using the original positions
        # shifted by already-applied delta to avoid corrupting translated content.
        block_tag_contents = {m.group(2).strip() for m in self._BLOCK_TAG.finditer(note_text)}
        value_tag_contents = {m.group(2).strip() for m in self._VALUE_TAG.finditer(note_text)}
        tag_contents = block_tag_contents | value_tag_contents
        
        for orig, translated in translations.items():
            # Skip if this orig was a tag content (already handled above)
            if orig in tag_contents:
                continue
            # Only replace if orig appears in the ORIGINAL note text (position anchor)
            if orig not in note_text:
                continue
            # Apply to result — safe because orig is free text, not injected by
            # earlier replacements (tag replacements change the entire tag span
            # including delimiters, not just the inner text)
            result = result.replace(orig, translated, 1)
        
        return result
    
    def _looks_like_text(self, value: str, in_value_tag: bool = False) -> bool:
        """Check if a value looks like natural language text.

        Args:
            value: The string to examine.
            in_value_tag: True when the value comes from a ``<Tag: value>`` context.
                Value-tag content is far more likely to be a technical identifier
                (scope enum, stat name, numeric ID) than free text, so stricter
                rules apply.
        """
        if not value:
            return False
        
        # Has non-ASCII characters → likely CJK or other translatable text
        if any(ord(c) > 127 for c in value):
            return True

        # In value-tag context apply stricter heuristics (FP-18):
        # many spaced values are engine enums ("One Ally", "Battle Start", etc.)
        if in_value_tag:
            # Must have at least 2 words AND length > 8 AND contain common text markers
            # to be considered natural language text in a value tag.
            if ' ' in value:
                words = value.split()
                # 2-word combos are often enum strings ("One Ally", "All Enemies") → skip
                if len(words) <= 2:
                    # Only accept if it has punctuation or looks like a sentence
                    if not any(c in value for c in '!?.,:;') and not value[0].isupper():
                        return False
                    # Even with uppercase, 2-word all-ASCII combos are risky
                    _lower = value.strip().lower()
                    _SCOPE_LIKE = frozenset({
                        'one enemy', 'all enemies', 'one ally', 'all allies',
                        'one random enemy', 'the user', 'all party members',
                        'battle start', 'map start', 'common event',
                        'action button', 'player touch', 'event touch',
                        'slow start', 'slow end', 'normal mode', 'hard mode',
                        'easy mode', 'hp rate', 'mp rate', 'tp rate',
                        'gauge color', 'window skin', 'screen x', 'screen y',
                    })
                    if any(s in _lower for s in _SCOPE_LIKE):
                        return False
                # 3+ words with uppercase start → likely natural text
                if len(words) >= 3 and value[0].isupper():
                    return True
                if len(words) >= 3:
                    return True
            # No spaces in value-tag: only accept if clearly text-like (punctuation/length)
            if any(c in value for c in '!?.,:;'):
                return len(value) > 4
            # Sentence-like pattern in value-tag requires more length
            if value[0].isupper() and len(value) > 10:
                return True
            return False

        # Standard (free-text / block-tag) context: original rules
        # Has spaces → likely text
        if ' ' in value and len(value) > 3:
            return True
        
        # Contains common text indicators
        if any(c in value for c in '!?.,:;'):
            return len(value) > 2
        
        # Sentence-like pattern
        if value[0].isupper() and len(value) > 5:
            return True
        
        return False

    def _is_technical_value(self, value: str) -> bool:
        """Return True when a note value looks like an identifier, path, asset, or JS code."""
        if not isinstance(value, str):
            return True

        stripped = value.strip().strip('"\'')
        if not stripped:
            return True

        lower = stripped.lower()
        if lower in {"true", "false", "null", "undefined", "on", "off", "yes", "no"}:
            return True

        if stripped.isdigit():
            return True

        if re.fullmatch(r"0x[0-9a-fA-F]+", stripped):
            return True

        if ('/' in stripped or '\\' in stripped) and ' ' not in stripped:
            return True

        if any(lower.endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ogg', '.wav', '.mp3', '.m4a', '.json', '.js')):
            return True

        # Underscored identifiers: block code-like patterns but not display names.
        # Block: UPPER_SNAKE (SKILL_TYPE), PascalCase_ID (Quest_01), digit-containing (item_3).
        # Allow: simple "Flame_Sword" (two+ alphabetic segments, no digits).
        if '_' in stripped and ' ' not in stripped:
            # Has digits → almost certainly a technical ID (Quest_01, item_3, bgm_001)
            if any(c.isdigit() for c in stripped):
                return True
            # UPPER_SNAKE_CASE (SKILL_TYPE_MAGIC)
            if re.fullmatch(r'[A-Z][A-Z0-9_]+', stripped):
                return True

        if len(stripped) <= 2 and stripped.isascii():
            return True

        # FP-21: Known RPG Maker state / element / status identifiers.
        # These are single capitalized words that match standard RPG state names.
        # e.g. "Poison", "Paralyze", "Blind", "Fire", "Ice" — used as DB references,
        # not as player-visible text (the actual display name is in the DB 'name' field).
        _KNOWN_RPGM_IDENTIFIERS: frozenset[str] = frozenset({
            'poison', 'paralyze', 'silence', 'blind', 'confusion', 'berserk',
            'sleep', 'stop', 'zombie', 'petrify', 'stone', 'freeze', 'burn',
            'stun', 'slow', 'haste', 'regen', 'mute',
            'fire', 'ice', 'thunder', 'water', 'wind', 'earth', 'light', 'dark',
            'holy', 'shadow', 'lightning', 'nature', 'magic', 'physical', 'neutral',
            'absorb', 'immunity', 'weakness', 'resistance', 'normal',
        })
        if stripped.lower() in _KNOWN_RPGM_IDENTIFIERS:
            return True

        # Structured config block: if majority of non-empty lines look like
        # "Key: simple_value" pairs (e.g. "Speed: 15", "Rate Y: 0.008", "HP Link: On"),
        # treat as technical plugin configuration, not translatable text.
        # This prevents false positives on block tags like <Visual Breathing Effect>
        # whose inner content is parameter data, not natural language.
        if '\n' in stripped:
            _kv_pattern = re.compile(r'^\s*[\w][\w\s]*:\s*[\d\w.%+-]+\s*$')
            non_empty_lines = [l for l in stripped.splitlines() if l.strip()]
            if non_empty_lines:
                kv_count = sum(1 for l in non_empty_lines if _kv_pattern.match(l))
                if kv_count / len(non_empty_lines) >= 0.6:
                    return True

        # JS/Ruby code detection for block content.
        # Research confirmed: VisuStella custom effect blocks contain JS code with these patterns.
        # Check per-line to handle multi-line code blocks.
        lines = stripped.splitlines()
        code_line_count = 0
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            # JS keywords at line start
            if re.match(r'^(if\s*\(|else\s*\{|for\s*\(|while\s*\(|return\s|var\s|let\s|const\s|function\s|this\.|new\s)', line_stripped):
                code_line_count += 1
            # Line ends with semicolon or brace — strong JS indicator
            elif line_stripped.endswith((';', '{', '}')):
                code_line_count += 1
            # Method call pattern: word.method( or word.property.method(
            elif re.search(r'\w+\.\w+\s*\(', line_stripped):
                code_line_count += 1
            # RPG Maker JS globals
            elif any(kw in line_stripped for kw in ('$game', '$data', 'Game_', 'Scene_', 'Window_', 'BattleManager', 'SceneManager')):
                code_line_count += 1

        # If majority of non-empty lines look like code, treat as technical
        non_empty = sum(1 for l in lines if l.strip())
        if non_empty > 0 and code_line_count / non_empty >= 0.5:
            return True

        return False
    
    def _in_ranges(self, pos: int, ranges: List[Tuple[int, int]]) -> bool:
        """Check if a position falls within any of the given ranges."""
        return any(s <= pos < e for s, e in ranges)

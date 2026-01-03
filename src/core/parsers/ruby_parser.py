"""
Ruby Parser for RPG Maker XP/VX/VX Ace games.
Handles extraction and injection of translatable text from .rvdata2 and .rxdata files.
Uses rubymarshal library for reading/writing Ruby Marshal format.
"""
import rubymarshal.reader
import rubymarshal.writer
import rubymarshal.classes
from typing import List, Tuple, Dict, Any, Set
from .base import BaseParser
import logging

logger = logging.getLogger(__name__)


class RubyParser(BaseParser):
    """
    Parser for RPG Maker XP/VX/VX Ace binary data files.
    Supports: .rvdata2 (VX Ace), .rxdata (XP), .rvdata (VX)
    """
    
    # Event command codes (same across RPG Maker versions with minor variations)
    TEXT_EVENT_CODES = {
        101: 'show_text_header',    # Show Text (settings)
        401: 'show_text',           # Show Text line
        102: 'show_choices',        # Show Choices
        402: 'choice_when',         # When [Choice]
        405: 'scroll_text',         # Scroll Text line
        108: 'comment',             # Comment
        408: 'comment_cont',        # Comment continuation
        320: 'change_name',         # Change Actor Name
        324: 'change_nickname',     # Change Actor Nickname (VX Ace)
        355: 'script_single',       # Script
        655: 'script_line',         # Script continuation
    }
    
    # Attribute names in Ruby objects that contain translatable text
    TRANSLATABLE_ATTRS = {
        'name', 'description', 'nickname', 'profile',
        'message1', 'message2', 'message3', 'message4',
    }
    
    # System data keys to translate
    SYSTEM_KEYS = {
        'words', 'terms', 'game_title', 'currency_unit',
    }
    
    def __init__(self, translate_notes: bool = False, translate_comments: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.translate_notes = translate_notes
        self.translate_comments = translate_comments
        self.extracted: List[Tuple[str, str]] = []
        self.visited: Set[int] = set()
    
    def extract_text(self, file_path: str) -> List[Tuple[str, str]]:
        """
        Extract all translatable text from a Ruby Marshal file.
        
        Returns:
            List of (path, text) tuples
        """
        with open(file_path, 'rb') as f:
            try:
                data = rubymarshal.reader.load(f)
            except Exception as e:
                logger.error(f"Failed to load {file_path}: {e}")
                return []
        
        self.extracted = []
        self.visited = set()
        self._walk(data, "")
        return self.extracted

    def _walk(self, obj: Any, path: str):
        """Recursively walk Ruby objects to find translatable text."""
        obj_id = id(obj)
        if obj_id in self.visited:
            return
        self.visited.add(obj_id)

        if isinstance(obj, str):
            # Strings are handled in _check_and_walk with context
            pass
        
        elif isinstance(obj, bytes):
            # Ruby strings might be bytes, try to decode
            try:
                text = obj.decode('utf-8')
                # Will be handled in _check_and_walk
            except UnicodeDecodeError:
                pass
        
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                self._check_and_walk(item, f"{path}.{i}" if path else str(i))
        
        elif isinstance(obj, dict):
            for k, v in obj.items():
                key_name = str(k) if not isinstance(k, (str, bytes)) else k
                if isinstance(key_name, bytes):
                    key_name = key_name.decode('utf-8', errors='replace')
                self._check_and_walk(v, f"{path}.{key_name}" if path else str(key_name), key_name=key_name)
        
        elif hasattr(obj, 'attributes'):
            # rubymarshal RubyObject
            attrs = getattr(obj, 'attributes', {})
            
            # Heuristic for sound objects (BGM, BGS, ME, SE)
            is_sound_obj = all(k in attrs for k in ['@name', '@volume', '@pitch'])
            
            for k, v in attrs.items():
                key_name = str(k) if not isinstance(k, (str, bytes)) else k
                if isinstance(key_name, bytes):
                    key_name = key_name.decode('utf-8', errors='replace')
                
                # Skip name in sound objects
                if is_sound_obj and key_name == '@name':
                    continue
                    
                # Remove leading @ from Ruby instance variable names
                display_key = key_name.lstrip('@') if isinstance(key_name, str) else key_name
                self._check_and_walk(v, f"{path}.@{display_key}" if path else f"@{display_key}", key_name=display_key)
        
        elif hasattr(obj, '__dict__'):
            for k, v in obj.__dict__.items():
                if not k.startswith('_'):
                    self._check_and_walk(v, f"{path}.{k}" if path else str(k), key_name=k)

    def _check_and_walk(self, val: Any, path: str, key_name: str = None):
        """Check if value should be extracted, then continue walking."""
        # Convert bytes to string if needed
        text_val = val
        if isinstance(val, bytes):
            try:
                text_val = val.decode('utf-8')
            except UnicodeDecodeError:
                text_val = None
        
        if isinstance(text_val, str):
            # Check if this is a translatable field
            if key_name and (key_name in self.TRANSLATABLE_ATTRS or key_name == '@name'):
                if key_name == '@note' and not self.translate_notes:
                    return
                if self.is_safe_to_translate(text_val, is_dialogue=(key_name != '@note')):
                    self.extracted.append((path, text_val))
            
            # Check system keys
            elif key_name and key_name in self.SYSTEM_KEYS:
                if self.is_safe_to_translate(text_val, is_dialogue=True):
                    self.extracted.append((path, text_val))
        
        # Check for EventCommand objects (RPG::EventCommand in Ruby)
        elif hasattr(val, 'attributes'):
            attrs = getattr(val, 'attributes', {})
            
            # Normalize attribute access (handle @code vs code)
            def get_attr(name):
                return attrs.get(name) or attrs.get(f'@{name}') or attrs.get(name.lstrip('@'))
            
            code = get_attr('code')
            params = get_attr('parameters')
            
            if code is not None and params is not None:
                self._extract_event_command(code, params, path)
            
            self._walk(val, path)
        else:
            self._walk(val, path)

    def _extract_event_command(self, code: int, params: list, path: str):
        """Extract translatable text from an event command."""
        if not isinstance(code, int) or not isinstance(params, list):
            return
        
        if code not in self.TEXT_EVENT_CODES:
            return
        
        # Show Text (401) / Scroll Text (405)
        if code in [401, 405]:
            if len(params) > 0:
                text = self._to_string(params[0])
                if self.is_safe_to_translate(text, is_dialogue=True):
                    self.extracted.append((f"{path}.@parameters.0", text))
        
        # Show Choices (102)
        elif code == 102:
            if len(params) > 0 and isinstance(params[0], list):
                for i, choice in enumerate(params[0]):
                    text = self._to_string(choice)
                    if self.is_safe_to_translate(text, is_dialogue=True):
                        self.extracted.append((f"{path}.@parameters.0.{i}", text))
        
        # Comment (108/408)
        elif code in [108, 408] and self.translate_comments:
            if len(params) > 0:
                text = self._to_string(params[0])
                if self.is_safe_to_translate(text, is_dialogue=True):
                    # Filter out pure code comments
                    if ' ' in text or len(text) > 15:
                        self.extracted.append((f"{path}.@parameters.0", text))
        
        elif code in [320, 324]:
            if len(params) > 1:
                text = self._to_string(params[1])
                if self.is_safe_to_translate(text, is_dialogue=True):
                    self.extracted.append((f"{path}.@parameters.1", text))

    def _to_string(self, val: Any) -> str:
        """Convert a value to string, handling bytes and common encodings."""
        if isinstance(val, str):
            return val
        elif isinstance(val, bytes):
            for encoding in ['utf-8', 'shift_jis', 'latin-1']:
                try:
                    return val.decode(encoding)
                except UnicodeDecodeError:
                    continue
            return val.decode('utf-8', errors='replace')
        return None

    def apply_translation(self, file_path: str, translations: Dict[str, str]) -> Any:
        """
        Apply translations back to the Ruby Marshal file.
        
        Args:
            file_path: Path to the original file
            translations: Dict mapping path -> translated_text
            
        Returns:
            Modified data object
        """
        with open(file_path, 'rb') as f:
            data = rubymarshal.reader.load(f)
        
        applied_count = 0
        failed_paths = []
        
        for path, text in translations.items():
            if not text:
                continue
            
            keys = path.split('.')
            ref = data
            
            try:
                for i, k in enumerate(keys[:-1]):
                    ref = self._traverse_key(ref, k)
                
                # Set last key
                last = keys[-1]
                self._set_value(ref, last, text)
                applied_count += 1
                
            except Exception as e:
                failed_paths.append(path)
        
        if failed_paths:
            logger.warning(f"Failed to apply {len(failed_paths)} translations")
        
        return data

    def _traverse_key(self, ref: Any, key: str) -> Any:
        """Traverse to a key in the object structure."""
        # Handle numeric indices
        if key.isdigit():
            return ref[int(key)]
        
        # Handle Ruby attribute notation (@name)
        if key.startswith('@'):
            attr_name = key[1:]
            if isinstance(ref, dict):
                return ref.get(attr_name) or ref.get(key)
            elif hasattr(ref, 'attributes'):
                attrs = ref.attributes
                return attrs.get(attr_name) or attrs.get(key)
        
        # Regular dict/list access
        if isinstance(ref, dict):
            return ref[key]
        elif isinstance(ref, list):
            return ref[int(key)]
        elif hasattr(ref, 'attributes'):
            return ref.attributes.get(key)
        else:
            return getattr(ref, key)

    def _set_value(self, ref: Any, key: str, value: str):
        """Set a value in the object structure."""
        # Determine if we need to encode to bytes (for Ruby string compatibility)
        final_value = value
        
        # Handle numeric indices
        if key.isdigit():
            idx = int(key)
            # Check if original was bytes
            if isinstance(ref[idx], bytes):
                final_value = value.encode('utf-8')
            ref[idx] = final_value
            return
        
        # Handle Ruby attribute notation
        if key.startswith('@'):
            attr_name = key[1:]
            if isinstance(ref, dict):
                orig_key = attr_name if attr_name in ref else key
                if isinstance(ref.get(orig_key), bytes):
                    final_value = value.encode('utf-8')
                ref[orig_key] = final_value
            elif hasattr(ref, 'attributes'):
                attrs = ref.attributes
                orig_key = attr_name if attr_name in attrs else key
                if isinstance(attrs.get(orig_key), bytes):
                    final_value = value.encode('utf-8')
                attrs[orig_key] = final_value
            return
        
        # Regular access
        if isinstance(ref, dict):
            if isinstance(ref.get(key), bytes):
                final_value = value.encode('utf-8')
            ref[key] = final_value
        elif isinstance(ref, list):
            idx = int(key)
            if isinstance(ref[idx], bytes):
                final_value = value.encode('utf-8')
            ref[idx] = final_value
        elif hasattr(ref, 'attributes'):
            attrs = ref.attributes
            if isinstance(attrs.get(key), bytes):
                final_value = value.encode('utf-8')
            attrs[key] = final_value
        else:
            setattr(ref, key, final_value)

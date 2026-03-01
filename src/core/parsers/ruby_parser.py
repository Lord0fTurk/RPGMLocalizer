import rubymarshal.reader
import rubymarshal.writer
import rubymarshal.classes
from typing import List, Tuple, Dict, Any, Set
from .base import BaseParser
import logging
import zlib
import re
from src.core.constants import (TRANSLATOR_RECURSION_MAX_DEPTH, 
                                RUBY_ENCODING_FALLBACK_LIST, 
                                RUBY_KEY_ENCODING_FALLBACK_LIST)

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
        105: 'scroll_text_header',  # Scroll Text header
        405: 'scroll_text',         # Scroll Text line
        108: 'comment',             # Comment
        408: 'comment_cont',        # Comment continuation
        320: 'change_name',         # Change Actor Name
        324: 'change_nickname',     # Change Actor Nickname (VX Ace)
        325: 'change_profile',      # Change Actor Profile
        355: 'script_single',       # Script
        655: 'script_line',         # Script continuation
    }
    
    # Attribute names in Ruby objects that contain translatable text
    TRANSLATABLE_ATTRS = {
        'name', 'description', 'nickname', 'profile',
        'message1', 'message2', 'message3', 'message4',
        'help', 'title', 'display_name', 'text', 'msg', 'message',
        'game_title', 'currency_unit'
    }
    
    # System data keys to translate
    SYSTEM_KEYS = {
        'words', 'terms', 'game_title', 'currency_unit',
    }

    # Heuristics for skipping non-translatable text in scripts
    SKIP_PATTERNS = [
        r'^[a-zA-Z0-9_]+$',  # Variable names
        r'\.png$', r'\.jpg$', r'\.ogg$', r'\.wav$', r'\.mp3$',  # Files
        r'^Basic \d+$',  # Internal basic labels
        r'^[A-Z][A-Z0-9_]*$',  # CONSTANTS
    ]
    
    def __init__(self, translate_notes: bool = False, translate_comments: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.translate_notes = translate_notes
        self.translate_comments = translate_comments
        self.extracted: List[Tuple[str, str, str]] = []
        self.visited: Set[int] = set()
        self.MAX_RECURSION_DEPTH = TRANSLATOR_RECURSION_MAX_DEPTH
    
    def extract_text(self, file_path: str) -> List[Tuple[str, str, str]]:
        """
        Extract all translatable text from a Ruby Marshal file.
        
        Returns:
            List of (path, text, context_tag) tuples
        """
        with open(file_path, 'rb') as f:
            try:
                data = rubymarshal.reader.load(f)
            except Exception as e:
                logger.error(f"Failed to load {file_path}: {e}")
                return []
        
        self.extracted = []
        self.visited = set()
        self._walk(data, "", 0)
        return self.extracted

    def _walk(self, obj: Any, path: str, depth: int):
        """Recursively walk Ruby objects to find translatable text."""
        if depth > self.MAX_RECURSION_DEPTH:
            return

        obj_id = id(obj)
        if obj_id in self.visited:
            return
        self.visited.add(obj_id)

        if isinstance(obj, str):
            # Strings are handled in _check_and_walk with context
            pass
        
        elif isinstance(obj, bytes):
            # Ruby strings might be bytes, try to decode with fallback encodings
            # XP/VX games often use Shift-JIS or Windows-1252
            text = None
            for enc in RUBY_ENCODING_FALLBACK_LIST:
                try:
                    text = obj.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            
            # Not calling _check_and_walk directly for bytes to avoid double processing loop
            # Check context validity only if decoding succeeded
            pass
        
        elif isinstance(obj, list):
            # Check if this looks like the Scripts.rvdata2 array
            # Format: [[id, name, compressed_code], ...]
            if len(obj) > 0 and len(obj[0]) == 3 and isinstance(obj[0][2], bytes) and path == "":
                self._process_scripts_array(obj)
                return

            for i, item in enumerate(obj):
                self._check_and_walk(item, f"{path}.{i}" if path else str(i))
        
        elif isinstance(obj, dict):
            for k, v in obj.items():
                key_name = str(k) if not isinstance(k, (str, bytes)) else k
                if isinstance(key_name, bytes):
                    # Try to decode key name with fallback
                    for enc in RUBY_KEY_ENCODING_FALLBACK_LIST:
                        try:
                            key_name = key_name.decode(enc)
                            break
                        except UnicodeDecodeError:
                            continue
                    else:
                        # All encodings failed, use replace mode
                        key_name = key_name.decode('utf-8', errors='replace')
                        
                self._check_and_walk(v, f"{path}.{key_name}" if path else str(key_name), depth + 1, key_name=key_name)


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
                self._check_and_walk(v, f"{path}.@{display_key}" if path else f"@{display_key}", depth + 1, key_name=display_key)
        
        elif hasattr(obj, '__dict__'):
            for k, v in obj.__dict__.items():
                if not k.startswith('_'):
                    self._check_and_walk(v, f"{path}.{k}" if path else str(k), depth + 1, key_name=k)

    def _process_scripts_array(self, scripts: list):
        """Process the special Scripts.rvdata2 array structure."""
        logger.info("Detected Scripts.rvdata2 structure. Extracting strings from ruby code...")
        for i, entry in enumerate(scripts):
            if len(entry) < 3:
                continue
                
            script_id = entry[0]
            script_name = self._to_string(entry[1])
            compressed_code = entry[2]
            
            if not isinstance(compressed_code, bytes):
                continue
                
            try:
                # 1. Decompress
                code_bytes = zlib.decompress(compressed_code)
                
                # 2. Decode - Use robust encoding detection for older RPG Maker versions
                code_text = None
                encodings = ['utf-8', 'shift_jis', 'cp1252', 'latin-1']
                for enc in encodings:
                    try:
                        code_text = code_bytes.decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue
                
                if code_text is None:
                    code_text = code_bytes.decode('utf-8', errors='ignore')
                
                # 3. Extract strings from code
                self._extract_from_code(code_text, f"{i}.code")
                
            except Exception as e:
                logger.warning(f"Failed to process script {i} ({script_name}): {e}")

    def _extract_from_code(self, code: str, path_prefix: str):
        """Extract valid strings from raw Ruby code using a tokenizer."""
        # Use valid string tokens
        tokens = self._tokenize_ruby_script(code)
        
        seen_strings = set()
        
        for idx, (start, end, text, quote_char) in enumerate(tokens):
            if text in seen_strings:
                continue
            
            # Use the same validation logic
            if self._is_valid_script_string(text):
                self.extracted.append((f"{path_prefix}.string_{idx}", text, "script"))
                seen_strings.add(text)

    def _extract_from_code_deprecated(self, code: str, path_prefix: str):
        """Extract valid strings from raw Ruby code using heuristics."""
        # Find single or double quoted strings
        # This is a basic regex, could benefit from a proper tokenizer but that's complex
        # We look for "..." or '...'
        matches = re.finditer(r'(["\'])(.*?)\1', code)
        
        seen_strings = set()
        
        for idx, match in enumerate(matches):
            text = match.group(2)
            
            if text in seen_strings:
                continue
                
            if not text or len(text) < 2:
                continue
                
            # --- Heuristics to Skip Garbage ---
            
            # 1. Skip if only ASCII letters/numbers/underscore (likely variable/func name)
            if re.match(r'^[a-zA-Z0-9_]+$', text):
                continue
                
            # 2. Skip standard file extensions
            if any(text.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.bmp', '.ogg', '.wav', '.mp3', '.rvdata2']):
                continue
                
            # 3. Skip symbols starting with : (though regex usually won't catch simple :sys unless quoted)
            if text.startswith(':'):
                continue

            # 4. Filter strictly: Must contain at least one space OR one non-ascii char
            # This avoids simple keywords but keeps "Game Over" or "ゲーム"
            has_space = ' ' in text
            has_non_ascii = any(ord(c) > 127 for c in text)
            
            if not (has_space or has_non_ascii):
                # If it's single word ascii, it's likely a technical string
                continue
                
            # 5. Check explicitly for Vocab-like usage or things that look like messages
            # (We accept it if it passed step 4)
            
            self.extracted.append((f"{path_prefix}.string_{idx}", text, "script"))
            seen_strings.add(text)

    def _check_and_walk(self, val: Any, path: str, depth: int, key_name: str = None):
        """Check if value should be extracted, then continue walking."""
        if depth > self.MAX_RECURSION_DEPTH:
            return
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
                    context_tag = "dialogue_block" if key_name in ['@message1', '@message2', '@message3', '@message4', '@description', '@help'] else "name"
                    if key_name in ['@name', '@nickname', '@title', '@game_title', '@currency_unit']:
                        context_tag = "name"
                    self.extracted.append((path, text_val, context_tag))
            
            # Check system keys
            elif key_name and key_name in self.SYSTEM_KEYS:
                if self.is_safe_to_translate(text_val, is_dialogue=True):
                    self.extracted.append((path, text_val, "system"))
        
        # Check for EventCommand objects (RPG::EventCommand in Ruby)
        elif hasattr(val, 'attributes'):
            attrs = getattr(val, 'attributes', {})
            
            # Normalize attribute access (handle @code vs code, bytes vs str)
            def get_attr(name):
                # rubymarshal keys can be bytes (symbols) or strings
                possibilities = [
                    name, f"@{name}", name.encode('utf-8'), f"@{name}".encode('utf-8')
                ]
                for p in possibilities:
                    if p in attrs:
                        return attrs[p]
                return None
            
            code = get_attr('code')
            params = get_attr('parameters')
            
            if code is not None and params is not None:
                self._extract_event_command(code, params, path)
            
            # CRITICAL: Do NOT recurse into Event Commands.
            # Only whitelisted codes handled in _extract_event_command should be processed.
            # Recursing blindly into generic attributes causes over-extraction of technical data.
            return
        else:
            self._walk(val, path, depth + 1)

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
                    self.extracted.append((f"{path}.@parameters.0", text, "message_dialogue"))
        
        # Show Choices (102)
        elif code == 102:
            if len(params) > 0 and isinstance(params[0], list):
                for i, choice in enumerate(params[0]):
                    text = self._to_string(choice)
                    if self.is_safe_to_translate(text, is_dialogue=True):
                        self.extracted.append((f"{path}.@parameters.0.{i}", text, "choice"))
        
        # Comment (108/408)
        elif code in [108, 408] and self.translate_comments:
            if len(params) > 0:
                text = self._to_string(params[0])
                if self.is_safe_to_translate(text, is_dialogue=True):
                    # Filter out pure code comments
                    if ' ' in text or len(text) > 15:
                        self.extracted.append((f"{path}.@parameters.0", text, "comment"))
        
        elif code in [320, 324]:
            if len(params) > 1:
                text = self._to_string(params[1])
                if self.is_safe_to_translate(text, is_dialogue=True):
                    self.extracted.append((f"{path}.@parameters.1", text, "name"))
        
        # Change Profile (325)
        elif code == 325:
            if len(params) > 1:
                text = self._to_string(params[1])
                if self.is_safe_to_translate(text, is_dialogue=True):
                    self.extracted.append((f"{path}.@parameters.1", text, "name"))
        
        # Show Choices (102)
        elif code == 102:
            if len(params) > 0 and isinstance(params[0], (list, tuple)):
                for i, choice in enumerate(params[0]):
                    text = self._to_string(choice)
                    if self.is_safe_to_translate(text, is_dialogue=True):
                        self.extracted.append((f"{path}.@parameters.0.{i}", text, "choice"))

    def _to_string(self, val: Any) -> str:
        """Convert a value to string, handling bytes and common encodings."""
        if isinstance(val, str):
            return val
        elif isinstance(val, bytes):
            # Try Shift-JIS first for higher accuracy in RPG Maker files (XP/VX/Ace)
            encodings = ['shift_jis', 'utf-8', 'euc-jp', 'latin-1']
            for encoding in encodings:
                try:
                    return val.decode(encoding)
                except (UnicodeDecodeError, LookupError):
                    continue
            return val.decode('utf-8', errors='replace')
        return None

    def apply_translation(self, file_path: str, translations: Dict[str, str]) -> Any:
        """
        Apply translations back to the Ruby Marshal file.
        """
        with open(file_path, 'rb') as f:
            data = rubymarshal.reader.load(f)
        
        applied_count = 0
        failed_paths = []
        
        # Check if this is a scripts file
        is_scripts = isinstance(data, list) and len(data) > 0 and len(data[0]) == 3 and isinstance(data[0][2], bytes)
        
        if is_scripts:
            # We need to perform a different application strategy for scripts
            data = self._apply_scripts_translation(data, translations)
            return data
            
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

    def _apply_scripts_translation(self, scripts: list, translations: Dict[str, str]) -> list:
        """Apply translations to the scripts array (re-compressing)."""
        # Group translations by script index
        script_trans = {}
        for path, text in translations.items():
            if ".code.string_" in path:
                # format: {index}.code.string_{match_idx}
                parts = path.split('.')
                idx = int(parts[0])
                if idx not in script_trans:
                    script_trans[idx] = []
                script_trans[idx].append((path, text))
        
        for idx in script_trans:
            if idx >= len(scripts):
                continue
                
            entry = scripts[idx]
            compressed_code = entry[2]
            
            try:
                # 1. Decompress
                code_bytes = zlib.decompress(compressed_code)
                code_text = code_bytes.decode('utf-8')
                
                # 2. Replace Strings
                # This is tricky because indices change if we just replace.
                # But since we use simple string replacement on the whole code block,
                # duplicate strings might be an issue.
                # Ideally we should reconstruct, but for now we'll do search/replace
                # based on unique context if possible, or just exact match replace.
                
                # BETTER APPROACH:
                # Iterate matches again to find locations, then apply replacements in reverse order
                # to keep indices valid.
                
                # Find all string tokens to locate them
                tokens = self._tokenize_ruby_script(code_text)
                
                replacements = [] # (start, end, new_text)
                
                for path, new_text in script_trans[idx]:
                    match_idx = int(path.split('_')[-1])
                    if match_idx < len(tokens):
                        start, end, _content, qs = tokens[match_idx]
                        
                        # Properly escape for Ruby strings:
                        # 1. Escape existing backslashes first
                        # 2. Then escape the quote character itself
                        escaped_text = new_text.replace('\\', '\\\\')
                        escaped_text = escaped_text.replace(qs, '\\' + qs)
                        replacement = f"{qs}{escaped_text}{qs}"
                        replacements.append((start, end, replacement))
                
                # Apply in reverse order
                replacements.sort(key=lambda x: x[0], reverse=True)
                
                new_code_list = list(code_text)
                for start, end, rep_text in replacements:
                    new_code_list[start:end] = list(rep_text)
                    
                new_code_text = "".join(new_code_list)
                
                # 3. Compress
                new_bytes = zlib.compress(new_code_text.encode('utf-8'))
                
                # 4. Update entry
                # Entry is [id, name, compressed_code]
                # We need to modify the list in place
                scripts[idx][2] = new_bytes
                
            except Exception as e:
                logger.error(f"Failed to apply translations to script {idx}: {e}")
                
        return scripts

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
                # Try all combinations: string, @string, bytes, @bytes
                for k in [attr_name, key, attr_name.encode('utf-8'), key.encode('utf-8')]:
                    if k in attrs: return attrs[k]
                return None
        
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
                # Determine original key type (bytes vs str)
                orig_key = None
                for k in [attr_name, key, attr_name.encode('utf-8'), key.encode('utf-8')]:
                    if k in attrs:
                        orig_key = k
                        break
                
                if orig_key is None: orig_key = key.encode('utf-8') # Default to symbol
                
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

    def _tokenize_ruby_script(self, code: str) -> List[Tuple[int, int, str, str]]:
        """
        Tokenize Ruby script to find string literals.
        Returns: List of (start_index, end_index, content, quote_char)
        """
        tokens = []
        
        # States
        STATE_NORMAL = 0
        STATE_SINGLE_QUOTE = 1
        STATE_DOUBLE_QUOTE = 2
        STATE_COMMENT = 3
        
        state = STATE_NORMAL
        i = 0
        length = len(code)
        start_quote = -1
        
        while i < length:
            char = code[i]
            
            if state == STATE_NORMAL:
                if char == '#':
                    state = STATE_COMMENT
                elif char == "'":
                    state = STATE_SINGLE_QUOTE
                    start_quote = i
                elif char == '"':
                    state = STATE_DOUBLE_QUOTE
                    start_quote = i
            
            elif state == STATE_COMMENT:
                if char == '\n':
                    state = STATE_NORMAL
            
            elif state == STATE_SINGLE_QUOTE:
                if char == '\\':
                    i += 1 # Skip next char (escaped)
                elif char == "'":
                    # End of string
                    content = code[start_quote+1 : i]
                    tokens.append((start_quote, i+1, content, "'"))
                    state = STATE_NORMAL
            
            elif state == STATE_DOUBLE_QUOTE:
                if char == '\\':
                    i += 1 # Skip next char (escaped)
                elif char == '"':
                    # End of string
                    content = code[start_quote+1 : i]
                    tokens.append((start_quote, i+1, content, '"'))
                    state = STATE_NORMAL
            
            i += 1
            
        return tokens

    def _is_valid_script_string(self, text: str) -> bool:
        """Validate if a script string is worth translating."""
        # Use the robust base validation first
        if not self.is_safe_to_translate(text, is_dialogue=True):
            return False
            
        if not text or len(text) < 2:
            return False
            
        # 1. Skip if only ASCII letters/numbers/underscore
        if re.match(r'^[a-zA-Z0-9_]+$', text):
            return False
            
        # 2. Skip standard file extensions
        if any(text.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.bmp', '.ogg', '.wav', '.mp3', '.rvdata2']):
            return False
            
        # 3. Skip symbols starting with :
        if text.startswith(':'):
            return False

        # 4. Must contain spaces OR non-ascii
        has_space = ' ' in text
        has_non_ascii = any(ord(c) > 127 for c in text)
        
        if not (has_space or has_non_ascii):
            return False
            
        return True

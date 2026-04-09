import rubymarshal.reader
import rubymarshal.writer
import rubymarshal.classes
from typing import List, Tuple, Dict, Any, Set, Optional
from .base import BaseParser
import logging
import zlib
import os
import threading
import inspect
import textwrap
from src.core.constants import (TRANSLATOR_RECURSION_MAX_DEPTH, 
                                 RUBY_ENCODING_FALLBACK_LIST, 
                                 RUBY_KEY_ENCODING_FALLBACK_LIST)
from .asset_text import asset_identifier_candidates, contains_asset_tuple_reference, contains_explicit_asset_reference, normalize_asset_text
from .extraction_surface_registry import ExtractionSurfaceRegistry

try:
    from tree_sitter import Language, Parser
except ImportError:  # pragma: no cover - exercised through fallback behavior
    Language = None
    Parser = None

logger = logging.getLogger(__name__)

_RUBY_ASSET_REGISTRY_CACHE: Dict[str, Set[str]] = {}
_RUBY_ASSET_REGISTRY_LOCK = threading.Lock()
_SAFE_RUBY_LOADER_CLASS: Any = None
_SAFE_RUBY_LOADER_WARNED: Set[str] = set()
_SAFE_RUBY_LOADER_WARNED_LOCK = threading.Lock()


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
    ASSET_FILE_EXTENSIONS = (
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp',
        '.ogg', '.wav', '.m4a', '.mp3', '.mid', '.midi',
        '.webm', '.mp4', '.avi', '.mov', '.ogv', '.mkv',
        '.rpgmvp', '.rpgmvo', '.rpgmvm', '.rvdata2', '.rvdata', '.rxdata'
    )
    ASSET_SCAN_DIRS = ("audio", "img", "movies", "fonts")
    
    def __init__(self, translate_notes: bool = False, translate_comments: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.translate_notes = translate_notes
        self.translate_comments = translate_comments
        self.allow_script_translation = False
        self.extracted: List[Tuple[str, str, str]] = []
        self.visited: Set[int] = set()
        self.MAX_RECURSION_DEPTH = TRANSLATOR_RECURSION_MAX_DEPTH
        self._known_asset_identifiers: Set[str] = set()
        self.last_apply_error: str | None = None
        self._surface_registry = ExtractionSurfaceRegistry()
        self._ruby_language = self._build_ruby_language()
        self._ruby_parser = Parser(self._ruby_language) if self._ruby_language is not None and Parser is not None else None
    
    def extract_text(self, file_path: str) -> List[Tuple[str, str, str]]:
        """
        Extract all translatable text from a Ruby Marshal file.
        
        Returns:
            List of (path, text, context_tag) tuples
        """
        self._known_asset_identifiers = self._get_known_asset_identifiers(file_path)
        try:
            data = self._load_ruby_marshal(file_path)
        except Exception as e:
            logger.error(f"Failed to load {file_path}: {e}")
            return []
        
        self.extracted = []
        self.visited = set()
        self._walk(data, "", 0)
        return self.extracted

    def _load_ruby_marshal(self, file_path: str) -> Any:
        """Load RubyMarshal data with a safe fallback for Scripts.rvdata2."""
        with open(file_path, 'rb') as f:
            try:
                return rubymarshal.reader.load(f)
            except UnicodeDecodeError as error:
                if os.path.basename(file_path).lower() != "scripts.rvdata2":
                    raise
                normalized_path = os.path.normpath(file_path).lower()
                with _SAFE_RUBY_LOADER_WARNED_LOCK:
                    if normalized_path not in _SAFE_RUBY_LOADER_WARNED:
                        _SAFE_RUBY_LOADER_WARNED.add(normalized_path)
                        logger.info(f"Using safe Scripts.rvdata2 loader for {file_path}: {error}")
                f.seek(0)
                return self._load_ruby_marshal_safe(f)

    def _load_ruby_marshal_safe(self, fd) -> Any:
        """Load RubyMarshal data using a patched string decode fallback."""
        loader_cls = self._get_safe_ruby_loader_class()
        if fd.read(1) != b"\x04":
            raise ValueError(r"Expected token \x04")
        if fd.read(1) != b"\x08":
            raise ValueError(r"Expected token \x08")

        loader = loader_cls(fd, registry=None)
        return loader.read()

    def _get_safe_ruby_loader_class(self) -> Any:
        """Build and cache a RubyMarshal reader with a tolerant unicode fallback."""
        global _SAFE_RUBY_LOADER_CLASS
        if _SAFE_RUBY_LOADER_CLASS is not None:
            return _SAFE_RUBY_LOADER_CLASS

        reader_module = rubymarshal.reader
        read_source = inspect.getsource(reader_module.Reader.read)
        read_source = textwrap.dedent(read_source)
        read_source = read_source.replace(
            'result = result.decode("unicode-escape")',
            'result = result.decode("latin1")',
        )

        namespace = dict(reader_module.__dict__)
        exec(read_source, namespace)
        safe_reader_cls = type(
            "SafeReader",
            (reader_module.Reader,),
            {"read": namespace["read"]},
        )

        _SAFE_RUBY_LOADER_CLASS = safe_reader_cls
        return safe_reader_cls

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
            if len(obj) > 0 and isinstance(obj[0], (list, tuple)) and len(obj[0]) == 3 and (
                isinstance(obj[0][2], bytes) or getattr(obj[0][2], "ruby_class_name", None) == "str"
            ) and path == "":
                self._process_scripts_array(obj)
                return

            for i, item in enumerate(obj):
                self._check_and_walk(item, f"{path}.{i}" if path else str(i), depth + 1)
        
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
                        
                self._check_and_walk(v, f"{path}.{key_name}" if path else str(key_name), depth + 1, attr_key=key_name)


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
                self._check_and_walk(v, f"{path}.@{display_key}" if path else f"@{display_key}", depth + 1, attr_key=display_key)
        
        elif hasattr(obj, '__dict__'):
            for k, v in obj.__dict__.items():
                if not k.startswith('_'):
                    self._check_and_walk(v, f"{path}.{k}" if path else str(k), depth + 1, attr_key=k)

    def _process_scripts_array(self, scripts: list):
        """Process the special Scripts.rvdata2 array structure."""
        logger.info("Detected Scripts.rvdata2 structure. Extracting strings from ruby code...")
        for i, entry in enumerate(scripts):
            if len(entry) < 3:
                continue
                
            script_id = entry[0]
            script_name = self._to_string(entry[1])
            compressed_code = entry[2]
            if getattr(compressed_code, "ruby_class_name", None) == "str" and hasattr(compressed_code, "text"):
                compressed_code = str(compressed_code).encode("latin1", errors="replace")
            
            if not isinstance(compressed_code, bytes):
                continue
                
            try:
                # 1. Decompress
                code_bytes = zlib.decompress(compressed_code)
                
                # 2. Decode - Use robust encoding detection for older RPG Maker versions
                code_text = self._decode_ruby_bytes(code_bytes)[0]
                if code_text is None:
                    continue
                
                # 3. Extract strings from code
                self._extract_from_code(code_text, f"{i}.code")
                
            except Exception as e:
                logger.warning(f"Failed to process script {i} ({script_name}): {e}")

    def _extract_from_code(self, code: str, path_prefix: str):
        """Extract valid strings from raw Ruby code using a tokenizer."""
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
        tokens = self._tokenize_ruby_script(code)

        seen_strings = set()

        for idx, (_start, _end, text, _quote_char) in enumerate(tokens):
            if text in seen_strings:
                continue
            if not self._is_valid_script_string(text):
                continue
            self.extracted.append((f"{path_prefix}.string_{idx}", text, "script"))
            seen_strings.add(text)

    def _check_and_walk(self, val: Any, path: str, depth: int, attr_key: Optional[str] = None):
        """Check if value should be extracted, then continue walking."""
        if depth > self.MAX_RECURSION_DEPTH:
            return
        # Convert bytes to string if needed
        text_val: Any = None
        if isinstance(val, bytes):
            text_val = self._to_string(val)
            if text_val is None:
                return
        elif isinstance(val, str):
            text_val = val
        elif getattr(val, "ruby_class_name", None) == "str" or (hasattr(val, "text") and hasattr(val, "attributes")):
            text_val = self._to_string(val)
        
        if isinstance(text_val, str):
            # Check if this is a translatable field
            if attr_key and self._should_extract_ruby_attr_value(attr_key, text_val):
                context_tag = self._ruby_attr_context_tag(attr_key)
                self.extracted.append((path, text_val, context_tag))
            
            # Check system keys
            elif attr_key and attr_key in self.SYSTEM_KEYS:
                if self._is_extractable_runtime_text(text_val, is_dialogue=True):
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

            # Generic RubyObject: recurse into nested attributes.
            for k, v in attrs.items():
                attr_name: Any = str(k) if not isinstance(k, (str, bytes)) else k
                if isinstance(attr_name, bytes):
                    attr_name = attr_name.decode('utf-8', errors='replace')

                display_key = str(attr_name).lstrip('@')
                if self._surface_registry.is_asset_key(display_key) or self._surface_registry.is_technical_key(display_key):
                    continue
                self._check_and_walk(v, f"{path}.@{display_key}" if path else f"@{display_key}", depth + 1, attr_key=display_key)
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
                if text is not None and self._is_extractable_runtime_text(text, is_dialogue=True):
                    self.extracted.append((f"{path}.@parameters.0", text, "message_dialogue"))
        
        # Show Choices (102)
        elif code == 102:
            if len(params) > 0 and isinstance(params[0], list):
                for i, choice in enumerate(params[0]):
                    text = self._to_string(choice)
                    if text is not None and self._is_extractable_runtime_text(text, is_dialogue=True):
                        self.extracted.append((f"{path}.@parameters.0.{i}", text, "choice"))
        
        # Comment (108/408)
        elif code in [108, 408] and self.translate_comments:
            if len(params) > 0:
                text = self._to_string(params[0])
                if text is not None and self.looks_like_translatable_comment(text) and self._is_extractable_runtime_text(text, is_dialogue=True):
                    self.extracted.append((f"{path}.@parameters.0", text, "comment"))
        
        elif code in [320, 324]:
            if len(params) > 1:
                text = self._to_string(params[1])
                if text is not None and self._is_extractable_runtime_text(text, is_dialogue=True):
                    self.extracted.append((f"{path}.@parameters.1", text, "name"))
        
        # Change Profile (325)
        elif code == 325:
            if len(params) > 1:
                text = self._to_string(params[1])
                if text is not None and self._is_extractable_runtime_text(text, is_dialogue=True):
                    self.extracted.append((f"{path}.@parameters.1", text, "name"))
        
        # Show Choices (102)
        elif code == 102:
            if len(params) > 0 and isinstance(params[0], (list, tuple)):
                for i, choice in enumerate(params[0]):
                    text = self._to_string(choice)
                    if text is not None and self._is_extractable_runtime_text(text, is_dialogue=True):
                        self.extracted.append((f"{path}.@parameters.0.{i}", text, "choice"))

    def _to_string(self, val: Any) -> Optional[str]:
        """Convert a value to string, handling bytes and common encodings."""
        if isinstance(val, str):
            return val
        elif isinstance(val, bytes):
            return self._decode_ruby_bytes(val)[0]
        elif getattr(val, "ruby_class_name", None) == "str" and hasattr(val, "text"):
            return str(val.text)
        return None

    def _should_extract_ruby_attr_value(self, attr_key: str, text_val: str) -> bool:
        """Return True when a Ruby attribute is a safe text surface."""
        normalized_key = attr_key.lstrip('@')
        if normalized_key == 'note' and not self.translate_notes:
            return False

        if self._surface_registry.is_asset_key(normalized_key) or self._surface_registry.is_technical_key(normalized_key):
            return False

        if normalized_key in {'name', 'nickname', 'title', 'game_title', 'currency_unit', 'description', 'help', 'message', 'message1', 'message2', 'message3', 'message4', 'text', 'msg'}:
            return self._is_extractable_runtime_text(text_val, is_dialogue=(normalized_key != 'note'))

        if self._surface_registry.is_text_key(normalized_key):
            return self._is_extractable_runtime_text(text_val, is_dialogue=(normalized_key != 'note'))

        return self._looks_like_textual_value(text_val)

    def _ruby_attr_context_tag(self, attr_key: str) -> str:
        """Map Ruby attributes to extraction context tags."""
        normalized_key = attr_key.lstrip('@')
        if normalized_key in {'name', 'nickname', 'title', 'game_title', 'currency_unit'}:
            return 'name'
        if normalized_key in {'message1', 'message2', 'message3', 'message4', 'description', 'help', 'text', 'msg'}:
            return 'dialogue_block'
        if normalized_key in {'note'}:
            return 'system'
        return 'name'

    def _looks_like_textual_value(self, value: str) -> bool:
        """Return True when a value resembles user-visible text."""
        if not isinstance(value, str):
            return False
        stripped = value.strip()
        if not stripped:
            return False
        if ' ' in stripped:
            return True
        if any(ord(char) > 127 for char in stripped):
            return True
        return any(marker in stripped for marker in ('!', '?', '.', ':', ';', '%')) and len(stripped) >= 4

    def _decode_ruby_bytes(self, val: bytes) -> tuple[Optional[str], Optional[str]]:
        """Decode Ruby bytes and return the detected text plus encoding."""
        if not isinstance(val, bytes):
            return None, None

        encodings = ['shift_jis', 'utf-8', 'euc-jp', 'cp1252', 'latin-1']
        for encoding in encodings:
            try:
                return val.decode(encoding), encoding
            except (UnicodeDecodeError, LookupError):
                continue

        return val.decode('utf-8', errors='replace'), 'utf-8'

    def apply_translation(self, file_path: str, translations: Dict[str, str]) -> Any:
        """
        Apply translations back to the Ruby Marshal file.
        """
        self.last_apply_error = None
        self._known_asset_identifiers = self._get_known_asset_identifiers(file_path)
        original_data = self._load_ruby_marshal(file_path)
        data = self._load_ruby_marshal(file_path)
        
        applied_count = 0
        failed_paths = []
        
        # Check whether the loaded structure is a script-container array.
        is_scripts = self._is_script_container(data)
        
        if is_scripts:
            if not self.allow_script_translation:
                logger.info("Skipping Scripts.rvdata2 write to preserve runtime stability.")
                self.last_apply_error = "Script container write disabled by default"
                return None
            # We need to perform a different application strategy for scripts
            data = self._apply_scripts_translation(data, translations)
            asset_violations = self._find_asset_mutations(original_data, data)
            if asset_violations:
                joined = ", ".join(asset_violations[:5])
                self.last_apply_error = f"Asset invariant violation: {joined}"
                logger.error("Asset invariant violation while applying %s: %s", os.path.basename(file_path), joined)
                return None
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

        asset_violations = self._find_asset_mutations(original_data, data)
        if asset_violations:
            joined = ", ".join(asset_violations[:5])
            self.last_apply_error = f"Asset invariant violation: {joined}"
            logger.error("Asset invariant violation while applying %s: %s", os.path.basename(file_path), joined)
            return None
        
        return data

    def _is_script_container(self, data: Any) -> bool:
        """Return True when the RubyMarshal payload looks like a Scripts-style array."""
        if not isinstance(data, list):
            return False

        first_entry = next((item for item in data if item is not None), None)
        return isinstance(first_entry, (list, tuple)) and len(first_entry) == 3 and (
            isinstance(first_entry[2], bytes) or getattr(first_entry[2], "ruby_class_name", None) == "str"
        )

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
            if getattr(compressed_code, "ruby_class_name", None) == "str" and hasattr(compressed_code, "text"):
                compressed_code = str(compressed_code).encode("latin1", errors="replace")
            
            try:
                # 1. Decompress
                code_bytes = zlib.decompress(compressed_code)
                code_text, detected_encoding = self._decode_ruby_bytes(code_bytes)
                if code_text is None:
                    continue
                
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
                output_encoding = detected_encoding or 'utf-8'
                new_bytes = zlib.compress(new_code_text.encode(output_encoding, errors='replace'))
                
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
        if self._ruby_parser is not None:
            parsed_tokens = self._tokenize_ruby_script_with_tree_sitter(code)
            if parsed_tokens:
                return parsed_tokens

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

    def _build_ruby_language(self):
        if Language is None:
            return None
        try:
            import importlib

            tree_sitter_ruby = importlib.import_module("tree_sitter_ruby")
        except ImportError:
            return None
        return Language(tree_sitter_ruby.language())

    def _tokenize_ruby_script_with_tree_sitter(self, code: str) -> List[Tuple[int, int, str, str]]:
        parser = self._ruby_parser
        if parser is None:
            return []

        source_bytes = code.encode("utf-8")
        tree = parser.parse(source_bytes)
        tokens: List[Tuple[int, int, str, str]] = []

        for node in self._iter_ruby_string_nodes(tree.root_node):
            raw_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")
            if not raw_text:
                continue
            if self._ruby_string_has_interpolation(node):
                continue

            quote = raw_text[0] if raw_text[0] in ('"', "'", '%') else '"'
            text = self._decode_ruby_literal_text(raw_text, quote)
            tokens.append((node.start_byte, node.end_byte, text, quote))

        return tokens

    def _iter_ruby_string_nodes(self, node):
        stack = [node]
        while stack:
            current = stack.pop()
            if current.type in {"string", "string_content", "interpolated_string", "interpolated_symbol"}:
                yield current
            stack.extend(reversed(current.children))

    def _ruby_string_has_interpolation(self, node) -> bool:
        for child in getattr(node, "named_children", []):
            if child.type in {"interpolation", "string_interpolation"}:
                return True
        return False

    def _decode_ruby_literal_text(self, raw_text: str, quote: str) -> str:
        if len(raw_text) < 2:
            return raw_text
        if quote == "'":
            return raw_text[1:-1]
        try:
            import ast

            return ast.literal_eval(raw_text)
        except (SyntaxError, ValueError):
            return raw_text[1:-1]

    def _is_valid_script_string(self, text: str) -> bool:
        """Validate if a script string is worth translating."""
        # Use the robust base validation first
        if not self._is_extractable_runtime_text(text, is_dialogue=True):
            return False
            
        if not text or len(text) < 2:
            return False
            
        # 1. Skip if only ASCII letters/numbers/underscore
        if all(char.isalnum() or char == '_' for char in text):
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

    def _is_extractable_runtime_text(self, text: Optional[str], *, is_dialogue: bool = False) -> bool:
        """Central safety gate for Ruby extraction paths."""
        if not isinstance(text, str):
            return False
        if not self.is_safe_to_translate(text, is_dialogue=is_dialogue):
            return False
        if self._contains_asset_reference(text):
            return False
        if self._matches_known_asset_identifier(text):
            return False
        return True

    @staticmethod
    def _normalize_asset_text(text: str) -> str:
        """Normalize strings for asset/path detection, including percent-decoded variants."""
        return normalize_asset_text(text)

    def _contains_asset_reference(self, text: str) -> bool:
        """Detect file path or asset reference patterns in Ruby strings."""
        return contains_explicit_asset_reference(text, self.ASSET_FILE_EXTENSIONS) or contains_asset_tuple_reference(text)

    def _matches_known_asset_identifier(self, text: str) -> bool:
        """Return True when text matches a real asset basename/path from the current project."""
        if not isinstance(text, str) or not text.strip():
            return False
        if not self._known_asset_identifiers:
            return False

        candidates = asset_identifier_candidates(text)
        if not candidates:
            return False

        return any(candidate in self._known_asset_identifiers for candidate in candidates)

    def _get_known_asset_identifiers(self, file_path: str) -> Set[str]:
        """Build or reuse a cached set of actual asset identifiers for the current project."""
        asset_root = self._find_asset_root(file_path)
        if not asset_root:
            return set()

        normalized_root = os.path.normpath(asset_root)
        with _RUBY_ASSET_REGISTRY_LOCK:
            cached = _RUBY_ASSET_REGISTRY_CACHE.get(normalized_root)
            if cached is not None:
                return cached

        identifiers: Set[str] = set()
        for directory_name in self.ASSET_SCAN_DIRS:
            directory_path = os.path.join(asset_root, directory_name)
            if not os.path.isdir(directory_path):
                continue

            for root, _dirs, files in os.walk(directory_path):
                for filename in files:
                    relative_path = os.path.relpath(os.path.join(root, filename), asset_root).replace("\\", "/").lower()
                    basename = os.path.basename(relative_path)
                    stem, _ext = os.path.splitext(basename)
                    rel_stem, _ = os.path.splitext(relative_path)
                    identifiers.add(relative_path)
                    identifiers.add(basename)
                    if stem:
                        identifiers.add(stem)
                    if rel_stem:
                        identifiers.add(rel_stem)

        with _RUBY_ASSET_REGISTRY_LOCK:
            _RUBY_ASSET_REGISTRY_CACHE[normalized_root] = identifiers
        return identifiers

    def _find_asset_root(self, file_path: str) -> Optional[str]:
        """Locate the asset root for RPG Maker projects."""
        current_dir = os.path.dirname(os.path.abspath(file_path))

        for _ in range(6):
            if self._looks_like_asset_root(current_dir):
                return current_dir

            www_dir = os.path.join(current_dir, "www")
            if self._looks_like_asset_root(www_dir):
                return www_dir

            parent_dir = os.path.dirname(current_dir)
            if parent_dir == current_dir:
                break
            current_dir = parent_dir

        return None

    def _looks_like_asset_root(self, directory: str) -> bool:
        """Return True when a directory resembles an RPG Maker asset root."""
        if not directory or not os.path.isdir(directory):
            return False
        return any(os.path.isdir(os.path.join(directory, child)) for child in self.ASSET_SCAN_DIRS)

    def _find_asset_mutations(self, original: Any, updated: Any) -> List[str]:
        """Return paths whose original asset text was changed during apply."""
        violations: List[str] = []
        visited: Set[tuple[int, int]] = set()
        self._walk_asset_differences(original, updated, "", visited, violations)
        return violations

    def _walk_asset_differences(
        self,
        original: Any,
        updated: Any,
        current_path: str,
        visited: Set[tuple[int, int]],
        violations: List[str],
    ) -> None:
        pair_id = (id(original), id(updated))
        if pair_id in visited:
            return
        visited.add(pair_id)

        original_text = self._to_string(original)
        updated_text = self._to_string(updated)
        if original_text is not None and updated_text is not None:
            if (self._contains_asset_reference(original_text) or self._matches_known_asset_identifier(original_text)) and original_text != updated_text:
                violations.append(current_path or "<root>")
            return

        if type(original) is not type(updated):
            return

        if isinstance(original, list):
            for index, (left, right) in enumerate(zip(original, updated)):
                child_path = f"{current_path}.{index}" if current_path else str(index)
                self._walk_asset_differences(left, right, child_path, visited, violations)
            return

        if isinstance(original, dict):
            for key in original.keys() & updated.keys():
                child_key = self._path_key(key)
                child_path = f"{current_path}.{child_key}" if current_path else child_key
                self._walk_asset_differences(original[key], updated[key], child_path, visited, violations)
            return

        if hasattr(original, 'attributes') and hasattr(updated, 'attributes'):
            original_attrs = getattr(original, 'attributes', {})
            updated_attrs = getattr(updated, 'attributes', {})
            for key in original_attrs.keys() & updated_attrs.keys():
                child_key = self._path_key(key)
                child_path = f"{current_path}.{child_key}" if current_path else child_key
                self._walk_asset_differences(original_attrs[key], updated_attrs[key], child_path, visited, violations)
            return

        if hasattr(original, '__dict__') and hasattr(updated, '__dict__'):
            original_items = {k: v for k, v in original.__dict__.items() if not k.startswith('_')}
            updated_items = {k: v for k, v in updated.__dict__.items() if not k.startswith('_')}
            for key in original_items.keys() & updated_items.keys():
                child_path = f"{current_path}.{key}" if current_path else key
                self._walk_asset_differences(original_items[key], updated_items[key], child_path, visited, violations)

    def _path_key(self, key: Any) -> str:
        """Normalize dict/attribute keys for diagnostic paths."""
        text = self._to_string(key)
        if text is not None:
            return text
        return str(key)

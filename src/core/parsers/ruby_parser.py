import rubymarshal.reader
import rubymarshal.writer
import rubymarshal.classes
import ast
from typing import Any
from dataclasses import dataclass
from rubymarshal.classes import Symbol, RubyString
from .base import BaseParser
import logging
import zlib
import os
import threading
import re
import inspect
import textwrap
import charset_normalizer
from src.core.constants import TRANSLATOR_RECURSION_MAX_DEPTH
from src.core.parsers.asset_text import (
    contains_explicit_asset_reference,
    contains_asset_tuple_reference,
    asset_identifier_candidates,
    normalize_asset_text,
    fuzzy_asset_normalize,
)
from .extraction_surface_registry import ExtractionSurfaceRegistry

try:
    from tree_sitter import Language, Parser
except ImportError:  # pragma: no cover - exercised through fallback behavior
    Language = None
    Parser = None

logger = logging.getLogger(__name__)

_RUBY_ASSET_REGISTRY_CACHE: dict[str, set[str]] = {}
_RUBY_ASSET_REGISTRY_LOCK = threading.Lock()
_SAFE_RUBY_LOADER_CLASS: Any = None
_SAFE_RUBY_LOADER_WARNED: set[str] = set()
_SAFE_RUBY_LOADER_WARNED_LOCK = threading.Lock()


@dataclass
class RubyStringInfo:
    """
    Captures encoding and metadata for Ruby Marshal strings to preserve encoding during translation.
    """
    text: str
    encoding: str
    is_bytes: bool = False
    original_bytes: bytes | None = None
    confidence: float = 1.0  # Encoding detection confidence


def _safe_decode_ruby_string(val: Any) -> RubyStringInfo:
    """
    Safely decode a Ruby string value using charset-normalizer with specific RM fallbacks.
    """
    if isinstance(val, str):
        return RubyStringInfo(text=val, encoding='utf-8')
    
    raw_bytes: bytes | None = None
    if isinstance(val, bytes):
        raw_bytes = val
    elif hasattr(val, 'value') and isinstance(val.value, bytes):
        raw_bytes = val.value
    
    if raw_bytes is not None:
        if not raw_bytes:
            return RubyStringInfo(text="", encoding='utf-8', is_bytes=True, original_bytes=raw_bytes)

        # Detect with priority fallbacks for common RPG Maker regions
        results = charset_normalizer.from_bytes(raw_bytes)
        res = results.best()
        
        detected_encoding = 'utf-8'
        confidence = 0.0
        
        if res:
            detected_encoding = res.encoding
            confidence = res.coherence
        
        # If confidence is low, try common RM encodings in sequence
        if confidence < 0.7:
            # Shift-JIS is the most common legacy encoding for RM XP/VX/Ace
            for enc in ['shift_jis', 'cp1252', 'euc_jp', 'gbk', 'cp949', 'euc_kr']:
                try:
                    decoded = raw_bytes.decode(enc)
                    return RubyStringInfo(
                        text=decoded, 
                        encoding=enc, 
                        is_bytes=True, 
                        original_bytes=raw_bytes,
                        confidence=0.8 # Higher confidence for successful manual match
                    )
                except (UnicodeDecodeError, LookupError):
                    continue

        try:
            decoded = raw_bytes.decode(detected_encoding)
            return RubyStringInfo(
                text=decoded, 
                encoding=detected_encoding, 
                is_bytes=True, 
                original_bytes=raw_bytes,
                confidence=confidence
            )
        except (UnicodeDecodeError, LookupError):
            # Absolute fallback
            return RubyStringInfo(
                text=raw_bytes.decode('utf-8', errors='replace'), 
                encoding='utf-8', 
                is_bytes=True, 
                original_bytes=raw_bytes,
                confidence=0.0
            )

    if hasattr(val, 'ruby_class_name'):
        return RubyStringInfo(text=str(val), encoding='utf-8')
    
    return RubyStringInfo(text=str(val), encoding='utf-8')


class RubyParser(BaseParser):
    """
    Parser for RPG Maker XP/VX/VX Ace binary data files.
    Supports: .rvdata2 (VX Ace), .rxdata (XP), .rvdata (VX)
    """
    
    # Event command codes (same across RPG Maker versions with minor variations)
    TEXT_EVENT_CODES = {
        101: 'show_text_xp',        # Show Text Header / XP Dialogue
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
        231: 'show_picture',        # Show Picture (Portrait)
        235: 'erase_picture',       # Erase Picture (Portrait)
    }
    
    # Range-based path marker for bundled dialogue
    BUNDLED_PATH_MARKER = "_bundled_"
    
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
    ASSET_SCAN_DIRS = ("audio", "img", "movies", "fonts", "Graphics", "Audio")
    PROTECTED_RUBY_FILES = {
        "animations",
        "tilesets",
        # "mapinfos" removed: map names are player-visible (area name displays, save screen)
    }
    # Allowlist for mapinfos: only the display name is translatable
    RUBY_MAPINFOS_ATTR_ALLOWLIST = {"name"}
    RUBY_FILE_ATTR_ALLOWLIST: dict[str, set[str]] = {
        "actors": {"name", "nickname", "description", "profile"},
        "classes": {"name"},
        "skills": {"name", "description", "message1", "message2", "message3", "message4"},
        "items": {"name", "description"},
        "weapons": {"name", "description"},
        "armors": {"name", "description"},
        "states": {"name", "description", "message1", "message2", "message3", "message4"},
        "enemies": {"name"},
        "system": {"game_title", "currency_unit", "terms", "words", "elements", "skill_types", "weapon_types", "armor_types"},
        "troops": set(),       # troop names are internal dev labels, not player-visible
        "commonevents": {"name"},  # common event names can appear in gallery/quest UIs
        "mapinfos": {"name"},  # MapInfos: map names shown in save screen / area transitions
    }
    
    def __init__(self, translate_notes: bool = False, translate_comments: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.translate_notes = translate_notes
        self.translate_comments = translate_comments
        self.allow_script_translation = False
        self.extracted: list[tuple[str, str, str]] = []
        self.visited: set[int] = set()
        self.MAX_RECURSION_DEPTH = TRANSLATOR_RECURSION_MAX_DEPTH
        self._known_asset_identifiers: set[str] = set()
        self.last_apply_error: str | None = None
        self._surface_registry = ExtractionSurfaceRegistry()
        self._ruby_language = self._build_ruby_language()
        self._ruby_parser = Parser(self._ruby_language) if self._ruby_language is not None and Parser is not None else None
        self._last_loaded_data: Any = None
        self._last_raw_bytes: bytes | None = None
        self._current_file_basename: str = ""
        self._current_file_ext: str = ""  # e.g. ".rxdata", ".rvdata", ".rvdata2"
        self._current_context_map: dict[str, str] = {}
        self._extracted_tag_map: dict[str, str] = {}
        self._last_face_name: str = ""
        self._active_picture_bust: bool = False
    def extract_text(self, file_path: str) -> list[tuple[str, str, str]]:
        """Extract translatable text from Ruby Marshal files."""
        self._known_asset_identifiers = self._get_known_asset_identifiers(file_path)
        self._current_file_basename = os.path.splitext(os.path.basename(file_path))[0].lower()
        self._current_file_ext = os.path.splitext(file_path)[1].lower()  # ".rxdata" / ".rvdata" / ".rvdata2"
        
        try:
            data = self._load_ruby_marshal(file_path)
            self._last_loaded_data = data
        except Exception as e:
            logger.error(f"Failed to load {file_path}: {e}")
            return []

        if self._is_protected_ruby_file():
            return []
        
        self.extracted = []
        self.visited = set()
        self._current_context_map = {}
        self._extracted_tag_map = {}
        self._active_picture_bust = False
        
        # Optimized identity pre-scan for context enrichment
        if isinstance(data, list) and self._current_file_basename in self.RUBY_FILE_ATTR_ALLOWLIST:
            for i, item in enumerate(data):
                if hasattr(item, 'attributes'):
                    attrs = item.attributes
                    # Search specifically for names/display names in Actors, Classes, etc.
                    for k in ('@name', '@display_name', b'@name', b'@display_name'):
                        # rubymarshal uses Symbol objects for keys often
                        found_val = None
                        if k in attrs:
                            found_val = attrs[k]
                        else:
                            # Try matching by string representation if it's a Symbol
                            for sk, sv in attrs.items():
                                if isinstance(sk, Symbol) and str(sk).lstrip('@') == str(k).lstrip('@/b\''):
                                    found_val = sv
                                    break
                        
                        if found_val:
                            name_str = self._to_string(found_val)
                            if name_str:
                                self._current_context_map[str(i)] = name_str
                                break
        
        # Root level context detection
        if hasattr(data, 'attributes'):
             attrs = data.attributes
             for k in ('@display_name', b'@display_name', '@game_title', b'@game_title'):
                 if k in attrs:
                     name_val = self._to_string(attrs[k])
                     if name_val:
                         self._current_context_map["ROOT"] = name_val
                         break

        self._walk(data, "", 0)
        return self.extracted

    def _update_event_context(self, item: Any, index: int) -> None:
        """Update context map for map events efficiently."""
        if hasattr(item, 'attributes'):
            attrs = getattr(item, 'attributes', {})
            # Fast check for common RM event name keys
            for k in ('@name', b'@name'):
                if k in attrs:
                    ev_name = self._to_string(attrs[k])
                    if ev_name:
                        self._current_context_map[f"events.{index}"] = ev_name
                        break

    def _is_script_container_structure(self, obj: list) -> bool:
        """Check if list resembles RPG Maker Scripts.rvdata2 structure."""
        if not obj or not isinstance(obj[0], (list, tuple)) or len(obj[0]) < 3:
            return False
        code_part = obj[0][2]
        return isinstance(code_part, bytes) or getattr(code_part, "ruby_class_name", None) == "str"

    def _load_ruby_marshal(self, file_path: str) -> Any:
        """Load RubyMarshal data with a safe fallback for Scripts.rvdata2."""
        with open(file_path, 'rb') as f:
            raw = f.read()
        self._last_raw_bytes = raw
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
        try:
            # rubymarshal 1.2.x uses Reader.read for dispatch. 
            # We ensure it handles malformed unicode-escape by forcing latin1 fallback
            # only where absolutely needed to prevent parser crashes.
            read_source = inspect.getsource(reader_module.Reader.read)
            read_source = textwrap.dedent(read_source)
            
            # Robust replacement that works across 1.0.0 and 1.2.x
            target = 'result = result.decode("unicode-escape")'
            if target in read_source:
                read_source = read_source.replace(target, 'result = result.decode("latin1", errors="replace")')
            
            namespace = dict(reader_module.__dict__)
            exec(read_source, namespace)
            
            safe_reader_cls = type(
                "SafeReader",
                (reader_module.Reader,),
                {"read": namespace["read"]},
            )
        except Exception as e:
            logger.warning(f"Surgical patch failed, falling back to standard Reader: {e}")
            safe_reader_cls = reader_module.Reader

        _SAFE_RUBY_LOADER_CLASS = safe_reader_cls
        return safe_reader_cls

    def _walk(self, obj: Any, path: str = "", depth: int = 0):
        """Recursively walk thru RPG Maker Ruby objects."""
        if depth > self.MAX_RECURSION_DEPTH or obj is None:
            return
            
        if isinstance(obj, Symbol):
            return # Skip symbols early
            
        obj_id = id(obj)
        if obj_id in self.visited:
            return
        self.visited.add(obj_id)

        if isinstance(obj, str):
            # Strings are handled in _check_and_walk with context
            pass
        
        elif isinstance(obj, list):
            # High-performance list traversal
            # Check for Scripts structure only at root
            if path == "" and self._is_script_container_structure(obj):
                self._process_scripts_array(obj)
                return

            # Legacy Engine Bundling logic (XP/VX/VXA)
            if self._is_command_list(obj):
                self._walk_command_list(obj, path, depth)
                return

            for i, item in enumerate(obj):
                # Context identification for Map Events (optimized path)
                if path in {"events", ".events"}:
                    self._update_event_context(item, i)

                self._check_and_walk(item, f"{path}.{i}" if path else str(i), depth + 1)
        
        elif isinstance(obj, dict):
            # Optimized dict traversal using items()
            for k, v in obj.items():
                key_name = self._to_string(k) or str(k)
                self._check_and_walk(v, f"{path}.{key_name}" if path else str(key_name), depth + 1, attr_key=key_name)


        elif hasattr(obj, 'attributes'):
            # rubymarshal RubyObject
            attrs = getattr(obj, 'attributes', {})
            
            # Heuristic for sound objects (BGM, BGS, ME, SE)
            is_sound_obj = all(k in attrs for k in ['@name', '@volume', '@pitch'])
            
            for k, v in attrs.items():
                key_name = str(k) if not isinstance(k, (str, bytes)) else k
                if isinstance(key_name, bytes):
                    result = charset_normalizer.from_bytes(key_name).best()
                    if result:
                        key_name = key_name.decode(result.encoding)
                    else:
                        key_name = key_name.decode('utf-8', errors='replace')
                
                # Skip name in sound objects
                if is_sound_obj and key_name == '@name':
                    continue
                    
                # Remove leading @ from Ruby instance variable names
                display_key = key_name.lstrip('@') if isinstance(key_name, str) else key_name
                if isinstance(display_key, str):
                    if self._surface_registry.is_asset_key(display_key) or self._surface_registry.is_technical_key(display_key):
                        continue
                self._check_and_walk(v, f"{path}.@{display_key}" if path else f"@{display_key}", depth + 1, attr_key=display_key)
        
        elif hasattr(obj, '__dict__'):
            for k, v in obj.__dict__.items():
                if not k.startswith('_'):
                    self._check_and_walk(v, f"{path}.{k}" if path else str(k), depth + 1, attr_key=k)

    def _is_command_list(self, obj: list) -> bool:
        """Heuristic to detect RPG Maker Event Command lists."""
        if not obj or len(obj) < 1:
            return False
        first = obj[0]
        if not hasattr(first, 'attributes'):
            return False
        attrs = first.attributes
        # Check for Symbol or String keys for 'code' and 'parameters'
        return (any(k in attrs for k in ['code', '@code', b'code', b'@code']) and 
                any(k in attrs for k in ['parameters', '@parameters', b'parameters', b'@parameters']))

    def _walk_command_list(self, commands: list, path: str, depth: int):
        """Iterate through event commands with state-aware bundling."""
        idx = 0
        length = len(commands)
        
        while idx < length:
            cmd = commands[idx]
            code = self._get_ruby_attr(cmd, 'code')
            params = self._get_ruby_attr(cmd, 'parameters')
            
            if not isinstance(code, int) or not isinstance(params, list):
                idx += 1
                continue

            # Handle Face/Context tracking
            if code == 101: 
                # Header in VX/VXA, Dialogue in XP
                if self._current_file_ext != '.rxdata' and len(params) >= 1:
                    self._last_face_name = self._to_string(params[0]) or ""

            # Check for bundling candidates
            is_xp = self._current_file_ext == '.rxdata'
            is_bundle_start = (code == 401) or (code == 405) or (is_xp and code == 101)
            
            if is_bundle_start:
                # Start grouping consecutive commands of the SAME type
                # Optimization: Cap bundling to prevent oversized requests (Max 30 lines or 2500 chars)
                block_lines = []
                start_idx = idx
                current_code = code
                current_chars = 0
                
                while idx < length:
                    inner_cmd = commands[idx]
                    inner_code = self._get_ruby_attr(inner_cmd, 'code')
                    inner_params = self._get_ruby_attr(inner_cmd, 'parameters')
                    
                    if inner_code != current_code:
                        break
                    
                    line_text = self._to_string(inner_params[0]) if inner_params else ""
                    line_to_add = line_text or ""
                    
                    # Character limit check
                    if current_chars + len(line_to_add) > 2500 or len(block_lines) >= 30:
                        break
                        
                    block_lines.append(line_to_add)
                    current_chars += len(line_to_add) + 1 # +1 for newline
                    idx += 1
                
                # Process the gathered block
                from src.core.constants import SAFE_INTERNAL_MERGE
                full_text = SAFE_INTERNAL_MERGE.join(block_lines)
                if full_text.strip() and self._is_extractable_runtime_text(full_text, is_dialogue=True):
                    tag = "message_dialogue" if current_code in [101, 401] else "scroll_text"
                    has_face = self._last_face_name or getattr(self, '_active_picture_bust', False)
                    has_plugin_tag = any(x in full_text for x in ["\\f[", "\\face[", "\\n<", "\\P[", "\\face_id", "\\face_name"])
                    
                    if (has_face or has_plugin_tag) and tag == "message_dialogue":
                        tag += "/hasPicture"
                    
                    # Store as a virtual range path
                    range_key = f"{start_idx}{self.BUNDLED_PATH_MARKER}{idx-1}"
                    self._append_extracted(f"{path}.{range_key}", full_text, tag)
                
                # Loop will continue from idx where inner_code != current_code OR limits reached
                continue

            # Standard processing for individual commands (Choices, etc.)
            self._extract_event_command(code, params, f"{path}.{idx}")
            idx += 1

    def _get_ruby_attr(self, obj: Any, name: str) -> Any:
        """Standardized attribute getter for rubymarshal objects."""
        if not hasattr(obj, 'attributes'):
            return None
        attrs = obj.attributes
        for k in [name, f"@{name}", name.encode('utf-8'), f"@{name}".encode('utf-8')]:
            if k in attrs:
                return attrs[k]
        return None

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

    def _check_and_walk(self, val: Any, path: str, depth: int, attr_key: str | None = None):
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
            if attr_key and self._should_extract_ruby_attr_value(attr_key, text_val, path):
                base_tag = self._ruby_attr_context_tag(attr_key)
                context = self._get_ruby_context(path)
                final_tag = f"{base_tag} | {context}" if context else base_tag
                self.extracted.append((path, text_val, final_tag))
            elif self._is_ruby_system_runtime_text_path(path):
                if self._is_extractable_runtime_text(text_val, is_dialogue=True):
                    context = self._get_ruby_context(path)
                    final_tag = f"system | {context}" if context else "system"
                    self.extracted.append((path, text_val, final_tag))
            
            # Check system keys
            elif attr_key and attr_key in self.SYSTEM_KEYS:
                if self._is_extractable_runtime_text(text_val, is_dialogue=True):
                    context = self._get_ruby_context(path)
                    final_tag = f"system | {context}" if context else "system"
                    self.extracted.append((path, text_val, final_tag))
        
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
        
        # Show Text (401) / Scroll Text (405) or Show Text XP (101)
        is_xp_text = (code == 101 and self._current_file_ext == '.rxdata')
        if code in [401, 405] or is_xp_text:
            if len(params) > 0:
                text = self._to_string(params[0])
                if text is not None and self._is_extractable_runtime_text(text, is_dialogue=True):
                    tag = "message_dialogue"
                    # Autonomous Detection: Engine face OR active picture bust OR plugin tags
                    has_face = self._last_face_name or getattr(self, '_active_picture_bust', False)
                    # Common Ruby Message tags: \f[, \face[, \n<, \P[, \face_id, \face_name
                    has_plugin_tag = any(x in text for x in ["\\f[", "\\face[", "\\n<", "\\P[", "\\face_id", "\\face_name"])
                    
                    if has_face or has_plugin_tag:
                        tag += "/hasPicture"
                        
                    self._append_extracted(f"{path}.@parameters.0", text, tag)
        
        # Show Text Header (101)
        elif code == 101:
            if len(params) >= 1:
                self._last_face_name = self._to_string(params[0]) or ""
        
        # Scroll Text Header (105): marks beginning of scroll text block; no user-visible text
        elif code == 105:
            pass  # No extractable content; scroll lines are handled via code 405 bundling
                
        elif code == 231: # Show Picture
            self._active_picture_bust = True
            
        elif code == 235: # Erase Picture (code 232 is Move Picture, not erase)
            self._active_picture_bust = False
        
        # Show Choices (102)
        elif code == 102:
            if len(params) > 0 and isinstance(params[0], list):
                for i, choice in enumerate(params[0]):
                    text = self._to_string(choice)
                    if text is not None and self._is_extractable_runtime_text(text, is_dialogue=True):
                        self._append_extracted(f"{path}.@parameters.0.{i}", text, "choice")
        
        # When [Choice] (402): params[1] is the choice branch label text
        elif code == 402:
            if len(params) > 1:
                text = self._to_string(params[1])
                if text is not None and self._is_extractable_runtime_text(text, is_dialogue=True):
                    self._append_extracted(f"{path}.@parameters.1", text, "choice")
        
        # Comment (108/408)
        elif code in [108, 408] and self.translate_comments:
            if len(params) > 0:
                text = self._to_string(params[0])
                if text is not None and self.looks_like_translatable_comment(text) and self._is_extractable_runtime_text(text, is_dialogue=True):
                    self._append_extracted(f"{path}.@parameters.0", text, "comment")
        
        elif code in [320, 324]:
            if len(params) > 1:
                text = self._to_string(params[1])
                if text is not None and self._is_extractable_runtime_text(text, is_dialogue=True):
                    self._append_extracted(f"{path}.@parameters.1", text, "name")
        
        # Change Profile (325)
        elif code == 325:
            if len(params) > 1:
                text = self._to_string(params[1])
                if text is not None and self._is_extractable_runtime_text(text, is_dialogue=True):
                    self._append_extracted(f"{path}.@parameters.1", text, "name")

    def _append_extracted(self, path: str, text: str, tag: str) -> None:
        self.extracted.append((path, text, tag))
        self._extracted_tag_map[path] = tag

    def _get_ruby_context(self, path: str) -> str:
        """Derive context string from path using the context map."""
        if not path:
            return self._current_context_map.get("ROOT", "")
            
        parts = path.lstrip('.').split('.')
        if not parts:
            return ""
            
        # Try full match: events.1
        if len(parts) >= 2:
            full_hit = self._current_context_map.get(f"{parts[0]}.{parts[1]}")
            if full_hit:
                return full_hit
                
        # Try root hit: 1 (Actors list)
        root_hit = self._current_context_map.get(parts[0])
        if root_hit:
            return root_hit
            
        return self._current_context_map.get("ROOT", "")

    def _to_string(self, val: Any) -> str | None:
        """Convert a value to string, handling bytes and common encodings."""
        if isinstance(val, Symbol):
            return None # Symbols are technical identifiers, never translatable text
        if isinstance(val, str):
            return val
        elif isinstance(val, bytes):
            return self._decode_ruby_bytes(val)[0]
        elif isinstance(val, RubyString):
            # RubyString may hold raw bytes with legacy encoding; decode properly
            if hasattr(val, 'value') and isinstance(val.value, bytes):
                decoded, _ = self._decode_ruby_bytes(val.value)
                return decoded
            return str(val)
        elif getattr(val, "ruby_class_name", None) == "str" and hasattr(val, "text"):
            return str(val.text)
        return None

    def _should_extract_ruby_attr_value(self, attr_key: str, text_val: str, path: str) -> bool:
        """Return True when a Ruby attribute is a safe text surface."""
        normalized_key = attr_key.lstrip('@')
        file_key = self._ruby_file_policy_key()

        if self._is_protected_ruby_file():
            return False

        if normalized_key == 'note' and not self.translate_notes:
            return False

        if self._surface_registry.is_asset_key(normalized_key) or self._surface_registry.is_technical_key(normalized_key):
            return False

        # Explicit allow for Map display names
        if file_key.startswith('map') and normalized_key == 'display_name':
             return self._is_extractable_runtime_text(text_val, is_dialogue=True, attr_key=normalized_key)

        # Skip non-allowlisted map content (event commands are handled by _walk_command_list)
        if file_key.startswith('map'):
            if file_key not in self.RUBY_FILE_ATTR_ALLOWLIST:
                return False

        allowed_attrs = self.RUBY_FILE_ATTR_ALLOWLIST.get(file_key)
        if allowed_attrs is not None:
            if file_key == 'system' and ('.@terms.' in path or '.@words.' in path or path.startswith('@terms.') or path.startswith('@words.')):
                return self._is_extractable_runtime_text(text_val, is_dialogue=True, attr_key=normalized_key)
            if normalized_key not in allowed_attrs:
                return False
            return self._is_extractable_runtime_text(text_val, is_dialogue=(normalized_key != 'note'), attr_key=normalized_key)

        if normalized_key in {'name', 'nickname', 'display_name', 'title', 'game_title', 'currency_unit', 'description', 'help', 'message', 'message1', 'message2', 'message3', 'message4', 'text', 'msg'}:
            return self._is_extractable_runtime_text(text_val, is_dialogue=(normalized_key != 'note'), attr_key=normalized_key)

        if self._surface_registry.is_text_key(normalized_key):
            return self._is_extractable_runtime_text(text_val, is_dialogue=(normalized_key != 'note'), attr_key=normalized_key)

        return self._looks_like_textual_value(text_val)

    def _ruby_file_policy_key(self) -> str:
        """Return the normalized file key used by structured Ruby extraction policy."""
        return self._current_file_basename.lower()

    def _is_protected_ruby_file(self) -> bool:
        """Return True for Ruby files that should not be generically translated."""
        return self._ruby_file_policy_key() in self.PROTECTED_RUBY_FILES

    def _is_ruby_system_runtime_text_path(self, path: str) -> bool:
        """Return True when a path belongs to safe nested Ruby System text surfaces."""
        if self._ruby_file_policy_key() != 'system':
            return False
        return (
            '.@terms.' in path
            or '.@words.' in path
            or path.startswith('@terms.')
            or path.startswith('@words.')
        )

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

    def _decode_ruby_bytes(self, val: bytes) -> tuple[str | None, str | None]:
        """Decode Ruby bytes and return the detected text plus encoding.
        
        Returns (None, None) when encoding detection has zero confidence
        (i.e. absolute utf-8 replace-mode fallback) to prevent garbled
        '?' characters from entering the translation pipeline.
        """
        if not isinstance(val, bytes):
            return None, None

        info = _safe_decode_ruby_string(val)
        if info.confidence == 0.0:
            logger.debug(f"Skipping low-confidence bytes (len={len(val)}): encoding undetermined")
            return None, None
        return info.text, info.encoding

    def _safe_decode_ruby_string_with_info(self, val: Any) -> RubyStringInfo:
        """Decode Ruby string value with full encoding metadata using RubyStringInfo."""
        return _safe_decode_ruby_string(val)

    def _deep_copy_ruby_data(self, data: Any) -> Any:
        """Create a deep copy of Ruby Marshal data for modification."""
        memo: dict[int, Any] = {}

        def clone(value: Any) -> Any:
            value_id = id(value)
            if value_id in memo:
                return memo[value_id]

            if isinstance(value, (str, bytes, int, float, bool, type(None))):
                return value

            if isinstance(value, list):
                copied_list: list[Any] = []
                memo[value_id] = copied_list
                copied_list.extend(clone(item) for item in value)
                return copied_list

            if isinstance(value, tuple):
                copied_tuple = tuple(clone(item) for item in value)
                memo[value_id] = copied_tuple
                return copied_tuple

            if isinstance(value, set):
                copied_set: set[Any] = set()
                memo[value_id] = copied_set
                for item in value:
                    copied_set.add(clone(item))
                return copied_set

            if isinstance(value, dict):
                copied_dict: dict[Any, Any] = {}
                memo[value_id] = copied_dict
                for key, item in value.items():
                    copied_dict[clone(key)] = clone(item)
                return copied_dict

            if hasattr(value, "__dict__"):
                try:
                    cloned_object = value.__class__.__new__(value.__class__)
                except Exception:
                    return value

                memo[value_id] = cloned_object
                for key, item in value.__dict__.items():
                    setattr(cloned_object, key, clone(item))
                return cloned_object

            return value

        return clone(data)

    def apply_translation(self, file_path: str, translations: dict[str, str], original_data: Any = None) -> Any:
        """
        Apply translations back to the Ruby Marshal file.
        
        For non-script containers, attempts binary patching first (preserves exact
        Marshal structure). Falls back to the legacy deserialize-modify-reserialize
        path if binary patching is unavailable.
        
        Returns:
            - bytes: Binary-patched raw data (ready for direct file write)
            - Any: Deserialized data for script containers (needs rubymarshal.writer)
            - None: On failure
        """
        self.last_apply_error = None
        self._known_asset_identifiers = self._get_known_asset_identifiers(file_path)
        self._current_file_basename = os.path.splitext(os.path.basename(file_path))[0].lower()
        self._current_file_ext = os.path.splitext(file_path)[1].lower()

        # Detect script containers early — they need the legacy path
        if original_data is not None:
            data = original_data
        else:
            data = self._load_ruby_marshal(file_path)

        is_scripts = self._is_script_container(data)

        if is_scripts:
            if not self.allow_script_translation:
                logger.info("Skipping Scripts.rvdata2 write to preserve runtime stability.")
                self.last_apply_error = "Script container write disabled by default"
                return None
            data_copy = self._deep_copy_ruby_data(data)
            original_for_check = self._deep_copy_ruby_data(data)
            data_copy = self._apply_scripts_translation(data_copy, translations)
            asset_violations = self._find_asset_mutations(original_for_check, data_copy)
            if asset_violations:
                joined = ", ".join(asset_violations[:5])
                self.last_apply_error = f"Asset invariant violation: {joined}"
                return None
            return data_copy

        # --- Binary patching path (non-script files) ---
        raw_bytes = getattr(self, '_last_raw_bytes', None)
        if raw_bytes is None:
            try:
                with open(file_path, 'rb') as f:
                    raw_bytes = f.read()
            except OSError:
                raw_bytes = None

        binary_patched = False
        if raw_bytes is not None and len(raw_bytes) >= 2 and raw_bytes[:2] == b'\x04\x08':
            try:
                from src.core.parsers.marshal_binary_patcher import patch_marshal_file
                patched = patch_marshal_file(raw_bytes, translations)
                if patched is not None:
                    return patched
                # None means no patches matched — fall through to legacy
            except Exception as e:
                logger.warning("Binary patcher failed for %s: %s, using legacy path",
                              os.path.basename(file_path), e)

        # --- Legacy fallback (deserialize-modify-reserialize) ---
        # `data` was already loaded above; deep-copy for mutation
        original_for_check = self._deep_copy_ruby_data(data)
        data = self._deep_copy_ruby_data(data)
        
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
                last = keys[-1]
                self._set_value(ref, last, text)
                applied_count += 1
            except Exception as e:
                failed_paths.append(path)
        
        if failed_paths:
            logger.warning(f"Failed to apply {len(failed_paths)} translations")

        asset_violations = self._find_asset_mutations(original_for_check, data)
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

    def _apply_scripts_translation(self, scripts: list, translations: dict[str, str]) -> list:
        """Apply translations to the scripts array (re-compressing)."""
        script_trans = {}
        for path, text in translations.items():
            if ".code.string_" in path:
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
                code_bytes = zlib.decompress(compressed_code)
                code_text, detected_encoding = self._decode_ruby_bytes(code_bytes)
                if code_text is None:
                    continue
                tokens = self._tokenize_ruby_script(code_text)
                replacements = []
                for path, new_text in script_trans[idx]:
                    match_idx = int(path.split('_')[-1])
                    if match_idx < len(tokens):
                        start, end, _content, qs = tokens[match_idx]
                        escaped_text = new_text.replace('\\', '\\\\')
                        escaped_text = escaped_text.replace(qs, '\\' + qs)
                        replacement = f"{qs}{escaped_text}{qs}"
                        replacements.append((start, end, replacement))
                replacements.sort(key=lambda x: x[0], reverse=True)
                new_code_list = list(code_text)
                for start, end, rep_text in replacements:
                    new_code_list[start:end] = list(rep_text)
                new_code_text = "".join(new_code_list)
                output_encoding = detected_encoding or 'utf-8'
                new_bytes = zlib.compress(new_code_text.encode(output_encoding, errors='replace'))
                scripts[idx][2] = new_bytes
            except Exception as e:
                logger.error(f"Failed to apply translations to script {idx}: {e}")
        return scripts

    def _traverse_key(self, ref: Any, key: str) -> Any:
        """Traverse to a key in the object structure."""
        if key.isdigit():
            return ref[int(key)]
        if key.startswith('@'):
            attr_name = key[1:]
            if isinstance(ref, dict):
                return ref.get(attr_name) or ref.get(key)
            elif hasattr(ref, 'attributes'):
                attrs = ref.attributes
                for k in [attr_name, key, attr_name.encode('utf-8'), key.encode('utf-8')]:
                    if k in attrs: return attrs[k]
                return None
        if isinstance(ref, dict):
            return ref[key]
        elif isinstance(ref, list):
            return ref[int(key)]
        elif hasattr(ref, 'attributes'):
            return ref.attributes.get(key)
        else:
            return getattr(ref, key)

    def _set_value(self, ref: Any, key: str, value: str):
        """Set a value in the object structure, handling bundled ranges and encodings."""
        if self.BUNDLED_PATH_MARKER in str(key):
            # Range path: e.g., 6_bundled_9 or @parameters.6_bundled_9
            clean_key = str(key).lstrip('@')
            self._apply_bundled_translation(ref, clean_key, value)
            return

        final_value: Any = value
        def encode_like_original(original: Any, text: str) -> Any:
            info = _safe_decode_ruby_string(original)
            encoding = info.encoding or 'utf-8'
            try:
                return text.encode(encoding)
            except (UnicodeEncodeError, LookupError):
                return text.encode('utf-8')
        if key.isdigit():
            idx = int(key)
            if idx < len(ref) and isinstance(ref[idx], bytes):
                final_value = encode_like_original(ref[idx], value)
            ref[idx] = final_value
            return
        if key.startswith('@'):
            attr_name = key[1:]
            if isinstance(ref, dict):
                orig_key = attr_name if attr_name in ref else key
                if isinstance(ref.get(orig_key), bytes):
                    final_value = encode_like_original(ref[orig_key], value)
                ref[orig_key] = final_value
            elif hasattr(ref, 'attributes'):
                attrs = ref.attributes
                orig_key = None
                for k in [attr_name, key, attr_name.encode('utf-8'), key.encode('utf-8')]:
                    if k in attrs:
                        orig_key = k
                        break
                if orig_key is None: orig_key = key.encode('utf-8')
                if isinstance(attrs.get(orig_key), bytes):
                    final_value = encode_like_original(attrs[orig_key], value)
                attrs[orig_key] = final_value
            return

        if isinstance(ref, dict):
            if isinstance(ref.get(key), bytes):
                final_value = encode_like_original(ref[key], value)
            ref[key] = final_value
        elif isinstance(ref, list):
            idx = int(key)
            if idx < len(ref) and isinstance(ref[idx], bytes):
                final_value = encode_like_original(ref[idx], value)
            ref[idx] = final_value
        elif hasattr(ref, 'attributes'):
            attrs = ref.attributes
            if isinstance(attrs.get(key), bytes):
                final_value = encode_like_original(attrs[key], value)
            attrs[key] = final_value
        else:
            try:
                setattr(ref, key, final_value)
            except Exception:
                pass

    def _apply_bundled_translation(self, ref: Any, attr_name: str, value: str):
        """Distribute bundled text back into consecutive EventCommand parameters."""
        # ref is expect to be the 'parameters' list of an EventCommand 
        # OR the list of commands itself depending on traversal.
        # But based on our walk, path was 'list.6_bundled_8', so last key is '6_bundled_8'
        # traversed as 'list' (ref), and last='6_bundled_8'
        try:
            start_s, end_s = attr_name.split(self.BUNDLED_PATH_MARKER)
            start_idx, end_idx = int(start_s), int(end_s)
            
            from src.core.constants import REGEX_INTERNAL_MERGE
            # Layer 4 Unbundling: Normalize internal separators (Obsidian v4.4: Tag-Aware)
            # Standardizes with or without <b> tags
            value = re.sub(r'(?:<b[^>]*>)?\s*[【\[\(\{\.\s]*_\s*[iI]\s*_\s*[】\]\)\}\.\s]*\s*(?:</b>)?', '【 _I_ 】', value)
            # Split using the hardened internal regex
            lines = re.split(REGEX_INTERNAL_MERGE, value, flags=re.IGNORECASE)
            
            # Layer 4 Fallback: If split failed to meaningful lines but we have newlines
            if len(lines) < (end_idx - start_idx + 1) and "\n" in value:
                lines = value.split("\n")
            
            # Target range in the commands list
            # We must be careful: if lines > original commands, we might need to inject.
            # However, for 0.6.5, we'll try to fit them or warn.
            # Stage 4 Hardening: If lines are missing but text is long, force split it
            expected_count = end_idx - start_idx + 1
            if len(lines) < expected_count and len(value) > 40:
                # Dynamically split by length to fill the message slots
                avg_len = max(20, len(value) // expected_count)
                lines = textwrap.wrap(value, avg_len, break_long_words=False) or [value]
                # If still not enough, pad with empty to clear original text
                while len(lines) < expected_count: lines.append("")
            for i in range(start_idx, end_idx + 1):
                if i >= len(ref): break
                cmd = ref[i]
                params = self._get_ruby_attr(cmd, 'parameters')
                if params and len(params) > 0:
                    line_to_set = lines[i - start_idx] if (i - start_idx) < len(lines) else None
                    
                    # Preserve encoding and AVOID EMPTY STRINGS on mismatch
                    original_val = params[0]
                    if line_to_set is None or not line_to_set.strip():
                        # Fail-safe: Keep original if translation is missing or mangled
                        continue

                    info = _safe_decode_ruby_string(original_val)
                    enc = info.encoding or 'utf-8'
                    try:
                        params[0] = line_to_set.encode(enc) if isinstance(original_val, bytes) else line_to_set
                    except:
                        params[0] = line_to_set.encode('utf-8') if isinstance(original_val, bytes) else line_to_set
        except Exception as e:
            logger.error(f"Failed to apply bundled translation: {e}")

    def _tokenize_ruby_script(self, code: str) -> list[tuple[int, int, str, str]]:
        """
        Tokenize Ruby script to find string literals.
        """
        if self._ruby_parser is not None:
            parsed_tokens = self._tokenize_ruby_script_with_tree_sitter(code)
            if parsed_tokens:
                return parsed_tokens
        tokens = []
        STATE_NORMAL, STATE_SINGLE_QUOTE, STATE_DOUBLE_QUOTE, STATE_COMMENT = 0, 1, 2, 3
        state = STATE_NORMAL
        i, start_quote = 0, -1
        length = len(code)
        while i < length:
            char = code[i]
            if state == STATE_NORMAL:
                if char == '#':
                    state = STATE_COMMENT
                elif char == "'":
                    state, start_quote = STATE_SINGLE_QUOTE, i
                elif char == '"':
                    state, start_quote = STATE_DOUBLE_QUOTE, i
            elif state == STATE_COMMENT:
                if char == '\n':
                    state = STATE_NORMAL
            elif state == STATE_SINGLE_QUOTE:
                if char == '\\': i += 1
                elif char == "'":
                    tokens.append((start_quote, i+1, code[start_quote+1:i], "'"))
                    state = STATE_NORMAL
            elif state == STATE_DOUBLE_QUOTE:
                if char == '\\': i += 1
                elif char == '"':
                    tokens.append((start_quote, i+1, code[start_quote+1:i], '"'))
                    state = STATE_NORMAL
            i += 1
        return tokens

    def _build_ruby_language(self):
        """Build tree-sitter language for Ruby scripts."""
        if Language is None:
            return None
        try:
            import tree_sitter_ruby
            return Language(tree_sitter_ruby.language())
        except Exception:
            return None

    def _tokenize_ruby_script_with_tree_sitter(self, code: str) -> list[tuple[int, int, str, str]]:
        parser = self._ruby_parser
        if parser is None:
            return []
        source_bytes = code.encode("utf-8")
        tree = parser.parse(source_bytes)
        tokens: list[tuple[int, int, str, str]] = []
        for node in self._iter_ruby_string_nodes(tree.root_node):
            raw_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")
            if not raw_text or self._ruby_string_has_interpolation(node):
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
        if len(raw_text) < 2: return raw_text
        if quote == "'": return raw_text[1:-1]
        try:
            return ast.literal_eval(raw_text)
        except Exception:
            return raw_text[1:-1]

    def _is_valid_script_string(self, text: str) -> bool:
        """Validate if a script string is worth translating."""
        if not self._is_extractable_runtime_text(text, is_dialogue=True):
            return False
        if not text or len(text) < 2:
            return False
        if all(char.isalnum() or char in '_-/' for char in text):
            if len(text) < 15 or any(term in text.lower() for term in ['sad', 'face', 'pic', 'spr', 'img', 'surface']):
                 return False
            return False
        if any(text.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.bmp', '.ogg', '.wav', '.mp3', '.rvdata2']):
            return False
        if text.startswith(':'): return False
        return ' ' in text or any(ord(c) > 127 for c in text)

    def _is_short_technical_word(self, text: str) -> bool:
        if not text or len(text) > 10:
            return False
        TECHNICAL = {
            'sad', 'happy', 'angry', 'cry', 'smile', 'look', 'stay', 'move',
            'basic', 'normal', 'none', 'auto', 'wait', 'test', 'item', 'skill',
            'actor', 'enemy', 'map', 'face', 'bgm', 'bgs', 'se', 'me', 'id',
            'start', 'stop', 'play', 'hit', 'damage', 'dead', 'active', 'passive'
        }
        stripped = text.lower().strip()
        return stripped in TECHNICAL or re.fullmatch(r'^[a-z_0-9]+$', stripped)

    def _is_extractable_runtime_text(self, text: str | None, *, is_dialogue: bool = False, attr_key: str | None = None) -> bool:
        if not isinstance(text, str): return False
        if attr_key:
            k = attr_key.lower()
            if any(term in k for term in ['name', 'graphic', 'face', 'character', 'battler', 'icon', 'se', 'bgm', 'me', 'bgs', 'image', 'picture', 'bitmap']):
                if k in ['name', 'nickname', 'display_name', 'title'] and not any(term in k for term in ['character', 'face', 'battler', 'graphic']):
                    pass
                else: return False
        # If it's explicitly marked as dialogue (Show Text, Choice), we bypass most safety filters
        # because these are guaranteed to be player-visible.
        if is_dialogue:
            # Only skip if it's very short and looks like a system marker or asset path
            # Only skip if it's exceptionally short (1 char) and ASCII
            if len(text) < 2 and text.isascii():
                return False
            # Still check for basic control code only strings
            if self.contains_only_control_codes(text):
                return False
            # Some games route portrait/face/asset identifiers through Show Text commands.
            # Keep normal prose, but skip single-token asset ids before they reach save-time invariants.
            stripped = text.strip()
            if stripped and self._matches_known_asset_identifier(stripped):
                if "\n" not in stripped and not self._is_likely_dialogue(stripped):
                    return False
            return True

        if not self.is_safe_to_translate(text, is_dialogue=is_dialogue):
            return False
        normalized = text.replace("\\", "/").lower()
        if "graphics/" in normalized or "audio/" in normalized:
            return False
        if re.search(r'<[^>]+:?\s*[^>]+>', text) and text.startswith('<') and text.endswith('>'):
            return False
        if not is_dialogue and self._is_short_technical_word(text):
            return False
        return not (self._contains_asset_reference(text) or self._matches_known_asset_identifier(text))

    @staticmethod
    def _normalize_asset_text(text: str) -> str:
        return normalize_asset_text(text)

    def _contains_asset_reference(self, text: str) -> bool:
        return contains_explicit_asset_reference(text, self.ASSET_FILE_EXTENSIONS) or contains_asset_tuple_reference(text)

    def _matches_known_asset_identifier(self, text: str) -> bool:
        if not isinstance(text, str) or not text.strip() or not self._known_asset_identifiers:
            return False
        candidates = asset_identifier_candidates(text)
        return any(candidate in self._known_asset_identifiers for candidate in (candidates or []))

    def _get_known_asset_identifiers(self, file_path: str) -> set[str]:
        asset_root = self._find_asset_root(file_path)
        if not asset_root: return set()
        normalized_root = os.path.normcase(os.path.abspath(asset_root))
        with _RUBY_ASSET_REGISTRY_LOCK:
            cached = _RUBY_ASSET_REGISTRY_CACHE.get(normalized_root)
            if cached is not None: return cached
        identifiers: set[str] = set()
        for directory_name in self.ASSET_SCAN_DIRS:
            directory_path = os.path.join(asset_root, directory_name)
            if not os.path.isdir(directory_path): continue
            for root, _dirs, files in os.walk(directory_path):
                for filename in files:
                    full_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(full_path, asset_root).replace("\\", "/").lower()
                    rel_scan = os.path.relpath(full_path, directory_path).replace("\\", "/").lower()
                    for v in [rel_path, rel_scan, os.path.basename(full_path).lower()]:
                        identifiers.add(v); identifiers.add(fuzzy_asset_normalize(v))
                        stem, _ = os.path.splitext(v)
                        if stem: identifiers.add(stem); identifiers.add(fuzzy_asset_normalize(stem))
                    parts = rel_path.split('/')
                    if len(parts) > 1:
                        for i in range(1, len(parts)):
                            suffix = "/".join(parts[i:])
                            identifiers.add(suffix); identifiers.add(fuzzy_asset_normalize(suffix))
        data_root = os.path.join(asset_root, "data")
        if os.path.isdir(data_root):
            for data_file in os.listdir(data_root):
                if data_file.lower().endswith(('.rvdata2', '.rxdata', '.rvdata')):
                    try:
                        with open(os.path.join(data_root, data_file), 'rb') as f:
                            content = f.read()
                            for m in re.findall(b'[a-zA-Z0-9_/\\\\]{3,40}', content):
                                try:
                                    s = m.decode('ascii').lower()
                                    if '/' in s or '\\' in s or len(s) < 15: identifiers.add(s); identifiers.add(fuzzy_asset_normalize(s))
                                except: continue
                            for m in re.findall(b'[a-zA-Z0-9_/\\\\]+\\.(?:png|jpg|jpeg|gif|bmp|ogg|wav|mp3|m4a|webm|mp4)', content, re.IGNORECASE):
                                try:
                                    s = m.decode('ascii').lower()
                                    identifiers.add(s); identifiers.add(fuzzy_asset_normalize(s))
                                    identifiers.add(s.split('.')[0]); identifiers.add(fuzzy_asset_normalize(s.split('.')[0]))
                                except: continue
                    except: continue
        with _RUBY_ASSET_REGISTRY_LOCK: _RUBY_ASSET_REGISTRY_CACHE[normalized_root] = identifiers
        return identifiers

    def _find_asset_root(self, file_path: str) -> str | None:
        abs_path = os.path.abspath(file_path)
        current_dir = os.path.dirname(abs_path)
        for _ in range(8):
            if self._looks_like_asset_root(current_dir): return current_dir
            for sub in ["www", "game", "package"]:
                if self._looks_like_asset_root(os.path.join(current_dir, sub)): return os.path.join(current_dir, sub)
            parent_dir = os.path.dirname(current_dir)
            if parent_dir == current_dir: break
            current_dir = parent_dir
        if "data" in abs_path.lower():
            root_candidate = abs_path.lower().split("data")[0]
            if os.path.isdir(root_candidate) and self._looks_like_asset_root(root_candidate): return root_candidate
        return None

    def _looks_like_asset_root(self, directory: str) -> bool:
        if not directory or not os.path.isdir(directory): return False
        return any(os.path.isdir(os.path.join(directory, child)) for child in self.ASSET_SCAN_DIRS)

    def _find_asset_mutations(self, original: Any, updated: Any) -> list[str]:
        violations: list[str] = []
        visited: set[tuple[int, int]] = set()
        self._walk_asset_differences(original, updated, "", visited, violations)
        return violations

    def _walk_asset_differences(self, original: Any, updated: Any, current_path: str, visited: set[tuple[int, int]], violations: list[str]) -> None:
        pair_id = (id(original), id(updated))
        if pair_id in visited: return
        visited.add(pair_id)
        original_text, updated_text = self._to_string(original), self._to_string(updated)
        if original_text is not None and updated_text is not None:
            # Check if this deviation is actually a violation
            is_potential_violation = (self._contains_asset_reference(original_text) or self._matches_known_asset_identifier(original_text))
            
            if is_potential_violation and original_text != updated_text:
                # EXEMPTION: Whitelisted text fields are allowed to change even if they collide with asset names.
                if self._is_whitelisted_text_path(current_path, original_text):
                    return

                violations.append(current_path or "<root>")
            return
        if type(original) is not type(updated): return
        if isinstance(original, list):
            for index, (left, right) in enumerate(zip(original, updated)):
                self._walk_asset_differences(left, right, f"{current_path}.{index}" if current_path else str(index), visited, violations)
        elif isinstance(original, dict):
            for key in original.keys() & updated.keys():
                child_path = f"{current_path}.{self._path_key(key)}" if current_path else self._path_key(key)
                self._walk_asset_differences(original[key], updated[key], child_path, visited, violations)
        elif hasattr(original, 'attributes') and hasattr(updated, 'attributes'):
            oa, ua = original.attributes, updated.attributes
            for key in oa.keys() & ua.keys():
                child_path = f"{current_path}.{self._path_key(key)}" if current_path else self._path_key(key)
                self._walk_asset_differences(oa[key], ua[key], child_path, visited, violations)
        elif hasattr(original, '__dict__') and hasattr(updated, '__dict__'):
            oi, ui = {k: v for k, v in original.__dict__.items() if not k.startswith('_')}, {k: v for k, v in updated.__dict__.items() if not k.startswith('_')}
            for key in oi.keys() & ui.keys():
                self._walk_asset_differences(oi[key], ui[key], f"{current_path}.{key}" if current_path else key, visited, violations)

    def _path_key(self, key: Any) -> str:
        text = self._to_string(key)
        return text if text is not None else str(key)

    def _is_whitelisted_text_path(self, path: str, text: str = "") -> bool:
        """
        Determines if a path belongs to a safe-to-translate text field.
        Enhanced for 0.6.5 to prevent false-positive save blocks.
        """
        if not path:
            return False

        # 1. Direct tag map lookup (Fastest)
        if self._extracted_tag_map.get(path, "").startswith(("message_dialogue", "choice", "comment", "scroll_text")):
            return True

        # 2. Path-based analysis (Most robust for 'apply' phase)
        parts = {p.lstrip('@') for p in path.split('.')}
        
        # Known safe RM database clusters
        safe_fields = {
            'name', 'nickname', 'description', 'profile', 'display_name', 
            'help', 'message1', 'message2', 'message3', 'message4',
            'game_title', 'currency_unit', 'text', 'msg', 'message',
            'parameters'
        }
        
        # If the path contains ANY recognized text parameter, it's safe
        if any(safe in parts for safe in safe_fields):
            return True

        # 3. Content Heuristics (Final defense for natural language)
        if text:
            # If it has spaces or RM codes, it's dialogue, not a 8.3 filename
            if ' ' in text.strip() or '\\' in text or any(c in text for c in '.!?,;:。！？'):
                return True
            # If it contains non-ASCII characters, it's clearly translated text
            if any(ord(c) > 127 for c in text):
                return True

        return False

    def _get_bundled_tag_for_path(self, path: str) -> str:
        match = re.match(r'^(.*?\.@list\.)(\d+)\.(@parameters\.0(?:\.\d+)?)$', path)
        if not match:
            return ""

        prefix, index_text, _suffix = match.groups()
        try:
            index = int(index_text)
        except ValueError:
            return ""

        for extracted_path, tag in self._extracted_tag_map.items():
            bundled_match = re.match(r'^(.*?\.@list\.)(\d+)_bundled_(\d+)$', extracted_path)
            if not bundled_match:
                continue
            bundled_prefix, start_text, end_text = bundled_match.groups()
            if bundled_prefix != prefix:
                continue
            start_idx = int(start_text)
            end_idx = int(end_text)
            if start_idx <= index <= end_idx:
                return tag

        return ""

    def _is_likely_dialogue(self, text: str) -> bool:
        """Heuristic to determine if a string is dialogue rather than an ID/Filename."""
        if not text or not isinstance(text, str): return False
        
        # Dialouge usually has spaces or sentence endings
        if ' ' in text.strip(): return True
        if any(p in text for p in '.!?,:;"\''): return True
        
        # If it contains engine codes like \V[n] or \C[n], it's dialogue
        if '\\' in text and any(c in text.upper() for c in 'VCNPGIS'): return True
        
        return False

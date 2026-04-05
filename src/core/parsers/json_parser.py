"""
JSON Parser for RPG Maker MV/MZ games.
Handles extraction and injection of translatable text from JSON data files.
"""
import json
import os
import re
import logging
import copy
import threading
from typing import List, Dict, Any, Tuple, Set
from .base import BaseParser
from .specialized_plugins import get_specialized_parser
from .js_tokenizer import JSStringTokenizer
from .plugin_metadata import PluginMetadataStore, PluginFileMetadata, PluginParameterMetadata
from .json_field_rules import is_protected_structured_noop_file
from .structured_json_extractor import StructuredJsonExtractor
from .technical_invariants import JsonAssetInvariantVerifier, JsonTechnicalInvariantVerifier

logger = logging.getLogger(__name__)

_ASSET_REGISTRY_CACHE: Dict[str, Set[str]] = {}
_ASSET_REGISTRY_LOCK = threading.Lock()

class JsonParser(BaseParser):
    """
    Parser for RPG Maker MV/MZ JSON files.
    Supports: Actors, Items, Skills, Weapons, Armors, Enemies, States, 
              CommonEvents, Maps, System, and deeply nested Plugin Parameters.
    """
    
    # Event codes that contain translatable text
    TEXT_EVENT_CODES = {
        101: 'show_text_header',    # Show Text (face, position settings) - params may have face name
        401: 'show_text',           # Show Text line
        102: 'show_choices',        # Show Choices
        405: 'scroll_text',         # Scroll Text line
        108: 'comment',             # Comment (often plugin commands with text)
        408: 'comment_cont',        # Comment continuation
        320: 'change_name',         # Change Actor Name
        324: 'change_nickname',     # Change Actor Nickname
        325: 'change_profile',      # Change Actor Profile
        356: 'plugin_command',      # Plugin Command (MV style - text in params)
        357: 'plugin_command_mz',   # Plugin Command (MZ style - may have text)
        655: 'script_line',         # Script (multi-line) - risky but sometimes has text
        355: 'script_single',       # Script (single) - only if contains strings
        402: 'choice_when',         # When [Choice]
        403: 'choice_cancel',       # When Cancel
        105: 'scroll_text_header',  # Scroll Text settings (MZ might have title)
        657: 'plugin_command_mz_cont',  # Plugin Command MZ continuation
        # Commented out: Labels, Jump to Label, Control Variables can break branching logic when translated
        # 118: 'label',               
        # 119: 'jump_to_label',       
        # 122: 'control_variables',   
    }
    
    # Database fields that are always translatable
    DATABASE_FIELDS = {
        'name', 'description', 'nickname', 'profile',
        'message1', 'message2', 'message3', 'message4',
        'gameTitle', 'title', 'message', 'help', 'text', 'msg', 'dialogue',
        'label', 'format', 'string', 'prefix', 'suffix', 'commandName',
        'displayName',  # Map display names
        'currencyUnit',  # Currency unit in System.json
        'battleName',  # Battle background name (sometimes text)
    }
    
    # System terms and lists that should be translated
    SYSTEM_TERMS = {
        'basic', 'commands', 'params', 'messages',
        'elements', 'skillTypes', 'weaponTypes', 'armorTypes', 'equipTypes',
        'terms', 'types',
        # Additional MV/MZ system arrays
        'etypeNames', 'stypeNames', 'wtypeNames', 'atypeNames',
    }
    
    # Fields to skip (internal use, not for translation)
    SKIP_FIELDS = {
        'id', 'animationId', 'characterIndex', 'characterName',
        'faceName', 'faceIndex', 'tilesetId', 'battleback1Name',
        'battleback2Name', 'bgm', 'bgs', 'se', 'me', 'parallaxName',
        'title1Name', 'title2Name',
        'locale',  # Technical locale identifier such as en_US / tr_TR
        'note',  # Skip note by default (often contains plugin data)
    }

    # Keys whose presence (alongside 'name') signals an audio/sound spec object.
    _SOUND_SPEC_AUDIO_KEYS = frozenset({'volume', 'pitch', 'pan'})
    _ASSET_CONTEXT_PATH_HINTS = frozenset({
        'audio', 'sound', 'voice', 'bgm', 'bgs', 'se', 'me',
        'movie', 'movies', 'video',
        'img', 'image', 'picture', 'face', 'character', 'battler',
        'tileset', 'parallax', 'battleback', 'title1', 'title2',
        'icon', 'filename', 'file',
    })
    
    # Expanded key patterns that commonly indicate translatable text in plugin parameters
    TEXT_KEY_INDICATORS = [
        'text', 'message', 'name', 'format', 'msg', 'desc',
        'title', 'label', 'caption', 'header', 'footer',
        'help', 'hint', 'tooltip', 'popup', 'notification',
        'dialogue', 'dialog', 'speech', 'talk',
        'menu', 'command', 'option', 'button',
        'string', 'content', 'display', 'info',
        'quest', 'journal', 'log', 'story',
        'victory', 'defeat', 'battle', 'escape', 'objective', 'task',
    ]

    # Asset-related key hints (likely file names / asset identifiers, not UI text)
    ASSET_KEY_HINTS = [
        'title1', 'title2', 'titles1', 'titles2',
        'battleback', 'battlebacks', 'parallax',
        'face', 'character', 'tileset', 'battler',
        'picture', 'image', 'img', 'icon', 'sprite',
        'filename', 'file',
    ]

    PLUGIN_METADATA_TECHNICAL_TYPES = {
        'actor', 'animation', 'armor', 'boolean', 'class', 'combo',
        'common_event', 'enemy', 'file', 'icon', 'item', 'location',
        'map', 'number', 'select', 'skill', 'state',
        'switch', 'tileset', 'troop', 'variable', 'weapon',
    }
    PLUGIN_METADATA_TEXT_HINTS = (
        'text', 'message', 'name', 'label', 'caption', 'title',
        'format', 'button', 'command', 'tooltip', 'help', 'unit',
    )
    PLUGIN_METADATA_ASSET_CONTEXT_HINTS = (
        'audio', 'bgm', 'bgs', 'me', 'se', 'sound',
        'image', 'img', 'picture', 'face', 'character', 'enemy',
        'actor', 'battler', 'system', 'animation', 'battleback',
        'tileset', 'parallax', 'title', 'font', 'movie', 'video',
        'icon', 'iconset', 'window',
    )
    PLUGIN_METADATA_ASSET_LIST_HINTS = (
        'preload', 'cache', 'custom files', 'file name', 'filename',
        'filepath', 'file path', 'folder', 'directory', 'without extension',
        'select a picture', 'ignore list',
    )

    # Explicitly technical keys in plugin configs
    NON_TRANSLATABLE_KEY_HINTS = [
        'switch', 'variable', 'symbol', 'condition', 'bind',
        'groupname',
        'sound', 'audio', 'bgm', 'bgs',
        'icon', 'align', 'width', 'height',
        'orientation',
        'opacity', 'speed', 'interval', 'scale', 'rate',
        'color', 'margin', 'padding', 'position', 'size',
        'volume', 'pitch', 'pan', 'duration', 'row', 'column',
        'precache', 'eval', 'script', 'code', 'regex',
    ]

    # Exact matches for short technical keys to avoid false positives (like 'me' in 'menu')
    NON_TRANSLATABLE_EXACT_KEYS = {
        'id', 'se', 'me', 'x', 'y', 'z'
    }
    INPUT_BINDING_TOKENS = {
        'ok', 'cancel', 'menu', 'shift', 'control', 'tab',
        'pageup', 'pagedown', 'up', 'down', 'left', 'right',
        'escape', 'none',
    }

    # Plugins whose parameters are entirely non-translatable (particle effects, etc.)
    # These plugins' args dicts are technical configuration, not player-visible text.
    NON_TRANSLATABLE_PLUGINS: Set[str] = {
        'TRP_ParticleMZ',
        'TRP_ParticleMZ_Preset',
        'TRP_ParticleMZ_ExRegion',
        'TRP_ParticleMZ_ExScreen',
        'TRP_ParticleMZ_Group',
        'TRP_ParticleMZ_List',
    }
    NON_TRANSLATABLE_PLUGIN_PATTERNS = [
        re.compile(r'^TRP_Particle', re.IGNORECASE),
    ]

    ASSET_FILE_EXTENSIONS = (
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tga', '.svg', '.webp',
        '.ogg', '.wav', '.m4a', '.mp3', '.mid', '.midi',
        '.webm', '.mp4', '.avi', '.mov', '.ogv', '.mkv',
        '.rpgmvp', '.rpgmvo', '.rpgmvm', '.rpgmvw'
    )

    PATH_DOT_ESCAPE = "__DOT__"
    PATH_DOT_ESCAPE_ESC = "__DOT_ESC__"
    LOCALE_LIKE_FILENAMES = {
        "translations.json",
    }
    ASSET_SCAN_DIRS = ("audio", "img", "movies", "fonts")
    LEGACY_DATABASE_NAME_FILES = {
        "actors.json",
        "armors.json",
        "classes.json",
        "enemies.json",
        "items.json",
        "skills.json",
        "states.json",
        "weapons.json",
    }
    
    def __init__(self, translate_notes: bool = False, translate_comments: bool = False, **kwargs):
        """
        Args:
            translate_notes: If True, includes 'note' fields for translation.
            translate_comments: If True, includes comments (code 108/408).
        """
        super().__init__(**kwargs)
        self.translate_notes = translate_notes
        self.translate_comments = translate_comments
        self.extracted: List[Tuple[str, str, str]] = []
        self._js_tokenizer = JSStringTokenizer()
        self._skip_fields = self.SKIP_FIELDS.copy()
        self._plugin_metadata_store: PluginMetadataStore | None = None
        self.last_apply_error: str | None = None
        self._known_asset_identifiers: Set[str] = set()
        self._structured_extractor = StructuredJsonExtractor(
            escape_path_key=self._escape_path_key,
            is_safe_to_translate=self.is_safe_to_translate,
            legacy_event_extractor=self._extract_legacy_event_entries,
            legacy_script_extractor=self._extract_legacy_script_entries,
            legacy_mz_plugin_extractor=self._extract_legacy_mz_plugin_entries,
        )
        self._invariant_verifier = JsonTechnicalInvariantVerifier(self._escape_path_key)
        self._asset_invariant_verifier = JsonAssetInvariantVerifier(
            self._escape_path_key,
            self._is_known_asset_text,
        )
        if translate_notes:
            self._skip_fields.discard('note')

    def _escape_path_key(self, key: str) -> str:
        """Escape dots in dict keys so path parsing is reversible."""
        if not isinstance(key, str):
            return str(key)
        escaped = key.replace(self.PATH_DOT_ESCAPE, self.PATH_DOT_ESCAPE_ESC)
        return escaped.replace('.', self.PATH_DOT_ESCAPE)

    def _unescape_path_key(self, key: str) -> str:
        """Restore escaped dots in dict keys."""
        if not isinstance(key, str):
            return key
        unescaped = key.replace(self.PATH_DOT_ESCAPE_ESC, self.PATH_DOT_ESCAPE)
        return unescaped.replace(self.PATH_DOT_ESCAPE, '.')
    
    def extract_text(self, file_path: str) -> List[Tuple[str, str, str]]:
        """Extract translatable text. Handles JSON, MV js/plugins.js, and locale files."""
        self._known_asset_identifiers = self._get_known_asset_identifiers(file_path)
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            content = f.read().strip()
            
        if not content:
            return []

        # Check if this is a locale file (locales/*.json - DKTools Localization etc.)
        is_locale_file = self._is_locale_file(file_path)
        
        # Handle js/plugins.js
        is_js = file_path.lower().endswith('.js')
        is_main_plugins_js = is_js and os.path.basename(file_path).lower() == 'plugins.js'
        self._plugin_metadata_store = self._build_plugin_metadata_store(file_path) if is_main_plugins_js else None
        
        self.extracted = []
        self._current_file_basename = os.path.basename(file_path).lower()
        
        if is_js:
            if is_main_plugins_js:
                prefix, json_str, suffix = self._extract_js_json(content)
                if prefix and json_str:
                    try:
                        data = json.loads(json_str)
                    except json.JSONDecodeError as e:
                         logger.error(f"Failed to parse JSON in {file_path}: {e}")
                         return []
                else:
                    self.log_message.emit("warning", f"Skipping {os.path.basename(file_path)}: Unknown plugins.js format")
                    return []
            else:
                self._extract_from_js_source(content)
                return self.extracted
        else:
            if not self._looks_like_json_document(content):
                logger.info(
                    "Skipping non-JSON sidecar file %s: content does not start with '{' or '['",
                    file_path,
                )
                return []
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON file {file_path}: {e}")
                return []
        
        # Handle locale files specially (simple key-value format)
        if is_locale_file:
            self._extract_from_locale(data)
        elif is_main_plugins_js:
             self._extract_from_plugins_js(data)
        elif self._structured_extractor.supports_file(file_path):
            self._structured_extractor.extract(file_path, data, self.extracted)
            if self.translate_notes and not is_protected_structured_noop_file(file_path):
                self._extract_structured_note_entries(data, "", self.extracted)
        else:
            self._walk(data, "")
        
        return self.extracted
    
    def _is_locale_file(self, file_path: str) -> bool:
        """Check if this is a locale file from DKTools or similar plugins."""
        # Normalize path separators and check if 'locales' folder is in path
        normalized = file_path.replace('\\', '/').lower()
        if '/locales/' in normalized and file_path.lower().endswith('.json'):
            return True
        return os.path.basename(file_path).lower() in self.LOCALE_LIKE_FILENAMES

    def _extract_from_locale(self, data: Any, current_path: str = "") -> None:
        """Extract text from locale-like files, supporting nested dict/list structures."""
        if isinstance(data, dict):
            for key, value in data.items():
                safe_key = self._escape_path_key(str(key))
                next_path = f"{current_path}.{safe_key}" if current_path else safe_key
                self._extract_from_locale(value, next_path)
            return

        if isinstance(data, list):
            for index, value in enumerate(data):
                next_path = f"{current_path}.{index}" if current_path else str(index)
                self._extract_from_locale(value, next_path)
            return

        if not isinstance(data, str):
            return

        text = data.strip()
        if not text:
            return

        # Skip very short ASCII values (likely just symbols), but keep valid
        # single-character localized entries such as CJK locale labels.
        if len(text) <= 1 and text.isascii():
            return

        if self._contains_asset_reference(text):
            return
        if self._matches_known_asset_identifier(text):
            return
        if self._is_technical_string(text):
            return

        self.extracted.append((current_path, data, "system"))

    def _looks_like_json_document(self, content: str) -> bool:
        """Return True when a .json file appears to contain an object/array document."""
        if not isinstance(content, str):
            return False
        stripped = content.lstrip("\ufeff \t\r\n")
        return stripped.startswith(("{", "["))

    def _extract_from_plugins_js(self, data: List[Dict]):
        """Extract text from plugins.js using specialized parsers where available."""
        if not isinstance(data, list):
            return

        for i, plugin in enumerate(data):
            if not isinstance(plugin, dict):
                continue
                
            name = plugin.get('name', '')
            status = plugin.get('status', False)
            parameters = plugin.get('parameters', {})
            
            # Skip known non-translatable plugins entirely
            if self._is_non_translatable_plugin(name):
                continue
            
            # Check for specialized parser
            specialized_parser = get_specialized_parser(name)
            
            if specialized_parser:
                logger.info(f"Using specialized parser for plugin: {name}")
                extracted_params = specialized_parser.extract_parameters(parameters, f"{i}.parameters")
                self.extracted.extend(extracted_params)
            else:
                metadata = self._plugin_metadata_store.get(name) if self._plugin_metadata_store else None
                if metadata:
                    self._extract_plugin_parameters(parameters, f"{i}.parameters", metadata)
                else:
                    # Fallback to generic walk for parameters
                    self._walk(parameters, f"{i}.parameters")

    def _build_plugin_metadata_store(self, file_path: str) -> PluginMetadataStore | None:
        """Create a metadata store for sibling js/plugins sources."""
        plugins_dir = os.path.join(os.path.dirname(file_path), "plugins")
        if not os.path.isdir(plugins_dir):
            return None
        return PluginMetadataStore(plugins_dir)

    def _extract_plugin_parameters(
        self,
        parameters: Any,
        base_path: str,
        plugin_metadata: PluginFileMetadata,
    ) -> None:
        """Extract plugin parameters using plugin header metadata when available."""
        if not isinstance(parameters, dict):
            self._walk(parameters, base_path)
            return

        for key, value in parameters.items():
            safe_key = self._escape_path_key(key)
            param_path = f"{base_path}.{safe_key}"
            param_metadata = plugin_metadata.get_param(key)
            self._extract_plugin_parameter_value(value, param_path, key, param_metadata, plugin_metadata)

    def _extract_plugin_parameter_value(
        self,
        value: Any,
        current_path: str,
        key: str,
        param_metadata: PluginParameterMetadata | None,
        plugin_metadata: PluginFileMetadata,
    ) -> None:
        """Recursively extract a plugin parameter value using optional metadata."""
        parsed_json = self._parse_plugin_parameter_json(value)
        if parsed_json is not None:
            self._extract_plugin_parameter_container(parsed_json, f"{current_path}.@JSON", param_metadata, plugin_metadata)
            return

        if isinstance(value, str):
            if self._should_extract_plugin_parameter_value(key, value, param_metadata, plugin_metadata):
                self.extracted.append((current_path, value, "dialogue_block"))
            return

        if isinstance(value, (dict, list)):
            self._extract_plugin_parameter_container(value, current_path, param_metadata, plugin_metadata)

    def _extract_plugin_parameter_container(
        self,
        container: Any,
        current_path: str,
        container_metadata: PluginParameterMetadata | None,
        plugin_metadata: PluginFileMetadata,
    ) -> None:
        """Recurse into parsed plugin parameter JSON containers."""
        if isinstance(container, dict):
            # Sound spec guard: skip dicts that look like audio objects ({name, volume/pitch/pan})
            if self._is_sound_like_object(container):
                return
            struct_fields = plugin_metadata.get_struct_fields(container_metadata.struct_name() if container_metadata else None)
            for key, value in container.items():
                safe_key = self._escape_path_key(key)
                nested_path = f"{current_path}.{safe_key}" if current_path else safe_key
                nested_metadata = struct_fields.get(key) if struct_fields else None
                self._extract_plugin_parameter_value(value, nested_path, key, nested_metadata, plugin_metadata)
            return

        if isinstance(container, list):
            item_metadata = container_metadata.array_item_metadata() if container_metadata else None
            for index, item in enumerate(container):
                nested_path = f"{current_path}.{index}" if current_path else str(index)
                if isinstance(item, str):
                    parsed_item = self._parse_plugin_parameter_json(item)
                    if parsed_item is not None:
                        self._extract_plugin_parameter_container(parsed_item, f"{nested_path}.@JSON", item_metadata, plugin_metadata)
                        continue
                    item_key = item_metadata.name if item_metadata else str(index)
                    if self._should_extract_plugin_parameter_value(item_key, item, item_metadata, plugin_metadata):
                        self.extracted.append((nested_path, item, "dialogue_block"))
                    continue
                self._extract_plugin_parameter_container(item, nested_path, item_metadata, plugin_metadata)

    def _parse_plugin_parameter_json(self, value: Any) -> Any | None:
        """Parse nested JSON stored as a plugin parameter string."""
        if not isinstance(value, str):
            return None

        stripped = value.strip()
        if not stripped or len(stripped) <= 2:
            return None

        if stripped.startswith(("{", "[")):
            try:
                return json.loads(stripped)
            except (json.JSONDecodeError, TypeError):
                return None

        if stripped.startswith('"') and stripped.endswith('"'):
            try:
                nested = json.loads(stripped)
            except (json.JSONDecodeError, TypeError):
                return None
            if isinstance(nested, str) and nested.strip().startswith(("{", "[")):
                try:
                    return json.loads(nested)
                except (json.JSONDecodeError, TypeError):
                    return None
        return None

    def _should_extract_plugin_parameter_value(
        self,
        key: str,
        value: str,
        param_metadata: PluginParameterMetadata | None,
        plugin_metadata: PluginFileMetadata | None = None,
    ) -> bool:
        """Decide whether a plugin parameter string is safe and useful to translate."""
        if not isinstance(value, str) or not value.strip():
            return False

        if self._matches_known_asset_identifier(value):
            return False

        if param_metadata and self._is_metadata_defined_technical_param(param_metadata, key, value, plugin_metadata):
            return False

        if param_metadata and self._has_metadata_defined_text_intent(param_metadata):
            hints = param_metadata.combined_hints()
            if (
                self._metadata_hints_include_asset_context(hints)
                and self._looks_like_asset_name(value)
            ):
                return False
            if self._contains_asset_reference(value) or self._is_technical_string(value):
                return False
            if not self.is_safe_to_translate(value, is_dialogue=True):
                return False
            if ' ' in value or any(ord(char) > 127 for char in value):
                return True
            hints = param_metadata.combined_hints()
            return any(marker in hints for marker in self.PLUGIN_METADATA_TEXT_HINTS) or '%' in value

        return self._should_extract_generic_plugin_parameter(key, value)

    def _should_extract_generic_plugin_parameter(self, key: str, value: str) -> bool:
        """Fallback heuristic for plugin parameters when source metadata is unavailable."""
        key_lower = key.lower()
        if self._contains_asset_reference(value):
            return False
        if self._matches_known_asset_identifier(value):
            return False

        if self._is_audio_key_context(key) and self._looks_like_audio_parameter_value(value):
            return False

        if self._is_input_binding_key_context(key) and self._are_input_binding_tokens(value):
            return False

        if 'font' in key_lower:
            if len(value) < 40 and not any(ord(c) > 127 for c in value):
                if value.strip().isalpha() or value.replace(' ', '').isalnum() or ',' in value or '.ttf' in value.lower():
                    return False

        if any(hint in key_lower for hint in self.ASSET_KEY_HINTS) and self._looks_like_asset_name(value):
            return False

        if any(hint in key_lower for hint in self.NON_TRANSLATABLE_KEY_HINTS) or key_lower in self.NON_TRANSLATABLE_EXACT_KEYS:
            if len(value) < 60 and '\n' not in value:
                return False

        audio_key_patterns = [
            r'(?i)^(?:se|me|bgm|bgs|sound|audio)_?name$',
            r'(?i)^(?:se|me|bgm|bgs|sound|audio)$',
            r'[a-z](?:Se|Me|Bgm|Bgs|Sound|Audio)(?:Name)?$',
            r'_(?:se|me|bgm|bgs|sound|audio)(?:_name)?$',
        ]
        if any(re.search(pat, key) for pat in audio_key_patterns):
            if len(value) < 60 and '\n' not in value:
                return False


        if not self.is_safe_to_translate(value, is_dialogue=(key != 'note')):
            return False
        if self._is_technical_string(value):
            return False
        if ' ' in value or any(ord(c) > 127 for c in value):
            return True
        if any(marker in key_lower for marker in self.TEXT_KEY_INDICATORS):
            return True
        return any(key_lower.endswith(suffix) for suffix in self.TEXT_KEY_SUFFIXES)

    def _has_metadata_defined_text_intent(self, param_metadata: PluginParameterMetadata) -> bool:
        """Return True when plugin metadata strongly suggests player-visible text."""
        hints = param_metadata.combined_hints()
        if param_metadata.base_type() not in ("", "multiline_string", "note", "string"):
            return False
        return any(marker in hints for marker in self.PLUGIN_METADATA_TEXT_HINTS)

    def _is_metadata_defined_technical_param(
        self,
        param_metadata: PluginParameterMetadata,
        key: str,
        value: str,
        plugin_metadata: PluginFileMetadata | None = None,
    ) -> bool:
        """Return True when plugin metadata indicates this value is technical."""
        if self._has_technical_key_hint(key):
            return True

        if self._looks_like_input_binding_param(key, value, param_metadata):
            return True

        if plugin_metadata and self._looks_like_metadata_defined_registry_label(key, value, plugin_metadata):
            return True

        base_type = param_metadata.base_type()
        if base_type == "note":
            return not self._has_metadata_defined_text_intent(param_metadata)
        if base_type in self.PLUGIN_METADATA_TECHNICAL_TYPES:
            return True
        if param_metadata.dir_path or param_metadata.require:
            return True
        if self._looks_like_metadata_defined_asset_registry(value, param_metadata):
            return True

        if self._is_audio_key_context(key) and self._looks_like_audio_parameter_value(value):
            return True

        hints = param_metadata.combined_hints()
        key_lower = key.lower()
        if self._has_metadata_defined_text_intent(param_metadata):
            return False

        if (
            base_type in ("", "multiline_string", "string")
            and (
                self._metadata_hints_include_asset_context(hints)
                or any(marker in key_lower for marker in self.ASSET_KEY_HINTS)
            )
            and self._looks_like_asset_name(value)
        ):
            return True
        return False

    def _looks_like_metadata_defined_registry_label(
        self,
        key: str,
        value: str,
        plugin_metadata: PluginFileMetadata,
    ) -> bool:
        """Return True when a plugin string acts as an option-registry label."""
        key_tokens = self._tokenize_key_hints(key)
        if "order" not in key_tokens:
            return False

        stripped = self._strip_rpgm_text_codes(value).strip()
        if not stripped or "\n" in stripped:
            return False

        if "category" in key_tokens:
            return re.fullmatch(r"[A-Za-z_][A-Za-z0-9_ ]*", stripped) is not None

        option_sets = self._collect_plugin_option_sets(plugin_metadata, key_tokens)
        if not option_sets:
            return False

        normalized = stripped.lower()
        return any(normalized in option_set for option_set in option_sets)

    def _collect_plugin_option_sets(
        self,
        plugin_metadata: PluginFileMetadata,
        key_tokens: Set[str],
    ) -> list[Set[str]]:
        """Collect option sets from related plugin metadata fields."""
        option_sets: list[Set[str]] = []

        def maybe_add_options(param: PluginParameterMetadata) -> None:
            if not param.options:
                return
            name_tokens = self._tokenize_key_hints(param.name)
            if not name_tokens or not (name_tokens & key_tokens):
                return
            normalized_options = {option.strip().lower() for option in param.options if option.strip()}
            if normalized_options:
                option_sets.append(normalized_options)

        for param in plugin_metadata.params.values():
            maybe_add_options(param)
        for fields in plugin_metadata.structs.values():
            for param in fields.values():
                maybe_add_options(param)
        return option_sets

    def _strip_rpgm_text_codes(self, text: str) -> str:
        """Remove common RPG Maker text codes for technical comparisons."""
        if not isinstance(text, str):
            return ""
        stripped = re.sub(r"\\[A-Za-z]+\[[^\]]*\]", "", text)
        stripped = re.sub(r"\\[{}]", "", stripped)
        return stripped

    def _is_input_binding_key_context(self, key: str) -> bool:
        """Return True when key tokens suggest an input binding, not UI text."""
        tokens = self._tokenize_key_hints(key)
        if not tokens:
            return False
        if not ({"button", "key", "input", "trigger", "hotkey"} & tokens):
            return False
        if {"text", "label", "name", "title", "caption"} & tokens:
            return False
        return True

    def _are_input_binding_tokens(self, value: str) -> bool:
        """Return True when a value is a key-binding token or token list."""
        if not isinstance(value, str):
            return False
        cleaned = value.strip().strip('"\'')
        if not cleaned or '\n' in cleaned:
            return False
        parts = [part for part in cleaned.lower().split() if part]
        if not parts:
            return False
        for part in parts:
            if part in self.INPUT_BINDING_TOKENS:
                continue
            if len(part) == 1 and part.isalpha():
                continue
            return False
        return True

    def _looks_like_input_binding_param(
        self,
        key: str,
        value: str,
        param_metadata: PluginParameterMetadata | None,
    ) -> bool:
        """Return True when plugin metadata indicates an input-binding value."""
        if not self._is_input_binding_key_context(key):
            return False
        if self._are_input_binding_tokens(value):
            return True
        if not param_metadata:
            return False

        default_value = param_metadata.default_value.strip().strip('"\'')
        if not self._are_input_binding_tokens(default_value):
            return False

        combined = " ".join(
            part for part in [param_metadata.name, param_metadata.text, param_metadata.description] if part
        ).lower()
        return 'button' in combined or 'key' in combined or 'input' in combined

    def _metadata_hints_include_asset_context(self, hints: str) -> bool:
        """Return True when metadata hints clearly indicate asset/file context."""
        if not isinstance(hints, str) or not hints:
            return False

        normalized_hints = hints.lower()
        hint_tokens = {token for token in re.split(r"[^a-z0-9]+", normalized_hints) if token}

        for marker in self.PLUGIN_METADATA_ASSET_CONTEXT_HINTS:
            marker_lower = marker.lower()
            if not marker_lower:
                continue
            if " " in marker_lower:
                if marker_lower in normalized_hints:
                    return True
                continue
            if len(marker_lower) <= 2:
                if marker_lower in hint_tokens:
                    return True
                continue
            if marker_lower in hint_tokens or marker_lower in normalized_hints:
                return True
        return False

    def _tokenize_key_hints(self, key: str) -> Set[str]:
        """Tokenize plugin keys to robustly detect technical hint words."""
        if not isinstance(key, str) or not key:
            return set()
        normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", key)
        tokens = [token for token in re.split(r"[^A-Za-z0-9]+", normalized.lower()) if token]
        return set(tokens)

    def _has_technical_key_hint(self, key: str) -> bool:
        """Return True when key tokens include explicit technical markers."""
        tokens = self._tokenize_key_hints(key)
        if not tokens:
            return False

        exact_hints = {hint.lower() for hint in self.NON_TRANSLATABLE_EXACT_KEYS}
        tech_hints = {hint.lower() for hint in self.NON_TRANSLATABLE_KEY_HINTS}

        if tokens & exact_hints:
            return True
        if tokens & tech_hints:
            return True
        return False

    def _is_audio_key_context(self, key: str) -> bool:
        """Return True when key tokens indicate audio/SE style parameters."""
        tokens = self._tokenize_key_hints(key)
        if not tokens:
            return False
        audio_tokens = {"audio", "sound", "voice", "se", "me", "bgm", "bgs"}
        if tokens & audio_tokens:
            return True
        joined = "_".join(sorted(tokens))
        return "soundeffect" in joined or "sound_effect" in joined

    def _looks_like_audio_parameter_value(self, value: str) -> bool:
        """Return True when value matches common RPG Maker audio parameter forms."""
        if not isinstance(value, str):
            return False
        cleaned = value.strip().strip('"\'')
        if not cleaned or '\n' in cleaned:
            return False

        # Common plugin SE format: "Name,volume,pitch" or "Name,volume,pitch,pan"
        if re.fullmatch(r"[^,\n\r]{1,80},\s*-?\d{1,3},\s*-?\d{1,3}(?:,\s*-?\d{1,3})?", cleaned):
            return True

        if self._looks_like_asset_name(cleaned):
            return True
        if self._contains_asset_reference(cleaned):
            return True
        return self._matches_known_asset_identifier(cleaned)

    def _looks_like_metadata_defined_asset_registry(
        self,
        value: str,
        param_metadata: PluginParameterMetadata,
    ) -> bool:
        """Detect combo/string parameters that actually contain asset registries."""
        hints = param_metadata.combined_hints()
        if not hints or self._has_metadata_defined_text_intent(param_metadata):
            return False

        has_asset_context = self._metadata_hints_include_asset_context(hints)
        has_asset_list_context = any(marker in hints for marker in self.PLUGIN_METADATA_ASSET_LIST_HINTS)
        if not has_asset_context and not has_asset_list_context:
            return False

        cleaned_value = value.strip()
        lower_value = cleaned_value.lower()
        if param_metadata.base_type() in {"combo", "select"}:
            return True
        if lower_value.startswith("custom:"):
            return True
        if cleaned_value in {"all", "important", "none"}:
            return True
        if "," in cleaned_value:
            parts = [part.strip() for part in cleaned_value.split(",") if part.strip()]
            if parts and all(
                self._looks_like_asset_name(part) or part.lower() in {"bgm", "bgs", "me", "se"}
                for part in parts
            ):
                return True
        return False

    def _walk(self, data: Any, current_path: str):
        """Recursively walk JSON structure to find translatable text."""
        if isinstance(data, dict):
            self._process_dict(data, current_path)
        elif isinstance(data, list):
            self._process_list(data, current_path)
        elif isinstance(data, str):
            # Check if this string itself is a nested JSON
            if (data.startswith('{') or data.startswith('[')) and len(data) > 2:
                try:
                    nested_data = json.loads(data)
                    self._walk(nested_data, f"{current_path}.@JSON")
                    return
                except (json.JSONDecodeError, TypeError):
                    pass

    def _walk_entries(self, data: Any, current_path: str) -> List[Tuple[str, str, str]]:
        """Recursively walk JSON structure and return list of entries (for use with external sink)."""
        results: List[Tuple[str, str, str]] = []
        if isinstance(data, dict):
            self._process_dict_entries(data, current_path, results)
        elif isinstance(data, list):
            self._process_list_entries(data, current_path, results)
        elif isinstance(data, str):
            if (data.startswith('{') or data.startswith('[')) and len(data) > 2:
                try:
                    nested_data = json.loads(data)
                    nested_results = self._walk_entries(nested_data, f"{current_path}.@JSON")
                    results.extend(nested_results)
                except (json.JSONDecodeError, TypeError):
                    pass
        return results

    def _process_dict_entries(self, data: dict, current_path: str, results: List[Tuple[str, str, str]]):
        """Process dict node and append entries to results list."""
        is_sound_obj = self._is_sound_like_object(data) or self._is_asset_context_path(current_path)
        for key, value in data.items():
            safe_key = self._escape_path_key(key)
            new_path = f"{current_path}.{safe_key}" if current_path else safe_key
            if key in self._skip_fields:
                continue
            if is_sound_obj and key == 'name':
                continue
            key_lower = key.lower()
            if any(key_lower.endswith(suffix) for suffix in self.CODE_KEY_SUFFIXES):
                continue
            if isinstance(value, str) and (value.startswith('{') or value.startswith('[')) and len(value) > 2:
                try:
                    nested_data = json.loads(value)
                    nested_results = self._walk_entries(nested_data, f"{new_path}.@JSON")
                    results.extend(nested_results)
                    continue
                except (json.JSONDecodeError, TypeError):
                    pass
            is_plugin_param = ".parameters" in new_path or ".@JSON" in new_path or "parameters" in current_path
            should_extract = False
            if key in self.DATABASE_FIELDS or (key == 'name' and not is_sound_obj):
                if key == 'name':
                    if self._should_extract_name(current_path, value, is_plugin_param):
                        should_extract = True
                    else:
                        if not isinstance(value, str):
                            results.extend(self._walk_entries(value, new_path))
                        continue
                elif isinstance(value, str):
                    should_extract = True
                else:
                    results.extend(self._walk_entries(value, new_path))
                    continue
            elif is_plugin_param and isinstance(value, str):
                if self._should_extract_generic_plugin_parameter(key, value):
                    should_extract = True
            if should_extract:
                if not isinstance(value, str):
                    results.extend(self._walk_entries(value, new_path))
                    continue
                context_tag = "dialogue_block" if is_plugin_param or (key in ['message1', 'message2', 'message3', 'message4', 'help', 'description']) else "name"
                if self._contains_asset_reference(value) or self._is_technical_string(value):
                    continue
                if self._matches_known_asset_identifier(value):
                    continue
                if not self.is_safe_to_translate(value, is_dialogue=(context_tag != "name")):
                    continue
                if key in ['name', 'nickname', 'gameTitle', 'title', 'currencyUnit']:
                    context_tag = "name"
                results.append((new_path, value, context_tag))
                continue
            if key in self.SYSTEM_TERMS:
                continue
            results.extend(self._walk_entries(value, new_path))

    def _process_list_entries(self, data: list, current_path: str, results: List[Tuple[str, str, str]]):
        """Process list node and append entries to results list."""
        for i, item in enumerate(data):
            new_path = f"{current_path}.{i}" if current_path else str(i)
            if isinstance(item, dict) and "code" in item and "parameters" in item:
                continue
            results.extend(self._walk_entries(item, new_path))

    # VisuStella MZ / Yanfly type annotation suffixes that indicate NON-translatable values
    # e.g. "drawGameTitle:func" -> value is JavaScript code
    # e.g. "BattleSystem:eval" -> value is JS eval expression
    # e.g. "CodeJS:json" -> value is JS code encoded as JSON string
    CODE_KEY_SUFFIXES = (':func', ':eval', ':json', ':code', ':js')
    
    # VisuStella MZ suffixes that indicate structural containers (recurse into them)
    STRUCT_KEY_SUFFIXES = (':struct', ':arraystruct', ':arraystr', ':arraynum')
    
    # VisuStella MZ suffixes that indicate translatable string values
    TEXT_KEY_SUFFIXES = (':str', ':num')
    
    def _extract_tags_from_note(self, note: str, base_path: str) -> List[Tuple[str, str]]:
        if not isinstance(note, str) or not note.strip(): return []
        results = []
        # Pattern 1: Block tags (e.g. <Description>...</Description>)
        pattern_block = r'<(?P<tag>\w*(?:Description|Text|Message|Desc|Name)\w*)>(?P<content>.*?)</(?P=tag)>'
        for i, match in enumerate(re.finditer(pattern_block, note, re.IGNORECASE | re.DOTALL)):
            content = match.group('content').strip()
            if len(content) > 1 and self._is_extractable_runtime_text(content, is_dialogue=True):
                results.append((f"{base_path}.@NOTEBLOCK_{i}", content))
                
        # Pattern 2: Inline tags (e.g. <Desc: text>)
        pattern_inline = r'<(?P<tag>\w*(?:_name|_desc|_text|_msg|Name|Desc|Text|Message)):(?P<content>.*?)>'
        for i, match in enumerate(re.finditer(pattern_inline, note, re.IGNORECASE)):
            content = match.group('content').strip()
            if len(content) > 1 and self._is_extractable_runtime_text(content, is_dialogue=True):
                results.append((f"{base_path}.@NOTEINLINE_{i}", content))
        return results

    def _apply_note_tag_translation(self, data: Any, base_path: str, updates: list, is_block: bool):
        note = self._get_value_at_path(data, base_path)
        if not isinstance(note, str): return
        
        if is_block:
            pattern = r'<(?P<tag>\w*(?:Description|Text|Message|Desc|Name)\w*)>(?P<content>.*?)</(?P=tag)>'
        else:
            pattern = r'<(?P<tag>\w*(?:_name|_desc|_text|_msg|Name|Desc|Text|Message)):(?P<content>.*?)>'
        
        matches = list(re.finditer(pattern, note, re.IGNORECASE | (re.DOTALL if is_block else 0)))
        updates_sorted = sorted(updates, key=lambda x: x[0], reverse=True)
        
        new_note = note
        for idx, trans_text in updates_sorted:
            if idx is None or idx >= len(matches) or not trans_text: continue
            match = matches[idx]
            content_start = match.start('content')
            content_end = match.end('content')
            original_content = new_note[content_start:content_end]
            
            leading_len = len(original_content) - len(original_content.lstrip())
            trailing_len = len(original_content) - len(original_content.rstrip())
            leading = original_content[:leading_len] if leading_len > 0 else ""
            trailing = original_content[len(original_content)-trailing_len:] if trailing_len > 0 else ""
            
            new_note = new_note[:content_start] + leading + trans_text + trailing + new_note[content_end:]
            
        self._set_value_at_path(data, base_path, new_note)

    def _is_non_translatable_plugin(self, plugin_name: str) -> bool:
        """Check if a plugin is known to have entirely non-translatable parameters."""
        if not plugin_name:
            return False
        if plugin_name in self.NON_TRANSLATABLE_PLUGINS:
            return True
        return any(p.search(plugin_name) for p in self.NON_TRANSLATABLE_PLUGIN_PATTERNS)

    def _should_skip_name_field(self, current_path: str) -> bool:
        """Check if a 'name' field should be skipped based on file type and path context.
        
        Event names in Maps, CommonEvents, and Troops are editor-only labels
        that should NOT be translated. Plugins reference events by name,
        so translating these causes fatal game errors.
        """
        basename = getattr(self, '_current_file_basename', '')
        
        # Map files: skip event names (path pattern: events.N)
        if basename.startswith('map') and basename.endswith('.json'):
            if re.match(r'^events\.\d+$', current_path):
                return True
        
        # CommonEvents and Troops: skip top-level item names (path pattern: N)
        if basename in ('commonevents.json', 'troops.json'):
            if re.match(r'^\d+$', current_path):
                return True
        
        return False

    def _is_asset_context_path(self, path: str) -> bool:
        """Return True when a JSON path strongly suggests asset/file-name context."""
        if not isinstance(path, str) or not path:
            return False

        normalized = path.replace(self.PATH_DOT_ESCAPE_ESC, self.PATH_DOT_ESCAPE)
        normalized = normalized.replace(self.PATH_DOT_ESCAPE, '.')
        normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1.\2", normalized)
        tokens = [token for token in re.split(r"[^a-zA-Z0-9]+", normalized.lower()) if token]
        if not tokens:
            return False

        for token in tokens:
            if token in self._ASSET_CONTEXT_PATH_HINTS:
                return True
            if len(token) <= 2:
                continue
            for hint in self._ASSET_CONTEXT_PATH_HINTS:
                if len(hint) <= 2:
                    continue
                if hint in token:
                    return True
        return False

    def _should_extract_name(self, current_path: str, value: Any, is_plugin_param: bool) -> bool:
        """Determine if a 'name' field value should be extracted for translation.
        
        Context-aware filtering:
        - Maps/CommonEvents/Troops event names: SKIP (editor-only)
        - Plugin parameter 'name': strict heuristics (usually identifiers)
        - Database file 'name' (Actors, Items, etc.): EXTRACT (player-visible)
        """
        # 1. Skip event-level names in Maps/CommonEvents/Troops
        if self._should_skip_name_field(current_path):
            return False

        # 1.5. Never translate name-like values inside asset/audio contexts.
        # This blocks extensionless identifiers such as Battle1, Town Theme, etc.
        if self._is_asset_context_path(current_path):
            return False
        
        # 2. In plugin parameter context, 'name' is usually an identifier (fog_shadow_w, NEXT)
        #    Only extract if value clearly looks like display text
        if is_plugin_param:
            if not isinstance(value, str) or not value.strip():
                return False
            v = value.strip()
            if self._matches_known_asset_identifier(v):
                return False
            # Require spaces (sentence-like) or non-ASCII (localized text) for extraction
            if not ((' ' in v and len(v) > 5) or any(ord(c) > 127 for c in v)):
                return False
            return (self.is_safe_to_translate(v, is_dialogue=True)
                    and not self._is_technical_string(v)
                    and not self._contains_asset_reference(v))

        if getattr(self, '_current_file_basename', '') in self.LEGACY_DATABASE_NAME_FILES:
            if not isinstance(value, str) or not value.strip():
                return False
            v = value.strip()
            if self._contains_asset_reference(v):
                return False
            if self._matches_known_asset_identifier(v):
                return False
            if self._is_technical_string(v):
                return False
            return True
        
        if not isinstance(value, str) or not value.strip():
            return False

        v = value.strip()
        if self._matches_known_asset_identifier(v):
            return False
        if self._contains_asset_reference(v) or self._is_technical_string(v):
            return False

        has_non_ascii = any(ord(char) > 127 for char in v)
        has_sentence_punctuation = any(mark in v for mark in ".!?;:ã€‚ï¼ï¼Ÿ")
        return has_non_ascii or has_sentence_punctuation or (' ' in v and len(v) > 2)

    def _process_dict(self, data: dict, current_path: str):
        """Process a dictionary node."""
        # Heuristic: If this dict looks like a BGM/SE/Sound object, skip its 'name'
        is_sound_obj = self._is_sound_like_object(data) or self._is_asset_context_path(current_path)
        
        for key, value in data.items():
            safe_key = self._escape_path_key(key)
            new_path = f"{current_path}.{safe_key}" if current_path else safe_key
            
            # Skip internal fields
            if key in self._skip_fields:
                continue
                
            # Skip name in sound objects
            if is_sound_obj and key == 'name':
                continue
            
            # VisuStella MZ type annotation filter:
            # Keys like "drawGameTitle:func", "BattleSystem:eval" contain JS code
            key_lower = key.lower()
            if any(key_lower.endswith(suffix) for suffix in self.CODE_KEY_SUFFIXES):
                continue  # JavaScript code â€” NEVER translate
            
            # 1. RECURSIVE JSON CHECK
            if isinstance(value, str) and (value.startswith('{') or value.startswith('[')) and len(value) > 2:
                try:
                    nested_data = json.loads(value)
                    self._walk(nested_data, f"{new_path}.@JSON") 
                    continue 
                except (json.JSONDecodeError, TypeError):
                    pass 

            if self.translate_notes and key == 'note' and isinstance(value, str) and value.strip():
                tags = self._extract_tags_from_note(value, new_path)
                for tag_path, tag_text in tags:
                    self.extracted.append((tag_path, tag_text, "dialogue_block"))

            # Check logic for extraction
            should_extract = False
            is_plugin_param = ".parameters" in new_path or ".@JSON" in new_path or "parameters" in current_path
            
            if key in self.DATABASE_FIELDS or (key == 'name' and not is_sound_obj):
                if key == 'name':
                    # Context-aware name filtering: skip event names, apply heuristics for plugins
                    if self._should_extract_name(current_path, value, is_plugin_param):
                        should_extract = True
                    else:
                        # Not extracting this name, but still recurse into nested structures
                        if not isinstance(value, str):
                            self._walk(value, new_path)
                        continue
                elif isinstance(value, str):
                    should_extract = True
                else:
                    self._walk(value, new_path)
                    continue
            elif is_plugin_param and isinstance(value, str):
                 if self._should_extract_generic_plugin_parameter(key, value):
                     should_extract = True

            if should_extract:
                if not isinstance(value, str):
                    self._walk(value, new_path)
                    continue

                context_tag = "dialogue_block" if is_plugin_param or (key in ['message1', 'message2', 'message3', 'message4', 'help', 'description']) else "name"
                if self._contains_asset_reference(value) or self._is_technical_string(value):
                    continue
                if self._matches_known_asset_identifier(value):
                    continue
                if not self.is_safe_to_translate(value, is_dialogue=(context_tag != "name")):
                    continue
                if key in ['name', 'nickname', 'gameTitle', 'title', 'currencyUnit']:
                    context_tag = "name"
                self.extracted.append((new_path, value, context_tag))
                continue
            
            # Check system terms
            if key in self.SYSTEM_TERMS:
                self._extract_system_terms(value, new_path)
                continue
            
            # Recurse
            self._walk(value, new_path)

    def _process_list(self, data: list, current_path: str):
        """Process a list node, including event commands with lookahead for multi-line blocks."""
        in_code_block = False
        i = 0
        while i < len(data):
            item = data[i]
            # Avoid leading dot if current_path is empty
            new_path = f"{current_path}.{i}" if current_path else str(i)
            
            # Check for event command structure
            if isinstance(item, dict) and "code" in item and "parameters" in item:
                code = item.get("code")
                
                # Protect Code/Script Event Comments from translation
                if code in (108, 408):
                    params = item.get("parameters", [])
                    if params and isinstance(params[0], str):
                        text_lower = params[0].strip().lower()
                        if text_lower.startswith('<') and '>' in text_lower:
                            tag_content = text_lower.split('>', 1)[0]
                            # Check if the tag indicates a script/eval block (VisuStella / Yanfly patterns)
                            is_code_tag = any(k in tag_content for k in ['eval', 'code', 'script', 'setup', 'action', 'js '])
                            if is_code_tag:
                                if text_lower.startswith('</'):
                                    in_code_block = False
                                else:
                                    in_code_block = True
                                    
                        # If we are inside an Eval/Code comment block, skip completely
                        if in_code_block:
                            i += 1
                            continue
                
                # Multi-line script merge: code 355 followed by 655 continuations
                if code == 355:
                    script_cmds = [item]
                    j = i + 1
                    while j < len(data) and isinstance(data[j], dict) and data[j].get("code") == 655:
                        script_cmds.append(data[j])
                        j += 1
                    self._process_script_block(script_cmds, current_path, i)
                    i = j
                    continue
                
                # MZ Plugin Command merge: code 357 followed by 657 continuations
                if code == 357:
                    plugin_cmds = [item]
                    j = i + 1
                    while j < len(data) and isinstance(data[j], dict) and data[j].get("code") == 657:
                        plugin_cmds.append(data[j])
                        j += 1
                    self._process_mz_plugin_block(plugin_cmds, current_path, i)
                    i = j
                    continue
                
                # Skip individual 655/657 lines (already consumed by lookahead above)
                if code in (655, 657):
                    i += 1
                    continue
                
                self._process_event_command(item, new_path)
                # CRITICAL: Do NOT recurse into Event Commands using generic _walk.
                # Only whitelisted event codes in _process_event_command contain translatable text.
                # Recursing here causes technical parameters (like filenames in Show Picture / Code 231)
                # to be dangerously extracted and translated.
                i += 1
                continue
            
            # Check for Nested JSON strings in list items
            if isinstance(item, str):
                 if (item.startswith('{') or item.startswith('[')) and len(item) > 2:
                    try:
                        nested_data = json.loads(item)
                        self._walk(nested_data, f"{new_path}.@JSON")
                        i += 1
                        continue
                    except (json.JSONDecodeError, TypeError):
                        pass
                 elif item.startswith('"') and item.endswith('"') and len(item) >= 2:
                    try:
                        nested_str = json.loads(item)
                        if isinstance(nested_str, str):
                            is_plugin_param = ".parameters" in new_path or ".@JSON" in new_path or "parameters" in current_path
                            if is_plugin_param and self._is_extractable_runtime_text(nested_str, is_dialogue=True):
                                if ' ' in nested_str or any(ord(c) > 127 for c in nested_str):
                                    self.extracted.append((f"{new_path}.@JSON", nested_str, "dialogue_block"))
                                    i += 1
                                    continue
                    except (json.JSONDecodeError, TypeError):
                        pass

                 # Fallback for plain strings in lists (if inside plugin parameters)
                 is_plugin_param = ".parameters" in new_path or ".@JSON" in new_path or "parameters" in current_path
                 if is_plugin_param:
                     should_extract = False
                     if self._is_extractable_runtime_text(item, is_dialogue=True):
                         if ' ' in item or any(ord(c) > 127 for c in item):
                             should_extract = True
                     if should_extract:
                         self.extracted.append((new_path, item, "dialogue_block"))
                         i += 1
                         continue

            # Recurse
            self._walk(item, new_path)
            i += 1

    def _process_event_command(self, cmd: dict, path: str):
        """Process an RPG Maker event command for translatable text."""
        self._process_event_command_into(cmd, path, None)

    def _process_event_command_into(
        self,
        cmd: dict,
        path: str,
        sink: List[Tuple[str, str, str]] | None,
    ) -> None:
        """Process an RPG Maker event command into either the parser sink or a custom sink."""
        code = cmd.get("code")
        params = cmd.get("parameters", [])
        target = sink if sink is not None else self.extracted
        
        if code not in self.TEXT_EVENT_CODES:
            return
        
        # Show Text (401) / Scroll Text (405) / Show Text Header (101 - MZ Speaker Name)
        if code in [401, 405]:
            if len(params) > 0 and self._is_extractable_runtime_text(params[0], is_dialogue=True):
                target.append((f"{path}.parameters.0", params[0], "message_dialogue"))

        elif code == 101:
            # Code 101: Show Text Header.
            # in MZ: [faceName, faceIndex, background, positionType, speakerName]
            if len(params) >= 5:
                speaker_name = params[4]
                if self._is_extractable_runtime_text(speaker_name, is_dialogue=True):
                    target.append((f"{path}.parameters.4", speaker_name, "name"))
        
        # Show Scrolling Text Header (105)
        # Format: [speed, noFastForward] - no text here, but some plugins add title
        elif code == 105:
            # Standard code 105 doesn't have text, but check for extended params
            if len(params) >= 3 and isinstance(params[2], str):
                if self._is_extractable_runtime_text(params[2], is_dialogue=True):
                    target.append((f"{path}.parameters.2", params[2], "system"))
        
        # Show Choices (102)
        elif code == 102:
            choices = params[0] if len(params) > 0 else []
            if isinstance(choices, list):
                for c_i, choice in enumerate(choices):
                    if self._is_extractable_runtime_text(choice, is_dialogue=True):
                        target.append((f"{path}.parameters.0.{c_i}", choice, "choice"))
                        
        # When [Choice] (402) - Translate branch label
        elif code == 402:
            if len(params) > 1 and isinstance(params[1], str):
                if self._is_extractable_runtime_text(params[1], is_dialogue=True):
                    target.append((f"{path}.parameters.1", params[1], "choice"))

        # Label (118) / Jump to Label (119)
        elif code in [118, 119]:
            if len(params) > 0 and isinstance(params[0], str):
                if self._is_extractable_runtime_text(params[0], is_dialogue=True):
                    target.append((f"{path}.parameters.0", params[0], "system"))
                    
        # Control Variables (122) - Operand Script
        elif code == 122:
            if len(params) >= 5 and params[3] == 4 and isinstance(params[4], str):
                script_text = params[4]
                tokens = self.js_tokenizer.extract_strings(script_text)
                for line_idx, char_idx, quote_char, token_str in tokens:
                    if self._is_extractable_runtime_text(token_str, is_dialogue=True):
                        target.append((f"{path}.parameters.4.@JS{char_idx}", token_str, "script"))
        
        # Comment (108/408) - Can contain plugin commands with text
        elif code in [108, 408] and self.translate_comments:
            if len(params) > 0 and isinstance(params[0], str):
                text = params[0].strip()
                if not self.looks_like_translatable_comment(text):
                    return
                if not self._is_extractable_runtime_text(text, is_dialogue=True):
                    return
                target.append((f"{path}.parameters.0", params[0], "comment"))
        
        elif code in [320, 324, 325]:
            if len(params) > 1 and self._is_extractable_runtime_text(params[1], is_dialogue=True):
                target.append((f"{path}.parameters.1", params[1], "name"))
        
        # Plugin Command MV (356) - params[0] is command string
        elif code == 356:
            if len(params) > 0 and isinstance(params[0], str):
                self._extract_mv_plugin_command_text(params[0], path, target)
        
        # Plugin Command MZ (357) - structured differently
        elif code == 357:
            # MZ plugin commands have structured params, look for 'text' fields
            if len(params) >= 4:
                # params format: [pluginName, commandName, commandText, {args}]
                plugin_name = params[0] if isinstance(params[0], str) else ""

                # Skip known non-translatable plugins (particle effects, etc.)
                if self._is_non_translatable_plugin(plugin_name):
                    return

                # Check commandText
                if isinstance(params[2], str) and self._is_extractable_runtime_text(params[2], is_dialogue=True):
                    target.append((f"{path}.parameters.2", params[2], "dialogue_block"))
                    
                # Also check args dict for common text fields
                if len(params) > 3 and isinstance(params[3], dict):
                    args = params[3]
                    # RECURSIVE CHECK HERE TOO
                    self._walk(args, f"{path}.parameters.3")
        
        # Script commands (355/655) are now handled via _process_script_block in _process_list
        # with proper multi-line merging and JSStringTokenizer extraction.
        # Code 657 (MZ Plugin continuation) is handled via _process_mz_plugin_block.

    def _process_script_block(self, commands: list, list_path: str, start_index: int):
        """
        Process a merged script block (code 355 + zero or more 655 continuations).
        
        Uses JSStringTokenizer to extract individual translatable string literals
        from the merged JavaScript code, instead of fragile regex patterns.
        """
        self._process_script_block_into(commands, list_path, start_index, None)

    def _process_script_block_into(
        self,
        commands: list,
        list_path: str,
        start_index: int,
        sink: List[Tuple[str, str, str]] | None,
    ) -> None:
        """Process a merged script block into either the parser sink or a custom sink."""
        # Merge all script lines
        lines = []
        for cmd in commands:
            params = cmd.get("parameters", [])
            if params and isinstance(params[0], str):
                lines.append(params[0])
            else:
                lines.append("")
        
        merged = '\n'.join(lines)
        
        if not merged.strip():
            return
        
        line_count = len(commands) - 1  # number of 655 continuation lines
        base_path = f"{list_path}.{start_index}" if list_path else str(start_index)
        target = sink if sink is not None else self.extracted
        
        # Use JSStringTokenizer to find all translatable strings
        strings = self._js_tokenizer.extract_translatable_strings(merged)
        
        for idx, (start, end, value, quote) in enumerate(strings):
            if not value.strip() or not self._is_extractable_runtime_text(value, is_dialogue=True):
                continue
                
            # STRICT HEURISTIC FOR SCRIPT STRINGS:
            # Script strings are dangerous (e.g. Galv.CACHE.load('pictures', 'Vale1'))
            # Only translate if it looks like a real sentence (has spaces) or is already localized (non-ascii)
            has_spaces = ' ' in value.strip()
            has_non_ascii = any(ord(c) > 127 for c in value)
            
            if not ((has_spaces and len(value.strip()) > 3) or has_non_ascii):
                continue
            
            if line_count > 0:
                path = f"{base_path}.@SCRIPTMERGE{line_count}.@JS{idx}"
            else:
                path = f"{base_path}.parameters.0.@JS{idx}"
            
            target.append((path, value, "dialogue_block"))

    def _process_mz_plugin_block(self, commands: list, list_path: str, start_index: int):
        """
        Process a merged MZ plugin command block (code 357 + zero or more 657 continuations).
        
        The first command (357) is processed normally. Continuation lines (657)
        may contain additional text parameters.
        """
        self._process_mz_plugin_block_into(commands, list_path, start_index, None)

    def _process_mz_plugin_block_into(
        self,
        commands: list,
        list_path: str,
        start_index: int,
        sink: List[Tuple[str, str, str]] | None,
    ) -> None:
        """Process an MZ plugin command block into either the parser sink or a custom sink."""
        first = commands[0]
        base_path = f"{list_path}.{start_index}" if list_path else str(start_index)
        target = sink if sink is not None else self.extracted
        
        # Skip known non-translatable plugins (particle effects, etc.)
        first_params = first.get("parameters", [])
        plugin_name = first_params[0] if first_params and isinstance(first_params[0], str) else ""
        if self._is_non_translatable_plugin(plugin_name):
            return
        
        # Process the first 357 command normally
        self._process_event_command_into(first, base_path, target)
        
        # Walk into dict params of the first (357) command (e.g., WD_Quest structured params at params[3])
        # Must append to target (sink), not self.extracted
        first_params = first.get("parameters", [])
        for p_idx, param in enumerate(first_params):
            if isinstance(param, dict):
                for entry_path, entry_text, entry_tag in self._walk_entries(param, f"{base_path}.parameters.{p_idx}"):
                    target.append((entry_path, entry_text, entry_tag))
        
        # Process 657 continuation lines
        for j, cmd in enumerate(commands[1:], 1):
            cmd_path = f"{list_path}.{start_index + j}" if list_path else str(start_index + j)
            params = cmd.get("parameters", [])
            
            # 657 can carry additional text args or structured data
            if not params:
                continue
            
            # If first param is a string, check if translatable
            if isinstance(params[0], str):
                if self._is_extractable_runtime_text(params[0], is_dialogue=True):
                    target.append((f"{cmd_path}.parameters.0", params[0], "dialogue_block"))
            
            # If there's a dict arg (like 357's structured params), walk it
            for p_idx, param in enumerate(params):
                if isinstance(param, dict):
                    self._walk(param, f"{cmd_path}.parameters.{p_idx}")

    def _extract_mv_plugin_command_text(
        self,
        command_text: str,
        path: str,
        sink: List[Tuple[str, str, str]] | None = None,
    ) -> None:
        """
        Extract only quoted text payloads from MV plugin commands.

        Translating a full code-356 command string is unsafe because translation
        engines can mutate command names, asset identifiers, and key=value
        bindings. Quoted payloads can be translated without touching the
        technical command envelope.
        """
        if not isinstance(command_text, str):
            return
        target = sink if sink is not None else self.extracted

        for quote_index, (_start, _end, _quote_char, segment_text) in enumerate(self._extract_quoted_segments(command_text)):
            cleaned_segment = segment_text.strip()
            if not cleaned_segment:
                continue
            if not self._is_extractable_runtime_text(cleaned_segment, is_dialogue=True):
                continue
            if self._looks_like_asset_name(cleaned_segment):
                continue
            target.append((f"{path}.parameters.0.@MVCMD{quote_index}", segment_text, "dialogue_block"))

    def _extract_quoted_segments(self, text: str) -> List[Tuple[int, int, str, str]]:
        """Return quoted segments as `(start, end, quote_char, inner_text)` tuples."""
        if not isinstance(text, str) or not text:
            return []

        segments: List[Tuple[int, int, str, str]] = []
        active_quote = ""
        segment_start = -1
        escaped = False

        for index, char in enumerate(text):
            if active_quote:
                if escaped:
                    escaped = False
                    continue
                if char == "\\":
                    escaped = True
                    continue
                if char == active_quote:
                    inner_text = text[segment_start + 1:index]
                    segments.append((segment_start, index, active_quote, inner_text))
                    active_quote = ""
                    segment_start = -1
                continue

            if char in {'"', "'"}:
                active_quote = char
                segment_start = index

        return segments

    def _extract_legacy_event_entries(
        self,
        command: dict[str, Any],
        path: str,
        sink: List[Tuple[str, str, str]],
    ) -> None:
        """Bridge legacy event extraction into the structured extractor."""
        self._process_event_command_into(command, path, sink)

    def _extract_legacy_script_entries(
        self,
        commands: list[dict[str, Any]],
        list_path: str,
        start_index: int,
        sink: List[Tuple[str, str, str]],
    ) -> None:
        """Bridge legacy merged-script extraction into the structured extractor."""
        self._process_script_block_into(commands, list_path, start_index, sink)

    def _extract_legacy_mz_plugin_entries(
        self,
        commands: list[dict[str, Any]],
        list_path: str,
        start_index: int,
        sink: List[Tuple[str, str, str]],
    ) -> None:
        """Bridge legacy MZ plugin-block extraction into the structured extractor."""
        self._process_mz_plugin_block_into(commands, list_path, start_index, sink)

    def _extract_structured_note_entries(
        self,
        data: Any,
        current_path: str,
        sink: List[Tuple[str, str, str]],
    ) -> None:
        """Extract note-tag translations for structured files without reopening generic walking."""
        if isinstance(data, dict):
            for key, value in data.items():
                safe_key = self._escape_path_key(key)
                new_path = f"{current_path}.{safe_key}" if current_path else safe_key
                if key == "note" and isinstance(value, str) and value.strip():
                    for tag_path, tag_text in self._extract_tags_from_note(value, new_path):
                        sink.append((tag_path, tag_text, "dialogue_block"))
                    continue
                self._extract_structured_note_entries(value, new_path, sink)
            return

        if isinstance(data, list):
            for index, item in enumerate(data):
                new_path = f"{current_path}.{index}" if current_path else str(index)
                self._extract_structured_note_entries(item, new_path, sink)

    def _extract_system_terms(self, data: Any, path: str):
        """Extract system terms (basic, commands, params, messages)."""
        if isinstance(data, list):
            for i, item in enumerate(data):
                if self._is_extractable_runtime_text(item, is_dialogue=True):
                    self.extracted.append((f"{path}.{i}", item, "system"))
        elif isinstance(data, dict):
            for key, value in data.items():
                safe_key = self._escape_path_key(key)
                if self._is_extractable_runtime_text(value, is_dialogue=True):
                    self.extracted.append((f"{path}.{safe_key}", value, "system"))
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        if self._is_extractable_runtime_text(item, is_dialogue=True):
                            self.extracted.append((f"{path}.{safe_key}.{i}", item, "system"))

    @staticmethod
    def _is_sound_like_object(data: dict) -> bool:
        """Return True when a dict resembles an RPG Maker audio/sound spec.

        RPG Maker sound objects use {name, volume, pitch, pan}, but some
        plugins may omit keys.  Requiring 'name' plus at least one of the
        audio-specific keys (volume/pitch/pan) is enough to identify them.
        """
        if not isinstance(data, dict):
            return False
        if 'name' not in data:
            return False
        return bool(JsonParser._SOUND_SPEC_AUDIO_KEYS & data.keys())

    def _is_technical_string(self, text: str) -> bool:
        """Heuristic to check if a string is a file path, boolean-like, technical id, or JS code."""
        if not isinstance(text, str):
            return True
            
        # Strip literal surrounding quotes that sometimes escape JSON parsing in plugin params
        cleaned_text = text.strip('"\' \n\r\t')
        text_lower = cleaned_text.lower()
        
        # Stricter Heuristics for Javascript APIs
        js_managers = ['textmanager.', 'datamanager.', 'imagemanager.', 'scenemanager.', 'soundmanager.', 'audiomanager.', 'console.']
        if any(manager in text_lower for manager in js_managers):
            return True

        # Boolean strings often found in plugins
        if text_lower in ['true', 'false', 'on', 'off', 'null', 'undefined', 'none', '']:
            return True
            
        # File paths / embedded asset references
        if self._contains_asset_reference(cleaned_text):
            return True
            
        # Coordinates or pure numbers masquerading as strings
        if cleaned_text.replace(',', '').replace('.', '').replace(' ', '').lstrip('-').isdigit():
            return True

        # CSS Colors: hex, rgb, rgba
        if cleaned_text.startswith('#') and len(cleaned_text) in [4, 5, 7, 9]:
            return True
        if text_lower.startswith(('rgb(', 'rgba(')):
            return True
        
        # JavaScript code detection â€” NEVER translate JS code
        # Common JS patterns: return statements, function calls, variable declarations
        js_keywords = [
            'return ', 'return;', 'function(', 'function (',
            'const ', 'var ', 'let ', 'this.', 'new ',
            '=>', '===', '!==', '&&', '||',
            '.call(', '.apply(', '.bind(',
            'Math.', 'Graphics.', 'Window_', 'Scene_', 'Game_',
            'Sprite_', 'Bitmap.', 'bitmap.',
            'SceneManager.', 'BattleManager.', 'TextManager.',
            '$gameVariables', '$gameSwitches', '$gameParty',
            '$dataSystem', '$dataActors', '$dataItems',
            'ConfigManager[', 'config[',
        ]
        if any(kw in cleaned_text for kw in js_keywords):
            return True
        
        # JS-like patterns: semicolons at end, curly braces, parentheses with dots
        if cleaned_text.rstrip(';').endswith(';') and ('(' in cleaned_text or '.' in cleaned_text):
            return True
        if cleaned_text.strip().startswith(('if(', 'if (', 'for(', 'for (', 'while(')):
            return True
            
        # JS assignment or boolean evaluation (e.g. "show = true;", "enabled = false", "ext = 0;", "value += 1;")
        is_js_assign = False
        
        # 1. Has semicolon -> almost certainly JS (e.g., "show = true;")
        if re.fullmatch(r'^[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?\s*(?:[+\-*/]?={1,3}|!==?)\s*(?:true|false|null|undefined|!?[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?(?:\.[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?)*|\d+);$', cleaned_text):
            is_js_assign = True
        # 2. No semicolon, but RHS is a strict JS keyword (true, false, null, undefined)
        elif re.fullmatch(r'^[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?\s*(?:={1,3}|!==?)\s*(?:true|false|null|undefined)$', cleaned_text):
            is_js_assign = True
        # 3. Compound operators (+=, -=, *=, /=) without semicolon
        elif re.fullmatch(r'^[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?\s*(?:[+\-*/]={1,2})\s*(?:!?[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?(?:\.[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?)*|\d+)$', cleaned_text):
            is_js_assign = True
        # 4. Bracket notation or property access on either side (e.g. A[b] = c, a = b.c)
        elif re.fullmatch(r'^[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])+\s*(?:={1,3}|!==?)\s*(?:!?[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?(?:\.[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?)*|\d+)$', cleaned_text):
            is_js_assign = True
        elif re.fullmatch(r'^[a-zA-Z_][a-zA-Z0-9_]*\s*(?:={1,3}|!==?)\s*!?[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?(?:\.[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?)+$', cleaned_text):
            is_js_assign = True
            
        if is_js_assign:
            return True
            
        # 5. Strict eval/math expression detection (e.g., "100 + textSize * 10", "Width / 2", "1.5 * user", "x = y + Math.max(0, 10)")
        if re.fullmatch(r'^[\d\s\.\+\-\*/\(\)a-zA-Z_\[\]><=!&|?:,%;]+$', cleaned_text):
            # Must contain at least one operator and one letter
            if re.search(r'[\+\-\*/><=!&|]', cleaned_text) and re.search(r'[a-zA-Z]', cleaned_text):
                # Ensure no English/natural language consecutive words (e.g. "Name = John Doe").
                # Valid JS maths shouldn't have words separated ONLY by spaces.
                if not re.search(r'\b[a-zA-Z_]\w*\s+[a-zA-Z_]\w*\b', cleaned_text):
                    return True
                
        return False

    def _contains_asset_reference(self, text: str) -> bool:
        """Detect embedded asset/path references, even inside longer command strings."""
        if not isinstance(text, str):
            return False

        cleaned_text = text.strip().strip('"\'')
        if not cleaned_text:
            return False

        lower_text = cleaned_text.lower()
        if any(lower_text.endswith(ext) for ext in self.ASSET_FILE_EXTENSIONS):
            return True

        # NOTE: Use \s (not \\s) in raw strings to match whitespace correctly.
        # \\s in a raw string becomes regex [\s] = literal backslash + 's', NOT whitespace!
        if re.search(r"(?i)(?:^|[\s\\\"'`(=,:])(?:img|audio|movies|fonts|js|data|pictures|faces|characters|battlers|tilesets|parallaxes|sv_actors|sv_enemies|battlebacks[12]?)[/\\\\]", cleaned_text):
            return True

        ext_pattern = '|'.join(ext.lstrip('.') for ext in self.ASSET_FILE_EXTENSIONS)
        embedded_pattern = (
            r"(?i)(?:^|[\s\\\"'`(=,:])"
            r"(?:[a-z]:[/\\\\])?"
            r"(?:[^/\\\\\r\n\"'`]+[/\\\\])*"
            r"[^/\\\\\r\n\"'`]+\.(?:" + ext_pattern + r")(?=$|[^a-zA-Z0-9_])"
        )
        return re.search(embedded_pattern, cleaned_text) is not None


    def _looks_like_asset_name(self, text: str) -> bool:
        """Detect asset-like identifiers (supports embedded paths and spaced file names)."""
        if not isinstance(text, str):
            return False
        stripped = text.strip()
        if not stripped or '\n' in stripped or '\t' in stripped:
            return False
        if self._contains_asset_reference(stripped):
            return True
        if '/' in stripped or '\\' in stripped:
            return re.fullmatch(r'[A-Za-z0-9_ ./\\\-]+', stripped) is not None
        # Support spaced asset names (e.g. "Hero Face", "Actor1 Face") when word count is small.
        # Short spaced names (1-2 words) with only alphanumeric/underscore/hyphen chars are likely asset IDs.
        # Limit to 2 words to avoid false positives on sentence-like text (e.g. "The hero appears").
        if ' ' in stripped:
            words = stripped.split()
            if len(words) <= 2 and re.fullmatch(r'[A-Za-z0-9_ \-]+', stripped):
                return True
            return False
        return re.fullmatch(r'[A-Za-z0-9_\-]+', stripped) is not None

    def _is_extractable_runtime_text(self, text: Any, *, is_dialogue: bool = False) -> bool:
        """Central safety gate for extracted runtime text across JSON surfaces."""
        if not isinstance(text, str):
            return False
        if not self.is_safe_to_translate(text, is_dialogue=is_dialogue):
            return False
        if self._contains_asset_reference(text):
            return False
        if self._matches_known_asset_identifier(text):
            return False
        if self._is_technical_string(text):
            return False
        return True

    def _matches_known_asset_identifier(self, text: str) -> bool:
        """Return True when text matches a real asset basename/path from the current project."""
        if not isinstance(text, str) or not text.strip():
            return False
        if not self._known_asset_identifiers:
            return False

        normalized = text.strip().strip('"\'').replace('\\', '/').lower()
        if not normalized:
            return False

        candidates = {normalized}
        candidates.add(os.path.basename(normalized))
        stem, _ext = os.path.splitext(os.path.basename(normalized))
        if stem:
            candidates.add(stem)
        if '/' in normalized:
            rel_stem, _ = os.path.splitext(normalized)
            if rel_stem:
                candidates.add(rel_stem)

        return any(candidate in self._known_asset_identifiers for candidate in candidates)

    def _is_known_asset_text(self, text: str) -> bool:
        """Return True when text contains an explicit asset reference."""
        if not isinstance(text, str):
            return False
        # Do not use _matches_known_asset_identifier here.
        # It causes massive false positives during save (e.g. blocking the translation 
        # of "Wolf" because "Wolf.png" exists, or "Save" because "Save.ogg" exists).
        return self._contains_asset_reference(text)

    def _get_known_asset_identifiers(self, file_path: str) -> Set[str]:
        """Build or reuse a cached set of actual asset identifiers for the current project."""
        asset_root = self._find_asset_root(file_path)
        if not asset_root:
            return set()

        normalized_root = os.path.normpath(asset_root)
        with _ASSET_REGISTRY_LOCK:
            cached = _ASSET_REGISTRY_CACHE.get(normalized_root)
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

        with _ASSET_REGISTRY_LOCK:
            _ASSET_REGISTRY_CACHE[normalized_root] = identifiers
        return identifiers

    def _find_asset_root(self, file_path: str) -> str | None:
        """Locate the asset root (`www` for exports or project root otherwise)."""
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

    def apply_translation(self, file_path: str, translations: Dict[str, str]) -> Any:
        """Apply translations. Handles JSON, MV js/plugins.js, and locale files."""
        self.last_apply_error = None
        self._known_asset_identifiers = self._get_known_asset_identifiers(file_path)
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            content = f.read().strip()
            
        if not content:
            return None

        # Check if this is a locale file
        is_locale_file = self._is_locale_file(file_path)
        
        # Handle js/plugins.js
        is_js = file_path.lower().endswith('.js')
        is_main_plugins_js = is_js and os.path.basename(file_path).lower() == 'plugins.js'
        
        if is_js:
            if is_main_plugins_js:
                prefix, json_str, suffix = self._extract_js_json(content)
                if prefix and json_str:
                    self._js_prefix = prefix
                    self._js_suffix = suffix
                    try:
                        data = json.loads(json_str)
                    except json.JSONDecodeError:
                        self.last_apply_error = f"Could not parse JSON payload from {os.path.basename(file_path)}"
                        return None
                else:
                    self.last_apply_error = f"Unknown plugins.js wrapper format in {os.path.basename(file_path)}"
                    return None
            else:
                return self._apply_to_js_source(content, translations)
        else:
            if not self._looks_like_json_document(content):
                self.last_apply_error = f"Unsupported non-JSON sidecar in {os.path.basename(file_path)}"
                return None
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                self.last_apply_error = f"Could not parse JSON from {os.path.basename(file_path)}"
                return None
        original_data = copy.deepcopy(data) if isinstance(data, (dict, list)) else None
        if original_data is not None and (not is_js and not is_locale_file and self._structured_extractor.supports_file(file_path)):
            invalid_keys = self._find_invalid_structured_translation_keys(file_path, original_data, translations)
            if invalid_keys:
                joined = ", ".join(sorted(invalid_keys)[:5])
                self.last_apply_error = f"Structured surface rejected unsupported translation keys: {joined}"
                logger.error(
                    "Structured surface rejected unsupported keys in %s: %s",
                    os.path.basename(file_path),
                    joined,
                )
                return None
        
        applied_count = 0
        
        # Sort keys to handle nested JSON properly 
        # (Though dict order doesn't guarantee depth, but we process paths directly)
        
        # We need to handle nested JSON re-serialization. 
        # Identified by ".@JSON" in path.
        
        # Group translations by root path for nested JSON
        # e.g. path.to.param.@JSON.nested_key -> needs to update path.to.param
        
        nested_updates = {} # { 'path.to.param': { 'nested_key': 'trans' } }
        direct_updates = {}
        script_updates = {} # { 'base_path': [(line_count, js_index, trans_text), ...] }
        mv_plugin_updates = {} # { 'command_path': [(segment_index, trans_text), ...] }
        note_block_updates = {}
        note_inline_updates = {}
        
        def _try_int(value):
            try:
                return int(value)
            except (ValueError, TypeError):
                return None

        for path, trans_text in translations.items():
            if isinstance(trans_text, str):
                # Hardened Translation Sanitization: Translation engines (DeepL/Google/etc) often corrupt 
                # spacing around RPG Maker escape codes (turning "\n" into "\ n" or "\c[0]" into "\ c [0]").
                # This explicitly breaks JSON.parse() inside plugins when nested parameters are evaluated.
                # Here we repair one-or-more backslashes followed by spaces before a letter/brace.
                trans_text = re.sub(r'(\\+)\s+([a-zA-Z{}])', r'\1\2', trans_text)

            if self._should_block_asset_like_translation_update(original_data, path, trans_text):
                logger.warning(
                    "Skipping risky asset-like translation update in %s at %s",
                    os.path.basename(file_path),
                    path,
                )
                continue
                
            # IMPORTANT: Check @JSON BEFORE @JS because ".@JSON" contains ".@JS" as substring!
            # Without this order, @JSON paths would incorrectly enter the @JS branch.
            if ".@JSON" in path:
                # Split only on the FIRST @JSON to get root and nested parts
                parts = path.split(".@JSON", 1)
                root_part = parts[0]
                nested_part = parts[1] if len(parts) > 1 else ""
                # nested_part starts with .key, so remove leading dot
                if nested_part.startswith('.'):
                    nested_part = nested_part[1:]
                
                if root_part not in nested_updates:
                    nested_updates[root_part] = {}
                nested_updates[root_part][nested_part] = trans_text
            elif ".@MVCMD" in path:
                mv_cmd_split = path.split(".@MVCMD", 1)
                base_part = mv_cmd_split[0]
                segment_index = _try_int(mv_cmd_split[1])
                if segment_index is None or not base_part.endswith(".parameters.0"):
                    logger.warning(f"Skipping malformed MV plugin command path: {path}")
                    continue

                command_path = base_part.rsplit(".parameters.0", 1)[0]
                if command_path not in mv_plugin_updates:
                    mv_plugin_updates[command_path] = []
                mv_plugin_updates[command_path].append((segment_index, trans_text))
            elif ".@JS" in path:
                # Script string replacement (JSStringTokenizer paths)
                if ".@SCRIPTMERGE" in path:
                    # Format: base_path.@SCRIPTMERGEn.@JSm
                    merge_split = path.split(".@SCRIPTMERGE")
                    base_path = merge_split[0]
                    rest = merge_split[1]  # "n.@JSm"
                    merge_js_split = rest.split(".@JS")
                    line_count = _try_int(merge_js_split[0])
                    js_index = _try_int(merge_js_split[1])
                    if line_count is None or js_index is None:
                        logger.warning(f"Skipping malformed script path: {path}")
                        continue
                else:
                    # Format: base_path.parameters.0.@JSm
                    js_split = path.split(".@JS")
                    base_path = js_split[0].rsplit(".parameters.0", 1)[0]
                    js_index = _try_int(js_split[1])
                    if js_index is None:
                        logger.warning(f"Skipping malformed script path: {path}")
                        continue
                    line_count = 0
                
                if base_path not in script_updates:
                    script_updates[base_path] = []
                script_updates[base_path].append((line_count, js_index, trans_text))
            elif ".@NOTEBLOCK_" in path:
                parts = path.split(".@NOTEBLOCK_")
                base_path = parts[0]
                idx = _try_int(parts[1])
                if base_path not in note_block_updates: note_block_updates[base_path] = []
                note_block_updates[base_path].append((idx, trans_text))
            elif ".@NOTEINLINE_" in path:
                parts = path.split(".@NOTEINLINE_")
                base_path = parts[0]
                idx = _try_int(parts[1])
                if base_path not in note_inline_updates: note_inline_updates[base_path] = []
                note_inline_updates[base_path].append((idx, trans_text))
            else:
                direct_updates[path] = trans_text
                
        # 1. Apply Direct Translations
        for path, trans_text in direct_updates.items():
            if not trans_text: continue
            self._set_value_at_path(data, path, trans_text)
            
        # 2. Apply Nested JSON Translations (recursive for multi-level @JSON)
        for root_path, nested_trans in nested_updates.items():
            self._apply_nested_json_translation(data, root_path, nested_trans)
        
        # 3. Apply Script Translations (JSStringTokenizer paths)
        for base_path, updates in script_updates.items():
            self._apply_script_translation(data, base_path, updates)

        # 4. Apply MV Plugin Command Translations
        for command_path, updates in mv_plugin_updates.items():
            self._apply_mv_plugin_command_translation(data, command_path, updates)

        # 5. Apply Note Tag Translations
        for base_path, updates in note_block_updates.items():
            self._apply_note_tag_translation(data, base_path, updates, is_block=True)
        for base_path, updates in note_inline_updates.items():
            self._apply_note_tag_translation(data, base_path, updates, is_block=False)
                
        if is_locale_file:
            for key, trans_text in translations.items():
                if not isinstance(trans_text, str) or not trans_text:
                    continue
                self._set_value_at_path(data, key, trans_text)
            if original_data is not None:
                asset_violations = self._asset_invariant_verifier.find_mutated_assets(original_data, data)
                if asset_violations:
                    joined = ", ".join(item.path for item in asset_violations[:5])
                    self.last_apply_error = f"Asset invariant violation: {joined}"
                    logger.error("Asset invariant violation while applying %s: %s", os.path.basename(file_path), joined)
                    return None
            return data

        if is_main_plugins_js:
            if original_data is not None:
                asset_violations = self._asset_invariant_verifier.find_mutated_assets(original_data, data)
                if asset_violations:
                    joined = ", ".join(item.path for item in asset_violations[:5])
                    self.last_apply_error = f"Asset invariant violation: {joined}"
                    logger.error("Asset invariant violation while applying %s: %s", os.path.basename(file_path), joined)
                    return None
            # Preserve plugin parameters exactly unless the user explicitly translated them.
            # Reconstruct the plugin.js file
            new_json_str = json.dumps(data, indent=None, ensure_ascii=False, separators=(',', ':'))
            return self._js_prefix + new_json_str + self._js_suffix
        else:
            if original_data is not None:
                asset_violations = self._asset_invariant_verifier.find_mutated_assets(original_data, data)
                if asset_violations:
                    joined = ", ".join(item.path for item in asset_violations[:5])
                    self.last_apply_error = f"Asset invariant violation: {joined}"
                    logger.error("Asset invariant violation while applying %s: %s", os.path.basename(file_path), joined)
                    return None
            if original_data is not None and (not is_js and not is_locale_file and self._structured_extractor.supports_file(file_path)):
                allowed_paths = self._invariant_verifier.build_allowed_paths(translations.keys())
                violations = self._invariant_verifier.find_unexpected_changes(original_data, data, allowed_paths)
                if violations:
                    joined = ", ".join(f"{item.path} ({item.reason})" for item in violations[:5])
                    self.last_apply_error = f"Structured invariant violation: {joined}"
                    logger.error(
                        "Structured invariant violation while applying %s: %s",
                        os.path.basename(file_path),
                        joined,
                    )
                    return None
            return data

    def _should_block_asset_like_translation_update(
        self,
        original_data: Any,
        path: str,
        translated_value: Any,
    ) -> bool:
        """Return True when a translation update appears to mutate an asset identifier."""
        if original_data is None:
            return False
        if not isinstance(path, str) or not isinstance(translated_value, str):
            return False

        original_value = self._resolve_original_value_for_translation_path(original_data, path)
        if not isinstance(original_value, str):
            return False

        original_clean = original_value.strip().strip('"\'')
        translated_clean = translated_value.strip().strip('"\'')
        if not original_clean or not translated_clean:
            return False
        if original_clean == translated_clean:
            return False

        if self._is_plugin_parameter_path(path):
            if self._looks_like_plugin_registry_label(path, original_clean):
                return True
            if self._is_input_binding_key_context(path) and self._are_input_binding_tokens(original_clean):
                return True
            if self._is_technical_string(original_clean):
                return True

        path_asset_context = self._is_asset_context_path(path) or self._is_audio_key_context(path)
        if not path_asset_context:
            if not self._has_technical_key_hint(path):
                return False
            return self._is_risky_technical_identifier(original_clean)

        if self._looks_like_audio_parameter_value(original_clean):
            return True
        if self._contains_asset_reference(original_clean):
            return True
        if self._matches_known_asset_identifier(original_clean):
            return True
        if self._looks_like_asset_name(original_clean):
            return True
        return False

    def _is_plugin_parameter_path(self, path: str) -> bool:
        """Return True when path points inside plugins.js parameters."""
        if not isinstance(path, str):
            return False
        return ".parameters." in path or path.endswith(".parameters")

    def _looks_like_plugin_registry_label(self, path: str, value: str) -> bool:
        """Return True for plugin order labels that double as identifiers."""
        key_tokens = self._tokenize_key_hints(path)
        if "order" not in key_tokens:
            return False

        stripped = self._strip_rpgm_text_codes(value).strip()
        if not stripped or "\n" in stripped:
            return False

        if "category" in key_tokens:
            return re.fullmatch(r"[A-Za-z_][A-Za-z0-9_ ]*", stripped) is not None

        if "type" not in key_tokens:
            return False

        if re.fullmatch(r"[A-Za-z][A-Za-z0-9' _-]{0,39}", stripped) is None:
            return False
        word_count = len([word for word in stripped.split() if word])
        return 1 <= word_count <= 4

    def _is_risky_technical_identifier(self, value: str) -> bool:
        """Return True for short identifier-like technical values that must not be translated."""
        if not isinstance(value, str):
            return False
        cleaned = value.strip().strip('"\'')
        if not cleaned or '\n' in cleaned:
            return False
        if self._is_technical_string(cleaned):
            return True
        return re.fullmatch(r"[A-Za-z_][A-Za-z0-9_\-.]*", cleaned) is not None

    def _resolve_original_value_for_translation_path(self, data: Any, path: str) -> Any:
        """Resolve original source value for direct and nested @JSON translation paths."""
        if not isinstance(path, str) or not path:
            return None

        if ".@JSON" in path:
            root_path, nested_path = path.split(".@JSON", 1)
            nested_path = nested_path.lstrip('.')
            root_value = self._get_value_at_path(data, root_path)
            if not isinstance(root_value, str):
                return None
            try:
                nested_obj = json.loads(root_value)
            except (json.JSONDecodeError, TypeError):
                return None
            if not nested_path:
                return nested_obj
            return self._resolve_original_value_for_translation_path(nested_obj, nested_path)

        if any(marker in path for marker in (".@JS", ".@MVCMD", ".@NOTEBLOCK_", ".@NOTEINLINE_")):
            return None

        return self._get_value_at_path(data, path)

    def _find_invalid_structured_translation_keys(
        self,
        file_path: str,
        data: Any,
        translations: Dict[str, str],
    ) -> List[str]:
        """Return translation keys that are not part of the structured file's allowed surface."""
        allowed_entries: List[Tuple[str, str, str]] = []
        self._structured_extractor.extract(file_path, data, allowed_entries)
        if self.translate_notes and not is_protected_structured_noop_file(file_path):
            self._extract_structured_note_entries(data, "", allowed_entries)

        allowed_paths = {path for path, _text, _tag in allowed_entries}
        return [path for path in translations.keys() if path not in allowed_paths]

    def _apply_nested_json_translation(self, data: Any, root_path: str, nested_trans: dict):
        """
        Apply translations to nested JSON strings, handling arbitrary depth recursion.
        
        Supports paths like: a.b.@JSON.c.d.@JSON.e where there are multiple levels
        of JSON-encoded strings embedded within each other.
        """
        json_str = self._get_value_at_path(data, root_path)
        if not isinstance(json_str, str):
            return
            
        try:
            nested_obj = json.loads(json_str)
        except (json.JSONDecodeError, TypeError):
            return
        
        # Separate translations that go deeper vs. ones for this level
        deeper = {}   # paths that have another @JSON
        direct = {}   # paths without @JSON (apply directly to nested_obj)
        
        for sub_path, text in nested_trans.items():
            if ".@JSON" in sub_path:
                # There's another level of nesting
                parts = sub_path.split(".@JSON", 1)
                inner_root = parts[0]
                inner_rest = parts[1].lstrip('.')
                if inner_root not in deeper:
                    deeper[inner_root] = {}
                deeper[inner_root][inner_rest] = text
            else:
                direct[sub_path] = text
        
        # Apply direct translations to this level
        for sub_path, text in direct.items():
            if text:
                if sub_path == "":
                    # The translated text REPLACES the json root object itself (i.e. double-encoded strings like '"text"')
                    nested_obj = text
                else:
                    self._set_value_at_path(nested_obj, sub_path, text)
        
        # Recurse for deeper nested JSON levels
        for inner_root, inner_trans in deeper.items():
            self._apply_nested_json_translation(nested_obj, inner_root, inner_trans)
        
        # Re-serialize and save back to parent object
        new_json_str = json.dumps(nested_obj, ensure_ascii=False)
        self._set_value_at_path(data, root_path, new_json_str)

    def _apply_script_translation(self, data: Any, base_path: str, updates: list):
        """
        Apply translations to script blocks using JSStringTokenizer.
        
        Finds the script commands in the data, merges them, replaces string
        literals at the recorded positions, and splits back into lines.
        
        Args:
            data: The full JSON data structure
            base_path: Path to the first command (355) in the event list
            updates: List of (line_count, js_index, translated_text) tuples
        """
        # Parse base_path to find the event list and command index
        path_parts = base_path.rsplit('.', 1)
        if len(path_parts) != 2:
            return
        
        list_path = path_parts[0]
        try:
            cmd_index = int(path_parts[1])
        except ValueError:
            return
        
        # Get the event list
        event_list = self._get_value_at_path(data, list_path)
        if not isinstance(event_list, list):
            return
        
        # Determine line_count (take max from updates for safety)
        line_count = max(u[0] for u in updates) if updates else 0
        
        # Collect script commands
        script_cmds = []
        for k in range(cmd_index, min(cmd_index + 1 + line_count, len(event_list))):
            cmd = event_list[k]
            if isinstance(cmd, dict) and cmd.get("parameters"):
                script_cmds.append(cmd)
        
        if not script_cmds:
            return
        
        # Merge script lines
        lines = []
        for cmd in script_cmds:
            params = cmd.get("parameters", [""])
            lines.append(params[0] if params and isinstance(params[0], str) else "")
        
        merged = '\n'.join(lines)
        
        # Re-extract translatable strings to get current positions
        strings = self._js_tokenizer.extract_translatable_strings(merged)
        
        # Apply replacements in reverse order (preserve positions)
        updates_sorted = sorted(updates, key=lambda x: x[1], reverse=True)
        
        for _, js_index, trans_text in updates_sorted:
            if not trans_text or js_index >= len(strings):
                continue
            start, end, _, quote = strings[js_index]
            merged = self._js_tokenizer.replace_string_at(merged, start, end, quote, trans_text)
        
        # Split back into lines and update commands
        new_lines = merged.split('\n')
        for k, cmd in enumerate(script_cmds):
            if k < len(new_lines):
                cmd["parameters"][0] = new_lines[k]
            else:
                cmd["parameters"][0] = ""

    def _apply_mv_plugin_command_translation(self, data: Any, command_path: str, updates: list) -> None:
        """Replace extracted quoted text segments inside an MV plugin command."""
        command_value_path = f"{command_path}.parameters.0"
        command_text = self._get_value_at_path(data, command_value_path)
        if not isinstance(command_text, str):
            return

        segments = self._extract_quoted_segments(command_text)
        if not segments:
            return

        replacements = {segment_index: text for segment_index, text in updates if isinstance(text, str)}
        if not replacements:
            return

        rebuilt_parts: List[str] = []
        last_index = 0

        for segment_index, (start, end, quote_char, inner_text) in enumerate(segments):
            rebuilt_parts.append(command_text[last_index:start + 1])
            replacement_text = replacements.get(segment_index, inner_text)
            replacement_text = replacement_text.replace(quote_char, f"\\{quote_char}")
            rebuilt_parts.append(replacement_text)
            rebuilt_parts.append(quote_char)
            last_index = end + 1

        rebuilt_parts.append(command_text[last_index:])
        self._set_value_at_path(data, command_value_path, ''.join(rebuilt_parts))

    def _get_value_at_path(self, data: Any, path: str) -> Any:
        tmp_sep = "\0"
        clean_path = path.replace(self.PATH_DOT_ESCAPE, tmp_sep)
        # Filter out empty strings to handle leading or double dots
        keys = [k for k in clean_path.split('.') if k]
        
        ref = data
        try:
            i = 0
            while i < len(keys):
                k = keys[i]
                # Restore the escape sequence for unescaping
                k = k.replace(tmp_sep, self.PATH_DOT_ESCAPE)
                
                if isinstance(ref, list):
                    try:
                        k = int(k)
                    except ValueError:
                        # Fallback: list of dicts with string keys (legacy paths without index)
                        dict_key = self._unescape_path_key(k)
                        match = next((e for e in ref if isinstance(e, dict) and dict_key in e), None)
                        if match is None:
                            # Second fallback: key might contain unescaped dots (legacy format)
                            # Log warning and skip this path
                            logger.warning(f"Cannot resolve list index '{k}' in path: {path}")
                            return None
                        ref = match
                        i += 1
                        continue
                    if k >= len(ref):
                        logger.warning(f"List index {k} out of range in path: {path}")
                        return None
                    ref = ref[k]
                    i += 1
                    continue
                elif isinstance(ref, dict):
                    # Try direct key first
                    direct_key = self._unescape_path_key(k)
                    if direct_key in ref:
                        ref = ref[direct_key]
                        i += 1
                        continue

                    # Legacy support: merge subsequent segments to match dotted keys
                    merged = direct_key
                    found = False
                    for j in range(i + 1, len(keys)):
                        next_seg = keys[j].replace(tmp_sep, self.PATH_DOT_ESCAPE)
                        merged = f"{merged}.{self._unescape_path_key(next_seg)}"
                        if merged in ref:
                            ref = ref[merged]
                            i = j + 1
                            found = True
                            break
                    if not found:
                        return None
                    continue

                if ref is None:
                    return None
            return ref
        except (KeyError, IndexError, ValueError, TypeError):
            return None

    def _set_value_at_path(self, data: Any, path: str, value: Any):
        import re
        # Split path, but respect escaped dots
        tmp_sep = "\0"
        clean_path = path.replace(self.PATH_DOT_ESCAPE, tmp_sep)
        # Filter out empty strings to handle leading or double dots
        keys = [k for k in clean_path.split('.') if k]
        
        ref = data
        try:
            i = 0
            while i < len(keys) - 1:
                k = keys[i]
                # Restore the escape sequence for unescaping
                k = k.replace(tmp_sep, self.PATH_DOT_ESCAPE)
                
                if isinstance(ref, list):
                    try:
                        k = int(k)
                        if k >= len(ref):
                            logger.warning(f"List index {k} out of range in path: {path}")
                            return
                        ref = ref[k]
                    except ValueError:
                        # Fallback: list of dicts with string keys
                        dict_key = self._unescape_path_key(k)
                        match = next((e for e in ref if isinstance(e, dict) and dict_key in e), None)
                        if match is None:
                            # Second fallback: legacy unescaped dotted key
                            logger.warning(f"Cannot resolve list index '{k}' in path: {path}. Skipping.")
                            return
                        ref = match
                    i += 1
                    continue
                elif isinstance(ref, dict):
                    direct_key = self._unescape_path_key(k)
                    if direct_key in ref:
                        ref = ref[direct_key]
                        i += 1
                        continue

                    merged = direct_key
                    found = False
                    for j in range(i + 1, len(keys) - 1):
                        next_seg = keys[j].replace(tmp_sep, self.PATH_DOT_ESCAPE)
                        merged = f"{merged}.{self._unescape_path_key(next_seg)}"
                        if merged in ref:
                            ref = ref[merged]
                            i = j + 1
                            found = True
                            break
                    if not found:
                        return
                    continue
                else:
                    return

                i += 1
            
            last_key = keys[-1].replace(tmp_sep, self.PATH_DOT_ESCAPE)
            if isinstance(ref, list):
                try:
                    last_key = int(last_key)
                    if last_key >= len(ref):
                        logger.warning(f"List index {last_key} out of range in path: {path}")
                        return
                except (ValueError, TypeError) as e:
                    # Fallback: list of dicts with string keys
                    try:
                        dict_key = self._unescape_path_key(last_key)
                        match = next((e for e in ref if isinstance(e, dict) and dict_key in e), None)
                        if match is None:
                            # Second fallback: legacy unescaped dotted key
                            logger.warning(f"Cannot set list element with key '{last_key}' in path: {path}. Skipping.")
                            return
                        match[dict_key] = value
                        return
                    except Exception as ex:
                        logger.warning(f"Failed to set value in list at path {path}: {ex}")
                        return
            elif isinstance(ref, dict):
                try:
                    direct_key = self._unescape_path_key(last_key)
                    if direct_key in ref:
                        last_key = direct_key
                    else:
                        # Try merging with previous segments (legacy dotted keys)
                        merged = direct_key
                        idx = len(keys) - 2
                        while idx >= 0:
                            prev_seg = keys[idx].replace(tmp_sep, self.PATH_DOT_ESCAPE)
                            merged = f"{self._unescape_path_key(prev_seg)}.{merged}"
                            if merged in ref:
                                last_key = merged
                                break
                            idx -= 1
                        else:
                            last_key = direct_key
                except Exception as ex:
                    logger.warning(f"Failed to resolve dict key at path {path}: {ex}")
                    return
            
            # Check if this is a script command with $gameVariables.setValue pattern
            try:
                current_value = ref[last_key]
            except (KeyError, IndexError, TypeError) as e:
                logger.warning(f"Cannot access key '{last_key}' in path {path}: {e}")
                return
            except Exception as e:
                logger.warning(f"Unexpected error accessing path {path}: {e}")
                return

            if isinstance(current_value, str) and isinstance(value, str):
                # Check if target is a translated version of script command
                script_pattern = r'(\$gameVariables\.setValue\s*\(\s*\d+\s*,\s*["\'])(.+?)(["\'])\s*\)'
                current_match = re.search(script_pattern, current_value)
                value_match = re.search(script_pattern, value)
                
                if current_match and value_match:
                    # Both are script commands - extract the translated text and apply to current
                    translated_text = value_match.group(2)
                    # Replace only the dialogue part in the current script
                    new_script = re.sub(
                        script_pattern,
                        lambda m: m.group(1) + translated_text + m.group(3) + ')',
                        current_value
                    )
                    ref[last_key] = new_script
                    return
            
            ref[last_key] = value
        except (KeyError, IndexError, ValueError, TypeError) as e:
            logger.error(f"Failed to set value at {path}: {e}")
            pass

    def _extract_js_json(self, content: str) -> Tuple[str, str, str]:
        """
        Robustly extract the JSON part from a plugins.js file.
        Returns: (prefix, json_str, suffix) or (None, None, None)
        """
        # Find the start: var $plugins = 
        # Using regex to find the variable assignment, but not the end
        match = re.search(r'(var\s+\$plugins\s*=\s*)', content)
        if not match:
            return None, None, None
            
        prefix = match.group(1)
        start_idx = match.end()
        
        # Determine if it starts with [ or {
        # Scan forward to find first non-whitespace
        json_start = -1
        first_char = ''
        
        for i in range(start_idx, len(content)):
            char = content[i]
            if char.isspace():
                continue
            if char in ['[', '{']:
                json_start = i
                first_char = char
                break
            else:
                # Unexpected character
                return None, None, None
                
        if json_start == -1:
            return None, None, None
            
        # Brace counting
        stack = []
        json_end = -1
        in_string = False
        quote_char = ''
        escape = False
        
        for i in range(json_start, len(content)):
            char = content[i]
            
            if in_string:
                if escape:
                    escape = False
                elif char == '\\':
                    escape = True
                elif char == quote_char:
                    in_string = False
            else:
                if char == '"' or char == "'":
                    in_string = True
                    quote_char = char
                elif char == '[':
                    stack.append('[')
                elif char == '{':
                    stack.append('{')
                elif char == ']':
                    if not stack or stack[-1] != '[':
                        # Mismatched or extra closing brace?
                        # If stack is empty, we found the end
                        if not stack:
                             json_end = i + 1
                             break
                        return None, None, None # Error
                    stack.pop()
                    if not stack:
                        json_end = i + 1
                        break
                elif char == '}':
                    if not stack or stack[-1] != '{':
                        if not stack:
                             json_end = i + 1
                             break
                        return None, None, None
                    stack.pop()
                    if not stack:
                        json_end = i + 1
                        break
                        
        if json_end != -1:
            # Extract
            # prefix includes whitespace between = and [ ?
            # match.group(1) is "var $plugins ="
            # We need to construct prefix up to json_start
            full_prefix = content[:json_start]
            json_str = content[json_start:json_end]
            suffix = content[json_end:]
            return full_prefix, json_str, suffix
            
        return None, None, None

    def _extract_from_js_source(self, content: str):
        """Extract hardcoded translatable strings from JS plugin files."""
        strings = self._js_tokenizer.extract_translatable_strings(content)
        for idx, (start, end, text, quote) in enumerate(strings):
            if not text: continue
            
            # String must be a sentence or contain non-ascii to be safe
            has_spaces = ' ' in text.strip()
            has_non_ascii = any(ord(c) > 127 for c in text)
            
            if (has_spaces and len(text.strip()) > 3) or has_non_ascii:
                if self._is_extractable_runtime_text(text, is_dialogue=True):
                    path = f"JS_SRC_{idx}"
                    self.extracted.append((path, text, "system"))

    def _apply_to_js_source(self, content: str, translations: Dict[str, str]) -> str:
        """Apply translations to a hardcoded JS plugin file."""
        strings = self._js_tokenizer.extract_translatable_strings(content)
        sorted_strings = sorted(enumerate(strings), key=lambda x: x[1][0], reverse=True)
        
        result = content
        for idx, (start, end, text, quote) in sorted_strings:
            path = f"JS_SRC_{idx}"
            if path in translations and translations[path]:
                trans_text = translations[path]
                safe_trans = self._js_tokenizer._escape_for_js(trans_text, quote)
                result = result[:start] + safe_trans + result[end:]
                
        return result

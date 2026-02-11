"""
JSON Parser for RPG Maker MV/MZ games.
Handles extraction and injection of translatable text from JSON data files.
"""
import json
import os
import re
import logging
from typing import List, Dict, Any, Tuple, Set
from .base import BaseParser
from .specialized_plugins import get_specialized_parser
from .js_tokenizer import JSStringTokenizer

logger = logging.getLogger(__name__)

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
    }
    
    # Database fields that are always translatable
    DATABASE_FIELDS = {
        'name', 'description', 'nickname', 'profile',
        'message1', 'message2', 'message3', 'message4',
        'gameTitle', 'title', 'message', 'help', 'text', 'msg', 'dialogue',
        'label', 'format', 'string', 'prefix', 'suffix', 'commandName',
        'displayName',  # Map display names
        'currencyUnit',  # Currency unit in System.json
        'locale',  # Locale identifier
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
        'battleback2Name', 'bgm', 'bgs', 'parallaxName',
        'title1Name', 'title2Name',
        'note',  # Skip note by default (often contains plugin data)
    }
    
    # Expanded key patterns that commonly indicate translatable text in plugin parameters
    TEXT_KEY_INDICATORS = [
        'text', 'message', 'name', 'format', 'msg', 'desc',
        'title', 'label', 'caption', 'header', 'footer',
        'help', 'hint', 'tooltip', 'popup', 'notification',
        'dialogue', 'dialog', 'speech', 'talk',
        'menu', 'command', 'option', 'button',
        'string', 'content', 'display', 'info',
        'quest', 'journal', 'log', 'story',
        'victory', 'defeat', 'battle', 'escape',
    ]

    # Asset-related key hints (likely file names / asset identifiers, not UI text)
    ASSET_KEY_HINTS = [
        'title1', 'title2', 'titles1', 'titles2',
        'battleback', 'battlebacks', 'parallax',
        'face', 'character', 'tileset', 'battler',
        'picture', 'image', 'img', 'icon', 'sprite',
        'filename', 'file',
    ]

    PATH_DOT_ESCAPE = "__DOT__"
    PATH_DOT_ESCAPE_ESC = "__DOT_ESC__"
    
    def __init__(self, translate_notes: bool = False, translate_comments: bool = True, **kwargs):
        """
        Args:
            translate_notes: If True, includes 'note' fields for translation.
            translate_comments: If True, includes comments (code 108/408).
        """
        super().__init__(**kwargs)
        self.translate_notes = translate_notes
        self.translate_comments = translate_comments
        self.extracted: List[Tuple[str, str]] = []
        self._js_tokenizer = JSStringTokenizer()
        self._skip_fields = self.SKIP_FIELDS.copy()
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
    
    def extract_text(self, file_path: str) -> List[Tuple[str, str]]:
        """Extract translatable text. Handles JSON, MV js/plugins.js, and locale files."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            
        if not content:
            return []

        # Check if this is a locale file (locales/*.json - DKTools Localization etc.)
        is_locale_file = self._is_locale_file(file_path)
        
        # Handle js/plugins.js (MV)
        is_js = file_path.lower().endswith('.js')
        if is_js:
            prefix, json_str, suffix = self._extract_js_json(content)
            if prefix and json_str:
                try:
                    data = json.loads(json_str)
                except json.JSONDecodeError as e:
                     logger.error(f"Failed to parse JSON in {file_path}: {e}")
                     return []
            else:
                self.log_message.emit("warning", f"Skipping {os.path.basename(file_path)}: Unknown JS format")
                return []
        else:
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON file {file_path}: {e}")
                return []
            
        self.extracted = []
        
        # Handle locale files specially (simple key-value format)
        if is_locale_file:
            self._extract_from_locale(data)
        elif is_js:
             self._extract_from_plugins_js(data)
        else:
            self._walk(data, "")
        
        return self.extracted
    
    def _is_locale_file(self, file_path: str) -> bool:
        """Check if this is a locale file from DKTools or similar plugins."""
        # Normalize path separators and check if 'locales' folder is in path
        normalized = file_path.replace('\\', '/').lower()
        return '/locales/' in normalized and file_path.lower().endswith('.json')
    
    def _extract_from_locale(self, data: dict):
        """Extract text from locale files (key-value format)."""
        if not isinstance(data, dict):
            return
        
        for key, value in data.items():
            if not isinstance(value, str):
                continue
                
            # Skip empty or whitespace-only values
            text = value.strip()
            if not text:
                continue
            
            # Skip very short values (likely just symbols or single chars)
            if len(text) <= 1:
                continue
                
            # Skip technical strings (file paths, etc.)
            if self._is_technical_string(text):
                continue
            
            # The key is the path for locale files
            self.extracted.append((key, value, "system"))

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
            
            # Skip disabled plugins? Ideally yes, but users might enable them later.
            # Let's parse all.
            
            # Check for specialized parser
            specialized_parser = get_specialized_parser(name)
            
            if specialized_parser:
                logger.info(f"Using specialized parser for plugin: {name}")
                extracted_params = specialized_parser.extract_parameters(parameters, f"{i}.parameters")
                self.extracted.extend(extracted_params)
            else:
                # Fallback to generic walk for parameters
                self._walk(parameters, f"{i}.parameters")

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

    # VisuStella MZ / Yanfly type annotation suffixes that indicate NON-translatable values
    # e.g. "drawGameTitle:func" -> value is JavaScript code
    # e.g. "BattleSystem:eval" -> value is JS eval expression
    # e.g. "CodeJS:json" -> value is JS code encoded as JSON string
    CODE_KEY_SUFFIXES = (':func', ':eval', ':json', ':code', ':js')
    
    # VisuStella MZ suffixes that indicate structural containers (recurse into them)
    STRUCT_KEY_SUFFIXES = (':struct', ':arraystruct', ':arraystr', ':arraynum')
    
    # VisuStella MZ suffixes that indicate translatable string values
    TEXT_KEY_SUFFIXES = (':str', ':num')

    def _process_dict(self, data: dict, current_path: str):
        """Process a dictionary node."""
        # Heuristic: If this dict looks like a BGM/SE/Sound object, skip its 'name'
        is_sound_obj = all(k in data for k in ['name', 'volume', 'pitch', 'pan'])
        
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
                continue  # JavaScript code — NEVER translate
            
            # 1. RECURSIVE JSON CHECK
            if isinstance(value, str) and (value.startswith('{') or value.startswith('[')) and len(value) > 2:
                try:
                    nested_data = json.loads(value)
                    self._walk(nested_data, f"{new_path}.@JSON") 
                    continue 
                except (json.JSONDecodeError, TypeError):
                    pass 

            # Check logic for extraction
            should_extract = False
            is_plugin_param = ".parameters" in new_path or ".@JSON" in new_path or "parameters" in current_path
            
            if key in self.DATABASE_FIELDS or (key == 'name' and not is_sound_obj):
                should_extract = True
            elif is_plugin_param and isinstance(value, str):
                 # Skip asset identifiers in plugin params (file names / image lists)
                 key_lower = key.lower()
                 if any(hint in key_lower for hint in self.ASSET_KEY_HINTS) and self._looks_like_asset_name(value):
                     continue
                 # Heuristics for loosely structured plugin parameters
                 if self.is_safe_to_translate(value, is_dialogue=(key != 'note')):
                     if not self._is_technical_string(value):
                        # Extract if it contains spaces (likely sentence) or non-ascii (likely localized)
                        if ' ' in value or any(ord(c) > 127 for c in value):
                             should_extract = True
                        # Relaxed check: keys containing text-related indicators
                        elif any(k in key.lower() for k in self.TEXT_KEY_INDICATORS):
                             should_extract = True

            if should_extract:
                context_tag = "dialogue_block" if is_plugin_param or (key in ['message1', 'message2', 'message3', 'message4', 'help', 'description']) else "name"
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
        i = 0
        while i < len(data):
            item = data[i]
            # Avoid leading dot if current_path is empty
            new_path = f"{current_path}.{i}" if current_path else str(i)
            
            # Check for event command structure
            if isinstance(item, dict) and "code" in item and "parameters" in item:
                code = item.get("code")
                
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

            # Recurse
            self._walk(item, new_path)
            i += 1

    def _process_event_command(self, cmd: dict, path: str):
        """Process an RPG Maker event command for translatable text."""
        code = cmd.get("code")
        params = cmd.get("parameters", [])
        
        if code not in self.TEXT_EVENT_CODES:
            return
        
        # Show Text (401) / Scroll Text (405) / Show Text Header (101 - MZ Speaker Name)
        if code in [401, 405]:
            if len(params) > 0 and self.is_safe_to_translate(params[0], is_dialogue=True):
                self.extracted.append((f"{path}.parameters.0", params[0], "dialogue_block"))

        elif code == 101:
            # Code 101: Show Text Header.
            # in MZ: [faceName, faceIndex, background, positionType, speakerName]
            if len(params) >= 5:
                speaker_name = params[4]
                if self.is_safe_to_translate(speaker_name, is_dialogue=True):
                    self.extracted.append((f"{path}.parameters.4", speaker_name, "name"))
        
        # Show Scrolling Text Header (105)
        # Format: [speed, noFastForward] - no text here, but some plugins add title
        elif code == 105:
            # Standard code 105 doesn't have text, but check for extended params
            if len(params) >= 3 and isinstance(params[2], str):
                if self.is_safe_to_translate(params[2], is_dialogue=True):
                    self.extracted.append((f"{path}.parameters.2", params[2], "system"))
        
        # Show Choices (102)
        elif code == 102:
            choices = params[0] if len(params) > 0 else []
            if isinstance(choices, list):
                for c_i, choice in enumerate(choices):
                    if self.is_safe_to_translate(choice, is_dialogue=True):
                        self.extracted.append((f"{path}.parameters.0.{c_i}", choice, "choice"))
        
        # Comment (108/408) - Can contain plugin commands with text
        elif code in [108, 408] and self.translate_comments:
            if len(params) > 0 and isinstance(params[0], str):
                text = params[0].strip()
                # 1. Must be safe to translate
                if not self.is_safe_to_translate(text):
                    return
                    
                # 2. Only extract if it looks like actual text (not pure code)
                if text and not text.startswith('<') and not text.startswith('::'):
                    # Heuristic: contains spaces and no special plugin markers
                    if ' ' in text or len(text) > 20:
                        self.extracted.append((f"{path}.parameters.0", params[0], "comment"))
        
        elif code in [320, 324, 325]:
            if len(params) > 1 and self.is_safe_to_translate(params[1]):
                self.extracted.append((f"{path}.parameters.1", params[1], "name"))
        
        # Plugin Command MV (356) - params[0] is command string
        elif code == 356:
            if len(params) > 0 and isinstance(params[0], str):
                cmd_text = params[0]
                # Plugin commands often have embedded filenames. 
                # IF it looks like a path/filename, skip it entirely.
                if not self.is_safe_to_translate(cmd_text):
                    return

                # Extract if it seems to contain dialogue (quotes, long text)
                if '"' in cmd_text or len(cmd_text) > 50:
                    self.extracted.append((f"{path}.parameters.0", cmd_text, "dialogue_block"))
        
        # Plugin Command MZ (357) - structured differently
        elif code == 357:
            # MZ plugin commands have structured params, look for 'text' fields
            if len(params) >= 4:
                # params format: [pluginName, commandName, commandText, {args}]
                # Check commandText
                if self.is_safe_to_translate(params[2]):
                    self.extracted.append((f"{path}.parameters.2", params[2], "dialogue_block"))
                    
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
        base_path = f"{list_path}.{start_index}"
        
        # Use JSStringTokenizer to find all translatable strings
        strings = self._js_tokenizer.extract_translatable_strings(merged)
        
        for idx, (start, end, value, quote) in enumerate(strings):
            if not self.is_safe_to_translate(value, is_dialogue=True):
                continue
            
            if line_count > 0:
                path = f"{base_path}.@SCRIPTMERGE{line_count}.@JS{idx}"
            else:
                path = f"{base_path}.parameters.0.@JS{idx}"
            
            self.extracted.append((path, value, "dialogue_block"))

    def _process_mz_plugin_block(self, commands: list, list_path: str, start_index: int):
        """
        Process a merged MZ plugin command block (code 357 + zero or more 657 continuations).
        
        The first command (357) is processed normally. Continuation lines (657)
        may contain additional text parameters.
        """
        first = commands[0]
        base_path = f"{list_path}.{start_index}"
        
        # Process the first 357 command normally
        self._process_event_command(first, base_path)
        
        # Process 657 continuation lines
        for j, cmd in enumerate(commands[1:], 1):
            cmd_path = f"{list_path}.{start_index + j}"
            params = cmd.get("parameters", [])
            
            # 657 can carry additional text args or structured data
            if not params:
                continue
            
            # If first param is a string, check if translatable
            if isinstance(params[0], str):
                if self.is_safe_to_translate(params[0], is_dialogue=True):
                    self.extracted.append((f"{cmd_path}.parameters.0", params[0], "dialogue_block"))
            
            # If there's a dict arg (like 357's structured params), walk it
            for p_idx, param in enumerate(params):
                if isinstance(param, dict):
                    self._walk(param, f"{cmd_path}.parameters.{p_idx}")

    def _extract_system_terms(self, data: Any, path: str):
        """Extract system terms (basic, commands, params, messages)."""
        if isinstance(data, list):
            for i, item in enumerate(data):
                if self.is_safe_to_translate(item, is_dialogue=True):
                    self.extracted.append((f"{path}.{i}", item, "system"))
        elif isinstance(data, dict):
            for key, value in data.items():
                safe_key = self._escape_path_key(key)
                if self.is_safe_to_translate(value, is_dialogue=True):
                    self.extracted.append((f"{path}.{safe_key}", value, "system"))
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        if self.is_safe_to_translate(item, is_dialogue=True):
                            self.extracted.append((f"{path}.{safe_key}.{i}", item, "system"))

    def _is_technical_string(self, text: str) -> bool:
        """Heuristic to check if a string is a file path, boolean-like, technical id, or JS code."""
        if not isinstance(text, str):
            return True
        text_lower = text.lower().strip()
        
        # Boolean strings often found in plugins
        if text_lower in ['true', 'false', 'on', 'off', 'null', 'undefined', 'none', '']:
            return True
            
        # File paths
        if any(text_lower.endswith(ext) for ext in [
            '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tga', '.svg',  # Images
            '.ogg', '.wav', '.m4a', '.mp3', '.mid',  # Audio
            '.webm', '.mp4', '.avi',  # Video
            '.rpgmvp', '.rpgmvo', '.rpgmvm', '.rpgmvw'  # RPG Maker encrypted
        ]):
            return True
            
        # Coordinates or pure numbers masquerading as strings
        if text.replace(',', '').replace('.', '').replace(' ', '').lstrip('-').isdigit():
            return True

        # CSS Colors: hex, rgb, rgba
        if text.startswith('#') and len(text) in [4, 5, 7, 9]:
            return True
        if text_lower.startswith(('rgb(', 'rgba(')):
            return True
        
        # JavaScript code detection — NEVER translate JS code
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
        ]
        if any(kw in text for kw in js_keywords):
            return True
        
        # JS-like patterns: semicolons at end, curly braces, parentheses with dots
        if text.rstrip().endswith(';') and ('(' in text or '.' in text):
            return True
        if text.strip().startswith(('if(', 'if (', 'for(', 'for (', 'while(')):
            return True
            
        return False

    def _looks_like_asset_name(self, text: str) -> bool:
        """Detect asset-like identifiers (no spaces, simple chars, often file base names)."""
        if not isinstance(text, str):
            return False
        stripped = text.strip()
        if not stripped or ' ' in stripped or '\n' in stripped or '\t' in stripped:
            return False
        # Allow letters, numbers, underscore, dash, slash, and dot
        return re.fullmatch(r"[A-Za-z0-9_./\-]+", stripped) is not None

    def apply_translation(self, file_path: str, translations: Dict[str, str]) -> Any:
        """Apply translations. Handles JSON, MV js/plugins.js, and locale files."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            
        if not content:
            return None

        # Check if this is a locale file
        is_locale_file = self._is_locale_file(file_path)
        
        # Handle js/plugins.js
        is_js = file_path.lower().endswith('.js')
        
        if is_js:
            prefix, json_str, suffix = self._extract_js_json(content)
            if prefix and json_str:
                self._js_prefix = prefix
                self._js_suffix = suffix
                try:
                    data = json.loads(json_str)
                except json.JSONDecodeError:
                    return None
            else:
                return None
        else:
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                return None
        
        # For locale files, simply update the values by key
        if is_locale_file:
            if isinstance(data, dict):
                for key, trans_text in translations.items():
                    if key in data and trans_text:
                        data[key] = trans_text
            return data
            
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
        
        def _try_int(value):
            try:
                return int(value)
            except (ValueError, TypeError):
                return None

        for path, trans_text in translations.items():
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
                
        return data

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

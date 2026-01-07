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
        'terms', 'types'
    }
    
    # Fields to skip (internal use, not for translation)
    SKIP_FIELDS = {
        'id', 'animationId', 'characterIndex', 'characterName',
        'faceName', 'faceIndex', 'tilesetId', 'battleback1Name',
        'battleback2Name', 'bgm', 'bgs', 'parallaxName',
        'note',  # Skip note by default (often contains plugin data)
    }
    
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
        self._skip_fields = self.SKIP_FIELDS.copy()
        if translate_notes:
            self._skip_fields.discard('note')
    
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
            import re
            # Find the start of the array [...] or object {...} after var $plugins =
            match = re.search(r'(var\s+\$plugins\s*=\s*)([\s\S]*?)(\s*;?\s*$)', content)
            if match:
                prefix = match.group(1)
                json_part = match.group(2).strip()
                try:
                    data = json.loads(json_part)
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
            self.extracted.append((key, value))

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

    def _process_dict(self, data: dict, current_path: str):
        """Process a dictionary node."""
        # Heuristic: If this dict looks like a BGM/SE/Sound object, skip its 'name'
        is_sound_obj = all(k in data for k in ['name', 'volume', 'pitch', 'pan'])
        
        for key, value in data.items():
            new_path = f"{current_path}.{key}" if current_path else key
            
            # Skip internal fields
            if key in self._skip_fields:
                continue
                
            # Skip name in sound objects
            if is_sound_obj and key == 'name':
                continue
            
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
                 # Heuristics for loosely structured plugin parameters
                 if self.is_safe_to_translate(value, is_dialogue=(key != 'note')):
                     if not self._is_technical_string(value):
                        # Extract if it contains spaces (likely sentence) or non-ascii (likely localized)
                        if ' ' in value or any(ord(c) > 127 for c in value):
                             should_extract = True
                        # Relaxed check: keys containing 'Text', 'Message', 'Name', 'Format'
                        elif any(k in key.lower() for k in ['text', 'message', 'name', 'format', 'msg', 'desc']):
                             should_extract = True

            if should_extract:
                self.extracted.append((new_path, value))
                continue
            
            # Check system terms
            if key in self.SYSTEM_TERMS:
                self._extract_system_terms(value, new_path)
                continue
            
            # Recurse
            self._walk(value, new_path)

    def _process_list(self, data: list, current_path: str):
        """Process a list node, including event commands."""
        for i, item in enumerate(data):
            new_path = f"{current_path}.{i}"
            
            # Check for event command structure
            if isinstance(item, dict) and "code" in item and "parameters" in item:
                self._process_event_command(item, new_path)
            
            # Check for Nested JSON strings in list items
            if isinstance(item, str):
                 if (item.startswith('{') or item.startswith('[')) and len(item) > 2:
                    try:
                        nested_data = json.loads(item)
                        self._walk(nested_data, f"{new_path}.@JSON")
                        continue
                    except (json.JSONDecodeError, TypeError):
                        pass

            # Recurse
            self._walk(item, new_path)

    def _process_event_command(self, cmd: dict, path: str):
        """Process an RPG Maker event command for translatable text."""
        code = cmd.get("code")
        params = cmd.get("parameters", [])
        
        if code not in self.TEXT_EVENT_CODES:
            return
        
        # Show Text (401) / Scroll Text (405) / Show Text Header (101 - MZ Speaker Name)
        if code in [401, 405]:
            if len(params) > 0 and self.is_safe_to_translate(params[0], is_dialogue=True):
                self.extracted.append((f"{path}.parameters.0", params[0]))

        elif code == 101:
            # Code 101: Show Text Header.
            # in MZ: [faceName, faceIndex, background, positionType, speakerName]
            if len(params) >= 5:
                speaker_name = params[4]
                if self.is_safe_to_translate(speaker_name, is_dialogue=True):
                    self.extracted.append((f"{path}.parameters.4", speaker_name))
        
        # Show Scrolling Text Header (105)
        # Format: [speed, noFastForward] - no text here, but some plugins add title
        elif code == 105:
            # Standard code 105 doesn't have text, but check for extended params
            if len(params) >= 3 and isinstance(params[2], str):
                if self.is_safe_to_translate(params[2], is_dialogue=True):
                    self.extracted.append((f"{path}.parameters.2", params[2]))
        
        # Show Choices (102)
        elif code == 102:
            choices = params[0] if len(params) > 0 else []
            if isinstance(choices, list):
                for c_i, choice in enumerate(choices):
                    if self.is_safe_to_translate(choice, is_dialogue=True):
                        self.extracted.append((f"{path}.parameters.0.{c_i}", choice))
        
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
                        self.extracted.append((f"{path}.parameters.0", params[0]))
        
        elif code in [320, 324, 325]:
            if len(params) > 1 and self.is_safe_to_translate(params[1]):
                self.extracted.append((f"{path}.parameters.1", params[1]))
        
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
                    self.extracted.append((f"{path}.parameters.0", cmd_text))
        
        # Plugin Command MZ (357) - structured differently
        elif code == 357:
            # MZ plugin commands have structured params, look for 'text' fields
            if len(params) >= 4:
                # params format: [pluginName, commandName, commandText, {args}]
                # Check commandText
                if self.is_safe_to_translate(params[2]):
                    self.extracted.append((f"{path}.parameters.2", params[2]))
                    
                # Also check args dict for common text fields
                if len(params) > 3 and isinstance(params[3], dict):
                    args = params[3]
                    # RECURSIVE CHECK HERE TOO
                    self._walk(args, f"{path}.parameters.3")
        
        # Script commands (355/655) - extract text from $gameVariables.setValue patterns
        # Common in visual novel style games like Treasure of Nadia
        elif code in [355, 655]:
            if len(params) > 0 and isinstance(params[0], str):
                script_text = params[0]
                # Look for $gameVariables.setValue(N, "...") pattern
                # This is commonly used for custom dialogue systems
                # Match patterns like: $gameVariables.setValue(21, "text here")
                # Capture the variable number and the text
                match = re.search(r'\$gameVariables\.setValue\s*\(\s*(\d+)\s*,\s*["\'](.+?)["\']\s*\)', script_text)
                if match:
                    var_num = match.group(1)
                    dialogue_text = match.group(2)
                    
                    # FIRST: Check for dialogue-like patterns (speaker prefixes like "MlBaEx>." "HeWoCl<.")
                    # These visual novel games use format: "SpeakerCodeExpression.Dialogue text"
                    # Pattern: 2 letters + 2 letters + 2 letters + delimiter (< > .)
                    has_dialogue_prefix = re.match(r'^[A-Za-z]{2}[A-Za-z]{2}[A-Za-z]{2}[<>.]', dialogue_text) is not None
                    
                    if has_dialogue_prefix:
                        # This is dialogue - extract it
                        self.extracted.append((f"{path}.parameters.0", script_text))
                        return
                    
                    # SECOND: Check if it's a filename/asset name (only if NOT dialogue)
                    is_filename_like = (
                        # No spaces and contains dashes/underscores (likely filename)
                        (' ' not in dialogue_text and ('-' in dialogue_text or '_' in dialogue_text) and len(dialogue_text) < 50) or
                        # Contains common asset prefixes (like PopUp-, BG-, CHR-, etc.)
                        re.match(r'^(PopUp|BG|CHR|GUI|MSG|MAP|FGUI|SP|SM|CG|ALBUM|HINT|KSPAGE|POPTEXT|Phone)-', dialogue_text) is not None or
                        # Video/function references
                        dialogue_text.endswith(('.mp4', '.ogg', '.m4a', '.webm', '.png', '.jpg'))
                    )
                    
                    if is_filename_like:
                        return  # Skip extraction for filenames
                    
                    # THIRD: For other text, extract if it looks like natural language
                    if self.is_safe_to_translate(dialogue_text, is_dialogue=True) and ' ' in dialogue_text:
                        self.extracted.append((f"{path}.parameters.0", script_text))

    def _extract_system_terms(self, data: Any, path: str):
        """Extract system terms (basic, commands, params, messages)."""
        if isinstance(data, list):
            for i, item in enumerate(data):
                if self.is_safe_to_translate(item, is_dialogue=True):
                    self.extracted.append((f"{path}.{i}", item))
        elif isinstance(data, dict):
            for key, value in data.items():
                if self.is_safe_to_translate(value, is_dialogue=True):
                    self.extracted.append((f"{path}.{key}", value))
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        if self.is_safe_to_translate(item, is_dialogue=True):
                            self.extracted.append((f"{path}.{key}.{i}", item))

    def _is_technical_string(self, text: str) -> bool:
        """Heuristic to check if a string is a file path, boolean-like, or technical id."""
        if not isinstance(text, str):
            return True
        text_lower = text.lower()
        
        # Boolean strings often found in plugins
        if text_lower in ['true', 'false', 'on', 'off', 'null', 'undefined']:
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
        if text.replace(',', '').replace('.', '').lstrip('-').isdigit():
            return True

        return False

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
            import re
            match = re.search(r'^([\s\S]*?var\s+\$plugins\s*=\s*)([\s\S]*?)(;?\s*$)', content)
            if match:
                self._js_prefix = match.group(1)
                json_str = match.group(2).strip()
                self._js_suffix = match.group(3)
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
        
        for path, trans_text in translations.items():
            if ".@JSON" in path:
                # Split only on the FIRST @JSON to get root and nested parts
                # This handles deeply nested JSON like: path.@JSON.inner.@JSON.deeper
                parts = path.split(".@JSON", 1)
                root_part = parts[0]
                nested_part = parts[1] if len(parts) > 1 else ""
                # nested_part starts with .key, so remove leading dot
                if nested_part.startswith('.'):
                    nested_part = nested_part[1:]
                
                if root_part not in nested_updates:
                    nested_updates[root_part] = {}
                nested_updates[root_part][nested_part] = trans_text
            else:
                direct_updates[path] = trans_text
                
        # 1. Apply Direct Translations
        for path, trans_text in direct_updates.items():
            if not trans_text: continue
            self._set_value_at_path(data, path, trans_text)
            
        # 2. Apply Nested JSON Translations
        for root_path, nested_trans in nested_updates.items():
            # Get the current JSON string
            json_str = self._get_value_at_path(data, root_path)
            if not isinstance(json_str, str):
                continue
                
            try:
                # Parse it
                nested_obj = json.loads(json_str)
                
                # Apply translations to this object
                for sub_path, text in nested_trans.items():
                     self._set_value_at_path(nested_obj, sub_path, text)
                
                # Re-serialize
                # Note: We must ensure we don't break format if inconsistent, 
                # but standard json.dumps is usually safe enough for plugins.js
                new_json_str = json.dumps(nested_obj, ensure_ascii=False)
                
                # Save back to main object
                self._set_value_at_path(data, root_path, new_json_str)
                
            except (json.JSONDecodeError, TypeError):
                continue
                
        return data

    def _get_value_at_path(self, data: Any, path: str) -> Any:
        keys = path.split('.')
        ref = data
        try:
            for k in keys:
                if isinstance(ref, list):
                    k = int(k)
                ref = ref[k]
            return ref
        except (KeyError, IndexError, ValueError, TypeError):
            return None

    def _set_value_at_path(self, data: Any, path: str, value: Any):
        import re
        keys = path.split('.')
        ref = data
        try:
            for k in keys[:-1]:
                if isinstance(ref, list):
                    k = int(k)
                ref = ref[k]
            
            last_key = keys[-1]
            if isinstance(ref, list):
                last_key = int(last_key)
            
            # Check if this is a script command with $gameVariables.setValue pattern
            current_value = ref[last_key]
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
        except (KeyError, IndexError, ValueError, TypeError):
            pass

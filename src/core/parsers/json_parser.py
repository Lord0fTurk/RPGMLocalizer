"""
JSON Parser for RPG Maker MV/MZ games.
Handles extraction and injection of translatable text from JSON data files.
"""
import json
import os
from typing import List, Dict, Any, Tuple, Set
from .base import BaseParser


class JsonParser(BaseParser):
    """
    Parser for RPG Maker MV/MZ JSON files.
    Supports: Actors, Items, Skills, Weapons, Armors, Enemies, States, 
              CommonEvents, Maps, System, and more.
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
    }
    
    # Database fields that are always translatable
    DATABASE_FIELDS = {
        'name', 'description', 'nickname', 'profile',
        'message1', 'message2', 'message3', 'message4',
        'gameTitle', 'title', 'message', 'help', 'text', 'msg', 'dialogue',
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
        """Extract translatable text. Handles JSON and MV js/plugins.js."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            
        if not content:
            return []

        # Handle js/plugins.js (MV)
        is_js = file_path.lower().endswith('.js')
        if is_js:
            import re
            # Find the start of the array [...] or object {...} after var $plugins =
            # We look for the first [ or { after the assignment and take everything until the last ] or }
            match = re.search(r'(var\s+\$plugins\s*=\s*)([\s\S]*?)(\s*;?\s*$)', content)
            if match:
                prefix = match.group(1)
                json_part = match.group(2).strip()
                # Ensure we only take the balanced JSON part if there are trailing comments
                # For plugins.js it's usually just an array at the end of the file
                data = json.loads(json_part)
            else:
                # If it doesn't match the pattern, it's not a standard RPG Maker plugins file
                self.log_message.emit("warning", f"Skipping {os.path.basename(file_path)}: Unknown JS format")
                return []
        else:
            data = json.loads(content)
            
        self.extracted = []
        self._walk(data, "")
        return self.extracted

    def _walk(self, data: Any, current_path: str):
        """Recursively walk JSON structure to find translatable text."""
        if isinstance(data, dict):
            self._process_dict(data, current_path)
        elif isinstance(data, list):
            self._process_list(data, current_path)

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
            
            # Check database fields
            if key in self.DATABASE_FIELDS or (key == 'name' and not is_sound_obj):
                if self.is_safe_to_translate(value, is_dialogue=(key != 'note')):
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
            
            # Recurse
            self._walk(item, new_path)

    def _process_event_command(self, cmd: dict, path: str):
        """Process an RPG Maker event command for translatable text."""
        code = cmd.get("code")
        params = cmd.get("parameters", [])
        
        if code not in self.TEXT_EVENT_CODES:
            return
        
        code_type = self.TEXT_EVENT_CODES[code]
        
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
                    for arg_key in ['text', 'Text', 'message', 'Message', 'dialogue', 'Dialogue']:
                        if arg_key in args and self.is_safe_to_translate(args[arg_key]):
                            self.extracted.append((f"{path}.parameters.3.{arg_key}", args[arg_key]))

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

    def apply_translation(self, file_path: str, translations: Dict[str, str]) -> Any:
        """Apply translations. Handles JSON and MV js/plugins.js."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            
        if not content:
            return None

        # Handle js/plugins.js
        is_js = file_path.lower().endswith('.js')
        
        if is_js:
            import re
            # Find the JSON part and anything before/after it
            match = re.search(r'^([\s\S]*?var\s+\$plugins\s*=\s*)([\s\S]*?)(;?\s*$)', content)
            if match:
                self._js_prefix = match.group(1)
                json_str = match.group(2).strip()
                self._js_suffix = match.group(3)
                data = json.loads(json_str)
            else:
                return None
        else:
            data = json.loads(content)
            
        applied_count = 0
        
        for path, trans_text in translations.items():
            if not trans_text:
                continue
            
            keys = path.split('.')
            ref = data
            
            try:
                # Traverse to parent
                for k in keys[:-1]:
                    if isinstance(ref, list):
                        k = int(k)
                    ref = ref[k]
                
                # Set value
                last_key = keys[-1]
                if isinstance(ref, list):
                    last_key = int(last_key)
                    
                ref[last_key] = trans_text
                applied_count += 1
                
            except (KeyError, IndexError, ValueError, TypeError):
                # Path no longer valid (data structure changed)
                pass
                
        return data

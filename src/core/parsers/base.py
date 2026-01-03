from abc import ABC, abstractmethod, ABCMeta
from typing import List, Any, Dict, Tuple
from PyQt6.QtCore import QObject, pyqtSignal as Signal


class ParserMeta(type(QObject), ABCMeta):
    """Metaclass that combines QObject's meta and ABCMeta to avoid conflicts."""
    pass


class BaseParser(QObject, metaclass=ParserMeta):
    """Base class for all parsers."""
    log_message = Signal(str, str)  # level, message

    def __init__(self, regex_blacklist: List[str] = None):
        super().__init__()
        import re
        self.blacklist_patterns = []
        if regex_blacklist:
            for pattern in regex_blacklist:
                try:
                    if pattern.strip():
                        self.blacklist_patterns.append(re.compile(pattern.strip(), re.IGNORECASE))
                except re.error:
                    pass  # Ignore invalid regex

    @abstractmethod
    def extract_text(self, file_path: str) -> List[Tuple[str, str]]:
        """
        Extracts translatable text.
        Returns list of (path_key, text).
        path_key is a string identifier to locate the text later (e.g. "events.1.pages.0.list.5.parameters.0")
        """
        pass

    @abstractmethod
    def apply_translation(self, file_path: str, translations: Dict[str, str]) -> Any:
        """
        Applies translations to the file content.
        translations: dict mapping path_key -> translated_text
        Returns the modified data structure (dict/list) ready to be saved.
        """
        pass

    def is_safe_to_translate(self, text: str, is_dialogue: bool = False) -> bool:
        """
        Heuristic to determine if a string is safe to translate.
        Filters out filenames, paths, internal keys, and asset IDs.
        
        Args:
            text: String to check
            is_dialogue: If True, bypasses some strict checks (used for Show Text, etc.)
        """
        if not text or not isinstance(text, str):
            return False
        
        trimmed = text.strip()
        if not trimmed:
            return False

        # 0. Check User Blacklist
        if self.blacklist_patterns:
            for pattern in self.blacklist_patterns:
                if pattern.search(trimmed):
                    return False

        # 1. Ignore common file extensions
        ignored_extensions = {
            '.ogg', '.m4a', '.wav', '.mp3', '.mid', # Audio
            '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.svg', '.tga', # Images
            '.webm', '.mp4', '.avi', '.mov', # Video
            '.rpgmvp', '.rpgmvo', '.rpgmvm', '.rpgmvw', # RPG Maker encrypted
            '.css', '.js', '.json', '.txt', '.map', '.bin', # Scripts/Data
            '.rvdata2', '.rxdata', '.rvdata' # Ruby Marshal
        }
        lower_trimmed = trimmed.lower()
        if any(lower_trimmed.endswith(ext) for ext in ignored_extensions):
            return False
            
        # 2. Ignore paths (contain slashes and no spaces)
        if ('/' in trimmed or '\\' in trimmed) and ' ' not in trimmed:
            return False
        
        # 3. Ignore technical identifiers / Asset IDs
        if ' ' not in trimmed:
            # If it has underscores or Mixed_Case, likely a key
            if '_' in trimmed:
                return False
            
            # Check for asset IDs (starts with text, ends with numbers e.g., pla1, actor1)
            # But allow if is_dialogue is true (e.g., "Attack1" might be a skill name)
            if not is_dialogue:
                if any(c.isdigit() for c in trimmed):
                    return False
                if any(c.isupper() for c in trimmed[1:]) and any(c.islower() for c in trimmed):
                    return False
            
            # Short ASCII strings that look like IDs (e.g., 'v1', 'id')
            if len(trimmed) < 2 and trimmed.isascii():
                return False

        # 4. Ignore pure numbers or special symbols
        clean_num = trimmed.replace('.', '').replace('-', '').replace(' ', '')
        if clean_num.isdigit():
            return False

        # 5. Ignore common plugin/engine prefixes
        prefixes = ('v[', 'n[', 'i[', '<', '::', 'eval(', 'Script:', 'Plugin:')
        if lower_trimmed.startswith(prefixes) and not is_dialogue:
            return False

        return True

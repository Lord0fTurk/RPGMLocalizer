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
    def extract_text(self, file_path: str) -> List[Tuple[str, str, str]]:
        """
        Extracts translatable text.
        Returns list of (path_key, text, context_tag).
        path_key: string identifier to locate the text (e.g. "events.1.pages.0.list.5.parameters.0")
        text: string to translate
        context_tag: type of text (e.g. 'dialogue', 'name', 'system', 'other')
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

    def contains_only_control_codes(self, text: str) -> bool:
        """Return True when text is composed only of RPG Maker control codes."""
        if not isinstance(text, str):
            return False

        stripped = text.strip()
        if not stripped:
            return False

        import re

        pattern = (
            r"(?:\s*"
            r"(?:\\[A-Za-z]+(?:\[[^\]\r\n]*\])?"
            r"|\\[!><\^.$|{}_])"
            r")+"
            r"\s*"
        )
        return re.fullmatch(pattern, stripped) is not None

    def looks_like_translatable_comment(self, text: str) -> bool:
        """Heuristic gate for event comments, which often contain plugin logic."""
        if not isinstance(text, str):
            return False

        stripped = text.strip()
        if not stripped or self.contains_only_control_codes(stripped):
            return False

        import re

        if stripped.startswith(("<", "::", "//", "/*", "*/", "@")):
            return False

        has_non_ascii = any(ord(char) > 127 for char in stripped)
        has_sentence_punctuation = any(mark in stripped for mark in ".!?;:。！？")
        word_count = len(stripped.split())

        if not has_non_ascii and not has_sentence_punctuation:
            command_like_pattern = (
                r"[A-Za-z0-9_./\\:=<>\-\[\],]+"
                r"(?:\s+[A-Za-z0-9_./\\:=<>\-\[\],]+)*"
            )
            if re.fullmatch(command_like_pattern, stripped):
                return False

        if has_non_ascii:
            return has_sentence_punctuation or word_count >= 2 or len(stripped) >= 10

        return has_sentence_punctuation or word_count >= 3

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
        
        # Strip whitespace AND string literal quotes 
        trimmed = text.strip('"\' \n\r\t')
        if not trimmed:
            return False

        if self.contains_only_control_codes(trimmed):
            return False

        # 0. Check User Blacklist
        if self.blacklist_patterns:
            for pattern in self.blacklist_patterns:
                if pattern.search(trimmed):
                    return False
        
        lower_trimmed = trimmed.lower()

        # 1. Ignore common file extensions (Expanded List)
        ignored_extensions = {
            # Audio
            '.ogg', '.m4a', '.wav', '.mp3', '.mid', '.midi', '.wma',
            # Images
            '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.svg', '.tga', '.psd',
            # Video
            '.webm', '.mp4', '.avi', '.mov', '.ogv', '.mkv',
            # RPG Maker Data / Script / Encrypted
            '.rpgmvp', '.rpgmvo', '.rpgmvm', '.rpgmvw', 
            '.css', '.js', '.json', '.txt', '.map', '.bin', '.dll',
            '.rvdata2', '.rxdata', '.rvdata', '.rb', '.coffee'
        }
        if any(lower_trimmed.endswith(ext) for ext in ignored_extensions):
            return False
            
        # 2. Ignore pure technical keywords (Plugin settings)
        technical_keywords = {
            'true', 'false', 'null', 'undefined', 'nan', 'none',
            'auto', 'always', 'never', 'default',
            'top', 'bottom', 'left', 'right', 'center', 'middle',
            'width', 'height', 'opacity', 'scale', 'blend',
            'x', 'y', 'z', 'id', 'index', 'code'
        }
        if lower_trimmed in technical_keywords:
            return False

        # 3. Ignore paths (contain slashes and no spaces)
        # BUT: Allow backslashes if the string contains non-ASCII characters (likely Japanese with control codes like \C[0])
        has_non_ascii = any(ord(c) > 127 for c in trimmed)
        # Forward slashes: always indicate paths
        if '/' in trimmed and ' ' not in trimmed:
            return False
        # Backslashes in non-dialogue mode: likely Windows paths
        # In dialogue mode: RPG Maker escape codes (\^, \C[N], \V[N]) use backslashes,
        # so we must not reject dialogue just because it contains backslashes.
        if '\\' in trimmed and not has_non_ascii and ' ' not in trimmed and not is_dialogue:
            return False
        
        # 4. Ignore Asset Names and Resource Keys
        if ' ' not in trimmed:
            # RPG Maker Asset Prefixes: $BigChar, !Door (only if no spaces)
            if trimmed.startswith(('$', '!')):
                return False
                
            # Allow if it contains non-ASCII characters (likely localized text even if single word/no spaces)
            if has_non_ascii:
                return True
                
            # If it has underscores or Mixed_Case, likely a key/variable - SKIP
            if '_' in trimmed:
                return False
            
            # Check for asset IDs (starts with text, ends with numbers e.g., pla1, actor1)
            # But allow if is_dialogue is true (e.g., "Attack1" might be a skill name)
            if not is_dialogue:
                # Common asset patterns like Actor1, Map001, etc.
                if any(c.isdigit() for c in trimmed) and any(c.isalpha() for c in trimmed):
                    return False
                # MixedCase strings without spaces are usually class names or keys
                if any(c.isupper() for c in trimmed[1:]) and any(c.islower() for c in trimmed):
                    return False
            
            # Short ASCII strings that look like IDs (e.g., 'v1', 'id')
            if len(trimmed) < 2 and trimmed.isascii():
                return False

        # 5. Ignore pure numbers or special symbols
        clean_num = trimmed.replace('.', '').replace('-', '').replace(' ', '').replace(',', '')
        if clean_num.isdigit():
            return False

        # 6. Ignore common CSS color patterns (rgb, rgba, hex)
        # hex colors: #abc, #aabbcc, #aabbccff
        if trimmed.startswith('#') and len(trimmed) in [4, 5, 7, 9]:
            clean_hex = trimmed[1:].lower()
            if all(c in '0123456789abcdef' for c in clean_hex):
                return False
        
        # rgb/rgba: rgba(0, 0, 0, 0.5)
        if lower_trimmed.startswith(('rgb(', 'rgba(')) and lower_trimmed.endswith(')'):
            return False

        # 7. Ignore common plugin/engine prefixes and Note Tags
        # Note Tags: <Tag: Value> or <Tag>
        if trimmed.startswith('<') and trimmed.endswith('>'):
            return False
            
        prefixes = ('v[', 'n[', 'i[', '::', 'eval(', 'script:', 'plugin:', 'rgba(', 'rgb(')
        if lower_trimmed.startswith(prefixes) and not is_dialogue:
            return False

        return True

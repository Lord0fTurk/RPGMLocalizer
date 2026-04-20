"""
JavaScript String Tokenizer for RPG Maker Script Commands.

Extracts string literals from JavaScript code found in event commands
(Code 355/655 - Script calls). This is NOT a full JS parser — it only 
identifies string tokens with their positions for safe extraction and replacement.

Used by json_parser.py to find translatable text inside script calls.
"""
import logging
import re
from typing import List, Tuple, Optional

try:
    from tree_sitter import Language, Parser
    import tree_sitter_javascript
except ImportError:  # pragma: no cover - exercised through fallback behavior
    Language = None
    Parser = None
    tree_sitter_javascript = None

logger = logging.getLogger(__name__)


class JSStringTokenizer:
    """
    Lightweight JavaScript string literal tokenizer.
    
    Extracts quoted string literals from JS code while properly handling:
    - Single quotes, double quotes, template literals (backticks)
    - Escape sequences (\\, \', \", \n, etc.)
    - Single-line comments (//)
    - Multi-line comments (/* ... */)
    - Regex literals (basic avoidance)
    """

    def __init__(self) -> None:
        self._language = self._build_language()
        self._parser = Parser(self._language) if self._language is not None and Parser is not None else None
    
    def extract_strings(self, js_code: str) -> List[Tuple[int, int, str, str]]:
        """
        Extract all string literals from JavaScript code.
        
        Args:
            js_code: JavaScript source code string
            
        Returns:
            List of (start_pos, end_pos, string_value, quote_char) tuples.
            start_pos/end_pos are indices in the original string (inclusive start, exclusive end).
            string_value is the unescaped content between quotes.
            quote_char is one of: '"', "'", '`'
        """
        if not js_code:
            return []

        if self._parser is not None:
            parsed = self._extract_strings_with_tree_sitter(js_code)
            if parsed:
                return parsed
        
        tokens = []
        i = 0
        length = len(js_code)
        
        while i < length:
            c = js_code[i]
            
            # --- Skip single-line comments ---
            if c == '/' and i + 1 < length and js_code[i + 1] == '/':
                i += 2
                while i < length and js_code[i] != '\n':
                    i += 1
                continue
            
            # --- Skip multi-line comments ---
            if c == '/' and i + 1 < length and js_code[i + 1] == '*':
                i += 2
                while i + 1 < length:
                    if js_code[i] == '*' and js_code[i + 1] == '/':
                        i += 2
                        break
                    i += 1
                else:
                    i = length  # unterminated comment
                continue

            # --- Regex literals ---
            if c == '/' and self._looks_like_regex_literal(js_code, i):
                i = self._skip_regex_literal(js_code, i)
                continue
            
            # --- String literals ---
            if c in ('"', "'", '`'):
                start = i
                quote = c
                i += 1
                value_parts = []
                terminated = False
                
                while i < length:
                    ch = js_code[i]
                    
                    if ch == '\\' and quote != '`':
                        # Escape sequence
                        i += 1
                        if i < length:
                            escaped = js_code[i]
                            # Common escape sequences
                            escape_map = {'n': '\n', 't': '\t', 'r': '\r', '\\': '\\',
                                          "'": "'", '"': '"', '0': '\0'}
                            value_parts.append(escape_map.get(escaped, escaped))
                        i += 1
                        continue
                    
                    if ch == '\\' and quote == '`':
                        # Template literal escape
                        i += 1
                        if i < length:
                            value_parts.append(js_code[i])
                        i += 1
                        continue
                    
                    if ch == quote:
                        # End of string
                        i += 1
                        terminated = True
                        break
                    
                    # Template literal: skip ${...} expressions
                    if quote == '`' and ch == '$' and i + 1 < length and js_code[i + 1] == '{':
                        # Find matching closing brace
                        depth = 1
                        i += 2
                        expr_start = i
                        while i < length and depth > 0:
                            if js_code[i] == '{':
                                depth += 1
                            elif js_code[i] == '}':
                                depth -= 1
                            i += 1
                        value_parts.append('${...}')  # placeholder for expression
                        continue
                    
                    value_parts.append(ch)
                    i += 1
                
                if terminated:
                    value = ''.join(value_parts)
                    tokens.append((start, i, value, quote))
                continue
            
            i += 1
        
        return tokens

    def _build_language(self):
        if Language is None or tree_sitter_javascript is None:
            return None
        return Language(tree_sitter_javascript.language())

    def _extract_strings_with_tree_sitter(self, js_code: str) -> List[Tuple[int, int, str, str]]:
        parser = self._parser
        if parser is None:
            return []
        source_bytes = js_code.encode("utf-8")
        tree = getattr(parser, "parse")(source_bytes)
        tokens: List[Tuple[int, int, str, str]] = []

        # Build a byte-offset → char-offset mapping to handle multi-byte UTF-8
        # characters. tree-sitter returns byte offsets; Python str indexing uses
        # char offsets. Without this conversion, _is_in_comparison (and similar
        # helpers) can raise IndexError on strings with non-ASCII characters.
        byte_to_char: list[int] = []
        for char_idx, ch in enumerate(js_code):
            byte_len = len(ch.encode("utf-8"))
            byte_to_char.extend([char_idx] * byte_len)
        # Sentinel: one past the last char maps to len(js_code)
        byte_to_char.append(len(js_code))

        for node in self._iter_string_nodes(tree.root_node):
            raw_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")
            if not raw_text:
                continue

            if node.type == "template_string":
                if any(child.type == "template_substitution" for child in node.named_children):
                    continue
                value = raw_text[1:-1] if len(raw_text) >= 2 else raw_text
                quote = "`"
            else:
                quote = raw_text[0] if raw_text and raw_text[0] in ('"', "'") else '"'
                value = self._decode_literal_value(raw_text, quote)

            # Convert byte offsets → char offsets
            char_start = byte_to_char[node.start_byte] if node.start_byte < len(byte_to_char) else len(js_code)
            char_end = byte_to_char[node.end_byte] if node.end_byte < len(byte_to_char) else len(js_code)

            tokens.append((char_start, char_end, value, quote))

        return tokens

    def _iter_string_nodes(self, node):
        stack = [node]
        while stack:
            current = stack.pop()
            if current.type in {"string", "template_string"}:
                yield current
            stack.extend(reversed(current.children))

    def _decode_literal_value(self, raw_text: str, quote: str) -> str:
        if len(raw_text) < 2:
            return raw_text
        if quote == '`':
            return raw_text[1:-1]
        try:
            import ast

            return ast.literal_eval(raw_text)
        except (SyntaxError, ValueError):
            return raw_text[1:-1]
    
    def extract_translatable_strings(self, js_code: str, 
                                      min_length: int = 2,
                                      require_non_ascii_or_space: bool = True
                                      ) -> List[Tuple[int, int, str, str]]:
        """
        Extract only strings that look like translatable text (not technical).
        
        Filters out:
        - Empty strings
        - Very short strings (< min_length)
        - Strings that look like file paths, IDs, or technical values
        - Strings inside comparison operators (==, !=, ===, !==)
        
        Args:
            js_code: JavaScript source code
            min_length: Minimum string length to consider
            require_non_ascii_or_space: If True, string must contain space or non-ASCII chars
            
        Returns:
            Filtered list of (start_pos, end_pos, string_value, quote_char) tuples
        """
        all_strings = self.extract_strings(js_code)
        result = []
        
        for start, end, value, quote in all_strings:
            # Skip empty
            if not value or not value.strip():
                continue
            
            # Skip too short
            if len(value.strip()) < min_length:
                continue
            
            # Skip technical values
            if self._is_technical_string(value):
                continue
            
            # Check context: skip strings in comparisons
            if self._is_in_comparison(js_code, start):
                continue

            # Skip strings that are part of regex constructors.
            if self._is_in_regex_constructor(js_code, start):
                continue

            # Skip tagged raw templates used for technical patterns/paths.
            if self._is_in_string_raw_template(js_code, start):
                continue

            # Skip strings used in path/URL constructors.
            if self._is_in_path_constructor(js_code, start):
                continue

            # Skip strings used in technical code execution helpers.
            if self._is_in_code_constructor(js_code, start):
                continue

            # Skip strings used in data transform wrappers.
            if self._is_in_data_wrapper(js_code, start):
                continue

            # Skip only separator-like strings used in join/split helpers.
            if self._is_in_separator_helper(js_code, start, value):
                continue
            
            # Optionally require space or non-ASCII (indicates natural language)
            if require_non_ascii_or_space:
                has_space = ' ' in value
                has_non_ascii = any(ord(c) > 127 for c in value)
                if not has_space and not has_non_ascii:
                    # Allow function calls with text-like args even without spaces
                    # e.g. $gameMessage.add("Fire!")
                    if len(value) < 4:
                        continue
            
            result.append((start, end, value, quote))
        
        return result
    
    def replace_string_at(self, js_code: str, start: int, end: int, 
                          quote: str, new_value: str) -> str:
        """
        Replace a string literal at a specific position in JS code.
        
        Properly re-escapes the new value for the given quote type.
        
        Args:
            js_code: Original JavaScript code
            start: Start position (inclusive, points to opening quote)
            end: End position (exclusive, points past closing quote)
            quote: Quote character used ('"', "'", '`')
            new_value: New unescaped string value
            
        Returns:
            Modified JavaScript code
        """
        escaped = self._escape_for_js(new_value, quote)
        return js_code[:start] + quote + escaped + quote + js_code[end:]
    
    def _escape_for_js(self, value: str, quote: str) -> str:
        """Escape a string value for embedding in JavaScript source."""
        result = value.replace('\\', '\\\\')
        if quote == '"':
            result = result.replace('"', '\\"')
        elif quote == "'":
            result = result.replace("'", "\\'")
        elif quote == '`':
            result = result.replace('`', '\\`')
            result = result.replace('${', '\\${')
        result = result.replace('\n', '\\n')
        result = result.replace('\r', '\\r')
        result = result.replace('\t', '\\t')
        # JS line terminators that would break string literals
        result = result.replace('\u2028', '\\u2028')
        result = result.replace('\u2029', '\\u2029')
        # Rare control characters
        result = result.replace('\0', '\\0')
        return result
    
    def _is_technical_string(self, value: str) -> bool:
        """Check if a string value looks technical (not translatable)."""
        v = value.strip()
        v_lower = v.lower()

        js_managers = ['textmanager.', 'datamanager.', 'imagemanager.', 'scenemanager.', 'soundmanager.', 'audiomanager.']
        if any(manager in v_lower for manager in js_managers):
            return True

        js_code_markers = ('eval(', 'function(', 'new function(', 'settimeout(', 'setinterval(')
        if any(marker in v_lower for marker in js_code_markers):
            return True
        
        # Boolean-ish
        if v_lower in ('true', 'false', 'null', 'undefined', 'none', 'nan',
                        'auto', 'default', 'on', 'off'):
            return True
        
        # Pure numbers
        try:
            float(v.replace(',', ''))
            return True
        except ValueError:
            pass
        
        # File extensions
        file_exts = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg',
                     '.ogg', '.wav', '.m4a', '.mp3', '.mid',
                     '.webm', '.mp4', '.avi',
                     '.js', '.json', '.css', '.txt',
                     '.rpgmvp', '.rpgmvo', '.rpgmvm')
        if any(v_lower.endswith(ext) for ext in file_exts):
            return True
        
        # File paths (contains / or \ without spaces)
        if ('/' in v or '\\' in v) and ' ' not in v:
            return True
        
        # CSS colors
        if v.startswith('#') and len(v) in (4, 5, 7, 9):
            return True
        if v_lower.startswith(('rgb(', 'rgba(')):
            return True
        
        # Variable/function names: snake_case only when all chars are ASCII alnum + underscore
        # (avoids blocking non-ASCII text like "köy_yolu_açıklaması")
        if '_' in v and ' ' not in v and re.match(r'^[A-Za-z0-9_]+$', v):
            return True
        
        # camelCase identifier (lowerCamelCase or UpperCamelCase, no spaces, no non-ASCII)
        if re.match(r'^[A-Za-z][A-Za-z0-9]*(?:[A-Z][a-z0-9]+)+$', v):
            return True
        
        # RPG Maker asset names (starts with $ or !)
        if v.startswith(('$', '!')) and ' ' not in v:
            return True
        
        # Event/switch/variable names
        if v.startswith(('EV', 'SW', 'VAR')) and any(c.isdigit() for c in v):
            return True
        
        return False

    def _looks_like_regex_literal(self, js_code: str, slash_index: int) -> bool:
        """Heuristically determine whether a slash starts a regex literal."""
        if slash_index + 1 >= len(js_code):
            return False

        prev = slash_index - 1
        while prev >= 0 and js_code[prev] in ' \t\r\n':
            prev -= 1

        if prev < 0:
            return True

        prev_char = js_code[prev]
        if prev_char in '([{:;,!?=<>+-*%&|^~':
            return True

        tail = js_code[max(0, prev - 12):prev + 1].lower()
        if any(tail.endswith(keyword) for keyword in ('return', 'throw', 'case', 'if', 'while', 'for', 'with', 'delete', 'void', 'typeof', 'new', 'in')):
            return True

        return False

    def _skip_regex_literal(self, js_code: str, slash_index: int) -> int:
        """Skip a regex literal, including character classes and flags."""
        i = slash_index + 1
        length = len(js_code)
        in_class = False

        while i < length:
            ch = js_code[i]
            if ch == '\\':
                i += 2
                continue
            if ch == '[':
                in_class = True
            elif ch == ']' and in_class:
                in_class = False
            elif ch == '/' and not in_class:
                i += 1
                while i < length and js_code[i].isalpha():
                    i += 1
                return i
            i += 1

        return length

    def _is_in_regex_constructor(self, js_code: str, string_start: int) -> bool:
        """Return True when a string is an argument to RegExp/new RegExp."""
        prefix = js_code[max(0, string_start - 24):string_start].lower()
        compact = "".join(prefix.split())
        return compact.endswith('regexp(') or compact.endswith('newregexp(')

    def _is_in_string_raw_template(self, js_code: str, string_start: int) -> bool:
        """Return True when a template literal is tagged with String.raw."""
        if string_start <= 0:
            return False

        prefix = js_code[max(0, string_start - 32):string_start].lower()
        compact = "".join(prefix.split())
        return compact.endswith('string.raw`') or compact.endswith('string.raw(')

    def _is_in_path_constructor(self, js_code: str, string_start: int) -> bool:
        """Return True when a string is used in path/URL construction."""
        prefix = js_code[max(0, string_start - 32):string_start].lower()
        compact = "".join(prefix.split())
        markers = (
            'path.join(',
            'path.resolve(',
            'path.normalize(',
            'path.basename(',
            'path.dirname(',
            'path.extname(',
            'newurl(',
            'url(',
        )
        for marker in markers:
            marker_pos = compact.rfind(marker)
            if marker_pos == -1:
                continue
            if ')' not in compact[marker_pos:]:
                return True
        return False

    def _is_in_code_constructor(self, js_code: str, string_start: int) -> bool:
        """Return True when a string is used in eval/Function/timer code helpers."""
        prefix = js_code[max(0, string_start - 32):string_start].lower()
        compact = "".join(prefix.split())
        return any(
            compact.endswith(marker)
            for marker in (
                'eval(',
                'function(',
                'newfunction(',
                'settimeout(',
                'setinterval(',
                'requestanimationframe(',
                'queuemicrotask(',
                'promise.resolve(',
                'promise.reject(',
                'object.assign(',
            )
        )

    def _is_in_data_wrapper(self, js_code: str, string_start: int) -> bool:
        """Return True when a string is used in JSON/base64 wrapper helpers."""
        prefix = js_code[max(0, string_start - 32):string_start].lower()
        compact = "".join(prefix.split())
        return any(
            compact.endswith(marker)
            for marker in (
                'json.parse(',
                'json.stringify(',
                'atob(',
                'btoa(',
            )
        )

    def _looks_like_separator_value(self, value: str) -> bool:
        """Return True when a string is likely an array/string separator."""
        stripped = value.strip()
        if not stripped:
            return False
        if any(char.isalnum() for char in stripped):
            return False
        allowed = set(" \t\r\n,./_|:-+*#;\\")
        return all(char in allowed for char in stripped)

    def _is_in_separator_helper(self, js_code: str, string_start: int, value: str) -> bool:
        """Return True when a string is a separator for join/split-style helpers."""
        prefix = js_code[max(0, string_start - 24):string_start].lower()
        compact = "".join(prefix.split())
        if not any(compact.endswith(marker) for marker in ('join(', 'split(')):
            return False
        return self._looks_like_separator_value(value)
    
    def _is_in_comparison(self, js_code: str, string_start: int) -> bool:
        """
        Check if a string literal appears to be in a comparison expression.
        Looks at the characters before the opening quote for ==, !=, ===, !==
        and also detects switch-case labels (case "value":).
        """
        # Look backwards from string_start, skipping whitespace
        i = string_start - 1
        while i >= 0 and js_code[i] in ' \t':
            i -= 1
        
        if i < 0:
            return False
        
        # Check for comparison operators
        # ===, !==  (3 chars)
        if i >= 2 and js_code[i-2:i+1] in ('===', '!=='):
            return True
        # ==, !=  (2 chars)
        if i >= 1 and js_code[i-1:i+1] in ('==', '!='):
            return True

        # Switch-case label: case "value": — the keyword before the string
        prefix = js_code[max(0, string_start - 16):string_start].lower().strip()
        if prefix.endswith('case'):
            return True

        return False

"""
JavaScript String Tokenizer for RPG Maker Script Commands.

Extracts string literals from JavaScript code found in event commands
(Code 355/655 - Script calls). This is NOT a full JS parser — it only 
identifies string tokens with their positions for safe extraction and replacement.

Used by json_parser.py to find translatable text inside script calls.
"""
import re
import logging
from typing import List, Tuple, Optional

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
        return result
    
    def _is_technical_string(self, value: str) -> bool:
        """Check if a string value looks technical (not translatable)."""
        v = value.strip()
        v_lower = v.lower()

        js_managers = ['textmanager.', 'datamanager.', 'imagemanager.', 'scenemanager.', 'soundmanager.', 'audiomanager.']
        if any(manager in v_lower for manager in js_managers):
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
        
        # Variable/function names (camelCase, snake_case, PascalCase without spaces)
        if '_' in v and ' ' not in v:
            return True
        
        # RPG Maker asset names (starts with $ or !)
        if v.startswith(('$', '!')) and ' ' not in v:
            return True
        
        # Event/switch/variable names
        if v.startswith(('EV', 'SW', 'VAR')) and any(c.isdigit() for c in v):
            return True
        
        return False
    
    def _is_in_comparison(self, js_code: str, string_start: int) -> bool:
        """
        Check if a string literal appears to be in a comparison expression.
        Looks at the characters before the opening quote for ==, !=, ===, !==
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
        
        return False

import re
from typing import Tuple, Dict, List
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# RPG Maker Control Code Patterns
# ============================================================================
# Standard codes: \V[n], \N[n], \P[n], \G, \C[n], \I[n], \{, \}, \$, \., \|, \!, \>, \<, \^, \\
# Plugin codes: Yanfly, VisuStella, etc.
# HTML-like tags: <br>, <color=...>, <center>, etc.

# Pattern 1: Standard RPG Maker escape codes
RPGM_CODE_PATTERN = re.compile(
    r'\\\\'                     # Double backslash \\
    r'|'
    r'\\[A-Za-z]+\[\d+\]'       # \V[123], \N[1], \C[0]
    r'|'
    r'\\[A-Za-z]+<[^>]*>'       # Yanfly extended: \msgCore<...>, \VisuMZ<...>
    r'|'
    r'\\[A-Za-z]+'              # \G, \$, \! (letter codes)
    r'|'
    r'\\[^A-Za-z0-9\s]'         # \|, \., \>, \^ (symbol codes)
)

# Pattern 2: HTML-like tags (common in MV/MZ plugins)
HTML_TAG_PATTERN = re.compile(
    r'<[Bb][Rr]\s*/?>'                      # <br>, <BR>, <br/>
    r'|'
    r'</?[Cc][Ee][Nn][Tt][Ee][Rr]>'         # <center>, </center>
    r'|'
    r'<[Cc][Oo][Ll][Oo][Rr]=[^>]+>'         # <color=#FF0000>
    r'|'
    r'</[Cc][Oo][Ll][Oo][Rr]>'              # </color>
    r'|'
    r'<[Ww][Oo][Rr][Dd][Ww][Rr][Aa][Pp]>'   # <wordwrap>
    r'|'
    r'<[Ff][Oo][Nn][Tt]\s+[^>]+>'           # <font size=...>
    r'|'
    r'</[Ff][Oo][Nn][Tt]>'                  # </font>
    r'|'
    r'<[Ii][Cc][Oo][Nn]:\d+>'               # <icon:123>
)

# Pattern 3: Ruby expression interpolation (VX Ace scripts)
RUBY_EXPR_PATTERN = re.compile(r'#\{[^}]+\}')

# Pattern 4: Plugin command tags (VisuStella, Yanfly)
PLUGIN_TAG_PATTERN = re.compile(
    r'<[A-Za-z][A-Za-z0-9_\s:=,.-]*>'       # Generic <TagName> or <Tag: value>
    r'|'
    r'</[A-Za-z][A-Za-z0-9_]*>'             # </TagName>
)

# Combined pattern for efficiency (standard + HTML + Ruby)
COMBINED_PATTERN = re.compile(
    f'{RPGM_CODE_PATTERN.pattern}'
    f'|{HTML_TAG_PATTERN.pattern}'
    f'|{RUBY_EXPR_PATTERN.pattern}'
)


def protect_rpgm_syntax(text: str, use_extended: bool = True) -> Tuple[str, Dict[str, str]]:
    """
    Protects RPG Maker control codes, HTML tags, and plugin codes from translation.
    Replaces them with unique placeholders.
    
    Args:
        text: The text to protect.
        use_extended: If True, uses the extended pattern (HTML tags, plugin codes).
    
    Returns:
        Tuple of (protected_text, placeholder_map)
    """
    placeholders: Dict[str, str] = {}
    counter = 0
    
    out_parts: List[str] = []
    last = 0
    
    pattern = COMBINED_PATTERN if use_extended else RPGM_CODE_PATTERN
    
    for m in pattern.finditer(text):
        start, end = m.start(), m.end()
        # Append text before the match
        out_parts.append(text[last:start])
        
        token = m.group(0)
        # Create a unique key that Google Translate won't mess up.
        # Using Unicode brackets for visibility and uniqueness.
        key = f"〖{counter}〗"
        placeholders[key] = token
        out_parts.append(key)
        
        counter += 1
        last = end
        
    out_parts.append(text[last:])
    protected_text = ''.join(out_parts)
    
    return protected_text, placeholders


def restore_rpgm_syntax(text: str, placeholders: Dict[str, str]) -> str:
    """
    Restores valid RPG Maker control codes from placeholders.
    Handles cases where translator may have added spaces around keys.
    """
    result = text
    missing_keys = []
    
    # 1. First Pass: Exact Replacements (Fastest & Safest)
    for key, original in placeholders.items():
        if key in result:
            result = result.replace(key, original)
            
    # Check what's still missing
    for key, original in placeholders.items():
        if key not in result and original not in result: # Check if original might have been put back already
             
            # Key format is 〖n〗
            try:
                ph_id = key[1:-1]
            except IndexError:
                continue

            # 2. Robust Regex Search for Mangled Keys
            # Looks for any bracket type with the ID inside: (0), [0], {0}, <0>, 〖0〗
            # Also handles flexible whitespace: ( 0 )
            esc_id = re.escape(ph_id)
            
            # Pattern: Any opening bracket + whitespace? + ID + whitespace? + Any closing bracket
            # We construct a specific pattern for this ID to minimize false positives
            pattern = r'(?:[〖\[\(\{\<])\s*' + esc_id + r'\s*(?:[〗\]\)\}\>])'
            
            match = re.search(pattern, result)
            if match:
                # Replace the first occurrence found
                result = result.replace(match.group(0), original, 1)
            else:
                # 3. Last Resort: Check if the number itself exists surrounded by weird characters?
                # Maybe too risky. For now, mark as missing.
                missing_keys.append(key)
    
    if missing_keys:
        logger.warning(f"Could not restore {len(missing_keys)} placeholders: {missing_keys[:3]}...")
        # Optional: Append missing originals to the end to prevent game logic break?
        # for key in missing_keys:
        #     result += " " + placeholders[key]
            
    return result


def validate_restoration(original: str, restored: str, placeholders: Dict[str, str]) -> Tuple[bool, List[str]]:
    """
    Validates that all original control codes are present in the restored text.
    
    Returns:
        Tuple of (is_valid, list_of_missing_codes)
    """
    missing = []
    
    for key, code in placeholders.items():
        if code not in restored:
            missing.append(code)
    
    return (len(missing) == 0, missing)


def count_codes(text: str, use_extended: bool = True) -> int:
    """
    Counts the number of control codes in a text string.
    """
    pattern = COMBINED_PATTERN if use_extended else RPGM_CODE_PATTERN
    return len(pattern.findall(text))

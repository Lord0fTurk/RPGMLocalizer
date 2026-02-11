import re
import logging
from typing import Dict, Tuple, List

from src.core.constants import TOKEN_LINE_BREAK, REGEX_LINE_SPLIT

logger = logging.getLogger(__name__)

# =============================================================================
# RPG MAKER ADVANCED PROTECTION PATTERNS (v2.2 - Hybrid O(N) + Fallback)
# =============================================================================

RPGM_PATTERNS = [
    r'\\[VvCcNnPpGgIi][Ss]?\[[\d\s,]*\]',
    r'\\[\.\!\|\^\$\{\}\>\<]',
    r'#\{[^\}]+\}',                  
    r'\$\{[^\}]+\}',                  
    r'\b(?:eval|script|evalText|note|meta):\s*[^\n]+', 
    r'<[^>]+>',
    r'\[\[[^\]]+\]\]',                
    r'\{\{[^\}]+\}\}',                
    r'\\\\',                          
    r'\\\[', r'\\\]',                 
    r'XRPYX[A-Z0-9_]+XRPYX',
]

PROTECT_RE = re.compile(f"({'|'.join(RPGM_PATTERNS)})", re.IGNORECASE)

# Bozulmuş placeholder'ları onarmak için kullanılan "Surgical Healing" şablonu
# Sadece gerektiğinde (lazy init) oluşturulacak.
SPACED_RE_TEMPLATE = r'X\s*R\s*P\s*Y\s*X\s*{core_spaced}\s*X\s*R\s*P\s*Y\s*X'

def _make_spaced_core_pattern(core: str) -> str:
    return r'\s*'.join(re.escape(c) for c in core)

def protect_rpgm_syntax(text: str) -> Tuple[str, Dict[str, str]]:
    if not text:
        return text, {}

    placeholders = {}
    
    def replacer(match):
        token = match.group(0)
        
        if token.upper().startswith("XRPYX") and token.upper().endswith("XRPYX"):
            return token
            
        ph_id = len(placeholders)
        
        if token.startswith('\\'): prefix = "CMD"
        elif token.startswith('<'): prefix = "TAG"
        elif token.startswith('#') or token.startswith('$'): prefix = "SCPT"
        elif '[[' in token or '{{' in token: prefix = "EXT" 
        else: prefix = "VAR"
            
        key = f"XRPYX{prefix}{ph_id}XRPYX"
        placeholders[key] = token
        
        return f" {key} "

    protected_text = PROTECT_RE.sub(replacer, text)
    protected_text = " ".join(protected_text.split())
    
    return protected_text, placeholders

def restore_rpgm_syntax(translated: str, placeholders: Dict[str, str]) -> str:
    """
    O(N) Complexity ile optimize edilmiş restore fonksiyonu (Hybrid Approach).
    Phase 1: Fast Regex (Çoğu durum için)
    Phase 2: Surgical Healing (Nadir bozulmalar için)
    """
    if not translated or not placeholders:
        return translated

    result = translated
    
    # --- PHASE 1: Single Pass Fast Replacement (O(N) for 99% of cases) ---
    # Bu regex hem düzgün "XRPYXVAR0XRPYX" hem de Google'ın hafif bozduğu 
    # "XRPYX VAR 0 XRPYX" veya "xrpyxvar0xrpyx" hallerini yakalar.
    
    # Bu regex tüm varyasyonları tek seferde bulur.
    # Group 0: Full match, Group 1: Inner content (VAR0, CMD1 etc.)
    # X...R...P...Y...X... [VAR0] ...X...R...P...Y...X...
    flexible_token_pattern = re.compile(
        r'X\s*R\s*P\s*Y\s*X\s*([A-Z]+\d+)\s*X\s*R\s*P\s*Y\s*X', 
        re.IGNORECASE
    )
    
    # Text in this phase is mutable only via replacement
    def token_replacer(match):
        # core = VAR0
        core = match.group(1).upper() 
        # Reconstruct key: XRPYXVAR0XRPYX
        original_key = f"XRPYX{core}XRPYX"
        
        # O(1) Lookup
        if original_key in placeholders:
            return placeholders[original_key]
        return match.group(0) # Dokunma

    result = flexible_token_pattern.sub(token_replacer, result)
    
    # --- PHASE 2: Surgical Healing (Only for heavily damaged tokens) ---
    # Eğer metinde hala onarılmamış placeholder kalıntısı varsa (X...P...Y...)
    # ve orijinal kodların bazıları eksikse çalışır.
    
    # Hızlı kontrol: "X" harfi bile yoksa uğraşma
    if "X" in result.upper():
         # Hangi kodlar eksik?
         missing_keys = [k for k, v in placeholders.items() if v not in result]
         
         if missing_keys:
             for key in missing_keys:
                 original = placeholders[key]
                 core = key.replace("XRPYX", "") # VAR0
                 
                 # Harf hatası olsa bile yakala (X F P Y X ... VAR 0 ...)
                 # Bu regex çok maliyetli olduğu için sadece eksik kalanlar için çalıştırıyoruz.
                 core_spaced = _make_spaced_core_pattern(core)
                 # X...R...P...Y...X...VAR0...X...R...P...Y...X...
                 fuzzy_pat = SPACED_RE_TEMPLATE.format(core_spaced=core_spaced)
                 
                 if re.search(fuzzy_pat, result, re.IGNORECASE):
                     # Use lambda to avoid backslash interpretation in replacement string
                     # RPG Maker codes like \C[14], \N[2] contain backslashes that
                     # re.sub would interpret as backreferences (causing 'bad escape' errors)
                     safe_original = original  # capture for closure
                     result = re.sub(fuzzy_pat, lambda m: safe_original, result, flags=re.IGNORECASE)

    # --- PHASE 3: Final Syntax Polish (Orphan Cleanup) ---
    result = re.sub(r'\\\s+([VvCcNnPpGgIiSs])\s*\[', r'\\\1[', result)
    result = re.sub(r'<\s*([^>]+)\s*>', r'<\1>', result)
    result = result.replace(r'# {', r'#{').replace(r'$ {', r'${')
    
    return result


def repair_missing_tokens(original: str, restored: str, placeholders: Dict[str, str]) -> str:
    """
    Auto-repair: When Google Translate completely destroys XRPYX tokens,
    re-inject the missing RPG Maker codes at their original positions.
    
    Strategy:
    - Find which original tokens are missing from restored text
    - Check where they appear in the original (prefix/suffix/inline)
    - Re-inject them at the corresponding position in the restored text
    """
    if not original or not restored or not placeholders:
        return restored
    
    # Find missing tokens
    clean_restored = restored.replace(" ", "").lower()
    missing = []
    for ph, orig_token in placeholders.items():
        if orig_token == TOKEN_LINE_BREAK:
            continue
        if orig_token.replace(" ", "").lower() not in clean_restored:
            missing.append((ph, orig_token))
    
    if not missing:
        return restored
    
    # Sort missing tokens by their position in the original text
    positioned = []
    for ph, token in missing:
        pos = original.find(token)
        if pos == -1:
            # Token was in a different form, try case-insensitive
            pos = original.lower().find(token.lower())
        positioned.append((pos if pos >= 0 else len(original), token))
    
    positioned.sort(key=lambda x: x[0])
    
    # Classify tokens as prefix (beginning), suffix (end), or inline
    orig_len = len(original)
    prefix_tokens = []
    suffix_tokens = []
    
    for pos, token in positioned:
        # If token is in the first third of the original → prefix
        if pos < orig_len * 0.33:
            prefix_tokens.append(token)
        # If token is in the last third → suffix
        elif pos > orig_len * 0.66:
            suffix_tokens.append(token)
        else:
            # Inline - try to position relative; default to suffix
            suffix_tokens.append(token)
    
    # Re-inject
    result = restored
    if prefix_tokens:
        result = "".join(prefix_tokens) + result
    if suffix_tokens:
        result = result + "".join(suffix_tokens)
    
    return result


def validate_restoration(original: str, restored: str, placeholders: Dict[str, str]) -> Tuple[bool, List[str]]:
    r"""
    Validate that all critical RPG Maker codes are present in the restored text.
    
    Tolerant approach: Ignore missing decorative codes (\C[N], \I[N]) but require
    structural codes (\V[N], \N[N], <tags>, #{}, ${}) that affect game logic.
    """
    missing_tokens = []
    clean_restored = restored.replace(" ", "").lower()
    
    # Separators for merging
    if TOKEN_LINE_BREAK in placeholders.values():
        # Merging case - more tolerant
        for ph, original_token in placeholders.items():
            # Line break token is internal, skip
            if original_token == TOKEN_LINE_BREAK:
                continue
            
            # Decorative codes: missing \C[N], \I[N] is OK (color/icon)
            if original_token.upper().startswith(r'\C[') or original_token.upper().startswith(r'\I['):
                continue
            
            clean_token = original_token.replace(" ", "").lower()
            if clean_token not in clean_restored:
                missing_tokens.append(original_token)
    else:
        # Single text case - strict validation
        for ph, original_token in placeholders.items():
            clean_token = original_token.replace(" ", "").lower()
            if clean_token not in clean_restored:
                missing_tokens.append(original_token)
            
    return len(missing_tokens) == 0, missing_tokens

import re
import logging
import unicodedata
from typing import Dict, Tuple, List

from src.core.constants import TOKEN_LINE_BREAK, REGEX_LINE_SPLIT

logger = logging.getLogger(__name__)

# =============================================================================
# SCRIPT TRANSLITERATION RECOVERY & ADVANCED PROTECTION
# =============================================================================
_CYRILLIC_TO_LATIN = str.maketrans({
    'А': 'A', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E',
    'И': 'I', 'К': 'K', 'Л': 'L', 'М': 'M', 'Н': 'N',
    'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T',
    'У': 'U', 'Х': 'X',
})

_GREEK_TO_LATIN = str.maketrans({
    'Α': 'A', 'Β': 'B', 'Γ': 'G', 'Δ': 'D', 'Ε': 'E',
    'Ι': 'I', 'Κ': 'K', 'Μ': 'M', 'Ν': 'N', 'Ο': 'O',
    'Ρ': 'R', 'Σ': 'S', 'Τ': 'T', 'Χ': 'X',
})

_TRANSLITERATED_TOKEN_RE = re.compile(
    r'[A-ZА-ЯΑ-Ω][A-ZА-ЯΑ-Ω0-9_]*(?:\s+\d+)'
    r'|[A-ZА-ЯΑ-Ω][A-ZА-ЯΑ-Ω0-9_]*\d+'
    r'|[A-ZА-ЯΑ-Ω][A-ZА-ЯΑ-Ω0-9]*_[A-ZА-ЯΑ-Ω0-9_]+'
)

# =============================================================================
# RPG MAKER ADVANCED PROTECTION PATTERNS 
# =============================================================================

RPGM_PATTERNS = [
    r'\\+[VvCcNnPpGgIi][Ss]?\[[\d\s,]*\]',
    # VisuStella & Custom Plugins
    r'\\+[Ff][SsBbIi](?:\[[\d\s,\-]*\])?',
    r'\\+[Pp][XxYy]\[[\d\s,\.\-]*\]',
    r'\\+(?:MSGCore|pop|WordWrap)\[[^\]]*\]',
    r'\\+[\.\!\|\^\$\{\}\>\<]',
    r'#\{[^\}]+\}',                  
    r'\$\{[^\}]+\}',                  
    r'\b(?:eval|script|evalText|note|meta):\s*[^\n]+', 
    r'<[^>]+>',
    r'\[\[[^\]]+\]\]',                
    r'\{\{[^\}]+\}\}',                
    r'\\{2,}',                          
    r'\\+\[', r'\\+\]',                 
    r'XRPYX[A-Z0-9_]+XRPYX',
]

PROTECT_RE = re.compile(f"({'|'.join(RPGM_PATTERNS)})", re.IGNORECASE)

# Bozulmuş placeholder'ları onarmak için kullanılan şablonlar (Unicode bracket'lar opsiyonel)
SPACED_RE_TEMPLATE = r'(?:\u27e6)?\s*R\s*L\s*P\s*H\s*_\s*{core_spaced}\s*(?:\u27e7)?'

def _make_spaced_core_pattern(core: str) -> str:
    return r'\s*'.join(re.escape(c) for c in core)

def protect_rpgm_syntax(text: str) -> Tuple[str, Dict[str, str]]:
    if not text:
        return text, {}

    placeholders = {}
    
    def replacer(match):
        token = match.group(0)
        
        if '\u27e6' in token and '\u27e7' in token:
            return token
            
        ph_id = len(placeholders)
        
        if token.startswith('\\'): prefix = "CMD"
        elif token.startswith('<'): prefix = "TAG"
        elif token.startswith('#') or token.startswith('$'): prefix = "SCPT"
        elif '[[' in token or '{{' in token: prefix = "EXT" 
        else: prefix = "VAR"
            
        # Alfabe bağımsız Unicode parantezleri (⟦ = \u27e6, ⟧ = \u27e7)
        # Transliterasyon hatalarını kökten çözer
        key = f"\u27e6RLPH_{prefix}{ph_id}\u27e7"
        placeholders[key] = token
        
        return key

    protected_text = PROTECT_RE.sub(replacer, text)
    
    return protected_text, placeholders

def restore_rpgm_syntax(translated: str, placeholders: Dict[str, str]) -> str:
    """
    O(N) Complexity ile optimize edilmiş restore fonksiyonu (Hybrid Approach).
    """
    if not translated or not placeholders:
        return translated

    result = translated
    
    # --- PHASE 0: TRANSLITERATION RECOVERY ---
    # Google Translate Rusça/Yunanca'da VAR0 yerine ВАР0 çevirmiş olabilir.
    def _recover_transliterated(match):
        original = match.group(0)
        normalized = original.translate(_CYRILLIC_TO_LATIN).translate(_GREEK_TO_LATIN)
        # Sadece \u27e6... normalized ... \u27e7  yerine doğrudan metin içinden eski formata dönük koruma yapıyoruz.
        # Spaced ve bozuk Unicode tokenları Phase 1 ve 2'de halledilir.
        return normalized
        
    if "А" in result.upper() or "Α" in result.upper() or "В" in result.upper():
         # Eski tip hata payı için
         result = _TRANSLITERATED_TOKEN_RE.sub(_recover_transliterated, result)

    # --- PHASE 1: Fast Regex (Çoğu durum için) ---
    # Google ⟦⟧ boşlukla açabilir: ⟦ RLPH_VAR0 ⟧
    flexible_token_pattern = re.compile(
        r'\u27e6\s*R\s*L\s*P\s*H\s*_\s*([A-Z]+\d+)\s*\u27e7', 
        re.IGNORECASE
    )
    
    def token_replacer(match):
        core = match.group(1).upper() 
        original_key = f"\u27e6RLPH_{core}\u27e7"
        
        if original_key in placeholders:
            return placeholders[original_key]
        return match.group(0)

    result = flexible_token_pattern.sub(token_replacer, result)
    
    # --- PHASE 2: Surgical Healing (Only for heavily damaged tokens) ---
    if "R" in result.upper() and "L" in result.upper():
         missing_keys = [k for k, v in placeholders.items() if v not in result]
         
         if missing_keys:
             for key in missing_keys:
                 original = placeholders[key]
                 core = key.replace("\u27e6RLPH_", "").replace("\u27e7", "") 
                 
                 core_spaced = _make_spaced_core_pattern(core)
                 fuzzy_pat = SPACED_RE_TEMPLATE.format(core_spaced=core_spaced)
                 
                 if re.search(fuzzy_pat, result, re.IGNORECASE):
                     safe_original = original  
                     result = re.sub(fuzzy_pat, lambda m: safe_original, result, flags=re.IGNORECASE)

    # Fallback to exact replacement just in case they survived unmodified
    result = _replace_exact_placeholders(result, placeholders)

    # --- PHASE 3: Final Syntax Polish (Orphan Cleanup) ---
    result = re.sub(r'\\\s+([VvCcNnPpGgIiSs])\s*\[', r'\\\1[', result)
    result = re.sub(r'<\s*([^>]+)\s*>', r'<\1>', result)
    result = result.replace(r'# {', r'#{').replace(r'$ {', r'${')
    
    return result

def _replace_exact_placeholders(text: str, placeholders: Dict[str, str]) -> str:
    # Sort length descending
    for k in sorted(placeholders.keys(), key=len, reverse=True):
        if k in text:
            text = text.replace(k, placeholders[k])
    return text


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

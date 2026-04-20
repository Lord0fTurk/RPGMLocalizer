# -*- coding: utf-8 -*-
"""
RPG Maker Syntax Guard Module (Adapted from RenLocalizer v3.3+)
===============================================================
RPG Maker oyunlarında kod yapısını koruma ve geri yükleme işlemlerini yönetir.
Bu modül, çeviri motorlarının (Google, DeepL, vb) oyun kodunu ve değişkenleri 
bozmasını engellemek için "Askeri Düzeyde" koruma sağlar.

Architecture (Motor-Aware):
---------------------------
1. **Protection Layer:** 
   - Token-based: Pure Unicode tokens (⟦RPGM...⟧) for format="text" mode
   - HTML-based: <span translate="no"> wrappers for format="html" mode

2. **Fuzzy Recovery (4-Phase):**
   - Phase 0: Unicode token restore (spaced tokens)
   - Phase 0.1: Bracket-substituted tokens recovery
   - Phase 1: Standard token restoration
   - Phase 1+: Missing token injection (proportional positioning)

3. **Validation & Repair:**
   - Integrity checking with tolerance (spaced, case-insensitive)
   - Tag nesting repair
   - Missing placeholder injection

Sources:
- RenLocalizer v3.3+ (fuzzy recovery, injection)
- RPGMLocalizer v0.6.5 (lexer patterns)
- battle-tested with multiple engines
"""

import re
import uuid
from typing import Dict, Tuple, List, Optional

# =============================================================================
# RPG MAKER CODE PATTERNS (Single Source of Truth)
# =============================================================================
# Ren'Py'den farklı olarak RPG Maker şu kod yapılarına sahiptir:
# 
# 1. **Escape Sequences:**
#    - \c[n]     : Color change
#    - \i[n]     : Icon display
#    - \{        : Increase size
#    - \}        : Decrease size
#    - \.        : Slow text speed
#    - \!        : Wait for input
#    - \>        : Instant text display
#    - \<        : Cancel text display
#    - \n        : New line (or \n without brackets)
#    - \p[n]     : Party member name
#    - \g        : Gold display
#    - \$        : Gold symbol
#
# 2. **Plugin-Specific Markers:**
#    - \f[name]           : Face image (plugin)
#    - \msghnd            : Message handler (plugin)
#    - \n<character_name> : Character nameplate (advanced plugin)
#    - \P[n]              : Player variable reference
#
# 3. **Special Tags:**
#    - <WordWrap>         : Word wrapping
#    - [name]             : Single-bracket variable reference
#    - [sad], [happy]     : Multi-purpose tags (portrait, state, etc.)

# Pre-compiled Regex Patterns
# Core RPG Maker escape sequences
_PAT_ESCAPE_SEQUENCE = r'\\(?:[c|i|n|p|g|$|{|}|.|!|>|<|f|P|n<])'

# Escaped braces: [[...]] or {{...}} (MUST BE FIRST - most specific)
_PAT_ESCAPED_BRACE = r'\[\[.*?\]\]|\{\{.*?\}\}'

# Core escape sequences with specific arguments
_PAT_CODE_ARGS = r'\\(?:c|i|p|P|f|n)<\d+>\]|\\\w<[^>]+>'
_PAT_COLORS = r'\\c\[\d+\]'
_PAT_ICONS = r'\\i\[\d+\]'
_PAT_PARTY = r'\\p\[\d\]'
_PAT_PLAYER_VAR = r'\\P\[[^\]]+\]'
_PAT_FACE = r'\\f\[[^\]]+\]'
_PAT_NAMEPLATE = r'\\n<[^>]+>'

# Simple escape sequences (no args)
_PAT_MSG_HANDLER = r'\\msghnd'
_PAT_SIMPLE_ESCAPES = r'\\[{}.<>!g$\\nip^;]'

# Special tags
_PAT_WORDWRAP = r'<WordWrap>'
_PAT_SPECIAL_TAGS = r'<(?:clear|indent|left|center|right)>'

# Bracket codes - simplified
_PAT_BRACKET_FLAVOR = r'\[(?:sad|happy|angry|sweat|confused|smirk|evil|thinking|doubt|grin|NOTE|custom)\d*\]'

# Generic bracket variable [anything]
_PAT_BRACKET_VAR = r'\[([^\[\]]+)\]'

# Combined pattern (Order: most specific → least specific)
_PROTECT_PATTERN_STR = (
    r'(\[\[.*?\]\]|'                    # [[escaped]]
    r'\{\{.*?\}\}|'                      # {{escaped}}
    r'\\c\[\d+\]|'                       # \c[n] - color
    r'\\C\[\d+\]|'                       # \C[n] - color (uppercase)
    r'\\i\[\d+\]|'                       # \i[n] - icon
    r'\\I\[\d+\]|'                       # \I[n] - icon (uppercase)
    r'\\p\[\d+\]|'                       # \p[n] - party member name
    r'\\P\[[^\]]+\]|'                    # \P[var] - player variable
    r'\\f\[[^\]]+\]|'                    # \f[filename] - face image
    r'\\n<[^>]+>|'                       # \n<name> - nameplate
    r'\\[Ww]\[\d+\]|'                   # \W[n]/\w[n] - wait frames
    r'\\[Ff][Bb]|'                       # \FB/\fb - font bold toggle
    r'\\[Ff][Ii]|'                       # \FI/\fi - font italic toggle
    # --- MV/MZ plugin escape extensions (case-insensitive via alternation) ---
    r'\\[Vv]\[\d+\]|'                   # \V[n]/\v[n] - variable value display
    r'\\[Nn]\[\d+\]|'                   # \N[n]/\n[n] - actor name
    r'\\[Ff][Ss]\[\d+\]|'              # \FS[n]/\fs[n] - font size
    r'\\[Ff][Ss]\b|'                    # \FS without bracket (some plugins)
    r'\\[Oo][Cc]\[\d+\]|'              # \OC[n] - VisuStella outline color
    r'\\[Hh][Cc]\[\d+\]|'              # \HC[n] - VisuStella hex color
    r'\\[Aa][Cc]\[\d+\]|'              # \AC[n] - VisuStella actor class color
    r'\\[Pp][Xx]\[\d+\]|'              # \PX[n] - position X
    r'\\[Pp][Yy]\[\d+\]|'              # \PY[n] - position Y
    r'\\[Ww][Cc]\[\d+\]|'              # \WC[n] - window color
    r'\\[Tt][Tt]\[[^\]]+\]|'           # \TT[text] - tooltip
    r'\\[Bb][Gg]\[[^\]]+\]|'           # \BG[img] - background image
    r'\\[Mm][Ss][Gg][Cc][Oo][Rr][Ee][^\[]*\[[^\]]*\]|'  # \MSGCore[...]
    r'\\[Pp][Oo][Pp]\[[^\]]*\]|'       # \pop[...] - popup
    r'\\[Ww][Oo][Rr][Dd][Ww][Rr][Aa][Pp]\[[^\]]*\]|'  # \WordWrap[...]
    # --- simple escapes ---
    r'\\msghnd|'                          # \msghnd
    r'\\[{}.<>!g$\\nip^;]|'              # Simple escape sequences (\!, \^, \., \; etc.)
    r'<WordWrap>|'                        # <WordWrap>
    r'<(?:clear|indent|left|center|right)>|'  # Other tags
    r'\[(?:sad|happy|angry|sweat|confused|smirk|evil|thinking|doubt|grin|NOTE|custom)\d*\]|'  # Flavor tags
    r'\[[^\[\]]+\])'                     # Generic [variable]
)

# Pre-compile all patterns
PROTECT_RE = re.compile(_PROTECT_PATTERN_STR)

# Legacy/Fallback patterns
PUA_START = '\uE000'  # Marker for start/end of placeholder
PUA_PAIR_OPEN = '\uE001'  # Marker for [[
PUA_PAIR_CLOSE = '\uE002'  # Marker for ]]


def protect_rpgm_syntax(text: str) -> Tuple[str, Dict[str, str]]:
    """
    RPG Maker kodlarını tokenize eder ve korunan metin döner.
    
    Strateji:
    1. Tüm RPG Maker kodlarını (\\c[1], [name], vb) bulur
    2. Her kodu bir token'a dönüştürür: ⟦RPGM{NS}_{TYPE}_{ID}⟧
    3. Korunan metni ve token sözlüğünü döner
    
    Args:
        text: Orijinal metin (RPG Maker kodlarle)
    
    Returns:
        (protected_text, token_map) tuple
        - protected_text: Kodların token'larla değiştirilmiş hali
        - token_map: {token_key: original_code} dictionary
    """
    if not text:
        return "", {}
    
    placeholders: Dict[str, str] = {}
    result_text = text
    token_namespace = uuid.uuid4().hex[:6].upper()
    
    # Find all matches and collect them
    matches = list(PROTECT_RE.finditer(text))
    if not matches:
        return text, {}
    
    # Replace from right to left to preserve positions
    for idx, match in enumerate(reversed(matches)):
        code_content = match.group(0)
        
        # Determine code type for better categorization
        if code_content.startswith('\\c[') or code_content.startswith('\\C['):
            code_type = 'COLOR'
        elif re.match(r'\\[Oo][Cc]\[', code_content) or re.match(r'\\[Hh][Cc]\[', code_content) or re.match(r'\\[Aa][Cc]\[', code_content) or re.match(r'\\[Ww][Cc]\[', code_content):
            code_type = 'COLOR'
        elif code_content.startswith('\\i[') or code_content.startswith('\\I['):
            code_type = 'ICON'
        elif re.match(r'\\[Ww]\[\d', code_content):
            code_type = 'WAIT'
        elif re.match(r'\\[Ff][Bb]$', code_content) or re.match(r'\\[Ff][Ii]$', code_content):
            code_type = 'FONT'
        elif code_content.startswith('\\p[') or code_content.startswith('\\P['):
            code_type = 'PARTY'
        elif re.match(r'\\[Vv]\[', code_content):
            code_type = 'VAR'
        elif re.match(r'\\[Nn]\[', code_content) or code_content.startswith('\\n<'):
            code_type = 'NAME'
        elif re.match(r'\\[Ff][Ss]', code_content):
            code_type = 'FONT'
        elif code_content.startswith('\\f['):
            code_type = 'FACE'
        elif code_content.startswith('['):
            code_type = 'BRACKET'
        elif code_content.startswith('<'):
            code_type = 'TAG'
        else:
            code_type = 'OTHER'
        
        # Create token with position info
        token_id = len(matches) - 1 - idx
        token = f'⟦RPGM{token_namespace}_{code_type}_{token_id}⟧'
        placeholders[token] = code_content
        
        # Replace in result (right to left)
        start = match.start()
        end = match.end()
        result_text = result_text[:start] + token + result_text[end:]
    
    return result_text, placeholders


def protect_rpgm_syntax_html(text: str) -> str:
    """
    RPG Maker kodlarını HTML <span translate="no"> ile sararak korur.
    
    format="html" mode kullanan otomatik motorlar için kullanılır.
    Token yerine HTML wrapping kullanılır.
    
    Args:
        text: Orijinal metin
    
    Returns:
        HTML-protected metin
    """
    if not text:
        return ""
    
    def protect_code(match):
        code = match.group(0)
        # HTML entities kullanmadan sadece span ile sarla
        return f'<span translate="no">{code}</span>'
    
    return PROTECT_RE.sub(protect_code, text)


def restore_rpgm_syntax(text: str, placeholders: Dict[str, str]) -> str:
    """
    Tokenları orijinal RPG Maker kodlarına geri dönüştürür (4-Phase Restoration).
    
    Phases:
    1. Unicode bracket restore (Space-mangled tokens)
    2. Bracket-substituted tokens (Google bracket mutation)
    3. Standard token restoration
    4. Missing token injection
    
    Args:
        text: Çevrilmiş metin (tokenwith)
        placeholders: Token → original_code sözlüğü
    
    Returns:
        Restored metin (orijinal RPG Maker kodlarla)
    """
    if not text or not placeholders:
        return text
    
    result = text
    
    # PHASE 0: Unicode Bracket Restore
    # Google, ⟦tokens⟧ içine/arasına boşluk ekleyebilir: ⟦ T 0 ⟧
    if '⟦' in result or '\u27e6' in result:
        unicode_token_re = re.compile(r'⟦\s*([^\u27e7]+?)\s*⟧')
        
        def restore_unicode_token(match):
            token_inner = ''.join(match.group(1).split())
            token_key = f'⟦{token_inner}⟧'
            
            if token_key in placeholders:
                return placeholders[token_key]
            
            # Fuzzy match: Case-insensitive TYPE_ID suffix matching
            if '_' in token_inner:
                # Extract TYPE_ID suffix (e.g., "COLOR_0" from "rpgm79eb1b_COLOR_0")
                parts = token_inner.split('_')
                if len(parts) >= 3:
                    # Use last two parts for disambiguation: TYPE + ID
                    suffix_lower = '_' + '_'.join(parts[-2:]).lower() + '⟧'
                elif len(parts) == 2:
                    suffix_lower = '_' + parts[-1].lower() + '⟧'
                else:
                    suffix_lower = '_' + parts[-1].lower() + '⟧'
                
                # Find matching token with same suffix (case-insensitive)
                for key in placeholders.keys():
                    key_lower = key.lower()
                    if key_lower.endswith(suffix_lower):
                        return placeholders[key]
            
            return match.group(0)
        
        result = unicode_token_re.sub(restore_unicode_token, result)
    
    # PHASE 0.1: Bracket-Substituted Token Recovery
    # Google: ⟦RPGM...⟧ → [RPGM...], (RPGM...), {RPGM...}, 【RPGM...】
    if '[RPGM' in result or '(RPGM' in result or '{RPGM' in result or '【RPGM' in result:
        bracket_recovery_re = re.compile(
            r'[\[\(\{【⟦]\s*(RPGM[A-Za-z0-9_]+?)\s*[\]\)\}】⟧]'
        )
        
        def recover_bracket_sub(match):
            token_inner = ''.join(match.group(1).split())
            token_key = f'⟦{token_inner}⟧'
            
            if token_key in placeholders:
                return placeholders[token_key]
            
            # Fuzzy: Case-insensitive TYPE_ID suffix matching (same as Phase 0)
            if '_' in token_inner:
                parts = token_inner.split('_')
                if len(parts) >= 3:
                    suffix_lower = '_' + '_'.join(parts[-2:]).lower() + '⟧'
                elif len(parts) == 2:
                    suffix_lower = '_' + parts[-1].lower() + '⟧'
                else:
                    suffix_lower = '_' + parts[-1].lower() + '⟧'
                
                for key in placeholders.keys():
                    key_lower = key.lower()
                    if key_lower.endswith(suffix_lower):
                        return placeholders[key]
            
            return match.group(0)
        
        result = bracket_recovery_re.sub(recover_bracket_sub, result)
    
    # PHASE 1: Standard Token Replacement
    # Token'ları büyüklüğe göre sıra (longest first) - partial match'i önlemek için
    sorted_tokens = sorted(placeholders.keys(), key=len, reverse=True)
    for token in sorted_tokens:
        original = placeholders[token]
        result = result.replace(token, original)
    
    # PHASE 2: Spacing normalization
    # RPG Maker kodları civarında istenmeyen boşlukları temizle
    # Örn: Merhaba \c[1] → Merhaba\c[1] (ileri uyumlu)
    result = re.sub(r'\s+\\([ciIpPngf])', r' \\\1', result)
    
    # PHASE 3: Final cleanup — only normalize bracket spacing ADJACENT to known tokens,
    # not in free-form player text (avoids corrupting [[item]] game syntax).
    # Token pattern: ⟦...⟧ neighbourhood only.
    result = re.sub(r'(?<=⟧)\s*\[\s*\[', '[[', result)
    result = re.sub(r'\]\s*\](?=\s*⟦)', ']]', result)
    result = re.sub(r'\[\s+([a-zA-Z0-9_]+)\s+\]', r'[\1]', result)
    
    return result


def validate_translation_integrity(text: str, placeholders: Dict[str, str]) -> List[str]:
    """
    Çevirinin bütünlüğünü doğrular - eksik kodları raporlar.
    
    Args:
        text: Çevrilmiş metin (kodlarla)
        placeholders: Token → original_code sözlüğü
    
    Returns:
        Eksik kodların listesi (boş = başarılı)
    """
    if not placeholders:
        return []
    
    missing = []
    
    # Doğrudan kontrol
    for token, original in placeholders.items():
        if original not in text:
            # Toleranslı kontrol (boşluk ve harf büyüklüğü göz ardı)
            clean_text = text.replace(" ", "").lower()
            clean_orig = original.replace(" ", "").lower()
            
            if clean_orig not in clean_text:
                missing.append(original)
    
    return missing


def inject_missing_placeholders(translated_text: str, 
                               protected_text: str,
                               placeholders: Dict[str, str],
                               missing_originals: List[str]) -> str:
    """
    Çevirici tarafından tamamen silinen kodları oransal pozisyonda enjekte eder.
    
    Strateji:
    1. Eksik kod'un protected metin'deki pozisyonunu bul (ratio)
    2. Aynı oranı translated metin'e uygula
    3. Word boundary respecting enjeksyon
    
    Args:
        translated_text: Çevrilmiş metin (eksik kodlarla)
        protected_text: Korunmuş metin (tüm kodlarla)
        placeholders: Token sözlüğü
        missing_originals: Eksik kodların listesi
    
    Returns:
        Kodları enjekte edilmiş metin
    """
    if not missing_originals or not translated_text or not protected_text:
        return translated_text
    
    # Reverse map: original_code → token
    code_to_token = {v: k for k, v in placeholders.items()}
    
    insertions = []
    protected_len = len(protected_text)
    
    for orig_code in missing_originals:
        token = code_to_token.get(orig_code)
        if not token:
            continue
        
        pos = protected_text.find(token)
        if pos < 0:
            continue
        
        ratio = pos / protected_len if protected_len > 0 else 0.5
        insertions.append((ratio, orig_code))
    
    if not insertions:
        return translated_text
    
    # Sort by position
    insertions.sort(key=lambda x: x[0])
    
    # Insert from right to left
    result = translated_text
    trans_len = len(result)
    
    for ratio, orig_code in reversed(insertions):
        insert_pos = int(ratio * trans_len)
        
        # Find safe insertion point (word boundary)
        best_pos = None
        for delta in range(0, 21):
            for candidate in [insert_pos + delta, insert_pos - delta]:
                if 0 <= candidate <= len(result):
                    if ((candidate > 0 and result[candidate - 1] == ' ') or
                        (candidate < len(result) and result[candidate] == ' ')):
                        best_pos = candidate
                        break
            else:
                continue
            break
        
        # Fallback
        if best_pos is None:
            best_pos = len(result) if (insert_pos > len(result) / 2) else 0
        
        # Insert with spaces
        left = result[:best_pos].rstrip()
        right = result[best_pos:].lstrip()
        
        if left and right:
            result = f"{left} {orig_code} {right}"
        elif right:
            result = f"{orig_code} {right}"
        elif left:
            result = f"{left} {orig_code}"
        else:
            result = orig_code
    
    # Normalize spaces
    result = re.sub(r'  +', ' ', result).strip()
    
    return result


# =============================================================================
# API EXPORTS (Motor-aware protection)
# =============================================================================

def protect_for_translation(text: str, use_html: bool = False) -> Tuple[str, Dict[str, str]]:
    """
    Motor-aware protection selector.
    
    Args:
        text: Original text with RPG Maker codes
        use_html: If True, use HTML wrapping; else use token-based
    
    Returns:
        (protected_text, metadata) where metadata = token_map or {}
    """
    if use_html:
        return protect_rpgm_syntax_html(text), {}
    return protect_rpgm_syntax(text)


def restore_from_translation(text: str, metadata: Dict[str, str], use_html: bool = False) -> str:
    """
    Motor-aware restoration selector.
    
    Args:
        text: Translated text
        metadata: Token map from protect_for_translation
        use_html: If True, skip restoration (HTML already restored by engine)
    
    Returns:
        Restored text with original RPG Maker codes
    """
    if use_html:
        # HTML mode: Engine didn't change the codes, just return
        return text
    
    # Token mode: restore from metadata
    if not metadata:
        return text
    
    restored = restore_rpgm_syntax(text, metadata)
    return restored

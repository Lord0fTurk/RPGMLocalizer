"""
RPG Maker Syntax Guard Module (Modernized v0.8.0)
===================================================

Provides unbreakable protection for RPG Maker escape codes and plugin tags
during translation, supporting both Google Web endpoints and AI/LLM engines.

Protection Formats:
- Google Translate / Web APIs: Mathematical angle brackets ⟦RLPH{hex}_{id}⟧ (U+27E6 / U+27E7).
- AI / LLM engines: XML tags <ph id="N">...</ph> or ASCII placeholders __PH_N__.

Restoration Pipeline (6 Stages):
- Stage 0:   Exact match replacement.
- Stage 0.5: Bare token recovery (brackets completely stripped by engine).
- Stage 1:   Script transliteration repair (Cyrillic/Greek to Latin phonetics).
- Stage 2:   Spaced token healing (⟦ RLPH ... ⟧, ⟦ T 0 ⟧).
- Stage 3:   Bracket substitution healing ([RLPH...], {RLPH...}, 【RLPH...】).
- Stage 4:   Levenshtein / Heuristic suffix matching.
- Stage 5:   Corruption Fallback (reverts to original text if critical codes are lost).
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, List, Tuple

from src.core.text_segmenter import (
    Segment,
    SegmentType,
    clean_text as _segmenter_clean,
    reassemble as _segmenter_reassemble,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Transliteration Mappings (Anti-corruption for Google Translate)
# ---------------------------------------------------------------------------
_CYRILLIC_TO_LATIN = str.maketrans({
    'А': 'A', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E',
    'И': 'I', 'К': 'K', 'Л': 'L', 'М': 'M', 'Н': 'N',
    'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T',
    'У': 'U', 'Х': 'H',
    'а': 'A', 'в': 'V', 'г': 'G', 'д': 'D', 'е': 'E',
    'и': 'I', 'к': 'K', 'л': 'L', 'м': 'M', 'н': 'N',
    'о': 'O', 'п': 'P', 'р': 'R', 'с': 'S', 'т': 'T',
    'у': 'U', 'х': 'H',
})

_GREEK_TO_LATIN = str.maketrans({
    'Α': 'A', 'Β': 'B', 'Γ': 'G', 'Δ': 'D', 'Ε': 'E',
    'Ι': 'I', 'Κ': 'K', 'Μ': 'M', 'Ν': 'N', 'Ο': 'O',
    'Ρ': 'R', 'Σ': 'S', 'Τ': 'T', 'Χ': 'H',
    'α': 'A', 'β': 'B', 'γ': 'G', 'δ': 'D', 'ε': 'E',
    'ι': 'I', 'κ': 'K', 'μ': 'M', 'ν': 'N', 'ο': 'O',
    'ρ': 'R', 'σ': 'S', 'τ': 'T', 'χ': 'H',
})

# ---------------------------------------------------------------------------
# Comprehensive RPG Maker Pattern Definition
# ---------------------------------------------------------------------------
_RPGM_CODE_PATTERNS = (
    r'(\[\[.*?\]\]|'                     # [[escaped]]
    r'\{\{.*?\}\}|'                      # {{escaped}}
    r'\\(?:[cCiIpPfFwWvVnNoOaAhHxXyY]|fs|fn|oc|ow|hc|ac|px|py|wc|tt|bg)\[(?:[^\[\]]*|\[[^\[\]]*\])*\]|'  # Nested brackets like \C[\V[1]]
    r'\\c\[\d+\]|'                       # \c[n] - color
    r'\\C\[\d+\]|'                       # \C[n] - color (uppercase)
    r'\\i\[\d+\]|'                       # \i[n] - icon
    r'\\I\[\d+\]|'                       # \I[n] - icon (uppercase)
    r'\\p\[\d+\]|'                       # \p[n] - party member name
    r'\\P\[[^\]]+\]|'                    # \P[var] - player variable
    r'\\f\[[^\]]+\]|'                    # \f[filename] - face image
    r'\\n<[^>]+>|'                       # \n<name> - nameplate
    r'\\[Nn][Cc]<[^>]+>|'                # \NC<text>/\nc<text> - Yanfly name window
    r'\\[Ww]\[\d+\]|'                    # \W[n]/\w[n] - wait frames
    r'\\[Ff][Bb]|'                       # \FB/\fb - font bold toggle
    r'\\[Ff][Ii]|'                       # \FI/\fi - font italic toggle
    r'\\[Vv]\[\d+\]|'                    # \V[n]/\v[n] - variable value
    r'\\[Nn]\[\d+\]|'                    # \N[n]/\n[n] - actor name
    r'\\[Ff][Ss]\[\d+\]|'               # \FS[n]/\fs[n] - font size
    r'\\[Ff][Ss]\b|'                     # \FS without bracket
    r'\\[Ff][Nn]<[^>]+>|'                # \FN<font>/\fn<font> - font name
    r'\\[Oo][Cc]\[\d+\]|'               # \OC[n] - VisuStella outline color
    r'\\[Oo][Ww]\[[^\]]+\]|'            # \OW[width]/\ow[width] - outline width
    r'\\[Hh][Cc]\[\d+\]|'               # \HC[n] - VisuStella hex color
    r'\\[Hh][Cc]<[^>]+>|'                # \HC<color>/\hc<color> - hex color (angle form)
    r'\\[Aa][Cc]\[\d+\]|'               # \AC[n] - VisuStella actor color
    r'\\[Pp][Xx]\[\d+\]|'               # \PX[n] - position X
    r'\\[Pp][Yy]\[\d+\]|'               # \PY[n] - position Y
    r'\\[Ww][Cc]\[\d+\]|'               # \WC[n] - window color
    r'\\[Tt][Tt]\[[^\]]+\]|'            # \TT[text] - tooltip
    r'\\[Bb][Gg]\[[^\]]+\]|'            # \BG[img] - background image
    r'\\[Mm][Ss][Gg][Cc][Oo][Rr][Ee][^\[]*\[[^\]]*\]|'  # \MSGCore[...]
    r'\\[Pp][Oo][Pp]\[[^\]]*\]|'        # \pop[...] - popup
    r'\\[Ww][Oo][Rr][Dd][Ww][Rr][Aa][Pp]\[[^\]]*\]|'  # \WordWrap[...]
    r'\\msghnd|'                         # \msghnd
    r'\\[{}.<>!gG$\\nip^;|]|'            # Simple escapes (incl. \G currency, \| wait)
    r'\b(?:if|en|req|cond|eval)\s*\((?:[^()\n]|\([^()\n]*\))+\)|'  # Choice condition plugins: if(s[1]), en(v[2]>=10)
    r'\b[vsVS]\[\d+\]|'                 # Variable/switch references: v[2], s[10]
    r'</?[a-zA-Z][a-zA-Z0-9_\s:-]*>|'    # XML/plugin tags: <WordWrap>, <ChoiceHelp>, <page condition>
    r'\[(?:sad|happy|angry|sweat|confused|smirk|evil|thinking|doubt|grin|NOTE|custom)\d*\]|'  # Flavor tags
    r'\[[^\[\]]+\])'                     # Generic [variable]
)

RPGM_CODE_RE = re.compile(_RPGM_CODE_PATTERNS)

_CRITICAL_CODE_PREFIXES = (
    "\\V[", "\\v[", "\\N[", "\\n[", "\\P[", "\\p[", "\\C[", "\\c[",
    "\\I[", "\\i[", "\\G", "\\g", "\\$", "\\FS[", "\\fs[",
    "v[", "s[", "V[", "S[", "if(", "en(", "req(", "cond(", "eval(",
)


class ProtectionFormat(Enum):
    """Supported placeholder token formats."""
    UNICODE_BRACKET = auto()  # ⟦RLPH{hex}_{id}⟧ for Google
    XML_TAG = auto()          # <ph id="N">...</ph> for LLM
    ASCII_TAG = auto()        # __PH_N__ for simple ASCII prompts


@dataclass(slots=True)
class ProtectedText:
    """Structured result of protecting text."""
    text: str
    token_map: Dict[str, str]
    format_type: ProtectionFormat
    original_text: str


def _compute_salt(text: str) -> str:
    """Generate a short 6-char hex salt derived from text content."""
    return hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()[:6].upper()


def _is_critical_code(code: str) -> bool:
    """Determine if a code is critical for engine stability."""
    norm = code.strip()
    return any(norm.startswith(prefix) for prefix in _CRITICAL_CODE_PREFIXES)


# ---------------------------------------------------------------------------
# Protection Core
# ---------------------------------------------------------------------------
def protect_rpgm_syntax(
    text: str,
    format_type: ProtectionFormat = ProtectionFormat.UNICODE_BRACKET,
) -> Tuple[str, Dict[str, str]]:
    """Protect RPG Maker syntax in *text* using specified format."""
    if not text:
        return "", {}

    token_map: Dict[str, str] = {}
    salt = _compute_salt(text)
    counter = 0
    parts: List[str] = []
    last_idx = 0

    for match in RPGM_CODE_RE.finditer(text):
        code = match.group(0)
        parts.append(text[last_idx:match.start()])

        if format_type == ProtectionFormat.UNICODE_BRACKET:
            token = f"\u27e6RLPH{salt}_{counter}\u27e7"
        elif format_type == ProtectionFormat.XML_TAG:
            token = f'<ph id="{counter}">{code}</ph>'
        else:
            token = f"__PH_{counter}__"

        token_map[token] = code
        parts.append(token)
        counter += 1
        last_idx = match.end()

    parts.append(text[last_idx:])
    return "".join(parts), token_map


def protect_rpgm_syntax_xml(text: str) -> Tuple[str, Dict[str, str]]:
    """Convenience wrapper for XML tag protection (<ph id="N">...</ph>)."""
    return protect_rpgm_syntax(text, format_type=ProtectionFormat.XML_TAG)


# ---------------------------------------------------------------------------
# Restoration Pipeline Stages
# ---------------------------------------------------------------------------
def _stage0_exact_restore(text: str, token_map: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
    """Stage 0: Fast direct replacement of intact tokens."""
    remaining = dict(token_map)
    res = text
    for token, original in sorted(token_map.items(), key=lambda x: len(x[0]), reverse=True):
        if token in res:
            res = res.replace(token, original)
            remaining.pop(token, None)
    return res, remaining


def _stage05_bare_token_restore(text: str, remaining: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
    """Stage 0.5: Recover tokens where outer brackets were stripped by the engine."""
    if not remaining:
        return text, remaining

    res = text
    to_remove: List[str] = []
    bare_map = {k.strip("\u27e6\u27e7"): (k, v) for k, v in remaining.items() if k.startswith("\u27e6")}

    if bare_map:
        bare_pattern = re.compile(r'\b(RLPH[A-F0-9]{6}_\d+)\b')
        def repl(m: re.Match) -> str:
            token_inner = m.group(1)
            if token_inner in bare_map:
                full_key, original = bare_map[token_inner]
                to_remove.append(full_key)
                return original
            return m.group(0)

        res = bare_pattern.sub(repl, res)
        for k in to_remove:
            remaining.pop(k, None)

    return res, remaining


def _stage1_transliteration_repair(text: str, remaining: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
    """Stage 1: Normalize Cyrillic/Greek transliterations of token identifiers."""
    if not remaining:
        return text, remaining

    res = text
    to_remove: List[str] = []

    norm_map = {k.strip("\u27e6\u27e7"): (k, v) for k, v in remaining.items()}
    corrupt_pattern = re.compile(
        r'[\u27e6\[\(\{\u3010]?\s*([A-Za-z0-9_]*[А-Яа-яΑ-Ωα-ω][A-Za-zА-Яа-яΑ-Ωα-ω0-9_]*)\s*[\u27e7\]\)\}\u3011]?'
    )

    def repl(m: re.Match) -> str:
        raw_inner = m.group(1)
        normalized = raw_inner.translate(_CYRILLIC_TO_LATIN).translate(_GREEK_TO_LATIN).upper()
        if normalized in norm_map:
            full_key, original = norm_map[normalized]
            to_remove.append(full_key)
            return original
        return m.group(0)

    res = corrupt_pattern.sub(repl, res)
    for k in to_remove:
        remaining.pop(k, None)

    return res, remaining


def _stage2_spaced_token_heal(text: str, remaining: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
    """Stage 2: Heal whitespace injected between token characters."""
    if not remaining:
        return text, remaining

    res = text
    to_remove: List[str] = []
    clean_target_map = {re.sub(r'[\s_]+', '', k.strip("\u27e6\u27e7")).upper(): (k, v) for k, v in remaining.items()}
    spaced_pattern = re.compile(r'[\u27e6\[\(\{\u3010]\s*([Rr]\s*[Ll]\s*[Pp]\s*[Hh][A-Za-z0-9_\s]*?)\s*[\u27e7\]\)\}\u3011]')

    def repl(m: re.Match) -> str:
        cleaned = re.sub(r'[\s_]+', '', m.group(1)).upper()
        if cleaned in clean_target_map:
            full_key, original = clean_target_map[cleaned]
            to_remove.append(full_key)
            return original
        return m.group(0)

    res = spaced_pattern.sub(repl, res)
    for k in to_remove:
        remaining.pop(k, None)

    return res, remaining


def _stage3_bracket_substitution_heal(text: str, remaining: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
    """Stage 3: Heal substituted bracket styles: [RLPH...], {RLPH...}, (RLPH...), 【RLPH...】."""
    if not remaining:
        return text, remaining

    res = text
    to_remove: List[str] = []

    for full_key, original in list(remaining.items()):
        if full_key.startswith("\u27e6") and full_key.endswith("\u27e7"):
            inner = full_key[1:-1]
            pattern = re.compile(r'[\[\(\{\u3010<]\s*' + re.escape(inner) + r'\s*[\]\)\}\u3011>]')
            if pattern.search(res):
                res = pattern.sub(lambda m, orig=original: orig, res, count=1)
                to_remove.append(full_key)

    for k in to_remove:
        remaining.pop(k, None)

    return res, remaining


def _stage4_heuristic_levenshtein(text: str, remaining: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
    """Stage 4: Suffix/ID heuristic matching for partially mangled tokens."""
    if not remaining:
        return text, remaining

    res = text
    to_remove: List[str] = []

    for full_key, original in list(remaining.items()):
        if "_" in full_key:
            suffix = full_key.rsplit("_", 1)[-1].rstrip("\u27e7")
            suffix_pattern = re.compile(
                r'[\u27e6\[\(\{\u3010]?\s*RLPH[A-Za-z0-9]*_' + re.escape(suffix) + r'\s*[\u27e7\]\)\}\u3011]?'
            )
            if suffix_pattern.search(res):
                res = suffix_pattern.sub(lambda m, orig=original: orig, res, count=1)
                to_remove.append(full_key)

    for k in to_remove:
        remaining.pop(k, None)

    return res, remaining


def _stage5_corruption_fallback(
    translated_text: str,
    original_text: str,
    remaining_tokens: Dict[str, str],
) -> str:
    """Stage 5: Corruption Fallback. Reverts to original text if critical codes are lost."""
    if not remaining_tokens or not original_text:
        return translated_text

    critical_missing = [orig for orig in remaining_tokens.values() if _is_critical_code(orig)]
    if critical_missing:
        logger.warning(
            "SyntaxGuard Corruption Fallback triggered: %d critical code(s) missing %s. Reverting text to original.",
            len(critical_missing), critical_missing,
        )
        return original_text

    return translated_text


# ---------------------------------------------------------------------------
# Public Restoration API
# ---------------------------------------------------------------------------
def restore_rpgm_syntax(
    text: str,
    placeholders: Dict[str, str],
    original_text: str = "",
) -> str:
    """Restore tokens with the 6-stage anti-corruption pipeline."""
    if not text or not placeholders:
        return text

    if any(k.startswith('<ph') or k.isdigit() for k in placeholders):
        return restore_rpgm_syntax_xml(text, placeholders, original_text)

    # 6-Stage Restoration Pipeline
    res, rem = _stage0_exact_restore(text, placeholders)
    if rem:
        res, rem = _stage2_spaced_token_heal(res, rem)
    if rem:
        res, rem = _stage3_bracket_substitution_heal(res, rem)
    if rem:
        res, rem = _stage1_transliteration_repair(res, rem)
    if rem:
        res, rem = _stage05_bare_token_restore(res, rem)
    if rem:
        res, rem = _stage4_heuristic_levenshtein(res, rem)

    res = _stage5_corruption_fallback(res, original_text, rem)
    return res


def restore_rpgm_syntax_xml(
    text: str,
    placeholders: Dict[str, str],
    original_text: str = "",
) -> str:
    """Restore XML tag placeholders (<ph id="N">...</ph>)."""
    if not text or not placeholders:
        return text

    id_pattern = re.compile(r'id\s*=\s*["\']?([A-Za-z0-9_]+)["\']?', re.IGNORECASE)
    id_map: Dict[str, str] = {}
    full_map: Dict[str, str] = {}
    for k, v in placeholders.items():
        full_map[k] = v
        m = id_pattern.search(k)
        if m:
            id_map[m.group(1)] = v
        else:
            id_map[k] = v

    ph_pattern = re.compile(
        r'<ph\b[^>]*\bid\s*=\s*["\']?([A-Za-z0-9_]+)["\']?[^>]*>.*?</\s*ph\s*>',
        re.IGNORECASE | re.DOTALL,
    )

    handled_keys: Set[str] = set()

    def replacer(match: re.Match) -> str:
        ph_id = match.group(1)
        full_match = match.group(0)
        if ph_id in id_map:
            handled_keys.add(ph_id)
            return id_map[ph_id]
        if full_match in full_map:
            handled_keys.add(full_match)
            return full_map[full_match]
        return full_match

    result = ph_pattern.sub(replacer, text)

    if original_text:
        missing_critical = [
            code for pid, code in id_map.items()
            if pid not in handled_keys and _is_critical_code(code)
        ]
        if missing_critical:
            logger.warning(
                "XML SyntaxGuard Corruption Fallback: missing critical codes %s. Reverting to original.",
                missing_critical,
            )
            return original_text

    return result


# ---------------------------------------------------------------------------
# Backward Compatibility Helpers
# ---------------------------------------------------------------------------
def protect_for_translation(text: str, use_html: bool = False) -> Tuple[str, Any]:
    """Compatibility API for callers expecting segment lists."""
    _ = use_html
    return _segmenter_clean(text)


def restore_from_translation(text: str, metadata: Any, use_html: bool = False) -> str:
    """Compatibility API for callers passing either token dicts or segment lists."""
    _ = use_html
    if isinstance(metadata, list):
        return _segmenter_reassemble(text, metadata)
    if isinstance(metadata, dict):
        return restore_rpgm_syntax(text, metadata)
    return text


def protect_rpgm_syntax_html(text: str) -> str:
    """Compatibility API for HTML protection."""
    clean, _ = _segmenter_clean(text)
    return clean


def validate_translation_integrity(text: str, placeholders: Dict[str, str]) -> List[str]:
    """Legacy no-op compatibility helper."""
    _ = text, placeholders
    return []


def inject_missing_placeholders(
    translated_text: str,
    protected_text: str,
    placeholders: Dict[str, str],
    missing_originals: List[str],
) -> str:
    """Legacy no-op compatibility helper."""
    _ = protected_text, placeholders, missing_originals
    return translated_text


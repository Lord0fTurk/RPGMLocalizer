"""
Syntax and escape code validation for RPG Maker game strings.
Inspects control codes, message box line limits, and character casing.
"""
from __future__ import annotations

import re
from typing import List, Tuple

# Comprehensive regex pattern matching standard RPG Maker codes, plugin codes,
# XML/note tags, flavor brackets, and single-character control codes (XP/VX/VXA/MV/MZ).
_CODE_PATTERN = re.compile(
    r"""(?xi)
    \\(?:
        [a-z_]+(?:\[(?:[^\[\]\r\n]|\[[^\[\]\r\n]*\])*\]|<[^>\r\n]*>)?  # e.g. \C[1], \V[10], \C[\V[1]], \fn<Font>, \eval<...>, \G
        |[!.<>|^$\\{}]                                                  # single-character control codes: \!, \., \|, \^, \{, \}
    )
    |</?[a-zA-Z][a-zA-Z0-9_\s:-]*>                                     # <WordWrap>, <tag>
    |\[(?:sad|happy|angry|sweat|confused|smirk|evil|thinking|doubt|grin|NOTE|custom)\d*\]  # Flavor emotion tags
    """
)

# Turkish character mapping table for case-insensitive search normalization
_TURKISH_LOWER_MAP = str.maketrans({
    "İ": "i",
    "I": "ı",
    "Ğ": "ğ",
    "Ü": "ü",
    "Ş": "ş",
    "Ö": "ö",
    "Ç": "ç",
})


def _find_unclosed_brackets(text: str) -> list[str]:
    r"""Scan text for unclosed escape code brackets (e.g. \C[12 or \fn<Font)."""
    unclosed = []
    # Check square brackets after escape codes
    for m in re.finditer(r"\\[a-zA-Z_]+\[", text):
        start = m.start()
        idx = m.end()
        depth = 1
        while idx < len(text) and depth > 0:
            ch = text[idx]
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
            elif ch == "\n":
                break
            idx += 1
        if depth > 0:
            snippet = text[start:min(start + 25, len(text))].replace("\n", " ").strip()
            unclosed.append(snippet)

    # Check angle brackets after escape codes
    for m in re.finditer(r"\\[a-zA-Z_]+<", text):
        start = m.start()
        idx = m.end()
        depth = 1
        while idx < len(text) and depth > 0:
            ch = text[idx]
            if ch == "<":
                depth += 1
            elif ch == ">":
                depth -= 1
            elif ch == "\n":
                break
            idx += 1
        if depth > 0:
            snippet = text[start:min(start + 25, len(text))].replace("\n", " ").strip()
            unclosed.append(snippet)

    return unclosed


def extract_escape_codes(text: str) -> list[str]:
    """Extract all RPG Maker control codes from text preserving order."""
    if not text:
        return []
    return _CODE_PATTERN.findall(text)


def validate_codes(orig: str, trans: str) -> list[str]:
    """Compare escape codes between original and translated text.

    Returns a list of warning descriptions if codes are missing or broken.
    """
    warnings: list[str] = []
    if not orig and not trans:
        return warnings

    # Check for unclosed brackets in translation
    if trans:
        for bad_snippet in _find_unclosed_brackets(trans):
            warnings.append(f"Kapatılmamış kaçış kodu parantezi: '{bad_snippet}'")

    orig_codes = extract_escape_codes(orig or "")
    trans_codes = extract_escape_codes(trans or "")

    # Normalize codes to case-insensitive comparison for matching
    trans_codes_lower = [c.lower() for c in trans_codes]

    # Count occurrences to detect missing or dropped codes
    from collections import Counter
    orig_counter = Counter(c.lower() for c in orig_codes)
    trans_counter = Counter(trans_codes_lower)

    for code_lower, count in orig_counter.items():
        trans_count = trans_counter.get(code_lower, 0)
        if trans_count < count:
            # Find the original representation for clear messaging
            sample = next((c for c in orig_codes if c.lower() == code_lower), code_lower)
            diff = count - trans_count
            if diff == 1:
                warnings.append(f"Eksik kontrol kodu: {sample}")
            else:
                warnings.append(f"Eksik kontrol kodu ({diff} adet): {sample}")

    return warnings


def check_line_overflow(text: str, tag: str = "dialogue", max_lines: int = 4) -> tuple[int, bool]:
    """Return line count and boolean flag indicating message box overflow.

    Standard RPG Maker message windows accommodate 4 dialogue lines.
    """
    if not text:
        return 1, False

    line_count = text.count("\n") + 1
    # Check if tag is dialogue-related
    is_dialogue = any(s in (tag or "").lower() for s in ("dialogue", "message", "scroll"))
    overflow = is_dialogue and line_count > max_lines
    return line_count, overflow


def normalize_turkish(text: str) -> str:
    """Normalize text with Turkish-aware case-folding for search operations."""
    if not text:
        return ""
    return text.translate(_TURKISH_LOWER_MAP).casefold()

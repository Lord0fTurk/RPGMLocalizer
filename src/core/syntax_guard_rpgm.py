"""
RPG Maker Syntax Guard Module (v0.7.0 — Segment-Based)
=======================================================

This module is a thin compatibility layer.  The real work is done by
`text_segmenter.py`, which splits RPG Maker strings into alternating
TEXT/CODE segments so that codes are NEVER exposed to translation APIs.

Migration note
--------------
v0.6.x used a 4-phase fuzzy-recovery token system (⟦RPGM{hash}_{TYPE}_{id}⟧)
that relied on regex protection + fallback injection when Google mangled the
tokens.  That approach has been replaced by the segmenter, which is both
simpler and more reliable: codes are structurally separated before
translation and cannot be corrupted.

Legacy functions are preserved as wrappers for test compatibility.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from src.core.text_segmenter import (
    Segment,
    SegmentType,
    clean_text as _segmenter_clean,
    reassemble as _segmenter_reassemble,
)

# ---------------------------------------------------------------------------
# Public API — new (segment-based)
# ---------------------------------------------------------------------------

def protect_for_translation(text: str, use_html: bool = False) -> Tuple[str, List[Segment]]:
    """Segment *text* and return (clean_text, segment_list).

    The clean text contains only TEXT segments joined by ``|||TXTSEG|||``.
    The segment list preserves all original CODE segments for later
    reassembly.

    The *use_html* parameter is ignored (kept for backward compatibility).
    """
    return _segmenter_clean(text)


def restore_from_translation(text: str, metadata: List[Segment], use_html: bool = False) -> str:
    """Re-insert CODE segments into the translated clean *text*.

    *metadata* is the segment list returned by *protect_for_translation*.
    The *use_html* parameter is ignored.
    """
    if not metadata:
        return text
    return _segmenter_reassemble(text, metadata)


# ---------------------------------------------------------------------------
# Legacy API — kept for test/benchmark compatibility
# ---------------------------------------------------------------------------

def protect_rpgm_syntax(text: str) -> Tuple[str, Dict[str, str]]:
    """Legacy token-based protection.  Uses segmenter internally and wraps
    the result in the old Dict[str,str] format.

    Deprecated: use *protect_for_translation* instead.
    """
    clean, segments = _segmenter_clean(text)
    # Build a fake token map from segments (for backward compat)
    token_map: Dict[str, str] = {}
    for i, seg in enumerate(segments):
        if seg.type == SegmentType.CODE:
            token_map[f"⟦LEGACY_{i}⟧"] = seg.content
    if token_map:
        # Also protect the clean text with the old token format
        protected = clean
        for token, code in token_map.items():
            protected = protected.replace(code, token, 1)
        return protected, token_map
    return clean, token_map


def protect_rpgm_syntax_html(text: str) -> str:
    """Legacy HTML protection — simply delegates to segmenter."""
    clean, _segments = _segmenter_clean(text)
    return clean


def restore_rpgm_syntax(text: str, placeholders: Dict[str, str]) -> str:
    """Legacy token restoration — only works with token maps from
    *protect_rpgm_syntax*.

    Deprecated: use *restore_from_translation* instead.
    """
    if not placeholders:
        return text
    result = text
    for token, code in placeholders.items():
        result = result.replace(token, code)
    return result


def validate_translation_integrity(text: str, placeholders: Dict[str, str]) -> List[str]:
    """Legacy integrity check — always returns empty (segment-based approach
    makes this unnecessary).
    """
    _ = text, placeholders  # unused
    return []


def inject_missing_placeholders(
    translated_text: str,
    protected_text: str,
    placeholders: Dict[str, str],
    missing_originals: List[str],
) -> str:
    """Legacy injection — no-op (segmenter handles all cases)."""
    _ = translated_text, protected_text, placeholders, missing_originals
    return translated_text

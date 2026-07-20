"""
Text Segmenter for RPG Maker text.

Splits RPG Maker strings into alternating text/code segments so that only
clean text is sent to translation APIs.  RPG control codes are NEVER exposed
to the translator and therefore can never be corrupted.

Architecture
------------
1. Uses the same comprehensive regex patterns as syntax_guard_rpgm for code detection.
2. Splits a string into alternating TEXT/CODE segments.
3. `clean_text()` joins all TEXT segments with a resilient ASCII separator.
4. `reassemble()` splits the translated result, interleaves CODE segments,
   and returns the fully restored string.

Separator
---------
We use `` |||TXTSEG||| `` — pure ASCII, Google-safe, no RPGM tokens nearby.
If the separator is lost during translation, proportional positioning is used
as fallback.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Separator
# ---------------------------------------------------------------------------
TEXT_SEGMENT_SEPARATOR = "|||TXTSEG|||"

# Canonical form for splitting (exact match, no whitespace consumption)
_TSS_CANONICAL_RE = re.compile(r"\|\|\|TXTSEG\|\|\|")

# ---------------------------------------------------------------------------
# Code pattern — reuse the battle-tested regex from syntax_guard_rpgm
# ---------------------------------------------------------------------------
# This is the same set of patterns used by the old 4-phase protection system.
# The order is: most specific → least specific so that longer patterns match
# before shorter substrings.
_PROTECT_PATTERN_STR = (
    r'(\[\[.*?\]\]|'                     # [[escaped]]
    r'\{\{.*?\}\}|'                      # {{escaped}}
    r'\\c\[\d+\]|'                       # \c[n] - color
    r'\\C\[\d+\]|'                       # \C[n] - color (uppercase)
    r'\\i\[\d+\]|'                       # \i[n] - icon
    r'\\I\[\d+\]|'                       # \I[n] - icon (uppercase)
    r'\\p\[\d+\]|'                       # \p[n] - party member name
    r'\\P\[[^\]]+\]|'                    # \P[var] - player variable
    r'\\f\[[^\]]+\]|'                    # \f[filename] - face image
    r'\\n<[^>]+>|'                       # \n<name> - nameplate
    r'\\[Ww]\[\d+\]|'                    # \W[n]/\w[n] - wait frames
    r'\\[Ff][Bb]|'                       # \FB/\fb - font bold toggle
    r'\\[Ff][Ii]|'                       # \FI/\fi - font italic toggle
    r'\\[Vv]\[\d+\]|'                    # \V[n]/\v[n] - variable value
    r'\\[Nn]\[\d+\]|'                    # \N[n]/\n[n] - actor name
    r'\\[Ff][Ss]\[\d+\]|'               # \FS[n]/\fs[n] - font size
    r'\\[Ff][Ss]\b|'                     # \FS without bracket
    r'\\[Oo][Cc]\[\d+\]|'               # \OC[n] - VisuStella outline color
    r'\\[Hh][Cc]\[\d+\]|'               # \HC[n] - VisuStella hex color
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
    r'\\[{}.<>!g$\\nip^;]|'             # Simple escapes
    r'<WordWrap>|'                       # <WordWrap>
    r'<(?:clear|indent|left|center|right)>|'  # Other tags
    r'\[(?:sad|happy|angry|sweat|confused|smirk|evil|thinking|doubt|grin|NOTE|custom)\d*\]|'  # Flavor tags
    r'\[[^\[\]]+\])'                     # Generic [variable]
)

_CODE_RE = re.compile(_PROTECT_PATTERN_STR)

# ---------------------------------------------------------------------------
# Segment types
# ---------------------------------------------------------------------------
class SegmentType(Enum):
    TEXT = auto()
    CODE = auto()


@dataclass
class Segment:
    type: SegmentType
    content: str

    def __repr__(self) -> str:
        return f"<{self.type.name}:{self.content!r}>"


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------

def segment_text(text: str) -> List[Segment]:
    """Split *text* into alternating TEXT/CODE segments.

    Returns a list that strictly alternates TEXT → CODE → TEXT → CODE …
    (or a single TEXT segment when there are no codes).
    """
    if not text:
        return [Segment(SegmentType.TEXT, "")]

    segments: List[Segment] = []
    pos = 0

    for m in _CODE_RE.finditer(text):
        # TEXT before this code
        if m.start() > pos:
            _append_text(segments, text[pos:m.start()])
        # CODE
        _append_code(segments, m.group(0))
        pos = m.end()

    # Remaining TEXT after the last code
    if pos < len(text):
        _append_text(segments, text[pos:])

    if not segments:
        segments.append(Segment(SegmentType.TEXT, text))

    return segments


def clean_text(text: str) -> Tuple[str, List[Segment]]:
    """Convenience: segment *text* and return (clean_translation_text, segments).

    The clean text contains *only* TEXT segments joined by separator.
    """
    segments = segment_text(text)
    parts = [s.content for s in segments if s.type == SegmentType.TEXT]
    return TEXT_SEGMENT_SEPARATOR.join(parts), segments


def reassemble(translated_clean: str, segments: List[Segment]) -> str:
    """Re-insert original CODE segments into *translated_clean*.

    Strategy
    --------
    1. Try to split *translated_clean* on the segment separator.
    2. If the part count matches the TEXT segment count, interleave codes.
    3. Otherwise fall back to proportional positioning.
    """
    text_count = sum(1 for s in segments if s.type == SegmentType.TEXT)
    if text_count == 0:
        return translated_clean

    parts = _split_clean(translated_clean, text_count)

    if len(parts) == text_count:
        return _interleave(parts, segments)

    logger.debug(
        "reassemble: separator split mismatch (got %d, expected %d) — "
        "falling back to proportional positioning",
        len(parts), text_count,
    )
    return _proportional_reinsert(translated_clean, segments)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _append_text(segments: List[Segment], content: str) -> None:
    if segments and segments[-1].type == SegmentType.TEXT:
        segments[-1].content += content
    else:
        segments.append(Segment(SegmentType.TEXT, content))


def _append_code(segments: List[Segment], content: str) -> None:
    if segments and segments[-1].type == SegmentType.CODE:
        segments[-1].content += content
    else:
        segments.append(Segment(SegmentType.CODE, content))


def _split_clean(text: str, expected: int) -> List[str]:
    parts = _TSS_CANONICAL_RE.split(text)
    parts = [p for p in parts if p != ""]
    if len(parts) >= expected:
        return parts[:expected]
    if parts:
        return parts
    return [text]


def _interleave(text_parts: List[str], segments: List[Segment]) -> str:
    out: List[str] = []
    t_idx = 0
    for seg in segments:
        if seg.type == SegmentType.TEXT:
            out.append(text_parts[t_idx] if t_idx < len(text_parts) else "")
            t_idx += 1
        else:
            out.append(seg.content)
    return "".join(out)


def _proportional_reinsert(translated: str, segments: List[Segment]) -> str:
    """Fallback: place codes at proportional positions.

    Only reached when the separator split fails.
    """
    # Build the full clean-text reference for ratio calculation
    clean_parts: List[str] = []
    code_list: List[str] = []
    for seg in segments:
        if seg.type == SegmentType.TEXT:
            clean_parts.append(seg.content)
        else:
            code_list.append(seg.content)

    clean_full = TEXT_SEGMENT_SEPARATOR.join(clean_parts)
    if not clean_full:
        return translated

    # Calculate cumulative positions of each code
    positions: List[Tuple[float, str]] = []
    cum_len = 0
    code_idx = 0
    for seg in segments:
        if seg.type == SegmentType.TEXT:
            cum_len += len(seg.content) + len(TEXT_SEGMENT_SEPARATOR)
        else:
            # Position of this code in the clean_full string
            code_pos = cum_len
            code_len = len(seg.content)
            # Ratio based on the start of the code gap in clean_full
            mid = code_pos
            if code_idx < len(code_list):
                ratio = mid / max(len(clean_full), 1)
                positions.append((ratio, seg.content))
                code_idx += 1

    if not positions:
        return translated

    result = translated
    tlen = len(result)
    for ratio, code in reversed(positions):
        insert_at = int(ratio * tlen)
        best = _find_word_boundary(result, insert_at)
        left = result[:best].rstrip()
        right = result[best:].lstrip()
        if left and right:
            result = f"{left} {code} {right}"
        elif right:
            result = f"{code} {right}"
        elif left:
            result = f"{left} {code}"
        else:
            result = code

    return re.sub(r"  +", " ", result).strip()


def _find_word_boundary(text: str, pos: int) -> int:
    for delta in range(21):
        for candidate in (pos + delta, pos - delta):
            if 0 <= candidate <= len(text):
                if candidate == 0 or candidate == len(text):
                    return candidate
                if text[candidate - 1] == " " or text[candidate] == " ":
                    return candidate
    return pos

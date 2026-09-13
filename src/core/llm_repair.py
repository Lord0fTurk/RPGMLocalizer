from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from enum import Enum

_ARRAYS_TRIED = 8

FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)
RE_LINE_COMMENT = re.compile(r"(?m)^\s*//.*$")
RE_BLOCK_COMMENT = re.compile(r"(?s)/\*.*?\*/")
RE_TRAILING_COMMA = re.compile(r",\s*([\]}])")
STRING_RE = re.compile(r'''(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')''')


class RepairQuality(str, Enum):
    CLEAN = "clean"
    REPAIRED = "repaired"
    SALVAGED = "salvaged"


@dataclass(slots=True)
class RepairOutcome:
    items: list[str]
    quality: RepairQuality


def strip_fence(text: str) -> str:
    m = FENCE_RE.match(text.strip())
    return m.group(1).strip() if m else text.strip()


def _outside_strings(text: str):
    inside = False
    escaped = False
    for idx, ch in enumerate(text):
        if inside:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                inside = False
            continue
        else:
            if ch == '"':
                inside = True
                continue
            yield idx, ch


def _extract_array(text: str) -> str | None:
    depth = 0
    last_complete = None
    for idx, ch in _outside_strings(text):
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth < 0:
                depth = 0
            if depth == 0:
                return text[: idx + 1]
            if ch == "}" and depth == 1:
                last_complete = idx + 1
    if last_complete is not None:
        return text[:last_complete] + "]"
    return None


def _repair_syntax(text: str) -> str:
    fixed = RE_LINE_COMMENT.sub("", text)
    fixed = RE_BLOCK_COMMENT.sub("", fixed)
    # trailing commas: [1,2,] -> [1,2]
    fixed = RE_TRAILING_COMMA.sub(r"\1", fixed)
    # missing comma between array elements: "a" "b" -> "a","b"
    # Only for string literals: "x" \s+ "y"
    fixed = re.sub(r'"\s+"', '","', fixed)
    fixed = re.sub(r"'\s+'", "','", fixed)
    fixed = re.sub(r'"\s+\'', '","', fixed)
    fixed = re.sub(r"'\s+\"", "','", fixed)
    # single quotes around strings -> double quotes (only outside already-double)
    # Use salvage for full single-quote arrays, but try a light fix: replace ' with " when plausible
    # Heuristic: an array of single-quoted strings
    if fixed.strip().startswith("[") and "'" in fixed and '"' not in fixed:
        fixed = fixed.replace("'", '"')
    return fixed


def _decode_string_literal(raw: str) -> str | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        pass
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            return ast.literal_eval(raw)
    except Exception:
        pass
    # manual single-quote fallback
    if raw[0] == "'" and raw[-1] == "'":
        inner = raw[1:-1].replace("\\'", "'")
        try:
            return json.loads('"' + inner.replace("\\", "\\\\").replace('"', '\\"') + '"')
        except Exception:
            return inner
    return None


def _salvage_strings(text: str) -> list[str]:
    out: list[str] = []
    for m in STRING_RE.finditer(text):
        decoded = _decode_string_literal(m.group(0))
        if decoded is not None:
            out.append(decoded)
    return out


def _try_parse_array(candidate: str) -> list[str] | None:
    try:
        data = json.loads(candidate)
    except Exception:
        return None
    if isinstance(data, dict):
        for key in ("translations", "results", "data", "items"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break
        else:
            return None
    if not isinstance(data, list):
        return None
    # coerce to strings, skip non-string? Keep as str
    return [str(x) if not isinstance(x, str) else x for x in data]


def parse_llm_array(raw: str, expected_len: int | None = None) -> RepairOutcome | None:
    if not raw or not raw.strip():
        return None
    text = strip_fence(raw.strip())

    # Collect candidates: full text + up to ARRAYS_TRIED bracket starts
    candidates: list[str] = []
    starts = [m.start() for m in re.finditer(r"\[", text)]
    for s in starts[:_ARRAYS_TRIED]:
        sub = text[s:]
        extracted = _extract_array(sub)
        if extracted:
            candidates.append(extracted)
    candidates.append(text)

    # Deduplicate preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            uniq.append(c)

    for cand in uniq:
        # CLEAN
        items = _try_parse_array(cand)
        if items is not None:
            if expected_len is None or len(items) == expected_len:
                return RepairOutcome(items, RepairQuality.CLEAN)
            # Even length mismatch is a clean parse, but let caller decide fallback
            # Prefer to return it as CLEAN for now; caller will fallback to individual if mismatch
            return RepairOutcome(items, RepairQuality.CLEAN)

        # REPAIRED
        repaired = _repair_syntax(cand)
        if repaired != cand:
            items = _try_parse_array(repaired)
            if items is not None:
                return RepairOutcome(items, RepairQuality.REPAIRED)

        if "[" in cand:
            salvaged = _salvage_strings(repaired if 'repaired' in locals() and repaired != cand else cand)
            if salvaged:
                if expected_len is not None and len(salvaged) > expected_len:
                    salvaged = salvaged[:expected_len]
                if salvaged:
                    return RepairOutcome(salvaged, RepairQuality.SALVAGED)

    return None

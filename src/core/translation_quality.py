"""Structural checks for translated RPG text."""
from __future__ import annotations

from collections import Counter
import re

from src.core.text_segmenter import SegmentType, segment_text


_PLACEHOLDER_RE = re.compile(r"\$\{[^{}]+\}|\{[A-Za-z_][A-Za-z_0-9]*\}|%(?:\d+\$)?[sdif]")


def translation_issues(original: str, translated: str) -> list[str]:
    """Return reasons a translation needs review before writing game data."""
    if not translated or not translated.strip():
        return ["empty translation"]
    issues: list[str] = []
    source_codes = Counter(segment.content for segment in segment_text(original) if segment.type == SegmentType.CODE)
    translated_codes = Counter(segment.content for segment in segment_text(translated) if segment.type == SegmentType.CODE)
    if source_codes != translated_codes:
        issues.append("game codes or tags changed")
    if Counter(_PLACEHOLDER_RE.findall(original)) != Counter(_PLACEHOLDER_RE.findall(translated)):
        issues.append("format placeholders changed")
    if original.count("\n") != translated.count("\n"):
        issues.append("line break count changed")
    return issues

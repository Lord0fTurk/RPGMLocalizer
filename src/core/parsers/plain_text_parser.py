"""
Plain text parser for safe RPG Maker text surfaces.

Currently this parser supports only block-based `credits.txt` files used by
credits plugins. It intentionally ignores arbitrary `.txt` files because many
RPG Maker projects store technical metadata in text files.
"""
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseParser

SUPPORTED_TEXT_FILENAMES = frozenset({"credits.txt"})


class CreditsTextParser(BaseParser):
    """Parser for block-based RPG Maker credits text files."""

    BLOCK_START_RE = re.compile(r"^\s*<block:[^>]*>\s*$", re.IGNORECASE)
    BLOCK_END_RE = re.compile(r"^\s*</block>\s*$", re.IGNORECASE)

    def extract_text(self, file_path: str) -> List[Tuple[str, str, str]]:
        """Extract player-visible lines from credits blocks only."""
        if os.path.basename(file_path).lower() not in SUPPORTED_TEXT_FILENAMES:
            return []

        with open(file_path, "r", encoding="utf-8-sig", newline="") as handle:
            lines = handle.readlines()

        extracted: List[Tuple[str, str, str]] = []
        in_block = False

        for index, raw_line in enumerate(lines):
            line_text, _newline = self._split_line_ending(raw_line)
            stripped = line_text.strip()

            if self.BLOCK_START_RE.fullmatch(stripped):
                in_block = True
                continue

            if self.BLOCK_END_RE.fullmatch(stripped):
                in_block = False
                continue

            if not in_block or not stripped:
                continue

            if not self.is_safe_to_translate(line_text, is_dialogue=True):
                continue

            extracted.append((f"lines.{index}", line_text, "credits_text"))

        return extracted

    def apply_translation(self, file_path: str, translations: Dict[str, str]) -> Any:
        """Apply translations back into the original line positions."""
        if os.path.basename(file_path).lower() not in SUPPORTED_TEXT_FILENAMES:
            return None

        with open(file_path, "r", encoding="utf-8-sig", newline="") as handle:
            lines = handle.readlines()

        for path_key, translated_text in translations.items():
            line_index = self._parse_line_index(path_key)
            if line_index is None or line_index >= len(lines):
                continue
            if not isinstance(translated_text, str):
                continue

            _line_text, newline = self._split_line_ending(lines[line_index])
            lines[line_index] = f"{translated_text}{newline}"

        return "".join(lines)

    def _parse_line_index(self, path_key: str) -> Optional[int]:
        """Parse `lines.{index}` path keys used by this parser."""
        if not isinstance(path_key, str) or not path_key.startswith("lines."):
            return None

        try:
            return int(path_key.split(".", 1)[1])
        except (TypeError, ValueError):
            return None

    def _split_line_ending(self, line: str) -> Tuple[str, str]:
        """Split a line into content and its original newline sequence."""
        if line.endswith("\r\n"):
            return line[:-2], "\r\n"
        if line.endswith("\n"):
            return line[:-1], "\n"
        return line, ""

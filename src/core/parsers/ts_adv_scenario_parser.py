"""Parser for TS_ADVsystem scenario files encoded through TS_Decode."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseParser


TS_SCENARIO_EXTENSION = ".sl"


class TsAdvScenarioParser(BaseParser):
    """Round-trip parser for `scenario/*.sl` ADV text files."""

    def __init__(self, decode_key: int = 255, regex_blacklist: Optional[List[str]] = None) -> None:
        super().__init__(regex_blacklist=regex_blacklist or [])
        self.decode_key = decode_key
        self.last_apply_error: Optional[str] = None

    def extract_text(self, file_path: str) -> List[Tuple[str, str, str]]:
        """Extract dialogue-like lines from a TS scenario script."""
        self.last_apply_error = None
        if os.path.splitext(file_path)[1].lower() != TS_SCENARIO_EXTENSION:
            return []

        decoded = self._decode_text(file_path)
        extracted: List[Tuple[str, str, str]] = []

        for index, line in enumerate(decoded.splitlines()):
            normalized = line.strip()
            if not self._is_translatable_line(normalized):
                continue
            if not self.is_safe_to_translate(normalized, is_dialogue=True):
                continue
            extracted.append((f"lines.{index}", normalized, "dialogue_block"))

        return extracted

    def apply_translation(self, file_path: str, translations: Dict[str, str]) -> Any:
        """Apply translations and re-encode the scenario file content."""
        self.last_apply_error = None
        if os.path.splitext(file_path)[1].lower() != TS_SCENARIO_EXTENSION:
            return None

        decoded = self._decode_text(file_path)
        lines = decoded.splitlines()
        had_trailing_newline = decoded.endswith("\n")

        for path_key, translated_text in translations.items():
            line_index = self._parse_line_index(path_key)
            if line_index is None or line_index >= len(lines):
                continue
            if not isinstance(translated_text, str):
                continue
            lines[line_index] = translated_text

        updated = "\n".join(lines)
        if had_trailing_newline:
            updated += "\n"
        return self._encode_text(updated)

    def _decode_text(self, file_path: str) -> str:
        """Decode the TS scenario file using the configured XOR key."""
        with open(file_path, "r", encoding="utf-8") as handle:
            raw_text = handle.read()
        return "".join(chr(ord(char) ^ self.decode_key) for char in raw_text)

    def _encode_text(self, text: str) -> str:
        """Encode plain scenario text back into TS format."""
        return "".join(chr(ord(char) ^ self.decode_key) for char in text)

    def _is_translatable_line(self, line: str) -> bool:
        """Return True when a decoded scenario line should be sent to translation."""
        if not line:
            return False
        if line.startswith("@") or line.startswith("*") or line.startswith(";"):
            return False
        if line.startswith("["):
            return True
        if any(ord(char) > 127 for char in line):
            return True
        if any(mark in line for mark in ".!?…:)]"):
            return True
        word_count = len([word for word in line.split() if word])
        return word_count >= 3

    def _parse_line_index(self, path_key: str) -> Optional[int]:
        """Parse `lines.{index}` path keys used by this parser."""
        if not isinstance(path_key, str) or not path_key.startswith("lines."):
            return None
        try:
            return int(path_key.split(".", 1)[1])
        except (TypeError, ValueError):
            return None

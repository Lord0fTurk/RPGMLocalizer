"""Parser for Hendrix Localization CSV translation surfaces."""

from __future__ import annotations

import csv
import io
import os
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseParser


HENDRIX_CSV_FILENAME = "game_messages.csv"


class HendrixLocalizationCsvParser(BaseParser):
    """Round-trip parser for Hendrix Localization CSV files."""

    def __init__(
        self,
        source_lang: str = "auto",
        target_lang: str = "tr",
        regex_blacklist: List[str] | None = None,
    ) -> None:
        super().__init__(regex_blacklist=regex_blacklist)
        self.source_lang = (source_lang or "auto").strip().lower()
        self.target_lang = (target_lang or "tr").strip().lower()
        self.last_apply_error: Optional[str] = None

    def extract_text(self, file_path: str) -> List[Tuple[str, str, str]]:
        """Extract translatable rows from the `Original` column."""
        self.last_apply_error = None
        if os.path.basename(file_path).lower() != HENDRIX_CSV_FILENAME:
            return []

        delimiter, rows = self._read_rows(file_path)
        if not rows:
            return []

        headers = rows[0]
        original_index = self._find_header_index(headers, "Original")
        if original_index is None:
            return []

        extracted: List[Tuple[str, str, str]] = []
        for row_index, row in enumerate(rows[1:], start=1):
            original_text = self._get_cell(row, original_index)
            if not original_text or not original_text.strip():
                continue
            if not self.is_safe_to_translate(original_text, is_dialogue=True):
                continue
            extracted.append((f"rows.{row_index}.Original", original_text, "dialogue_block"))

        return extracted

    def apply_translation(self, file_path: str, translations: Dict[str, str]) -> Any:
        """Apply translations into the target language column, adding it if needed."""
        self.last_apply_error = None
        if os.path.basename(file_path).lower() != HENDRIX_CSV_FILENAME:
            return None

        delimiter, rows = self._read_rows(file_path)
        if not rows:
            self.last_apply_error = "Hendrix CSV is empty"
            return None

        headers = rows[0]
        target_index = self._find_header_index(headers, self.target_lang)
        if target_index is None:
            headers.append(self.target_lang)
            target_index = len(headers) - 1

        for row in rows[1:]:
            self._ensure_row_width(row, len(headers))

        for path_key, translated_text in translations.items():
            row_index = self._parse_row_index(path_key)
            if row_index is None or row_index >= len(rows):
                continue
            if not isinstance(translated_text, str):
                continue

            row = rows[row_index]
            self._ensure_row_width(row, len(headers))
            row[target_index] = translated_text

        output = io.StringIO(newline="")
        writer = csv.writer(output, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        writer.writerows(rows)
        return "\ufeff" + output.getvalue()

    def _read_rows(self, file_path: str) -> Tuple[str, List[List[str]]]:
        """Read CSV rows and detect the delimiter used by the file."""
        with open(file_path, "r", encoding="utf-8-sig", newline="") as handle:
            content = handle.read()

        if not content:
            return ",", []

        delimiter = self._detect_delimiter(content)
        reader = csv.reader(io.StringIO(content, newline=""), delimiter=delimiter)
        rows = [list(row) for row in reader]
        return delimiter, rows

    def _detect_delimiter(self, content: str) -> str:
        """Detect whether the Hendrix file uses commas or semicolons."""
        first_line = content.splitlines()[0] if content.splitlines() else content
        if first_line.count(";") > first_line.count(","):
            return ";"
        return ","

    def _find_header_index(self, headers: List[str], target_header: str) -> Optional[int]:
        """Return a case-insensitive header index."""
        target_lower = target_header.lower()
        for index, header in enumerate(headers):
            if isinstance(header, str) and header.strip().lower() == target_lower:
                return index
        return None

    def _get_cell(self, row: List[str], index: int) -> str:
        """Safely fetch a CSV cell by index."""
        if index < 0 or index >= len(row):
            return ""
        return row[index]

    def _ensure_row_width(self, row: List[str], width: int) -> None:
        """Ensure a CSV row is wide enough for the current header count."""
        while len(row) < width:
            row.append("")

    def _parse_row_index(self, path_key: str) -> Optional[int]:
        """Parse `rows.{index}.Original` path keys used by this parser."""
        if not isinstance(path_key, str):
            return None
        parts = path_key.split(".")
        if len(parts) != 3 or parts[0] != "rows" or parts[2] != "Original":
            return None
        try:
            return int(parts[1])
        except (TypeError, ValueError):
            return None

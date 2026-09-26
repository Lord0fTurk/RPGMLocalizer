"""WOLF RPG Editor external scenario text parser (Data/Evtext/**/*.txt).

In WOLF RPG visual novels and dialogue-heavy games, scenario scripts are often
stored as plain text files in `Data/Evtext/` and loaded dynamically via
Common Events (e.g. CID 122).

Format:
  - Control lines start with: `/`, `//`, `@`, `<`, `<<`, `#`
  - All other lines are user-facing dialogue, narrative, or speaker tags (e.g. 'Yuri:')
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseParser
from .wolf_binary import normalize_for_cp932

logger = logging.getLogger("WolfEvtextParser")

# Non-translatable control line prefixes in WOLF Evtext scripts
WOLF_EVTEXT_CONTROL_PREFIXES: tuple[str, ...] = (
    "/",     # Commands like /evcg, /bgv, /fin, /fout, /ch, /shake
    "//",    # Comments
    "@",     # Sound effect or timing markers like @1, @2
    "<",     # Tags like <<GET_FILE_EXIST>> or <SQUARE>
    "#",     # Comments or script directives
)


def is_wolf_evtext_file(file_path: str) -> bool:
    """Return True if the file is an Evtext script inside a WOLF project."""
    if not file_path or not file_path.lower().endswith(".txt"):
        return False
    norm = os.path.normpath(file_path).lower()
    parts = norm.split(os.sep)
    return "evtext" in parts or any(p.startswith("evtext") for p in parts)


class WolfEvtextParser(BaseParser):
    """Parser for WOLF RPG external scenario text files (Data/Evtext/**/*.txt)."""

    def __init__(
        self,
        regex_blacklist: Optional[List[str]] = None,
        translate_comments: bool = False,
    ) -> None:
        super().__init__(regex_blacklist=regex_blacklist)
        self.translate_comments = translate_comments
        self.last_apply_error: Optional[str] = None
        self._last_detected_encoding: str = "cp932"

    def _detect_encoding(self, raw_bytes: bytes) -> str:
        """Detect whether text is UTF-8 (with/without BOM) or legacy CP932 (Shift-JIS)."""
        if raw_bytes.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig"

        # Try strict UTF-8 first
        try:
            raw_bytes.decode("utf-8")
            return "utf-8"
        except UnicodeDecodeError:
            pass

        # Default for legacy WOLF RPG is CP932 (Shift-JIS)
        try:
            raw_bytes.decode("cp932")
            return "cp932"
        except UnicodeDecodeError:
            pass

        return "utf-8"

    def is_line_translatable(self, line: str) -> bool:
        """Check if a line in an Evtext file contains translatable user-facing text."""
        stripped = line.strip()
        if not stripped:
            return False

        # Exclude engine directives and comments
        if any(stripped.startswith(prefix) for prefix in WOLF_EVTEXT_CONTROL_PREFIXES):
            return False

        # Must have at least one alphanumeric or Japanese character
        has_content = any(c.isalnum() or ord(c) > 0x2000 for c in stripped)
        if not has_content:
            return False

        return True

    def extract_text(self, file_path: str) -> List[Tuple[str, str, str]]:
        """Extract translatable lines from an Evtext .txt file."""
        entries: List[Tuple[str, str, str]] = []
        if not os.path.isfile(file_path):
            return entries

        try:
            with open(file_path, "rb") as f:
                raw_bytes = f.read()
        except OSError as exc:
            logger.error("Failed to read Evtext file %s: %s", file_path, exc)
            return entries

        encoding = self._detect_encoding(raw_bytes)
        self._last_detected_encoding = encoding

        try:
            content = raw_bytes.decode(encoding, errors="replace")
        except Exception as exc:
            logger.error("Failed to decode Evtext file %s: %s", file_path, exc)
            return entries

        lines = content.splitlines()
        for idx, line in enumerate(lines):
            if not self.is_line_translatable(line):
                continue

            text_to_translate = line.strip()
            if any(p.search(text_to_translate) for p in self.blacklist_patterns):
                continue

            # Identify if it's a speaker label (e.g. 'Yuri:' or 'Squid Inkwell:')
            tag = "name" if (text_to_translate.endswith(":") and len(text_to_translate) < 40) else "dialogue"
            entries.append((f"lines/{idx}", text_to_translate, tag))

        return entries

    def apply_translation(self, file_path: str, translations: Dict[str, str]) -> Optional[bytes]:
        """Apply translations to Evtext lines and return updated binary payload."""
        self.last_apply_error = None
        if not os.path.isfile(file_path):
            self.last_apply_error = f"File not found: {file_path}"
            return None

        try:
            with open(file_path, "rb") as f:
                raw_bytes = f.read()
        except OSError as exc:
            self.last_apply_error = str(exc)
            return None

        if not translations:
            return raw_bytes

        encoding = self._detect_encoding(raw_bytes)
        try:
            content = raw_bytes.decode(encoding, errors="replace")
        except Exception as exc:
            self.last_apply_error = f"Decode error: {exc}"
            return None

        # Determine line ending style (\r\n vs \n)
        newline = "\r\n" if "\r\n" in content else "\n"
        lines = content.splitlines()

        for idx in range(len(lines)):
            locator = f"lines/{idx}"
            if locator in translations:
                trans_text = translations[locator]
                # If target file is CP932, apply transliteration to protect unmapped unicode characters
                if encoding in ("cp932", "shift_jis", "sjis"):
                    trans_text = normalize_for_cp932(trans_text)
                lines[idx] = trans_text

        new_content = newline.join(lines) + (newline if content.endswith(newline) or content.endswith("\n") else "")

        try:
            if encoding in ("cp932", "shift_jis", "sjis"):
                return new_content.encode("cp932", errors="replace")
            elif encoding == "utf-8-sig":
                return new_content.encode("utf-8-sig")
            else:
                return new_content.encode("utf-8")
        except Exception as exc:
            self.last_apply_error = f"Encode error: {exc}"
            logger.error("Failed to encode translated Evtext file %s: %s", file_path, exc)
            return None

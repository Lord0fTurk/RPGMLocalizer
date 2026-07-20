"""RPG Maker font replacer — Noto Sans bundled font + custom font support.

Reads TTF metrics without external dependencies, updates gamefont.css
non-destructively, and auto-recalculates word-wrap limits.
"""
from __future__ import annotations

import logging
import os
import re
import struct
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

NOTO_SANS_URL = (
    "https://github.com/google/fonts/raw/main/ofl/notosans/"
    "NotoSans%5Bwdth%2Cwght%5D.ttf"
)
NOTO_SANS_FILENAME = "NotoSans-Variable.ttf"
NOTO_FALLBACK_URL = (
    "https://raw.githubusercontent.com/google/fonts/main/ofl/notosans/"
    "NotoSans-Regular.ttf"
)
NOTO_FALLBACK_FILENAME = "NotoSans-Regular.ttf"

CACHE_DIR_NAME = ".rpgm_fonts"

CSS_REPLACE_RE = re.compile(
    r'(@font-face\s*\{[^}]*font-family\s*:\s*[\'"])GameFont([\'"])',
    re.IGNORECASE,
)
CSS_SRC_RE = re.compile(
    r'(src\s*:\s*url\([\'"]?)([^)]+?)([\'"]?\s*\))',
    re.IGNORECASE,
)


@dataclass
class FontMetrics:
    family_name: str
    avg_char_width_px: float
    ascent_px: float
    descent_px: float
    units_per_em: int
    weight: int


def _read_ttf_name_table(data: bytes, name_id: int) -> str | None:
    """Extract a name string from the TTF name table (nameID = name_id)."""
    try:
        pos = data.find(b"name")
        if pos < 0 or pos % 4 != 0:
            return None
        table_offset = pos
        fmt = struct.unpack_from(">HHH", data, table_offset + 4)
        count, string_offset, _string_storage_offset = (
            fmt[1], table_offset + struct.unpack_from(">H", data, table_offset + 6)[0],
            table_offset + 6
        )
        string_start = table_offset + struct.unpack_from(">H", data, table_offset + 6)[0]
        rec_base = table_offset + 8
        for i in range(count):
            rec = struct.unpack_from(">HHHHHH", data, rec_base + i * 12)
            _platform_id, _encoding_id, _language_id, rec_name_id, length, offset = rec
            if rec_name_id == name_id:
                raw = data[string_start + offset:string_start + offset + length]
                try:
                    return raw.decode("utf-16-be").rstrip("\x00")
                except UnicodeDecodeError:
                    return raw.decode("latin-1", errors="replace").rstrip("\x00")
    except (struct.error, IndexError):
        pass
    return None


def measure_font_metrics(ttf_path: str | Path, target_size: int = 28) -> FontMetrics | None:
    """Read TTF/OTF file and extract font metrics at *target_size* px.

    No external dependencies — pure struct-based TTF header parsing.
    Works with TrueType (.ttf) and OpenType (.otf) files.
    """
    path = Path(ttf_path)
    if not path.is_file():
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None

    if len(data) < 12:
        return None

    try:
        table_count = struct.unpack_from(">H", data, 4)[0]
    except struct.error:
        return None

    def _find_table(tag: bytes) -> int | None:
        for i in range(table_count):
            entry = struct.unpack_from(">4sIII", data, 12 + i * 16)
            if entry[0] == tag:
                return entry[2]
        return None

    # Read head table — unitsPerEm
    head_off = _find_table(b"head")
    if head_off is None:
        return None
    units_per_em = struct.unpack_from(">H", data, head_off + 18)[0]
    if units_per_em <= 0:
        return None

    # Read OS/2 table — xAvgCharWidth, usWeightClass
    os2_off = _find_table(b"OS/2")
    x_avg = 500
    weight = 400
    if os2_off is not None and os2_off + 4 <= len(data):
        x_avg_raw = struct.unpack_from(">h", data, os2_off + 2)[0]
        weight = struct.unpack_from(">H", data, os2_off + 4)[0]
        if x_avg_raw > 0:
            x_avg = x_avg_raw

    # Read hhea table — ascent, descent
    hhea_off = _find_table(b"hhea")
    ascent = 0
    descent = 0
    if hhea_off is not None and hhea_off + 10 <= len(data):
        ascent = struct.unpack_from(">h", data, hhea_off + 4)[0]
        descent = struct.unpack_from(">h", data, hhea_off + 6)[0]

    family = _read_ttf_name_table(data, 1) or path.stem

    scale = target_size / max(units_per_em, 1)

    return FontMetrics(
        family_name=family,
        avg_char_width_px=round(x_avg * scale, 2),
        ascent_px=round(ascent * scale, 2),
        descent_px=round(descent * scale, 2),
        units_per_em=units_per_em,
        weight=weight,
    )


def _get_font_cache_dir() -> Path:
    from src.utils.app_paths import get_cache_dir
    path = Path(get_cache_dir("RPGMLocalizer")).parent / CACHE_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def download_noto_sans(
    progress_callback: Callable[[str], None] | None = None,
) -> Path | None:
    """Download Noto Sans (variable) from Google Fonts GitHub mirror.

    Falls back to the static Regular variant if the variable font fails.
    Returns the path to the cached .ttf file.
    """
    cache_dir = _get_font_cache_dir()

    def _dl(url: str, filename: str) -> Path | None:
        dest = cache_dir / filename
        if dest.is_file() and dest.stat().st_size > 10000:
            logger.info("Using cached font: %s", dest)
            return dest
        try:
            logger.info("Downloading font from %s …", url)
            if progress_callback:
                progress_callback("Downloading Noto Sans font …")
            req = urllib.request.Request(url, headers={"User-Agent": "RPGMLocalizer/0.7"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                blob = resp.read()
            if len(blob) < 1000:
                raise OSError("Downloaded file too small — likely a redirect page")
            dest.write_bytes(blob)
            logger.info("Font cached at %s", dest)
            return dest
        except Exception as exc:
            logger.warning("Font download failed (%s): %s", filename, exc)
            return None

    result = _dl(NOTO_SANS_URL, NOTO_SANS_FILENAME)
    if result is not None:
        return result
    logger.warning("Variable font failed, trying static fallback …")
    return _dl(NOTO_FALLBACK_URL, NOTO_FALLBACK_FILENAME)


def install_font_to_game(
    font_path: str | Path,
    game_dir: str | Path,
    log_callback: Callable[[str], None] | None = None,
) -> FontMetrics | None:
    """Copy *font_path* into the game's ``fonts/`` directory.

    Non-destructive: the original gamefont.css is backed up (by the pipeline's
    BackupManager) before modification.  A new ``@font-face`` entry is prepended
    to ``fonts/gamefont.css`` so the engine loads the new font with higher
    priority.

    Returns measured FontMetrics so wrap limits can be recalculated.
    """
    font_path = Path(font_path)
    game_dir = Path(game_dir)

    if not font_path.is_file():
        return None

    # Detect game directory layout (www/ subfolder for MV/MZ)
    for candidate in (game_dir, game_dir / "www"):
        if (candidate / "data").is_dir() and (candidate / "fonts").is_dir():
            game_dir = candidate
            break

    fonts_dir = game_dir / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)

    css_path = fonts_dir / "gamefont.css"

    metrics = measure_font_metrics(font_path)
    if metrics is None:
        return None

    # Copy font file
    dest_name = font_path.name
    dest = fonts_dir / dest_name
    try:
        dest.write_bytes(font_path.read_bytes())
    except OSError as exc:
        logger.error("Failed to copy font to %s: %s", dest, exc)
        return None

    if log_callback:
        log_callback(f"Font copied: {dest_name}")

    # Update gamefont.css
    if not css_path.is_file():
        css_path.write_text(
            f'@font-face {{\n'
            f'    font-family: "GameFont";\n'
            f'    src: url("{dest_name}") format("truetype");\n'
            f'}}\n',
            encoding="utf-8",
        )
        if log_callback:
            log_callback("gamefont.css created")
        return metrics

    css_content = css_path.read_text(encoding="utf-8")

    # Prepend a new @font-face so it takes priority over the existing one.
    # CSS uses first-match for @font-face with same font-family.
    new_face = (
        f'@font-face {{\n'
        f'    font-family: "GameFont";\n'
        f'    src: url("{dest_name}") format("truetype");\n'
        f'}}\n'
    )
    css_path.write_text(new_face + css_content, encoding="utf-8")

    if log_callback:
        log_callback(
            f"gamefont.css updated — {metrics.family_name} "
            f"({metrics.avg_char_width_px} px/char)"
        )

    return metrics


def detect_game_font(game_dir: str | Path) -> str | None:
    """Detect the current game font from gamefont.css."""
    game_dir = Path(game_dir)
    for candidate in (game_dir, game_dir / "www"):
        css_path = candidate / "fonts" / "gamefont.css"
        if css_path.is_file():
            try:
                content = css_path.read_text(encoding="utf-8")
                for m in re.finditer(
                    r"font-family\s*:\s*[\"']?(\w+)[\"']?",
                    content, re.IGNORECASE,
                ):
                    return m.group(1)
                src_match = CSS_SRC_RE.search(content)
                if src_match:
                    return src_match.group(2)
            except OSError:
                pass
    return None


def calculate_wrap_limits(
    window_width: int,
    font_metrics: FontMetrics | None = None,
    avg_char_width: float = 13.5,
) -> tuple[int, int]:
    """Calculate standard and portrait wrap limits.

    If *font_metrics* is provided, uses the font's measured average character
    width.  Otherwise falls back to *avg_char_width* (13.5 px for M+ 1m).

    Returns (standard_limit, portrait_limit).
    """
    if window_width <= 0:
        return (54, 44)
    cw = font_metrics.avg_char_width_px if font_metrics else avg_char_width
    usable = window_width * 0.88
    standard = max(20, int((usable - 32) / cw))
    portrait = max(15, int((usable - 32 - 144) / cw))
    return (standard, portrait)

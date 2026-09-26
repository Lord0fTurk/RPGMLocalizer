"""High-level WOLF RPG Editor parser for RPGMLocalizer.

Implements BaseParser interface for:
  - Map data: Data/MapData/**/*.mps
  - Common events: Data/BasicData/CommonEvent.dat
  - Database entries: Data/BasicData/*.project + *.dat
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.utils.file_ops import safe_write
from .base import BaseParser
from .wolf_binary import (
    CID_BATTLE_MESSAGE,
    CID_CHOICES,
    CID_ERROR_MESSAGE,
    CID_MESSAGE,
    CID_PICTURE_TEXT,
    CID_STRING_OP,
    WolfCommonEvents,
    WolfDatabase,
    WolfFormatError,
    WolfMap,
    iter_command_texts,
    locator_set,
    translatable_fields,
)

logger = logging.getLogger("WolfParser")

WOLF_DRAW_PRIMITIVES: tuple[str, ...] = ("<square", "<line", "<grad")
WOLF_PATH_PREFIXES: tuple[str, ...] = (
    "picture/", "data/", "systemgraphic/", "audio/", "se/", "bgm/", "save/", "movie/"
)


class WolfParser(BaseParser):
    """Parser for WOLF RPG Editor binary game data files."""

    def __init__(
        self,
        regex_blacklist: Optional[List[str]] = None,
        translate_comments: bool = False,
    ) -> None:
        super().__init__(regex_blacklist=regex_blacklist)
        self.translate_comments = translate_comments
        self.last_apply_error: Optional[str] = None

    def is_wolf_text_translatable(self, cid: int, text: str) -> bool:
        """Determine if a command text slot is translatable user-facing text.

        Excludes drawing primitives, image/audio file paths, and control symbols.
        """
        if not text or not text.strip():
            return False
        trimmed = text.strip()
        lower = trimmed.lower()

        # Command 150 drawing primitives & picture folder paths
        if cid == CID_PICTURE_TEXT:
            if any(lower.startswith(p) for p in WOLF_DRAW_PRIMITIVES):
                return False
            if any(lower.startswith(p) for p in WOLF_PATH_PREFIXES):
                return False

        # File paths in any command
        if any(lower.endswith(ext) for ext in (
            ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".ogg", ".wav", ".mp3", ".sav", ".dat", ".mps", ".mid"
        )):
            return False
        if any(lower.startswith(p) for p in WOLF_PATH_PREFIXES):
            return False

        # CID 122 (String Operation) programmatic flags, state identifiers, and booleans
        if cid == CID_STRING_OP:
            if lower in ("true", "false", "null", "none", "on", "off", "ok", "yes", "no"):
                return False
            # Uppercase state flags or identifiers like FLAG_CLEAR, STAGE_01, EV_START
            if re.fullmatch(r"[A-Z0-9_\-\.]{2,}", trimmed):
                return False
            # Script step / phase identifiers like step_1, phase_boss, quest_done
            if re.fullmatch(r"(?:step|phase|flag|event|quest|state|var|mode)_[0-9a-zA-Z_]+", lower):
                return False

        # Ignore pure control codes or symbol sequences
        if self.contains_only_control_codes(trimmed):
            return False
        if re.fullmatch(r"[\s\d\+\-\*\/\=\<\>\(\)\[\]\{\}\\\_\,\.\:\;\#\%\@\^\&\|\~\?\!\'\"\u25b2\u25bc\u2190-\u2193\u21d2]+", trimmed):
            return False

        return self.is_safe_to_translate(trimmed, is_dialogue=True)

    def extract_text(self, file_path: str) -> List[Tuple[str, str, str]]:
        """Extract translatable text entries as (locator, text, tag)."""
        entries: List[Tuple[str, str, str]] = []
        if not os.path.exists(file_path):
            return entries

        ext = os.path.splitext(file_path)[1].lower()
        base = os.path.basename(file_path).lower()

        try:
            if ext == ".mps":
                entries = self._extract_map(file_path)
            elif base == "commonevent.dat":
                entries = self._extract_common_events(file_path)
            elif ext == ".dat":
                entries = self._extract_database(file_path)
        except WolfFormatError as wfe:
            logger.warning("Wolf RPG parsing skipped for %s: %s", file_path, wfe)
        except Exception as exc:
            logger.error("Unexpected error parsing Wolf file %s: %s", file_path, exc, exc_info=True)

        return entries

    def _extract_map(self, file_path: str) -> List[Tuple[str, str, str]]:
        entries: List[Tuple[str, str, str]] = []
        game_map = WolfMap.read(file_path)
        for event_idx, event in enumerate(game_map.events):
            for page_idx, page in enumerate(event.pages):
                prefix = f"events/{event_idx}/pages/{page_idx}/commands"
                for locator, text in iter_command_texts(page.commands, prefix):
                    cmd_idx = int(locator.split("/")[-3])
                    cmd = page.commands[cmd_idx]
                    if not self.is_wolf_text_translatable(cmd.cid, text):
                        continue
                    if any(p.search(text) for p in self.blacklist_patterns):
                        continue
                    if cmd.cid in (CID_MESSAGE, CID_BATTLE_MESSAGE):
                        tag = "dialogue"
                    elif cmd.cid == CID_CHOICES:
                        tag = "choice"
                    else:
                        tag = "system"
                    entries.append((locator, text, tag))
        return entries

    def _extract_common_events(self, file_path: str) -> List[Tuple[str, str, str]]:
        entries: List[Tuple[str, str, str]] = []
        ce = WolfCommonEvents.read(file_path)
        for event_idx, event in enumerate(ce.events):
            prefix = f"events/{event_idx}/commands"
            for locator, text in iter_command_texts(event.commands, prefix):
                cmd_idx = int(locator.split("/")[-3])
                cmd = event.commands[cmd_idx]
                if not self.is_wolf_text_translatable(cmd.cid, text):
                    continue
                if any(p.search(text) for p in self.blacklist_patterns):
                    continue
                if cmd.cid in (CID_MESSAGE, CID_BATTLE_MESSAGE):
                    tag = "dialogue"
                elif cmd.cid == CID_CHOICES:
                    tag = "choice"
                else:
                    tag = "system"
                entries.append((locator, text, tag))
        return entries

    @staticmethod
    def _is_translatable_db_type(base_name: str, type_idx: int, type_name: str) -> bool:
        """Filter out non-translatable internal types, variable lists, and asset registers."""
        if base_name == "sysdatabase.dat":
            # In SysDatabase, only Type 0 (Map Settings) contains player-facing map display names.
            # All other types (variable names, BGM/SE lists, window skins) are internal engine settings.
            return type_idx == 0 or "マップ" in type_name

        tn = type_name.strip()
        if tn.startswith(("×", "[×", "----------------")):
            return False

        non_translatable_keywords = (
            "変数", "BGM", "BGS", "SE", "画像", "アニメーション",
            "影", "トランジション", "フォグ", "遠景",
        )
        if any(kw in tn for kw in non_translatable_keywords):
            return False

        return True

    def _extract_database(self, file_path: str) -> List[Tuple[str, str, str]]:
        entries: List[Tuple[str, str, str]] = []
        base = os.path.basename(file_path).lower()
        if base in ("game.dat", "sysdatabasebasic.dat"):
            return entries

        project_path = os.path.splitext(file_path)[0] + ".project"
        if not os.path.isfile(project_path):
            logger.warning(
                "WOLF database file '%s' skipped: Companion schema '%s' not found. "
                "Database records cannot be extracted without the project schema.",
                file_path,
                project_path,
            )
            return entries

        db = WolfDatabase.read(project_path, file_path)
        for type_idx, db_type in enumerate(db.types):
            if not self._is_translatable_db_type(base, type_idx, db_type.name):
                continue

            is_item_type = any(kw in db_type.name for kw in ("技能", "スキル", "アイテム", "武器", "防具", "装備"))
            is_actor_type = any(kw in db_type.name for kw in ("主人公", "プレイヤー", "仲間"))
            tag = "item" if is_item_type else ("actor" if is_actor_type else "system")

            fields = translatable_fields(db_type)
            for data_idx, record in enumerate(db_type.data):
                # 1. Extract record display name (e.g. skill, item, dungeon, or stat names)
                name = record.name.strip()
                if (
                    name
                    and not name.startswith(("■", "---", "※", "[×"))
                    and self.is_safe_to_translate(name)
                    and not any(p.search(name) for p in self.blacklist_patterns)
                ):
                    locator = f"types/{type_idx}/data/{data_idx}/name"
                    entries.append((locator, record.name, tag))

                # 2. Extract record translatable string field values (e.g. descriptions)
                for f in fields:
                    idx = f.value_index()
                    if idx >= len(record.string_values):
                        continue
                    text = record.string_values[idx]
                    if not text or not text.strip():
                        continue
                    if not self.is_safe_to_translate(text):
                        continue
                    if any(p.search(text) for p in self.blacklist_patterns):
                        continue
                    locator = f"types/{type_idx}/data/{data_idx}/string_values/{idx}"
                    entries.append((locator, text, tag))
        return entries

    def apply_translation(self, file_path: str, translations: Dict[str, str]) -> Optional[bytes]:
        """Apply translations to WOLF RPG data file and return updated binary payload."""
        self.last_apply_error = None
        if not translations:
            try:
                return Path(file_path).read_bytes()
            except Exception as exc:
                self.last_apply_error = str(exc)
                return None

        ext = os.path.splitext(file_path)[1].lower()
        base = os.path.basename(file_path).lower()

        try:
            if ext == ".mps":
                game_map = WolfMap.read(file_path)
                for locator, trans_text in translations.items():
                    locator_set(game_map, locator, trans_text)
                return game_map.to_bytes()

            elif base == "commonevent.dat":
                ce = WolfCommonEvents.read(file_path)
                for locator, trans_text in translations.items():
                    locator_set(ce, locator, trans_text)
                return ce.to_bytes()

            elif ext == ".dat":
                project_path = os.path.splitext(file_path)[0] + ".project"
                if not os.path.isfile(project_path):
                    self.last_apply_error = f"Missing project schema file for {file_path}"
                    return None
                db = WolfDatabase.read(project_path, file_path)
                for locator, trans_text in translations.items():
                    locator_set(db, locator, trans_text)

                proj_bytes, dat_bytes = db.to_project_and_dat_bytes()
                # If project file encoding upgraded or changed, write it safely
                try:
                    with safe_write(project_path, mode="wb") as f:
                        f.write(proj_bytes)
                except Exception as proj_err:
                    logger.warning("Failed to write updated project schema %s: %s", project_path, proj_err)

                return dat_bytes

        except Exception as exc:
            self.last_apply_error = f"WOLF translation application failed: {exc}"
            logger.error("Error applying translations to %s: %s", file_path, exc, exc_info=True)
            return None

        self.last_apply_error = f"Unsupported WOLF file extension: {ext}"
        return None

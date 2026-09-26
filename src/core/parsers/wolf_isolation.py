"""WOLF RPG Editor archive isolation and conflict neutralization.

In WOLF RPG Editor, Game.exe prioritizes packaged `.wolf` archives over loose
extracted directories in `Data/`. When a game has been unpacked and translated,
any remaining `.wolf` files must be safely isolated into `Data/_wolf_original/`
so the engine loads the translated loose files.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import List

logger = logging.getLogger("WolfIsolation")

ORIGINAL_ARCHIVES_DIR = "_wolf_original"


def find_wolf_data_dir(project_path: str) -> str | None:
    """Locate the WOLF RPG 'Data' directory case-insensitively."""
    if not project_path or not os.path.isdir(project_path):
        return None

    # Check direct project_path if it's already the Data folder
    if os.path.basename(os.path.normpath(project_path)).lower() == "data":
        return project_path

    # Check subdirectories matching 'data' case-insensitively, preserving on-disk casing
    try:
        with os.scandir(project_path) as entries:
            for entry in entries:
                if entry.is_dir() and entry.name.lower() == "data":
                    return entry.path
    except OSError:
        pass

    return None


def isolate_conflicting_wolf_archives(project_path: str) -> List[str]:
    """Move `.wolf` archives to `Data/_wolf_original/` if extracted directories exist.

    Returns the list of filenames moved.
    """
    data_dir = find_wolf_data_dir(project_path)
    if not data_dir:
        return []

    moved_files: List[str] = []
    dest_dir = os.path.join(data_dir, ORIGINAL_ARCHIVES_DIR)

    try:
        entries = os.listdir(data_dir)
    except OSError as exc:
        logger.warning("Failed to list WOLF data directory '%s': %s", data_dir, exc)
        return []

    # Identify existing subdirectories (e.g. BasicData, MapData, Evtext)
    existing_dirs = {
        name.lower(): name
        for name in entries
        if os.path.isdir(os.path.join(data_dir, name)) and name != ORIGINAL_ARCHIVES_DIR
    }

    # Find .wolf files that have a matching extracted directory or when core WOLF directories exist
    has_core_dirs = "basicdata" in existing_dirs or "mapdata" in existing_dirs
    wolf_files = [fn for fn in entries if fn.lower().endswith(".wolf") and os.path.isfile(os.path.join(data_dir, fn))]

    if not wolf_files:
        return []

    # If any extracted directory exists, we should isolate conflicting archives
    for fn in wolf_files:
        stem = os.path.splitext(fn)[0].lower()
        # Move if specific companion folder exists OR if core dirs exist (e.g. BasicData unpacked)
        should_isolate = stem in existing_dirs or has_core_dirs

        if should_isolate:
            os.makedirs(dest_dir, exist_ok=True)
            src_path = os.path.join(data_dir, fn)
            target_path = os.path.join(dest_dir, fn)

            try:
                if os.path.exists(target_path):
                    # Destination file already exists, remove src or replace
                    os.remove(src_path)
                else:
                    shutil.move(src_path, target_path)
                moved_files.append(fn)
                logger.info("Isolated conflicting WOLF archive: %s -> %s", fn, ORIGINAL_ARCHIVES_DIR)
            except OSError as exc:
                logger.error("Failed to move WOLF archive '%s': %s", fn, exc)

    if moved_files:
        readme_path = os.path.join(dest_dir, "README_RESTORE.txt")
        if not os.path.exists(readme_path):
            try:
                with open(readme_path, "w", encoding="utf-8") as f:
                    f.write(
                        "These are the original .wolf archive packages.\n"
                        "They were moved here so the WOLF RPG engine can read the translated loose files in 'Data/'.\n"
                        "To restore the original unmodded game, move these .wolf files back into 'Data/'.\n"
                    )
            except OSError:
                pass

    return moved_files


def restore_wolf_archives(project_path: str) -> List[str]:
    """Restore `.wolf` archives from `Data/_wolf_original/` back into `Data/`."""
    data_dir = find_wolf_data_dir(project_path)
    if not data_dir:
        return []

    source_dir = os.path.join(data_dir, ORIGINAL_ARCHIVES_DIR)
    if not os.path.isdir(source_dir):
        return []

    restored: List[str] = []
    try:
        entries = os.listdir(source_dir)
        for fn in entries:
            if fn.lower().endswith(".wolf"):
                src_path = os.path.join(source_dir, fn)
                target_path = os.path.join(data_dir, fn)
                shutil.move(src_path, target_path)
                restored.append(fn)

        # Remove readme and backup dir if empty
        readme_path = os.path.join(source_dir, "README_RESTORE.txt")
        if os.path.exists(readme_path):
            os.remove(readme_path)
        if not os.listdir(source_dir):
            os.rmdir(source_dir)
    except OSError as exc:
        logger.error("Failed to restore WOLF archives: %s", exc)

    return restored

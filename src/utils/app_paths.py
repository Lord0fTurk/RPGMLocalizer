from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "RPGMLocalizer"
PORTABLE_MARKER = ".portable"


def is_frozen() -> bool:
    """Return True when running from a packaged executable."""
    return bool(getattr(sys, "frozen", False))


def is_appimage() -> bool:
    """Return True when running inside a Linux AppImage."""
    return bool(os.environ.get("APPIMAGE") or os.environ.get("APP_IMAGE"))


def get_app_dir() -> Path:
    """Return the physical application directory."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def get_system_data_dir(app_name: str = APP_NAME) -> Path:
    """Return the OS-native writable application data directory."""
    if sys.platform == "win32":
        base_dir = os.environ.get("APPDATA")
        if not base_dir:
            base_dir = str(Path.home() / "AppData" / "Roaming")
        return Path(base_dir) / app_name

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / app_name
    return Path.home() / ".local" / "share" / app_name


import json
import re

def get_data_dir(app_name: str = APP_NAME) -> Path:
    """
    Determine the active writable data directory (Portable vs System mode).
    Matches RenLocalizer's priority rules.
    """
    app_dir = get_app_dir()

    # 1. Force System Mode for AppImages (mount is read-only)
    if is_appimage():
        return get_system_data_dir(app_name)

    # 2. Check for explicit portable marker
    if (app_dir / PORTABLE_MARKER).exists():
        return app_dir

    # 3. Legacy Fallback: If config.json already exists in app_dir and is writable,
    # assume portable legacy mode to prevent data loss.
    if (app_dir / "config.json").exists() and os.access(app_dir, os.W_OK):
        return app_dir

    # 4. Default to System Data Directory for clean/standard installations
    return get_system_data_dir(app_name)


# Parity alias matching RenLocalizer API
get_data_path = get_data_dir


def ensure_directory(path: Path) -> Path:
    """Ensure directory exists and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_data_directories(data_path: Path | None = None) -> None:
    """Ensure essential data directories exist within the data path."""
    target_path = data_path or get_data_dir()
    ensure_directory(target_path)
    ensure_directory(target_path / "logs")
    ensure_directory(target_path / "cache")
    ensure_directory(target_path / "tm")
    ensure_directory(target_path / "backups")


def normalize_project_name(name: str) -> str:
    """
    Strips version tags, duplicates, and platforms from a folder or title
    to produce a clean, stable project identifier.

    e.g. 'My Game v0.2.3-pc' -> 'My Game'
         'Game (1)' -> 'Game'
    """
    if not name:
        return ""

    # 1. Clean browser duplicates: e.g. "Game (1)" -> "Game"
    name = re.sub(r'\s*\(\d+\)\s*$', '', name)
    name = re.sub(r'\s*\[\d+\]\s*$', '', name)

    # 2. Strip version markers like v1.0, v1.0.0, 1.2, 0.4.5, 2026.04, 2026
    name = re.sub(r'(?i)\s+v?\d+(?:\.\d+)+(?:\s*-[a-zA-Z0-9]+)?\b', '', name)
    name = re.sub(r'(?i)\s+v\d+\b', '', name)
    name = re.sub(r'(?i)[-_\s]+v?\d+(?:\.\d+)+', '', name)
    name = re.sub(r'(?i)\s+(?:19|20)\d{2}(?:\.\d+)?\b', '', name)

    # 3. Strip platform indicators
    name = re.sub(r'(?i)[-_\s]+(?:pc|win|mac|linux|android|windows|osx|universal|chrome|html5)\b', '', name)

    # 4. Strip build stage indicators
    name = re.sub(r'(?i)[-_\s]+(?:beta|alpha|preview|demo|patreon|sub|pirated|uncensored|mod|remastered)\b', '', name)

    # 5. Sanitize filesystem-unsafe characters
    name = re.sub(r'[\\/*?:"<>|]', '_', name)

    # Clean up trailing spaces or dashes
    name = name.strip('-_ ')
    return name


def _extract_title_from_package_json(project_path: Path) -> str | None:
    """Extract game title from MV/MZ package.json."""
    candidates = (project_path / "package.json", project_path / "www" / "package.json")
    for pkg_file in candidates:
        if not pkg_file.is_file():
            continue
        try:
            with open(pkg_file, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
            title = data.get("window", {}).get("title") or data.get("name")
            if isinstance(title, str) and title.strip():
                return title.strip()
        except Exception:
            pass
    return None


def _extract_title_from_system_json(project_path: Path) -> str | None:
    """Extract game title from MV/MZ data/System.json."""
    candidates = (
        project_path / "data" / "System.json",
        project_path / "www" / "data" / "System.json",
    )
    for sys_file in candidates:
        if not sys_file.is_file():
            continue
        try:
            with open(sys_file, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
            title = data.get("gameTitle")
            if isinstance(title, str) and title.strip():
                return title.strip()
        except Exception:
            pass
    return None


def _extract_title_from_game_ini(project_path: Path) -> str | None:
    """Extract game title from XP/VX/VXA Game.ini."""
    ini_file = project_path / "Game.ini"
    if not ini_file.is_file():
        return None
    for enc in ("utf-8", "cp1252", "cp932", "latin1"):
        try:
            with open(ini_file, "r", encoding=enc, errors="ignore") as f:
                content = f.read()
            match = re.search(r'(?i)^\s*Title\s*=\s*(.+)$', content, re.MULTILINE)
            if match:
                title = match.group(1).strip()
                if title:
                    return title
            break
        except Exception:
            continue
    return None


def _extract_title_from_exe(project_path: Path, game_exe_path: str | Path | None) -> str | None:
    """Extract game title from custom executable."""
    generic_exes = {
        "game", "nw", "rpg_rt", "launcher", "setup", "uninstall",
        "run", "patch", "rpgmlocalizer", "index",
        "notification_helper", "chromedriver", "crash_inspector",
        "elevate", "ffmpeg", "node",
    }
    if game_exe_path:
        exe_p = Path(game_exe_path)
        if exe_p.is_file() and exe_p.stem.lower() not in generic_exes:
            return exe_p.stem

    if project_path.is_dir():
        try:
            for entry in project_path.iterdir():
                if entry.is_file() and entry.suffix.lower() == ".exe":
                    if entry.stem.lower() not in generic_exes:
                        return entry.stem
        except Exception:
            pass
    return None


def get_project_id(project_path: str | Path | None, game_exe_path: str | Path | None = None) -> str:
    """
    Extracts a robust and stable project identifier for translation cache.
    RPG Maker-aware identification strategies:
    1. MV/MZ package.json (window.title or name)
    2. MV/MZ data/System.json (gameTitle)
    3. XP/VX/VXA Game.ini (Title)
    4. Custom game executable name
    5. Fallback to normalized project directory name
    """
    if not project_path:
        return "default_project"

    p = Path(project_path)

    # Strategy 1: package.json (MV/MZ)
    title = _extract_title_from_package_json(p)
    if title:
        cleaned = normalize_project_name(title)
        if cleaned:
            return cleaned

    # Strategy 2: System.json (MV/MZ)
    title = _extract_title_from_system_json(p)
    if title:
        cleaned = normalize_project_name(title)
        if cleaned:
            return cleaned

    # Strategy 3: Game.ini (XP/VX/VXA)
    title = _extract_title_from_game_ini(p)
    if title:
        cleaned = normalize_project_name(title)
        if cleaned:
            return cleaned

    # Strategy 4: Custom game executable
    title = _extract_title_from_exe(p, game_exe_path)
    if title:
        cleaned = normalize_project_name(title)
        if cleaned:
            return cleaned

    # Strategy 5: Directory name
    dir_name = p.name or p.resolve().name
    if dir_name:
        cleaned = normalize_project_name(dir_name)
        if cleaned:
            return cleaned

    return "default_project"


def get_settings_path(filename: str = "config.json") -> Path:
    """Return the writable configuration file path."""
    return ensure_directory(get_data_dir()) / filename


def get_cache_dir(
    project_id: str | None = None,
    target_lang: str | None = None,
    dirname: str = "cache",
) -> Path:
    """
    Return the writable cache directory path.
    Supports project-isolated and target-language-isolated caching.
    """
    base = ensure_directory(get_data_dir() / dirname)
    if not project_id:
        return base

    safe_id = re.sub(r'[\\/*?:"<>|]', '_', project_id).strip() or "default_project"
    project_cache = ensure_directory(base / safe_id)

    if target_lang:
        safe_lang = re.sub(r'[\\/*?:"<>|]', '_', target_lang).strip()
        return ensure_directory(project_cache / safe_lang)

    return project_cache


def get_logs_dir(dirname: str = "logs") -> Path:
    """Return the writable logs directory path."""
    return ensure_directory(get_data_dir() / dirname)

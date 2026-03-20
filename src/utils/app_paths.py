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


def get_data_dir(app_name: str = APP_NAME) -> Path:
    """Return the active writable application data directory."""
    app_dir = get_app_dir()
    if (app_dir / PORTABLE_MARKER).exists():
        return app_dir

    if sys.platform == "win32":
        return app_dir

    return get_system_data_dir(app_name)


def ensure_directory(path: Path) -> Path:
    """Ensure directory exists and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_settings_path(filename: str = "settings.json") -> Path:
    """Return the writable settings file path."""
    return ensure_directory(get_data_dir()) / filename


def get_cache_dir(dirname: str = ".rpgm_cache") -> Path:
    """Return the writable cache directory path."""
    return ensure_directory(get_data_dir() / dirname)


def get_logs_dir(dirname: str = "logs") -> Path:
    """Return the writable logs directory path."""
    return ensure_directory(get_data_dir() / dirname)

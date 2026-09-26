import sys
import os
from typing import Optional

from src.utils.app_paths import get_app_dir

def resource_path(relative_path: str) -> str:
    """Get an absolute resource path for source and PyInstaller runs."""
    # PyInstaller creates a temp folder and stores path in _MEIPASS.
    base_path = getattr(sys, "_MEIPASS", None)
    if not base_path:
        base_path = os.fspath(get_app_dir())

    return os.path.join(base_path, relative_path)


def existing_resource_path(*relative_paths: str) -> Optional[str]:
    """Return the first existing resource path from the given candidates."""
    for relative_path in relative_paths:
        candidate = resource_path(relative_path)
        if os.path.exists(candidate):
            return candidate
    return None


def local_path_from_url(raw: str) -> str:
    """Normalise a dropped/pasted path that may be a ``file://`` URL.

    Uses ``QUrl.toLocalFile`` so both ``file:///D:/game`` (Windows) and
    ``file:///home/user/game`` (POSIX) resolve to the correct absolute path.
    Plain filesystem paths are returned stripped of surrounding quotes.
    """
    cleaned = (raw or "").strip().strip('"').strip("'")
    if cleaned.lower().startswith("file:"):
        try:
            from PyQt6.QtCore import QUrl
            local = QUrl(cleaned).toLocalFile()
            if local:
                return local
        except Exception:
            pass
    return cleaned

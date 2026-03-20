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

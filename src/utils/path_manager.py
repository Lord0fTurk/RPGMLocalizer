"""
Path Manager Module
===================
Provides RenLocalizer-compatible data path resolution, directory scaffolding,
project ID normalization, and cache paths for RPG Maker projects.
"""
from __future__ import annotations

from src.utils.app_paths import (
    APP_NAME,
    PORTABLE_MARKER,
    ensure_data_directories,
    ensure_directory,
    get_app_dir,
    get_cache_dir,
    get_data_dir,
    get_data_path,
    get_logs_dir,
    get_project_id,
    get_settings_path,
    get_system_data_dir,
    is_appimage,
    is_frozen,
    normalize_project_name,
)

__all__ = [
    "APP_NAME",
    "PORTABLE_MARKER",
    "is_frozen",
    "is_appimage",
    "get_app_dir",
    "get_system_data_dir",
    "get_data_dir",
    "get_data_path",
    "ensure_directory",
    "ensure_data_directories",
    "normalize_project_name",
    "get_project_id",
    "get_settings_path",
    "get_cache_dir",
    "get_logs_dir",
]

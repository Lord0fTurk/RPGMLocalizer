import json
import logging
import os
from typing import Any, Dict

from src.utils.app_paths import get_app_dir, get_data_dir, get_settings_path
from src.utils.file_ops import safe_write


class SettingsStore:
    def __init__(self, filename: str = "config.json") -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.filename = filename
        self.path = self._resolve_settings_path(filename)

    def _resolve_settings_path(self, filename: str) -> str:
        return os.fspath(get_settings_path(filename))

    def _find_legacy_settings(self) -> str | None:
        """Locate legacy configuration or settings files for seamless migration."""
        candidates = [
            get_data_dir() / "settings.json",
            get_app_dir() / "config.json",
            get_app_dir() / "settings.json",
        ]
        for candidate in candidates:
            if candidate.is_file() and os.fspath(candidate) != self.path:
                return os.fspath(candidate)
        return None

    def load(self) -> Dict[str, Any]:
        """Load settings, migrating from legacy files if needed."""
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data if isinstance(data, dict) else {}

            # Check for legacy files and migrate
            legacy_file = self._find_legacy_settings()
            if legacy_file and os.path.exists(legacy_file):
                with open(legacy_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.logger.info(f"Migrating legacy settings from {legacy_file} to {self.path}")
                    self.save(data)
                    return data

            return {}
        except Exception as e:
            self.logger.warning(f"Failed to load settings: {e}")
            return {}

    def save(self, data: Dict[str, Any]) -> None:
        """Save configuration atomically with UTF-8 encoding."""
        try:
            dir_name = os.path.dirname(self.path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with safe_write(self.path, mode="w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.warning(f"Failed to save settings: {e}")

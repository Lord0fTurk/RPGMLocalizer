import json
import logging
import os
from typing import Any, Dict

from src.utils.app_paths import get_settings_path
from src.utils.file_ops import safe_write


class SettingsStore:
    def __init__(self, filename: str = "settings.json") -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.path = self._resolve_settings_path(filename)

    def _resolve_settings_path(self, filename: str) -> str:
        return os.fspath(get_settings_path(filename))

    def load(self) -> Dict[str, Any]:
        try:
            if not os.path.exists(self.path):
                return {}
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            self.logger.warning(f"Failed to load settings: {e}")
            return {}

    def save(self, data: Dict[str, Any]) -> None:
        try:
            # Ensure the parent directory exists (first-run scenario)
            dir_name = os.path.dirname(self.path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with safe_write(self.path, mode="w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=True)
        except Exception as e:
            self.logger.warning(f"Failed to save settings: {e}")

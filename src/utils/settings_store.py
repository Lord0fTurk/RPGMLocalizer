import json
import logging
import os
import sys
from typing import Any, Dict

from PyQt6.QtCore import QStandardPaths


class SettingsStore:
    def __init__(self, filename: str = "settings.json"):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.path = self._resolve_settings_path(filename)

    def _resolve_settings_path(self, filename: str) -> str:
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.abspath(".")
        os.makedirs(base_dir, exist_ok=True)
        return os.path.join(base_dir, filename)

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
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=True)
        except Exception as e:
            self.logger.warning(f"Failed to save settings: {e}")

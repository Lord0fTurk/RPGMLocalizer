import json
import logging
from typing import Any, Dict, List

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

from src.backend.settings_backend import SettingsBackend
from src.utils.paths import existing_resource_path


class LocaleManager(QObject):
    """QObject backend bridge exposing the app's own UI language strings to QML.

    Unrelated to `SettingsBackend.targetLang`/`sourceLang`, which control the
    RPG Maker GAME text translation direction, not the app's interface language.
    """

    languageChanged = pyqtSignal()

    SUPPORTED_LANGUAGES: List[tuple[str, str]] = [
        ("en", "English"),
        ("tr", "Türkçe"),
        ("de", "Deutsch"),
        ("fr", "Français"),
        ("es", "Español"),
        ("pt-BR", "Português (Brasil)"),
        ("ru", "Русский"),
        ("fa", "فارسی"),
    ]
    DEFAULT_LANGUAGE = "en"
    TURKIC_LANGUAGES = {"tr", "az", "uz", "kk", "ky", "tk", "ug", "tt", "ba", "cv", "gag"}

    @classmethod
    def detect_system_language(cls) -> str:
        """Detect the OS UI language and map to one of the 8 supported application locales.

        Maps Turkic family languages (az, uz, kk, ky, tk, etc.) to Turkish ('tr').
        Defaults to English ('en') if unsupported.
        """
        try:
            from PyQt6.QtCore import QLocale
            sys_loc = QLocale.system()
            bcp47 = sys_loc.bcp47Name().lower()
            lang_code = bcp47.split("-")[0]

            if lang_code in cls.TURKIC_LANGUAGES:
                return "tr"
            elif lang_code == "pt":
                return "pt-BR"
            elif lang_code in ("de", "fr", "es", "ru", "fa", "en"):
                return lang_code
            elif lang_code in ("uk", "be"):  # Ukrainian, Belarusian -> Russian
                return "ru"
            elif lang_code in ("prs", "tg"):  # Dari, Tajik -> Persian
                return "fa"
        except Exception:
            pass

        return cls.DEFAULT_LANGUAGE

    _instance: "LocaleManager | None" = None

    @classmethod
    def get_instance(cls) -> "LocaleManager | None":
        return cls._instance

    @classmethod
    def get_text(cls, key_path: str, default: str = "") -> str:
        """Fetch string by dotted path (or leaf key) from the active LocaleManager instance, or fallback to default."""
        def _lookup(data: dict[str, Any]) -> str | None:
            if not isinstance(data, dict):
                return None
            cur: Any = data
            found = True
            for part in key_path.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    found = False
                    break
            if found and cur is not None:
                return str(cur)

            if "." not in key_path:
                for section in data.values():
                    if isinstance(section, dict) and key_path in section:
                        val = section[key_path]
                        return str(val) if val is not None else None
            return None

        inst = cls._instance
        if inst and inst._strings:
            res = _lookup(inst._strings)
            if res is not None:
                return res

        path = existing_resource_path("src/gui/i18n/en.json")
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    res = _lookup(data)
                    if res is not None:
                        return res
            except Exception:
                pass
        return default

    def __init__(self, settings_backend: SettingsBackend, parent: QObject | None = None) -> None:
        super().__init__(parent)
        LocaleManager._instance = self
        self.logger = logging.getLogger(self.__class__.__name__)
        self._settings = settings_backend
        self._base_strings: Dict[str, Any] = self._load_locale_file(self.DEFAULT_LANGUAGE)
        self._current_language = self.DEFAULT_LANGUAGE
        self._strings: Dict[str, Any] = self._base_strings

        chosen_lang = self._settings.uiLanguage
        if not chosen_lang:
            chosen_lang = self.detect_system_language()
            self._settings.uiLanguage = chosen_lang

        self._apply_language(chosen_lang)

    def _load_locale_file(self, code: str) -> Dict[str, Any]:
        path = existing_resource_path(f"src/gui/i18n/{code}.json")
        if not path:
            self.logger.warning("Locale file not found for language '%s'", code)
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError) as exc:
            self.logger.warning("Failed to load locale file '%s': %s", path, exc)
            return {}

    @staticmethod
    def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = LocaleManager._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

    def _apply_language(self, code: str) -> None:
        valid_codes = {c for c, _ in self.SUPPORTED_LANGUAGES}
        if code not in valid_codes:
            code = self.DEFAULT_LANGUAGE

        if code == self.DEFAULT_LANGUAGE:
            self._strings = dict(self._base_strings)
        else:
            override = self._load_locale_file(code)
            self._strings = self._deep_merge(self._base_strings, override)

        self._current_language = code

    @pyqtProperty(str, notify=languageChanged)
    def currentLanguage(self) -> str:
        return self._current_language

    @pyqtProperty("QVariant", notify=languageChanged)
    def strings(self) -> Dict[str, Any]:
        return self._strings

    @pyqtSlot(str)
    def setLanguage(self, code: str) -> None:
        if code == self._current_language:
            return
        self._apply_language(code)
        self._settings.uiLanguage = self._current_language
        self.languageChanged.emit()

    @pyqtSlot(result="QVariantList")
    def availableLanguages(self) -> List[Dict[str, str]]:
        return [{"code": code, "name": name} for code, name in self.SUPPORTED_LANGUAGES]

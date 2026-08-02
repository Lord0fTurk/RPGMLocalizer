import json
import logging
from typing import Any, Dict, List
from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

from src.utils.settings_store import SettingsStore


class SettingsBackend(QObject):
    """QObject backend bridge for managing application settings in QML."""

    settingsChanged = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.store = SettingsStore()
        self._data: Dict[str, Any] = {
            "target_lang": "tr",
            "source_lang": "auto",
            "engine": "google",
            "translate_notes": False,
            "translate_comments": False,
            "translate_plugins_js": True,
            "plugin_js_ui_extraction": True,
            "visustella_wordwrap": False,
            "auto_wordwrap": True,
            "wordwrap_limit_standard": 50,
            "wordwrap_limit_portrait": 38,
            "font_use_noto": True,
            "font_path": "",
            "backup_enabled": True,
            "use_cache": True,
            "glossary_path": "",
            "use_glossary": False,
            "export_path": "",
            "export_only": True,
            "export_distinct": False,
            "import_path": "",
            "regex_blacklist": "",
            "batch_size": 15,
            "concurrent_requests": 8,
            "progress_throttle_ms": 250,
            "use_multi_endpoint": True,
            "enable_lingva_fallback": True,
            "request_delay_ms": 0,
            "request_timeout": 45,
            "max_retries": 3,
            "openai_api_key": "",
            "openai_model": "gpt-4o-mini",
            "openai_base_url": "https://api.openai.com/v1",
            "gemini_api_key": "",
            "gemini_model": "gemini-2.0-flash",
            "local_llm_url": "http://localhost:11434/v1",
            "local_llm_model": "llama3",
            "deepl_api_key": "",
            "libretranslate_url": "http://localhost:5000",
            "libretranslate_api_key": "",
        }
        self.load()

    @pyqtSlot()
    def load(self) -> None:
        """Load settings from storage."""
        loaded = self.store.load()
        if loaded:
            for k, v in loaded.items():
                if k == "regex_blacklist" and isinstance(v, list):
                    self._data[k] = "\n".join(v)
                else:
                    self._data[k] = v
        self.settingsChanged.emit()

    @pyqtSlot()
    def save(self) -> None:
        """Save current settings to storage."""
        save_dict = self._data.copy()
        raw_regex = self._data.get("regex_blacklist", "")
        if isinstance(raw_regex, str):
            save_dict["regex_blacklist"] = [line.strip() for line in raw_regex.split("\n") if line.strip()]
        self.store.save(save_dict)

    def get_dict(self) -> Dict[str, Any]:
        """Return raw dictionary for translation pipeline consumption."""
        d = self._data.copy()
        raw_regex = self._data.get("regex_blacklist", "")
        if isinstance(raw_regex, str):
            d["regex_blacklist"] = [line.strip() for line in raw_regex.split("\n") if line.strip()]
        return d

    # --- Property Getters & Setters ---

    def _get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def _set(self, key: str, val: Any) -> None:
        if self._data.get(key) != val:
            self._data[key] = val
            self.save()
            self.settingsChanged.emit()

    @pyqtProperty(str, notify=settingsChanged)
    def targetLang(self) -> str:
        return str(self._get("target_lang", "tr"))

    @targetLang.setter
    def targetLang(self, val: str) -> None:
        self._set("target_lang", val)

    @pyqtProperty(str, notify=settingsChanged)
    def sourceLang(self) -> str:
        return str(self._get("source_lang", "auto"))

    @sourceLang.setter
    def sourceLang(self, val: str) -> None:
        self._set("source_lang", val)

    @pyqtProperty(str, notify=settingsChanged)
    def engine(self) -> str:
        return str(self._get("engine", "google"))

    @engine.setter
    def engine(self, val: str) -> None:
        self._set("engine", val)

    @pyqtProperty(bool, notify=settingsChanged)
    def translateNotes(self) -> bool:
        return bool(self._get("translate_notes", False))

    @translateNotes.setter
    def translateNotes(self, val: bool) -> None:
        self._set("translate_notes", val)

    @pyqtProperty(bool, notify=settingsChanged)
    def translateComments(self) -> bool:
        return bool(self._get("translate_comments", False))

    @translateComments.setter
    def translateComments(self, val: bool) -> None:
        self._set("translate_comments", val)

    @pyqtProperty(bool, notify=settingsChanged)
    def translatePluginsJs(self) -> bool:
        return bool(self._get("translate_plugins_js", True))

    @translatePluginsJs.setter
    def translatePluginsJs(self, val: bool) -> None:
        self._set("translate_plugins_js", val)

    @pyqtProperty(bool, notify=settingsChanged)
    def pluginJsUiExtraction(self) -> bool:
        return bool(self._get("plugin_js_ui_extraction", True))

    @pluginJsUiExtraction.setter
    def pluginJsUiExtraction(self, val: bool) -> None:
        self._set("plugin_js_ui_extraction", val)

    @pyqtProperty(bool, notify=settingsChanged)
    def visuStellaWordwrap(self) -> bool:
        return bool(self._get("visustella_wordwrap", False))

    @visuStellaWordwrap.setter
    def visuStellaWordwrap(self, val: bool) -> None:
        self._set("visustella_wordwrap", val)

    @pyqtProperty(bool, notify=settingsChanged)
    def autoWordwrap(self) -> bool:
        return bool(self._get("auto_wordwrap", True))

    @autoWordwrap.setter
    def autoWordwrap(self, val: bool) -> None:
        self._set("auto_wordwrap", val)

    @pyqtProperty(int, notify=settingsChanged)
    def wordwrapLimitStandard(self) -> int:
        return int(self._get("wordwrap_limit_standard", 50))

    @wordwrapLimitStandard.setter
    def wordwrapLimitStandard(self, val: int) -> None:
        self._set("wordwrap_limit_standard", val)

    @pyqtProperty(int, notify=settingsChanged)
    def wordwrapLimitPortrait(self) -> int:
        return int(self._get("wordwrap_limit_portrait", 38))

    @wordwrapLimitPortrait.setter
    def wordwrapLimitPortrait(self, val: int) -> None:
        self._set("wordwrap_limit_portrait", val)

    @pyqtProperty(bool, notify=settingsChanged)
    def fontUseNoto(self) -> bool:
        return bool(self._get("font_use_noto", True))

    @fontUseNoto.setter
    def fontUseNoto(self, val: bool) -> None:
        self._set("font_use_noto", val)

    @pyqtProperty(str, notify=settingsChanged)
    def fontPath(self) -> str:
        return str(self._get("font_path", ""))

    @fontPath.setter
    def fontPath(self, val: str) -> None:
        self._set("font_path", val)

    @pyqtProperty(bool, notify=settingsChanged)
    def backupEnabled(self) -> bool:
        return bool(self._get("backup_enabled", True))

    @backupEnabled.setter
    def backupEnabled(self, val: bool) -> None:
        self._set("backup_enabled", val)

    @pyqtProperty(bool, notify=settingsChanged)
    def useCache(self) -> bool:
        return bool(self._get("use_cache", True))

    @useCache.setter
    def useCache(self, val: bool) -> None:
        self._set("use_cache", val)

    @pyqtProperty(str, notify=settingsChanged)
    def glossaryPath(self) -> str:
        return str(self._get("glossary_path", ""))

    @glossaryPath.setter
    def glossaryPath(self, val: str) -> None:
        self._set("glossary_path", val)

    @pyqtProperty(bool, notify=settingsChanged)
    def useGlossary(self) -> bool:
        return bool(self._get("use_glossary", False))

    @useGlossary.setter
    def useGlossary(self, val: bool) -> None:
        self._set("use_glossary", val)

    @pyqtProperty(str, notify=settingsChanged)
    def exportPath(self) -> str:
        return str(self._get("export_path", ""))

    @exportPath.setter
    def exportPath(self, val: str) -> None:
        self._set("export_path", val)

    @pyqtProperty(bool, notify=settingsChanged)
    def exportOnly(self) -> bool:
        return bool(self._get("export_only", True))

    @exportOnly.setter
    def exportOnly(self, val: bool) -> None:
        self._set("export_only", val)

    @pyqtProperty(bool, notify=settingsChanged)
    def exportDistinct(self) -> bool:
        return bool(self._get("export_distinct", False))

    @exportDistinct.setter
    def exportDistinct(self, val: bool) -> None:
        self._set("export_distinct", val)

    @pyqtProperty(str, notify=settingsChanged)
    def importPath(self) -> str:
        return str(self._get("import_path", ""))

    @importPath.setter
    def importPath(self, val: str) -> None:
        self._set("import_path", val)

    @pyqtProperty(str, notify=settingsChanged)
    def regexBlacklist(self) -> str:
        return str(self._get("regex_blacklist", ""))

    @regexBlacklist.setter
    def regexBlacklist(self, val: str) -> None:
        self._set("regex_blacklist", val)

    @pyqtProperty(int, notify=settingsChanged)
    def batchSize(self) -> int:
        return int(self._get("batch_size", 15))

    @batchSize.setter
    def batchSize(self, val: int) -> None:
        self._set("batch_size", val)

    @pyqtProperty(int, notify=settingsChanged)
    def concurrentRequests(self) -> int:
        return int(self._get("concurrent_requests", 8))

    @concurrentRequests.setter
    def concurrentRequests(self, val: int) -> None:
        self._set("concurrent_requests", val)

    @pyqtProperty(int, notify=settingsChanged)
    def progressThrottleMs(self) -> int:
        return int(self._get("progress_throttle_ms", 250))

    @progressThrottleMs.setter
    def progressThrottleMs(self, val: int) -> None:
        self._set("progress_throttle_ms", val)

    @pyqtProperty(bool, notify=settingsChanged)
    def useMultiEndpoint(self) -> bool:
        return bool(self._get("use_multi_endpoint", True))

    @useMultiEndpoint.setter
    def useMultiEndpoint(self, val: bool) -> None:
        self._set("use_multi_endpoint", val)

    @pyqtProperty(bool, notify=settingsChanged)
    def enableLingvaFallback(self) -> bool:
        return bool(self._get("enable_lingva_fallback", True))

    @enableLingvaFallback.setter
    def enableLingvaFallback(self, val: bool) -> None:
        self._set("enable_lingva_fallback", val)

    @pyqtProperty(int, notify=settingsChanged)
    def requestDelayMs(self) -> int:
        return int(self._get("request_delay_ms", 0))

    @requestDelayMs.setter
    def requestDelayMs(self, val: int) -> None:
        self._set("request_delay_ms", val)

    @pyqtProperty(int, notify=settingsChanged)
    def requestTimeout(self) -> int:
        return int(self._get("request_timeout", 45))

    @requestTimeout.setter
    def requestTimeout(self, val: int) -> None:
        self._set("request_timeout", val)

    @pyqtProperty(int, notify=settingsChanged)
    def maxRetries(self) -> int:
        return int(self._get("max_retries", 3))

    @maxRetries.setter
    def maxRetries(self, val: int) -> None:
        self._set("max_retries", val)

    # --- AI & Engine Specific Settings Properties ---

    @pyqtProperty(str, notify=settingsChanged)
    def openaiApiKey(self) -> str:
        return str(self._get("openai_api_key", ""))

    @openaiApiKey.setter
    def openaiApiKey(self, val: str) -> None:
        self._set("openai_api_key", val)

    @pyqtProperty(str, notify=settingsChanged)
    def openaiModel(self) -> str:
        return str(self._get("openai_model", "gpt-4o-mini"))

    @openaiModel.setter
    def openaiModel(self, val: str) -> None:
        self._set("openai_model", val)

    @pyqtProperty(str, notify=settingsChanged)
    def openaiBaseUrl(self) -> str:
        return str(self._get("openai_base_url", "https://api.openai.com/v1"))

    @openaiBaseUrl.setter
    def openaiBaseUrl(self, val: str) -> None:
        self._set("openai_base_url", val)

    @pyqtProperty(str, notify=settingsChanged)
    def geminiApiKey(self) -> str:
        return str(self._get("gemini_api_key", ""))

    @geminiApiKey.setter
    def geminiApiKey(self, val: str) -> None:
        self._set("gemini_api_key", val)

    @pyqtProperty(str, notify=settingsChanged)
    def geminiModel(self) -> str:
        return str(self._get("gemini_model", "gemini-2.0-flash"))

    @geminiModel.setter
    def geminiModel(self, val: str) -> None:
        self._set("gemini_model", val)

    @pyqtProperty(str, notify=settingsChanged)
    def localLlmUrl(self) -> str:
        return str(self._get("local_llm_url", "http://localhost:11434/v1"))

    @localLlmUrl.setter
    def localLlmUrl(self, val: str) -> None:
        self._set("local_llm_url", val)

    @pyqtProperty(str, notify=settingsChanged)
    def localLlmModel(self) -> str:
        return str(self._get("local_llm_model", "llama3"))

    @localLlmModel.setter
    def localLlmModel(self, val: str) -> None:
        self._set("local_llm_model", val)

    @pyqtProperty(str, notify=settingsChanged)
    def deeplApiKey(self) -> str:
        return str(self._get("deepl_api_key", ""))

    @deeplApiKey.setter
    def deeplApiKey(self, val: str) -> None:
        self._set("deepl_api_key", val)

    @pyqtProperty(str, notify=settingsChanged)
    def libretranslateUrl(self) -> str:
        return str(self._get("libretranslate_url", "http://localhost:5000"))

    @libretranslateUrl.setter
    def libretranslateUrl(self, val: str) -> None:
        self._set("libretranslate_url", val)

    @pyqtProperty(str, notify=settingsChanged)
    def libretranslateApiKey(self) -> str:
        return str(self._get("libretranslate_api_key", ""))

    @libretranslateApiKey.setter
    def libretranslateApiKey(self, val: str) -> None:
        self._set("libretranslate_api_key", val)


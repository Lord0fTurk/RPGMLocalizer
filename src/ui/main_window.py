from PyQt6.QtCore import Qt, QSize, QThread
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QTabWidget

from qfluentwidgets import (FluentWindow, NavigationItemPosition, 
                             FluentIcon as FIF, InfoBar, InfoBarPosition,
                             setTheme, Theme, MSFluentWindow)

from src.core.translation_pipeline import TranslationPipeline
from src.core.enums import PipelineStage

from src.ui.interfaces.home_interface import HomeInterface
from src.ui.interfaces.settings_interface import SettingsInterface
from src.utils.settings_store import SettingsStore
from src.ui.interfaces.export_interface import ExportInterface
from src.ui.interfaces.about_interface import AboutInterface
from src.ui.interfaces.glossary_interface import GlossaryInterface
from src.ui.components.console_log import ConsoleLog
from src.utils.paths import existing_resource_path
from src.ui.styles import THEME_QSS


class MainWindow(MSFluentWindow):
    def __init__(self):
        super().__init__()

        self.thread = None
        self.pipeline = None

        self.initWindow()

        # --- Pages ---
        self.homeInterface = HomeInterface(self)
        self.settingsInterface = SettingsInterface(self)
        self.exportInterface = ExportInterface(self)
        self.glossaryInterface = GlossaryInterface(self)
        self.aboutInterface = AboutInterface(self)
        self.consoleInterface = ConsoleLog(self)
        self.consoleInterface.setObjectName("consoleInterface")

        # Data page: export + glossary as tabs
        self.dataInterface = QTabWidget(self)
        self.dataInterface.setObjectName("DataInterface")
        self.dataInterface.addTab(self.exportInterface, "Export / Import")
        self.dataInterface.addTab(self.glossaryInterface, "Glossary")

        # Navigation: 3 main items (Home, Settings, Data)
        self.addSubInterface(self.homeInterface, FIF.HOME, "Home")
        self.addSubInterface(self.settingsInterface, FIF.SETTING, "Settings")
        self.addSubInterface(self.dataInterface, FIF.LIBRARY, "Data")

        # Bottom items: Console, About, Support
        self.addSubInterface(self.consoleInterface, FIF.COMMAND_PROMPT, "Console",
                             position=NavigationItemPosition.BOTTOM)
        self.addSubInterface(self.aboutInterface, FIF.INFO, "About",
                             position=NavigationItemPosition.BOTTOM)
        self.navigationInterface.addItem(
            routeKey="support",
            icon=FIF.HEART,
            text="Patreon",
            onClick=self._open_patreon,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
        )

        # Signals
        self.homeInterface.start_requested.connect(self.start_pipeline)
        self.homeInterface.stop_requested.connect(self.stop_pipeline)
        self.exportInterface.start_requested.connect(self.homeInterface._on_start)
        self.settingsInterface.btn_clear_cache.clicked.connect(self.clear_cache)
        self.glossaryInterface.glossary_selected.connect(self.settingsInterface.set_glossary_path)

        self.settings_store = SettingsStore()
        self._load_persisted_settings()

    def initWindow(self):
        self.resize(1100, 780)
        self.setWindowTitle("RPGMLocalizer")
        icon_path = existing_resource_path("icon.png", "icon.ico")
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))
        screens = QApplication.screens()
        if screens:
            desktop = screens[0].availableGeometry()
            w, h = desktop.width(), desktop.height()
            self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)
        self.setMicaEffectEnabled(False)
        self.setStyleSheet(THEME_QSS)

    # ------------------------------------------------------------------
    # Pipeline lifecycle
    # ------------------------------------------------------------------

    def start_pipeline(self, data: dict):
        try:
            if self.thread is not None and self.thread.isRunning():
                return
        except RuntimeError:
            self.thread = None
            self.pipeline = None

        settings = data.copy()
        s = self.settingsInterface

        settings["translate_notes"] = s.chk_translate_notes.isChecked()
        settings["translate_comments"] = s.chk_translate_comments.isChecked()
        settings["plugin_js_ui_extraction"] = s.chk_plugin_js_ui_extraction.isChecked()
        settings["visustella_wordwrap"] = s.chk_visustella_wordwrap.isChecked()
        settings["auto_wordwrap"] = s.chk_auto_wordwrap.isChecked()
        settings["wordwrap_limit_standard"] = s.slider_wrap_standard.value()
        settings["wordwrap_limit_portrait"] = s.slider_wrap_portrait.value()
        settings["font_use_noto"] = s.chk_noto_font.isChecked()
        if s.card_font_path.contentLabel.text() not in ("None", ""):
            settings["font_path"] = s.card_font_path.contentLabel.text()
        else:
            settings["font_path"] = ""
        settings["backup_enabled"] = s.chk_backup.isChecked()
        settings["use_cache"] = s.chk_cache.isChecked()
        if s.chk_glossary.isChecked() and s.glossary_path:
            settings["glossary_path"] = s.glossary_path
            settings["use_glossary"] = True
        regex_text = s.txt_regex.toPlainText()
        if regex_text:
            settings["regex_blacklist"] = [line for line in regex_text.split('\n') if line.strip()]

        e = self.exportInterface
        if e.export_path:
            settings["export_path"] = e.export_path
            settings["export_only"] = e.chk_export_only.isChecked()
            settings["export_distinct"] = e.chk_distinct_export.isChecked()
        if e.import_path:
            settings["import_path"] = e.import_path

        settings["batch_size"] = s.slider_batch_size.value()
        settings["concurrent_requests"] = s.slider_concurrent.value()
        settings["progress_throttle_ms"] = s.slider_throttle.value()
        settings["use_multi_endpoint"] = s.chk_multi_endpoint.isChecked()
        settings["enable_lingva_fallback"] = s.chk_lingva_fallback.isChecked()
        settings["request_delay_ms"] = s.slider_request_delay.value()
        settings["request_timeout"] = s.slider_timeout.value()
        settings["max_retries"] = s.slider_max_retries.value()

        self.thread = QThread()
        self.pipeline = TranslationPipeline(settings)
        self.pipeline.moveToThread(self.thread)

        self._save_persisted_settings(settings)

        self.thread.started.connect(self.pipeline.run)
        self.pipeline.finished.connect(self.on_finished)
        self.pipeline.stage_changed.connect(self.on_stage_changed)
        self.pipeline.progress_updated.connect(self.on_progress)
        self.pipeline.log_message.connect(self.on_log_message)
        self.pipeline.finished.connect(self.thread.quit)
        self.pipeline.finished.connect(self.pipeline.deleteLater)
        self.thread.finished.connect(self._cleanup_thread)
        self.thread.finished.connect(self.thread.deleteLater)

        self.homeInterface.set_running(True)
        self.consoleInterface.clear()
        try:
            self.homeInterface.card_log.console.clear()
        except Exception:
            pass

        self.thread.start()

    def _cleanup_thread(self):
        try:
            self.thread = None
            self.pipeline = None
        except Exception:
            pass

    def stop_pipeline(self):
        if self.pipeline:
            self.pipeline.stop()
            self.on_log_message("warning", "Stopping...")

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def on_finished(self, success, message):
        self.homeInterface.set_running(False)
        self.exportInterface.set_processing_state(False)
        self.homeInterface.update_status(message if success else f"Error: {message}")
        self.on_log_message("success" if success else "error", message)

    def on_progress(self, current, total, text=""):
        if total > 0:
            pct = int((current / total) * 100)
            label = text or f"Processing... {pct}%"
            self.homeInterface.update_status(f"{label} ({current}/{total})", pct)
        else:
            self.homeInterface.update_status(text or "Processing...", 0)

    def on_stage_changed(self, stage_val, message):
        self.homeInterface.update_status(message)
        self.on_log_message("info", f"Stage: {message}")

    def on_log_message(self, level, message):
        if level != "debug":
            self.consoleInterface.log(level, message)
            # Also push to the dashboard's embedded console
            try:
                self.homeInterface.card_log.console.log(level, message)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------

    def _collect_persisted_settings(self) -> dict:
        data = {}
        hi = self.homeInterface
        s = self.settingsInterface
        e = self.exportInterface

        path = hi.txt_path.text().strip()
        if path:
            data["project_path"] = path
        data["source_lang"] = hi.SOURCE_LANGUAGES.get(hi.cmb_source.currentText(), "auto")
        data["target_lang"] = hi.TARGET_LANGUAGES.get(hi.cmb_target.currentText(), "tr")
        data["translate_notes"] = s.chk_translate_notes.isChecked()
        data["translate_comments"] = s.chk_translate_comments.isChecked()
        data["plugin_js_ui_extraction"] = s.chk_plugin_js_ui_extraction.isChecked()
        data["visustella_wordwrap"] = s.chk_visustella_wordwrap.isChecked()
        data["auto_wordwrap"] = s.chk_auto_wordwrap.isChecked()
        data["wordwrap_limit_standard"] = s.slider_wrap_standard.value()
        data["wordwrap_limit_portrait"] = s.slider_wrap_portrait.value()
        data["backup_enabled"] = s.chk_backup.isChecked()
        data["use_cache"] = s.chk_cache.isChecked()
        data["batch_size"] = s.slider_batch_size.value()
        data["concurrent_requests"] = s.slider_concurrent.value()
        data["progress_throttle_ms"] = s.slider_throttle.value()
        data["use_multi_endpoint"] = s.chk_multi_endpoint.isChecked()
        data["enable_lingva_fallback"] = s.chk_lingva_fallback.isChecked()
        data["request_delay_ms"] = s.slider_request_delay.value()
        data["request_timeout"] = s.slider_timeout.value()
        data["max_retries"] = s.slider_max_retries.value()
        data["use_glossary"] = s.chk_glossary.isChecked()
        data["glossary_path"] = s.glossary_path
        rt = s.txt_regex.toPlainText()
        if rt:
            data["regex_blacklist"] = [l for l in rt.split("\n") if l.strip()]
        return data

    def _load_persisted_settings(self) -> None:
        data = self.settings_store.load()
        if not data:
            return
        self.homeInterface.apply_settings(data)
        self.settingsInterface.apply_settings(data)

    def _save_persisted_settings(self, data: dict) -> None:
        if data:
            self.settings_store.save(data)

    def closeEvent(self, event):
        try:
            self._save_persisted_settings(self._collect_persisted_settings())
        except Exception:
            pass
        try:
            self.consoleInterface._flush_timer.stop()
        except Exception:
            pass
        try:
            if self.pipeline is not None:
                self.pipeline.stop()
        except (RuntimeError, AttributeError):
            pass
        try:
            if self.thread is not None and self.thread.isRunning():
                self.thread.quit()
                if not self.thread.wait(3000):
                    self.thread.terminate()
                    self.thread.wait(1000)
        except (RuntimeError, AttributeError):
            pass
        self.thread = None
        self.pipeline = None
        super().closeEvent(event)

    def clear_cache(self):
        from src.core.cache import get_cache
        try:
            cache = get_cache()
            cache.clear()
            cache.save()
            msg = f"Translation cache cleared"
            self.on_log_message("success", msg)
            InfoBar.success(title='Cache Cleared', content=msg,
                            orient=Qt.Orientation.Horizontal, isClosable=True,
                            position=InfoBarPosition.TOP_RIGHT, duration=3000, parent=self)
        except Exception as e:
            self.on_log_message("error", f"Failed to clear cache: {e}")

    def _open_patreon(self):
        import webbrowser
        webbrowser.open("https://www.patreon.com/cw/LordOfTurk")

import os
os.environ['QT_API'] = 'pyqt6'
import sys
from PyQt6.QtCore import Qt, QSize, QThread
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from qfluentwidgets import (FluentWindow, NavigationItemPosition, FluentTranslator, 
                            FluentIcon as FIF, SplashScreen, InfoBar, InfoBarPosition)

from src.core.translation_pipeline import TranslationPipeline
from src.core.enums import PipelineStage

from src.ui.interfaces.home_interface import HomeInterface
from src.ui.interfaces.settings_interface import SettingsInterface
from src.utils.settings_store import SettingsStore
from src.ui.interfaces.export_interface import ExportInterface
from src.ui.interfaces.about_interface import AboutInterface
from src.ui.interfaces.glossary_interface import GlossaryInterface
from src.ui.components.console_log import ConsoleLog

class MainWindow(FluentWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        
        # 1. Pipeline Setup
        self.thread = None
        self.pipeline = None
        
        # 2. UI Setup
        self.initWindow()
        
        # 3. Create Sub-Interfaces
        self.homeInterface = HomeInterface(self)
        self.settingsInterface = SettingsInterface(self)
        self.exportInterface = ExportInterface(self)
        self.glossaryInterface = GlossaryInterface(self)
        self.aboutInterface = AboutInterface(self)
        self.consoleInterface = ConsoleLog(self)
        self.consoleInterface.setObjectName("consoleInterface")
        
        # 4. Add to Navigation
        self.addSubInterface(self.homeInterface, FIF.HOME, "Translation")
        self.addSubInterface(self.settingsInterface, FIF.SETTING, "Settings")
        self.addSubInterface(self.glossaryInterface, FIF.BOOK_SHELF, "Glossary")
        self.addSubInterface(self.exportInterface, FIF.SHARE, "Export/Import")
        self.addSubInterface(self.aboutInterface, FIF.INFO, "About", position=NavigationItemPosition.BOTTOM)
        self.addSubInterface(self.consoleInterface, FIF.COMMAND_PROMPT, "Console", position=NavigationItemPosition.BOTTOM)
        
        # Add Support/Donate button
        self.navigationInterface.addItem(
            routeKey="support",
            icon=FIF.HEART,
            text="Support Developer",
            onClick=self._open_patreon,
            selectable=False,
            position=NavigationItemPosition.BOTTOM
        )
        
        # 5. Connect Signals
        self.homeInterface.start_requested.connect(self.start_pipeline)
        self.homeInterface.stop_requested.connect(self.stop_pipeline)
        self.settingsInterface.btn_clear_cache.clicked.connect(self.clear_cache)
        self.glossaryInterface.glossary_selected.connect(self.settingsInterface.set_glossary_path)

        self.settings_store = SettingsStore()
        self._load_persisted_settings()

    def initWindow(self):
        self.resize(900, 700)
        self.setWindowTitle("RPGMLocalizer")
        
        # Set window icon (scale from 2048x2048 to 64x64)
        from PyQt6.QtGui import QPixmap
        from PyQt6.QtCore import Qt as QtCore_Qt
        from src.utils.paths import resource_path
        
        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path)
            scaled_pixmap = pixmap.scaled(64, 64, QtCore_Qt.AspectRatioMode.KeepAspectRatio, QtCore_Qt.TransformationMode.SmoothTransformation)
            self.setWindowIcon(QIcon(scaled_pixmap))
        
        # Center on screen
        desktop = QApplication.screens()[0].availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w//2 - self.width()//2, h//2 - self.height()//2)
        
        # Theme is set in main.py before widget creation

    def start_pipeline(self, data: dict):
        # Check if thread exists AND is still valid (not deleted)
        try:
            if self.thread is not None and self.thread.isRunning():
                return
        except RuntimeError:
            # Thread was deleted, reset references
            self.thread = None
            self.pipeline = None
            
        # 1. Gather all settings (Merge Home data with Settings page data)
        settings = data.copy()
        
        # Parser Settings
        settings["translate_notes"] = self.settingsInterface.chk_translate_notes.isChecked()
        settings["translate_comments"] = self.settingsInterface.chk_translate_comments.isChecked()
        
        # Formatting Settings
        settings["visustella_wordwrap"] = self.settingsInterface.chk_visustella_wordwrap.isChecked()
        settings["auto_wordwrap"] = self.settingsInterface.chk_auto_wordwrap.isChecked()
        
        # Pipeline Settings
        settings["backup_enabled"] = self.settingsInterface.chk_backup.isChecked()
        settings["use_cache"] = self.settingsInterface.chk_cache.isChecked()
        
        # Glossary Settings
        if self.settingsInterface.chk_glossary.isChecked() and self.settingsInterface.glossary_path:
            settings["glossary_path"] = self.settingsInterface.glossary_path

        # Filtering Settings
        regex_text = self.settingsInterface.txt_regex.toPlainText()
        if regex_text:
            settings["regex_blacklist"] = [line for line in regex_text.split('\n') if line.strip()]
        
        # Export/Import Settings
        if self.exportInterface.export_path:
            settings["export_path"] = self.exportInterface.export_path
            settings["export_only"] = self.exportInterface.chk_export_only.isChecked()
        if self.exportInterface.import_path:
            settings["import_path"] = self.exportInterface.import_path
            
        # Performance Settings
        # Custom SliderSettingCard exposes .value() directly
        settings["batch_size"] = self.settingsInterface.slider_batch_size.value()
        settings["concurrent_requests"] = self.settingsInterface.slider_concurrent.value()

        # Network Settings
        settings["use_multi_endpoint"] = self.settingsInterface.chk_multi_endpoint.isChecked()
        settings["enable_lingva_fallback"] = self.settingsInterface.chk_lingva_fallback.isChecked()
        settings["request_delay_ms"] = self.settingsInterface.slider_request_delay.value()
        settings["request_timeout"] = self.settingsInterface.slider_timeout.value()
        settings["max_retries"] = self.settingsInterface.slider_max_retries.value()
        
        # 2. Initialize Thread & Pipeline
        self.thread = QThread()
        self.pipeline = TranslationPipeline(settings)
        self.pipeline.moveToThread(self.thread)

        self._save_persisted_settings(settings)
        
        # 3. Connect Pipeline Signals
        self.thread.started.connect(self.pipeline.run)
        self.pipeline.finished.connect(self.on_finished)
        self.pipeline.stage_changed.connect(self.on_stage_changed)
        self.pipeline.progress_updated.connect(self.on_progress)
        self.pipeline.log_message.connect(self.on_log_message)
        
        # Cleanup on finish
        self.pipeline.finished.connect(self.thread.quit)
        self.pipeline.finished.connect(self.pipeline.deleteLater)
        self.thread.finished.connect(self._cleanup_thread)
        self.thread.finished.connect(self.thread.deleteLater)
        
        # 4. Update UI State
        self.homeInterface.set_running(True)
        self.consoleInterface.clear()
        # Switch to console automatically to show progress? Maybe not, keep on home.
        
        # 5. Start
        self.thread.start()

    def _cleanup_thread(self):
        """Reset thread and pipeline references after cleanup."""
        try:
            self.thread = None
            self.pipeline = None
        except Exception:
            pass

    def closeEvent(self, event):
        try:
            self._save_persisted_settings(self._collect_persisted_settings())
        except Exception:
            pass
        super().closeEvent(event)

    def _collect_persisted_settings(self) -> dict:
        data = {}

        project_path = self.homeInterface.txt_path.text().strip()
        if project_path:
            data["project_path"] = project_path

        source_name = self.homeInterface.cmb_source.currentText()
        target_name = self.homeInterface.cmb_target.currentText()
        data["source_lang"] = self.homeInterface.source_languages.get(source_name, "auto")
        data["target_lang"] = self.homeInterface.target_languages.get(target_name, "tr")

        data["translate_notes"] = self.settingsInterface.chk_translate_notes.isChecked()
        data["translate_comments"] = self.settingsInterface.chk_translate_comments.isChecked()
        data["visustella_wordwrap"] = self.settingsInterface.chk_visustella_wordwrap.isChecked()
        data["auto_wordwrap"] = self.settingsInterface.chk_auto_wordwrap.isChecked()
        data["backup_enabled"] = self.settingsInterface.chk_backup.isChecked()
        data["use_cache"] = self.settingsInterface.chk_cache.isChecked()

        data["batch_size"] = self.settingsInterface.slider_batch_size.value()
        data["concurrent_requests"] = self.settingsInterface.slider_concurrent.value()

        data["use_multi_endpoint"] = self.settingsInterface.chk_multi_endpoint.isChecked()
        data["enable_lingva_fallback"] = self.settingsInterface.chk_lingva_fallback.isChecked()
        data["request_delay_ms"] = self.settingsInterface.slider_request_delay.value()
        data["request_timeout"] = self.settingsInterface.slider_timeout.value()
        data["max_retries"] = self.settingsInterface.slider_max_retries.value()

        data["use_glossary"] = self.settingsInterface.chk_glossary.isChecked()
        data["glossary_path"] = self.settingsInterface.glossary_path

        regex_text = self.settingsInterface.txt_regex.toPlainText()
        if regex_text:
            data["regex_blacklist"] = [line for line in regex_text.split("\n") if line.strip()]

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

    def stop_pipeline(self):
        if self.pipeline:
            self.pipeline.stop()
            self.on_log_message("warning", "Stopping...")

    def on_finished(self, success, message):
        self.homeInterface.set_running(False)
        self.homeInterface.update_status(message if success else f"Error: {message}")
        
        level = "success" if success else "error"
        self.on_log_message(level, message)

    def on_progress(self, current, total):
        if total > 0:
            percent = int((current / total) * 100)
            self.homeInterface.update_status(f"Processing... {percent}% ({current}/{total})", percent)
        else:
            self.homeInterface.update_status("Processing...", 0)

    def on_stage_changed(self, stage_val, message):
        self.homeInterface.update_status(message)
        self.on_log_message("info", f"Stage: {message}")

    def on_log_message(self, level, message):
        self.consoleInterface.log(level, message)
        
    def clear_cache(self):
        from src.core.cache import get_cache
        
        try:
            cache = get_cache()
            cache.clear()
            cache.save()
            msg = "Translation cache has been cleared."
            self.on_log_message("success", msg)
            
            InfoBar.success(
                title='Cache Cleared',
                content=msg,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                parent=self
            )
        except Exception as e:
            self.on_log_message("error", f"Failed to clear cache: {e}")

    def _open_patreon(self):
        """Open Patreon support page in browser."""
        import webbrowser
        webbrowser.open("https://www.patreon.com/cw/LordOfTurk")

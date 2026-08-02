import logging
import os
import shutil
import webbrowser
from typing import Any, Dict

from PyQt6.QtCore import QObject, QThread, Qt, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication, QFileDialog

from src.core.enums import PipelineStage
from src.core.translation_pipeline import TranslationPipeline
from src.utils.app_paths import get_cache_dir
from src.utils.paths import existing_resource_path
from src.backend.settings_backend import SettingsBackend


class AppBackend(QObject):
    """QObject backend bridge connecting QML UI to TranslationPipeline worker thread."""

    isRunningChanged = pyqtSignal()
    progressChanged = pyqtSignal()
    stageChanged = pyqtSignal(str)
    logEmitted = pyqtSignal(str, str)  # level, text
    infoNotice = pyqtSignal(str, str, str)  # notice_type, title, message
    finished = pyqtSignal(bool, str)  # success, summary

    def __init__(self, settings_backend: SettingsBackend, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.settings_backend = settings_backend

        self._thread: QThread | None = None
        self._pipeline: TranslationPipeline | None = None
        self._is_running: bool = False

        self._progress_current: int = 0
        self._progress_total: int = 0
        self._progress_text: str = "Ready"
        self._stage_text: str = "Idle"

        self._project_path: str = ""

    # --- Properties ---

    @pyqtProperty(bool, notify=isRunningChanged)
    def isRunning(self) -> bool:
        return self._is_running

    @pyqtProperty(str, constant=True)
    def appIconUrl(self) -> str:
        p = existing_resource_path("icon.png", "icon.ico")
        if p:
            return QUrl.fromLocalFile(p).toString()
        return ""

    @pyqtProperty(int, notify=progressChanged)
    def progressCurrent(self) -> int:
        return self._progress_current

    @pyqtProperty(int, notify=progressChanged)
    def progressTotal(self) -> int:
        return self._progress_total

    @pyqtProperty(str, notify=progressChanged)
    def progressText(self) -> str:
        return self._progress_text

    @pyqtProperty(str, notify=stageChanged)
    def stageText(self) -> str:
        return self._stage_text

    @pyqtProperty(str, notify=isRunningChanged)
    def projectPath(self) -> str:
        return self._project_path

    @projectPath.setter
    def projectPath(self, val: str) -> None:
        if self._project_path != val:
            self._project_path = val
            self.isRunningChanged.emit()

    # --- Slots ---

    @pyqtSlot(str)
    def setProjectPath(self, path: str) -> None:
        self.projectPath = path

    @pyqtSlot(result=str)
    def selectProjectDirectory(self) -> str:
        folder = QFileDialog.getExistingDirectory(
            None, "Select RPG Maker Project Directory", self._project_path or ""
        )
        if folder:
            self.projectPath = folder
            return folder
        return ""

    @pyqtSlot(result=str)
    def selectFontFile(self) -> str:
        file_path, _ = QFileDialog.getOpenFileName(
            None, "Select Custom Font File", "", "Font Files (*.ttf *.otf *.woff *.woff2);;All Files (*)"
        )
        if file_path:
            self.settings_backend.fontPath = file_path
            return file_path
        return ""

    @pyqtSlot(result=str)
    def selectGlossaryFile(self) -> str:
        file_path, _ = QFileDialog.getOpenFileName(
            None, "Select Glossary Dictionary File", "", "JSON Files (*.json);;CSV Files (*.csv);;All Files (*)"
        )
        if file_path:
            self.settings_backend.glossaryPath = file_path
            self.settings_backend.useGlossary = True
            return file_path
        return ""

    @pyqtSlot(result=str)
    def selectExportFile(self) -> str:
        file_path, _ = QFileDialog.getSaveFileName(
            None, "Export Translations Sidecar", "", "JSON Sidecar (*.json);;PO Files (*.po);;CSV Files (*.csv)"
        )
        return file_path or ""

    @pyqtSlot(result=str)
    def selectImportFile(self) -> str:
        file_path, _ = QFileDialog.getOpenFileName(
            None, "Import Translations Sidecar", "", "JSON/PO/CSV Files (*.json *.po *.csv);;All Files (*)"
        )
        return file_path or ""

    @pyqtSlot(str)
    def openUrl(self, url: str) -> None:
        try:
            webbrowser.open(url)
        except Exception as e:
            self.logger.warning(f"Could not open URL {url}: {e}")

    @pyqtSlot()
    def clearCache(self) -> None:
        try:
            cache_dir = get_cache_dir()
            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir)
                os.makedirs(cache_dir, exist_ok=True)
                self.infoNotice.emit("success", "Cache Cleared", "Translation cache cleared successfully.")
            else:
                self.infoNotice.emit("info", "Cache Empty", "No active cache directory found.")
        except Exception as e:
            self.infoNotice.emit("error", "Clear Cache Failed", f"Failed to clear cache: {e}")

    @pyqtSlot()
    def startPipeline(self) -> None:
        if self._is_running:
            return
        if not self._project_path or not os.path.exists(self._project_path):
            self.infoNotice.emit("warning", "Invalid Path", "Please select a valid RPG Maker project directory.")
            return

        settings = self.settings_backend.get_dict()
        settings["project_path"] = self._project_path

        self._is_running = True
        self.isRunningChanged.emit()

        self._thread = QThread()
        self._pipeline = TranslationPipeline(settings)
        self._pipeline.moveToThread(self._thread)

        self._thread.started.connect(self._pipeline.run)
        self._pipeline.finished.connect(self._on_pipeline_finished, Qt.ConnectionType.QueuedConnection)
        self._pipeline.stage_changed.connect(self._on_stage_changed, Qt.ConnectionType.QueuedConnection)
        self._pipeline.progress_updated.connect(self._on_progress_updated, Qt.ConnectionType.QueuedConnection)
        self._pipeline.log_message.connect(self._on_log_message, Qt.ConnectionType.QueuedConnection)
        self._pipeline.finished.connect(self._thread.quit, Qt.ConnectionType.QueuedConnection)
        self._pipeline.finished.connect(self._pipeline.deleteLater, Qt.ConnectionType.QueuedConnection)
        self._thread.finished.connect(self._cleanup_thread, Qt.ConnectionType.QueuedConnection)
        self._thread.finished.connect(self._thread.deleteLater, Qt.ConnectionType.QueuedConnection)

        self._thread.start()

    @pyqtSlot()
    def stopPipeline(self) -> None:
        if self._pipeline:
            self._pipeline.stop()
            self.logEmitted.emit("WARNING", "Stop requested by user...")

    # --- Signal Handlers ---

    def _on_stage_changed(self, stage_val: Any, _message: str = "") -> None:
        """Handle stage_changed(str, str) signal from pipeline."""
        if isinstance(stage_val, PipelineStage):
            self._stage_text = stage_val.value.capitalize()
        else:
            self._stage_text = str(stage_val).capitalize()
        self.stageChanged.emit(self._stage_text)

    def _on_progress_updated(self, current: int, total: int, text: str) -> None:
        self._progress_current = current
        self._progress_total = total
        self._progress_text = text
        self.progressChanged.emit()

    def _on_log_message(self, level: str, msg: str) -> None:
        self.logEmitted.emit(level.upper(), msg)

    def _on_pipeline_finished(self, success: bool, summary: str) -> None:
        self._is_running = False
        self.isRunningChanged.emit()
        if success:
            self.infoNotice.emit("success", "Translation Complete", summary or "Project localized successfully.")
        else:
            self.infoNotice.emit("error", "Translation Failed", summary or "Errors occurred during pipeline execution.")
        self.finished.emit(success, summary)

    def _cleanup_thread(self) -> None:
        self._thread = None
        self._pipeline = None

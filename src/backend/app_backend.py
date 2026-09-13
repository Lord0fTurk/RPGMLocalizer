import logging
import os
import shutil
import sys
import webbrowser
from typing import Any, Dict

from PyQt6.QtCore import QObject, QThread, Qt, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QFileDialog, QSystemTrayIcon, QStyle

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

        self._project_path: str = str(self.settings_backend.projectPath or "")
        self._tray_icon: QSystemTrayIcon | None = None
        self._init_tray()

        # Connect application lifecycle for zero-dangling graceful shutdown
        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.shutdown)

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
            self.settings_backend.projectPath = val
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
    def openProjectFolder(self) -> None:
        """Open the active project directory in the OS file manager."""
        if not self._project_path or not os.path.exists(self._project_path):
            return
        try:
            if os.name == 'nt':
                os.startfile(self._project_path)
            elif sys.platform == 'darwin':
                import subprocess
                subprocess.Popen(['open', self._project_path])
            else:
                import subprocess
                subprocess.Popen(['xdg-open', self._project_path])
        except Exception as exc:
            self.logger.warning(f"Could not open project directory {self._project_path}: {exc}")

    @pyqtSlot()
    def clearCache(self) -> None:
        try:
            from src.utils.app_paths import get_project_id
            project_id = get_project_id(self._project_path) if self._project_path else None
            cache_dir = get_cache_dir(project_id=project_id)
            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir)
                os.makedirs(cache_dir, exist_ok=True)
                msg = f"Translation cache cleared for [{project_id}]." if project_id else "Translation cache cleared successfully."
                self.infoNotice.emit("success", "Cache Cleared", msg)
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

    def _init_tray(self) -> None:
        """Initialize system tray icon for desktop notifications if a real QApplication is running."""
        self._tray_icon = None
        try:
            app = QApplication.instance()
            if app and isinstance(app, QApplication) and QSystemTrayIcon.isSystemTrayAvailable():
                self._tray_icon = QSystemTrayIcon(self)
                if not app.windowIcon().isNull():
                    self._tray_icon.setIcon(app.windowIcon())
                else:
                    p = existing_resource_path("icon.png", "icon.ico")
                    if p and os.path.exists(p):
                        self._tray_icon.setIcon(QIcon(p))
                    else:
                        self._tray_icon.setIcon(app.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation))
                self._tray_icon.show()
        except Exception as exc:
            self.logger.debug(f"Tray initialization skipped: {exc}")
            self._tray_icon = None

    def _show_system_notification(self, title: str, message: str, success: bool = True) -> None:
        """Show native OS desktop notification, play chime, and alert taskbar."""
        # 1. Desktop notification via QSystemTrayIcon
        try:
            if self._tray_icon and self._tray_icon.isVisible():
                icon = QSystemTrayIcon.MessageIcon.Information if success else QSystemTrayIcon.MessageIcon.Critical
                self._tray_icon.showMessage(title, message, icon, 5000)
        except Exception as e:
            self.logger.debug(f"Tray showMessage failed: {e}")

        # 2. Audio Chime
        try:
            if os.name == 'nt':
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK if success else winsound.MB_ICONHAND)
            else:
                QApplication.beep()
        except Exception:
            pass

        # 3. Flash taskbar icon to get user's attention
        try:
            app = QApplication.instance()
            if app and isinstance(app, QApplication):
                app.alert(None, 0)
        except Exception:
            pass

    def _on_pipeline_finished(self, success: bool, summary: str) -> None:
        self._is_running = False
        self.isRunningChanged.emit()

        title = "Translation Completed" if success else "Translation Failed"
        message = summary or ("Project successfully translated." if success else "An error occurred during translation.")
        self._show_system_notification(title, message, success=success)

        if success:
            self.infoNotice.emit("success", title, message)
        else:
            self.infoNotice.emit("error", title, message)
        self.finished.emit(success, summary)

    def _cleanup_thread(self) -> None:
        self._thread = None
        self._pipeline = None

    @pyqtSlot()
    def shutdown(self, timeout_ms: int = 3000) -> None:
        """Gracefully stop any active pipeline and terminate the worker thread safely."""
        if self._pipeline:
            self._pipeline.stop()
        if self._thread and self._thread.isRunning():
            self.logger.info("Graceful shutdown: waiting for worker thread...")
            self._thread.quit()
            if not self._thread.wait(timeout_ms):
                self.logger.warning(
                    f"Worker thread did not stop within {timeout_ms} ms; terminating forcibly."
                )
                self._thread.terminate()
                self._thread.wait(500)
        self._cleanup_thread()

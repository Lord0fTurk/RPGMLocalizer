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
from src.utils.paths import existing_resource_path, local_path_from_url
from src.backend.settings_backend import SettingsBackend

try:
    from version import VERSION
except ImportError:
    VERSION = "1.0.0"


class AppBackend(QObject):
    """QObject backend bridge connecting QML UI to TranslationPipeline worker thread."""

    isRunningChanged = pyqtSignal()
    projectPathChanged = pyqtSignal(str)
    detectedEngineChanged = pyqtSignal(str)
    detectedEngineCodeChanged = pyqtSignal(str)
    progressChanged = pyqtSignal()
    stageChanged = pyqtSignal(str)
    logEmitted = pyqtSignal(str, str)  # level, text
    infoNotice = pyqtSignal(str, str, str)  # notice_type, title, message
    finished = pyqtSignal(bool, str)  # success, summary
    cacheAboutToBeCleared = pyqtSignal()
    cacheCleared = pyqtSignal()

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
        self._detected_engine, self._detected_engine_code = self._detect_engine_type(self._project_path)
        self._tray_icon: QSystemTrayIcon | None = None
        self._init_tray()

        # Connect application lifecycle for zero-dangling graceful shutdown
        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.shutdown)

    def _detect_engine_type(self, path: str) -> tuple[str, str]:
        if not path or not os.path.isdir(path):
            return "", ""
        try:
            from src.core.engine_profiler import EngineProfiler, RpgMakerEngine
            profiler = EngineProfiler(path)
            profile = profiler.detect_engine()
            names = {
                RpgMakerEngine.MV: "RPG Maker MV",
                RpgMakerEngine.MZ: "RPG Maker MZ",
                RpgMakerEngine.VX_ACE: "RPG Maker VX Ace",
                RpgMakerEngine.VX: "RPG Maker VX",
                RpgMakerEngine.XP: "RPG Maker XP",
                RpgMakerEngine.WOLF_RPG: "WOLF RPG Editor",
                RpgMakerEngine.UNKNOWN: "",
            }
            return names.get(profile.engine, ""), profile.engine.value
        except Exception as e:
            self.logger.debug(f"Engine detection failed: {e}")
            return "", ""

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

    @pyqtProperty(str, constant=True)
    def appVersion(self) -> str:
        return f"v{VERSION}"

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

    @pyqtProperty(str, notify=projectPathChanged)
    def projectPath(self) -> str:
        return self._project_path

    @projectPath.setter
    def projectPath(self, val: str) -> None:
        if self._project_path != val:
            self._project_path = val
            self.settings_backend.projectPath = val
            self._detected_engine, self._detected_engine_code = self._detect_engine_type(val)
            self.projectPathChanged.emit(val)
            self.detectedEngineChanged.emit(self._detected_engine)
            self.detectedEngineCodeChanged.emit(self._detected_engine_code)
            self.isRunningChanged.emit()

    @pyqtProperty(str, notify=detectedEngineChanged)
    def detectedEngine(self) -> str:
        return self._detected_engine

    @pyqtProperty(str, notify=detectedEngineCodeChanged)
    def detectedEngineCode(self) -> str:
        return self._detected_engine_code

    # --- Slots ---

    @pyqtSlot()
    def clearProjectPath(self) -> None:
        self.projectPath = ""

    @pyqtSlot(str)
    def copyToClipboard(self, text: str) -> None:
        try:
            app = QApplication.instance()
            if app:
                cb = app.clipboard()
                if cb:
                    cb.setText(text)
        except Exception as exc:
            self.logger.warning(f"Failed to copy to clipboard: {exc}")

    @pyqtSlot(str)
    def setProjectPath(self, path: str) -> None:
        if not path:
            self.projectPath = ""
            return
        cleaned = local_path_from_url(path)
        if os.path.isfile(cleaned):
            cleaned = os.path.dirname(cleaned)
        self.projectPath = cleaned

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
            import gc
            import stat
            import time
            from src.core.cache import reset_cache
            from src.utils.app_paths import get_project_id

            # 1. Notify listeners (EditorBackend, etc.) to close SQLite DB connections & file locks
            self.cacheAboutToBeCleared.emit()

            # 2. Direct hook fallback if editor_backend is registered
            if hasattr(self, "editor_backend") and self.editor_backend:
                try:
                    self.editor_backend.closeStore()
                except Exception as exc:
                    self.logger.warning(f"Error closing editor store: {exc}")

            # 3. Reset the global translation cache singleton
            reset_cache()

            # 4. Force garbage collection to finalize any unreferenced file/sqlite handles
            gc.collect()

            project_id = get_project_id(self._project_path) if self._project_path else None
            cache_dir = get_cache_dir(project_id=project_id)
            cache_dir_str = str(cache_dir)

            if os.path.exists(cache_dir_str):
                def _handle_remove_readonly(func, path, exc):
                    try:
                        os.chmod(path, stat.S_IWRITE)
                        func(path)
                    except Exception:
                        pass

                deleted = False
                last_err = None
                for attempt in range(4):
                    try:
                        try:
                            shutil.rmtree(cache_dir_str, onexc=_handle_remove_readonly)
                        except TypeError:
                            shutil.rmtree(cache_dir_str, onerror=_handle_remove_readonly)
                        deleted = True
                        break
                    except (PermissionError, OSError) as exc:
                        last_err = exc
                        time.sleep(0.15)
                        gc.collect()

                if not deleted and last_err:
                    raise last_err

                os.makedirs(cache_dir_str, exist_ok=True)
                msg = f"Translation cache cleared for [{project_id}]." if project_id else "Translation cache cleared successfully."
                self.cacheCleared.emit()
                self.infoNotice.emit("success", "Cache Cleared", msg)
            else:
                self.cacheCleared.emit()
                self.infoNotice.emit("info", "Cache Empty", "No active cache directory found.")
        except Exception as e:
            self.logger.exception(f"Failed to clear cache: {e}")
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

        # completionDialog handles the primary user-facing result dialog.
        # Avoid emitting infoNotice("error") which spawns a redundant overlapping noticePopup.
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

import os
import sys
import threading

from src.utils.paths import existing_resource_path
from src.utils.qt_bootstrap import (
    apply_qt_application_attributes,
    bootstrap_qt_environment,
    emit_runtime_diagnostics,
)

bootstrap_qt_environment()

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QIcon
from PyQt6.QtQml import QQmlApplicationEngine
from PyQt6.QtWidgets import QApplication

from src.backend.app_backend import AppBackend
from src.backend.settings_backend import SettingsBackend


def main() -> None:
    apply_qt_application_attributes()

    # QApplication (not QGuiApplication) is required: AppBackend's file/folder
    # pickers use QFileDialog, a QtWidgets class that needs a real QApplication.
    app = QApplication(sys.argv)

    icon_path = existing_resource_path("icon.png", "icon.ico")
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    def _force_exit() -> None:
        non_daemon = [
            t for t in threading.enumerate()
            if t.is_alive() and not t.daemon and t is not threading.main_thread()
        ]
        if non_daemon:
            os._exit(0)

    app.aboutToQuit.connect(_force_exit)

    settings_backend = SettingsBackend()
    app_backend = AppBackend(settings_backend)

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("appBackend", app_backend)
    engine.rootContext().setContextProperty("settingsBackend", settings_backend)

    qml_file = existing_resource_path("src/gui/qml/Main.qml")
    if not qml_file or not os.path.exists(qml_file):
        qml_file = os.path.join(os.path.dirname(__file__), "src", "gui", "qml", "Main.qml")

    engine.load(QUrl.fromLocalFile(os.path.abspath(qml_file)))

    if not engine.rootObjects():
        sys.exit(-1)

    emit_runtime_diagnostics(app_backend._on_log_message)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

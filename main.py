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

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme

from src.ui.main_window import MainWindow


def main() -> None:
    apply_qt_application_attributes()

    from qfluentwidgets import Theme, setTheme, setThemeColor
    from PyQt6.QtGui import QPalette, QColor

    setThemeColor('#00b4d8')  # Turkuaz accent
    setTheme(Theme.DARK)

    app = QApplication(sys.argv)

    # Force a dark application palette as a safety net against system
    # theme palette leaks (custom/high-contrast Windows themes can inject
    # all-white colours even through Fusion).  qfluentwidgets and our QSS
    # handle the real styling, but this prevents edge-case white flashes.
    dark = QPalette()
    dark.setColor(QPalette.ColorRole.Window, QColor("#0a1628"))
    dark.setColor(QPalette.ColorRole.WindowText, QColor("#d6e6ff"))
    dark.setColor(QPalette.ColorRole.Base, QColor("#131f35"))
    dark.setColor(QPalette.ColorRole.AlternateBase, QColor("#1a2d4a"))
    dark.setColor(QPalette.ColorRole.Text, QColor("#d6e6ff"))
    dark.setColor(QPalette.ColorRole.Button, QColor("#1a2d4a"))
    dark.setColor(QPalette.ColorRole.ButtonText, QColor("#d6e6ff"))
    dark.setColor(QPalette.ColorRole.BrightText, QColor("#ff5252"))
    dark.setColor(QPalette.ColorRole.Highlight, QColor("#00b4d8"))
    dark.setColor(QPalette.ColorRole.HighlightedText, QColor("#0a1628"))
    dark.setColor(QPalette.ColorRole.Link, QColor("#48cae4"))
    dark.setColor(QPalette.ColorRole.PlaceholderText, QColor("#5a7090"))
    app.setPalette(dark)

    icon_path = existing_resource_path("icon.png", "icon.ico")
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    # Safety net: force-kill the process if background threads (ThreadPoolExecutor
    # workers, stuck QThreads, etc.) prevent a clean exit after the event loop ends.
    def _force_exit() -> None:
        non_daemon = [
            t for t in threading.enumerate()
            if t.is_alive() and not t.daemon and t is not threading.main_thread()
        ]
        if non_daemon:
            os._exit(0)

    app.aboutToQuit.connect(_force_exit)

    window = MainWindow()
    emit_runtime_diagnostics(window.on_log_message)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

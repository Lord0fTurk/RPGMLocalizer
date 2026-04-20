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

    # Explicitly disable system theme/accent color inheritance to prevent UI corruption
    # on custom or high-contrast Windows themes.
    from qfluentwidgets import Theme, setTheme, setThemeColor
    
    # Set a consistent accent color (Fluent Blue) instead of relying on Windows System Accent
    setThemeColor('#0078D4')
    
    # Hard-code Dark theme to ensure consistency
    setTheme(Theme.DARK)

    app = QApplication(sys.argv)

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

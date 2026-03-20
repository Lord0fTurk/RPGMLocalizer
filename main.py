import sys

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

    # Set theme BEFORE creating any widgets to prevent white screen on some systems
    setTheme(Theme.DARK)

    app = QApplication(sys.argv)

    icon_path = existing_resource_path("icon.png", "icon.ico")
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    emit_runtime_diagnostics(window.on_log_message)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

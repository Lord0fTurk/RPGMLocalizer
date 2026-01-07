import os
os.environ['QT_API'] = 'pyqt6'
import sys
from PyQt6.QtWidgets import QApplication
from qfluentwidgets import setTheme, Theme
from src.ui.main_window import MainWindow

def main():
    # Set theme BEFORE creating any widgets to prevent white screen on some systems
    setTheme(Theme.DARK)
    
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtGui import QFont
from qfluentwidgets import TextEdit, StrongBodyLabel

class ConsoleLog(QWidget):
    """
    A simple console log viewer using Fluent Widgets.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.vBoxLayout = QVBoxLayout(self)
        
        self.label = StrongBodyLabel("Process Log", self)
        self.textEdit = TextEdit(self)
        self.textEdit.setReadOnly(True)
        self.textEdit.setFont(QFont("Consolas", 10))
        
        self.vBoxLayout.addWidget(self.label)
        self.vBoxLayout.addWidget(self.textEdit)
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        
    def log(self, level: str, message: str):
        """Append a log message with color."""
        # Fluent TextEdit supports HTML
        colors = {
            "error": "#ff5252",
            "warning": "#ffd740",
            "success": "#69f0ae",
            "info": "#ffffff" # Default for dark theme
        }
        color = colors.get(level, "#ffffff")
        formatted = f'<span style="color:{color};">[{level.upper()}] {message}</span>'
        self.textEdit.append(formatted)
    
    def clear(self):
        self.textEdit.clear()

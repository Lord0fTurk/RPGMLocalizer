from datetime import datetime
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont, QTextCursor
from qfluentwidgets import TextEdit, StrongBodyLabel


class ConsoleLog(QWidget):
    """
    A buffered console log viewer.

    Batches log signals via QTimer and uses plain-text block append
    (not HTML) to avoid the overhead of QTextEdit's HTML renderer.
    ``MAX_LINES`` is kept moderate to keep ``blockCount()`` trimming cheap.
    """

    FLUSH_INTERVAL_MS = 200
    MAX_LINES = 300

    _COLORS: dict[str, str] = {
        "error":   "#e74c3c",
        "warning": "#f0a500",
        "success": "#2ecc71",
        "info":    "#7b93b5",
    }

    def __init__(self, parent=None, show_label=True):
        super().__init__(parent)
        self.setMinimumHeight(120)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        if show_label:
            self.label = StrongBodyLabel("Activity Log", self)
            layout.addWidget(self.label)

        self.textEdit = TextEdit(self)
        self.textEdit.setReadOnly(True)
        font = QFont()
        font.setFamilies(["Consolas", "SF Mono", "Liberation Mono", "DejaVu Sans Mono", "monospace"])
        font.setPointSize(10)
        self.textEdit.setFont(font)
        layout.addWidget(self.textEdit)

        self._pending: list[str] = []

        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(self.FLUSH_INTERVAL_MS)
        self._flush_timer.timeout.connect(self._flush_pending)
        self._flush_timer.start()

    def log(self, level: str, message: str) -> None:
        color = self._COLORS.get(level, "#e0e0e0")
        ts = datetime.now().strftime("%H:%M:%S")
        safe = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self._pending.append(
            f'<span style="color:{color};">[{ts}] {safe}</span>'
        )

    def clear(self) -> None:
        self._pending.clear()
        self.textEdit.clear()

    def _flush_pending(self) -> None:
        if not self._pending:
            return
        batch = "<br>".join(self._pending)
        self._pending.clear()

        self._trim()
        # Use insertPlainText + moveCursor instead of append() to avoid
        # full-document HTML re-render on every flush.
        cursor = self.textEdit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(batch + "<br>")
        # Scroll to bottom
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.textEdit.setTextCursor(cursor)

    def _trim(self) -> None:
        doc = self.textEdit.document()
        if doc.blockCount() <= self.MAX_LINES:
            return
        excess = doc.blockCount() - self.MAX_LINES
        cursor = self.textEdit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        for _ in range(excess):
            cursor.movePosition(QTextCursor.MoveOperation.Down,
                                QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        self.textEdit.setTextCursor(cursor)

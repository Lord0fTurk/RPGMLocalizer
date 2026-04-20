from datetime import datetime
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont, QTextCursor
from qfluentwidgets import TextEdit, StrongBodyLabel

class ConsoleLog(QWidget):
    """
    A buffered console log viewer using Fluent Widgets.

    Log messages are queued and flushed to the QTextEdit in batches via a
    QTimer (every FLUSH_INTERVAL_MS ms). This prevents the main thread from
    freezing when hundreds of log signals arrive in rapid succession during a
    translation run, because Qt's event queue is no longer flooded with
    individual append+repaint cycles.
    """

    FLUSH_INTERVAL_MS = 150   # Batch flush period (ms) — tune lower for snappier logs
    MAX_LINES = 600           # Hard cap on document block count to prevent O(n) reflow

    _COLORS: dict[str, str] = {
        "error":   "#ff5252",
        "warning": "#ffd740",
        "success": "#69f0ae",
        "info":    "#e0e0e0",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)

        self.label = StrongBodyLabel("Activity Log", self)
        self.textEdit = TextEdit(self)
        self.textEdit.setReadOnly(True)
        font = QFont()
        font.setFamilies(["Consolas", "SF Mono", "Liberation Mono", "DejaVu Sans Mono", "monospace"])
        font.setPointSize(10)
        self.textEdit.setFont(font)

        self.vBoxLayout.addWidget(self.label)
        self.vBoxLayout.addWidget(self.textEdit)

        self._pending: list[str] = []

        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(self.FLUSH_INTERVAL_MS)
        self._flush_timer.timeout.connect(self._flush_pending)
        self._flush_timer.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log(self, level: str, message: str) -> None:
        """Queue a coloured log line. Actual rendering happens on the next timer tick."""
        color = self._COLORS.get(level, "#e0e0e0")
        timestamp = datetime.now().strftime("%H:%M:%S")
        # Escape any '<' / '>' in the message so they don't break the HTML
        safe_msg = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self._pending.append(
            f'<span style="color:{color};">[{timestamp}] [{level.upper()}] {safe_msg}</span>'
        )

    def clear(self) -> None:
        self._pending.clear()
        self.textEdit.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _flush_pending(self) -> None:
        """Flush queued log lines to the QTextEdit in a single operation."""
        if not self._pending:
            return

        batch_html = "<br>".join(self._pending)
        self._pending.clear()

        self._trim_document()
        self.textEdit.append(batch_html)

    def _trim_document(self) -> None:
        """Remove oldest lines when the document exceeds MAX_LINES blocks."""
        doc = self.textEdit.document()
        excess = doc.blockCount() - self.MAX_LINES
        if excess <= 0:
            return

        cursor = self.textEdit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        for _ in range(excess):
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                                QTextCursor.MoveMode.KeepAnchor)
            cursor.movePosition(QTextCursor.MoveOperation.NextCharacter,
                                QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
        self.textEdit.setTextCursor(cursor)

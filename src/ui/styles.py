"""Dark Glass Ocean theme — Turkuaz / Mavi / Koyu Cam tonlari."""
from qfluentwidgets import setThemeColor

def apply_theme():
    """Apply the Ocean Glass colour palette globally."""
    setThemeColor('#00b4d8')

# Lazim oldugunda cagrilabilir; main.py dogrudan setThemeColor kullaniyor.
# Bu modul yalnizca QSS sabitini disari acar.

THEME_QSS = """
/* ========================================================================
   Base / Root — deep ocean
   ======================================================================== */

QWidget {
    background-color: #0a1628;
    color: #d6e6ff;
    font-family: "Segoe UI", -apple-system, "Noto Sans", "Liberation Sans", sans-serif;
    font-size: 13px;
}

/* ========================================================================
   Scroll areas — transparent overlay (glass effect)
   ======================================================================== */

QScrollArea#SettingsInterface,
QScrollArea#ExportInterface,
QScrollArea#AboutInterface,
QScrollArea#GlossaryInterface {
    background-color: transparent;
    border: none;
}

QScrollArea#SettingsInterface > QWidget > QWidget,
QScrollArea#ExportInterface > QWidget > QWidget,
QScrollArea#AboutInterface > QWidget > QWidget,
QScrollArea#GlossaryInterface > QWidget > QWidget {
    background-color: transparent;
}

/* ========================================================================
   Tab widget / tab bar — frosted glass tabs
   ======================================================================== */

QTabWidget::pane {
    border: none;
    background-color: #0a1628;
}

QTabBar::tab {
    background-color: rgba(17, 34, 64, 0.7);
    color: #7b93b5;
    border: 1px solid rgba(30, 58, 95, 0.5);
    border-bottom: none;
    padding: 8px 20px;
    margin-right: 2px;
    border-radius: 8px 8px 0 0;
    font-weight: 500;
}

QTabBar::tab:selected {
    background-color: rgba(26, 51, 86, 0.85);
    color: #d6e6ff;
    border-bottom: 2px solid #00b4d8;
    border-color: rgba(30, 58, 95, 0.7);
    border-bottom: 2px solid #00b4d8;
}

QTabBar::tab:hover:!selected {
    background-color: rgba(22, 42, 70, 0.8);
    color: #a0c4f0;
}

/* ========================================================================
   Splitter — glass edge
   ======================================================================== */

QSplitter::handle {
    background-color: rgba(30, 58, 95, 0.4);
    width: 1px;
}

QSplitter::handle:hover {
    background-color: #00b4d8;
}

/* ========================================================================
   Tool tips — floating glass card
   ======================================================================== */

QToolTip {
    background-color: rgba(20, 40, 70, 0.95);
    color: #d6e6ff;
    border: 1px solid rgba(30, 58, 95, 0.6);
    border-radius: 6px;
    padding: 7px 12px;
    font-size: 12px;
}

/* ========================================================================
   Selection highlight — turkuaz glow
   ======================================================================== */

QTextEdit, QLineEdit, QPlainTextEdit {
    selection-background-color: rgba(0, 180, 216, 0.3);
    selection-color: #e0f0ff;
}

/* ========================================================================
   Scroll bar — thin glass
   ======================================================================== */

QScrollBar:vertical {
    background-color: transparent;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background-color: rgba(30, 58, 95, 0.5);
    border-radius: 4px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: rgba(0, 180, 216, 0.4);
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background-color: transparent;
    height: 8px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background-color: rgba(30, 58, 95, 0.5);
    border-radius: 4px;
    min-width: 30px;
}

QScrollBar::handle:horizontal:hover {
    background-color: rgba(0, 180, 216, 0.4);
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ========================================================================
   Console log — dark glass panel
   ======================================================================== */

QTextEdit#consoleOutput {
    background-color: rgba(10, 22, 40, 0.9);
    color: #c8ddf0;
    border: 1px solid rgba(30, 58, 95, 0.5);
    border-radius: 8px;
    font-family: "Cascadia Code", "Consolas", "SF Mono", "Liberation Mono",
                 "DejaVu Sans Mono", monospace;
    font-size: 12px;
    padding: 10px;
    selection-background-color: rgba(0, 180, 216, 0.25);
}
"""

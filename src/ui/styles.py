DARK_THEME = """
QWidget {
    background-color: #1e1e1e;
    color: #ffffff;
    font-family: 'Segoe UI', sans-serif;
    font-size: 14px;
}

QGroupBox {
    border: 1px solid #3d3d3d;
    border-radius: 6px;
    margin-top: 12px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #00acc1;
    font-weight: bold;
}

QLineEdit {
    background-color: #2d2d2d;
    border: 1px solid #3d3d3d;
    border-radius: 4px;
    padding: 5px;
    color: #fff;
    selection-background-color: #00acc1;
}

QPushButton {
    background-color: #00acc1;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #00bcd4;
}

QPushButton:pressed {
    background-color: #0097a7;
}

QPushButton:disabled {
    background-color: #444;
    color: #888;
}

QProgressBar {
    border: 1px solid #3d3d3d;
    border-radius: 4px;
    text-align: center;
    background-color: #2d2d2d;
}

QProgressBar::chunk {
    background-color: #00acc1;
    width: 10px;
}

QTextEdit {
    background-color: #1e1e1e;
    border: 1px solid #3d3d3d;
    font-family: 'Consolas', monospace;
    font-size: 12px;
}
"""

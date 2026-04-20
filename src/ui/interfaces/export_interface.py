from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFileDialog, QHBoxLayout
from qfluentwidgets import (ScrollArea, SettingCardGroup, PushSettingCard, FluentIcon as FIF, PrimaryPushButton, SwitchSettingCard)
from PyQt6.QtCore import Qt, pyqtSignal as Signal

class ExportInterface(ScrollArea):
    """
    Interface for Exporting and Importing translations.
    """
    start_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ExportInterface")
        self.scrollWidget = QWidget()
        self.expandLayout = QVBoxLayout(self.scrollWidget)
        
        self.export_path = ""
        self.import_path = ""

        # Overview note
        self.hintGroup = SettingCardGroup("Transfer", self.scrollWidget)
        self.card_hint = PushSettingCard(
            "Choose file",
            FIF.INFO,
            "CSV for editing, JSON for round-trip",
            "Export translated text or import edited results.",
            self.hintGroup
        )
        self.hintGroup.addSettingCard(self.card_hint)

        # Export Group
        self.exportGroup = SettingCardGroup("Export", self.scrollWidget)
        
        self.card_export = PushSettingCard(
            "Select Output",
            FIF.SHARE,
            "Export to CSV/JSON",
            "Write extracted text to a file.",
            self.exportGroup
        )
        self.card_export.clicked.connect(self._select_export_path)
        
        self.chk_export_only = SwitchSettingCard(
            FIF.SAVE,
            "Export only",
            "Extract text without writing back to the game.",
            parent=self.exportGroup
        )
        self.chk_export_only.setChecked(True)
        
        self.chk_distinct_export = SwitchSettingCard(
            FIF.DOCUMENT,
            "Distinct entries only",
            "Group identical strings to reduce translator workload.",
            parent=self.exportGroup
        )
        
        self.exportGroup.addSettingCard(self.card_export)
        self.exportGroup.addSettingCard(self.chk_export_only)
        self.exportGroup.addSettingCard(self.chk_distinct_export)
        
        # Import Group
        self.importGroup = SettingCardGroup("Import", self.scrollWidget)
        
        self.card_import = PushSettingCard(
            "Select Input",
            FIF.DOWNLOAD,
            "Import from CSV/JSON",
            "Apply edited translations back to the game.",
            self.importGroup
        )
        self.card_import.clicked.connect(self._select_import_path)
        
        self.importGroup.addSettingCard(self.card_import)

        # Action Group
        self.actionGroup = SettingCardGroup("Action", self.scrollWidget)
        self.btn_execute = PrimaryPushButton("Execute Transfer", self.scrollWidget, FIF.PLAY)
        self.btn_execute.clicked.connect(self._handle_execute_click)
        
        # Add local reference to MainWindow to receive finish signals (if set)
        self._is_running = False
        
        # Layout
        self.expandLayout.addWidget(self.hintGroup)
        self.expandLayout.addWidget(self.exportGroup)
        self.expandLayout.addWidget(self.importGroup)
        self.expandLayout.addSpacing(20)
        self.expandLayout.addWidget(self.btn_execute)
        self.expandLayout.addStretch(1)
        
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.setStyleSheet("QWidget{background-color: transparent;}")
        
    def _handle_execute_click(self):
        """Disable button and start pipeline."""
        self.set_processing_state(True)
        self.start_requested.emit()

    def set_processing_state(self, is_running: bool):
        """Update button state to show/hide loading indicator."""
        self._is_running = is_running
        self.btn_execute.setEnabled(not is_running)
        # Using qfluentwidgets' internal loading state if supported or custom text
        if is_running:
            self.btn_execute.setText("Processing...")
            # If the button had an icon, we can clear it or change to a spinner
        else:
            self.btn_execute.setText("Execute Transfer")
            self.btn_execute.setIcon(FIF.PLAY)

    def _select_export_path(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Translations", "translations.csv", "CSV Files (*.csv);;JSON Files (*.json)"
        )
        if path:
            self.export_path = path
            self.card_export.setContent(path)
            
    def _select_import_path(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Translations", "", "CSV Files (*.csv);;JSON Files (*.json)"
        )
        if path:
            self.import_path = path
            self.card_import.setContent(path)

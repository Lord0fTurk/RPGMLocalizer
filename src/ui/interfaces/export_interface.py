from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFileDialog
from qfluentwidgets import (ScrollArea, SettingCardGroup, PushSettingCard, FluentIcon as FIF)
from PyQt6.QtCore import Qt

class ExportInterface(ScrollArea):
    """
    Interface for Exporting and Importing translations.
    """
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
        
        from qfluentwidgets import SwitchSettingCard
        self.chk_export_only = SwitchSettingCard(
            FIF.SAVE,
            "Export only",
            "Extract text without writing back.",
            parent=self.exportGroup
        )
        self.chk_export_only.setChecked(False)
        
        self.exportGroup.addSettingCard(self.card_export)
        self.exportGroup.addSettingCard(self.chk_export_only)
        
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

        # Layout
        self.expandLayout.addWidget(self.hintGroup)
        self.expandLayout.addWidget(self.exportGroup)
        self.expandLayout.addWidget(self.importGroup)
        self.expandLayout.addStretch(1)
        
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.setStyleSheet("QWidget{background-color: transparent;}")
        
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

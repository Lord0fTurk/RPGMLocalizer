from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QHeaderView, 
                             QFileDialog, QTableWidgetItem)
from qfluentwidgets import (ScrollArea, PrimaryPushButton, PushButton, 
                            TableWidget, FluentIcon as FIF, LineEdit, 
                            ComboBox, SwitchButton, SubtitleLabel, InfoBar, CheckBox)

from src.core.glossary import Glossary, create_sample_glossary
import os

class GlossaryInterface(ScrollArea):
    """ Interface for managing the glossary. """
    
    glossary_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.glossary = Glossary()
        self.current_file_path = None
        self.setObjectName("glossaryInterface")
        
        self.view = QWidget(self)
        self.vBoxLayout = QVBoxLayout(self.view)
        
        self.setWidget(self.view)
        self.setWidgetResizable(True)
        
        self._init_ui()
        self._connect_signals()
        
    def _init_ui(self):
        self.view.setObjectName('view')
        self.vBoxLayout.setContentsMargins(30, 30, 30, 30)
        self.vBoxLayout.setSpacing(20)

        # 1. Header
        self.lbl_title = SubtitleLabel("Glossary Manager", self)
        self.vBoxLayout.addWidget(self.lbl_title)
        
        # 2. Controls Toolbar
        self.hBoxToolbar = QHBoxLayout()
        
        # Inputs for new term
        self.txt_original = LineEdit(self)
        self.txt_original.setPlaceholderText("Original Term")
        self.txt_translation = LineEdit(self)
        self.txt_translation.setPlaceholderText("Translation")
        
        self.btn_add = PrimaryPushButton(FIF.ADD, "Add Term", self)
        
        self.chk_regex = CheckBox("Regex?", self)
        
        self.hBoxToolbar.addWidget(self.txt_original, 1)
        self.hBoxToolbar.addWidget(self.txt_translation, 1)
        self.hBoxToolbar.addWidget(self.chk_regex)
        self.hBoxToolbar.addWidget(self.btn_add)
        
        self.vBoxLayout.addLayout(self.hBoxToolbar)
        
        # 3. Action Buttons (Load, Save, etc)
        self.hBoxActions = QHBoxLayout()
        
        self.btn_load = PushButton(FIF.FOLDER, "Load Glossary", self)
        self.btn_save = PushButton(FIF.SAVE, "Save Glossary", self)
        self.btn_create_sample = PushButton(FIF.DOCUMENT, "Create Sample", self)
        self.btn_clear = PushButton(FIF.DELETE, "Clear All", self)
        
        self.hBoxActions.addWidget(self.btn_load)
        self.hBoxActions.addWidget(self.btn_save)
        self.hBoxActions.addWidget(self.btn_create_sample)
        self.hBoxActions.addStretch()
        self.hBoxActions.addWidget(self.btn_clear)
        
        self.vBoxLayout.addLayout(self.hBoxActions)
        
        # 4. Table
        self.table = TableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Original", "Translation", "Type"])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents) # Type column
        self.table.setBorderRadius(8)
        self.table.setBorderVisible(True)
        
        self.vBoxLayout.addWidget(self.table)
        
        # 5. Status
        self.lbl_status = SubtitleLabel(f"Total Terms: 0", self)
        self.lbl_status.setObjectName("lblStatus")
        self.vBoxLayout.addWidget(self.lbl_status)

    def _connect_signals(self):
        self.btn_add.clicked.connect(self.add_term)
        self.btn_load.clicked.connect(self.load_glossary)
        self.btn_save.clicked.connect(self.save_glossary)
        self.btn_create_sample.clicked.connect(self.create_sample)
        self.btn_clear.clicked.connect(self.clear_glossary)
        
        # Pressing Enter in translation box adds term
        self.txt_translation.returnPressed.connect(self.add_term)

    def add_term(self):
        original = self.txt_original.text().strip()
        trans = self.txt_translation.text().strip()
        is_regex = self.chk_regex.isChecked()
        
        if not original or not trans:
            InfoBar.warning("Input Error", "Both fields are required.", parent=self)
            return
            
        if original in self.glossary.terms:
             InfoBar.warning("Duplicate", "Term already exists. It will be updated.", parent=self)
        
        self.glossary.add_term(original, trans, is_regex)
        self._refresh_table()
        
        # Clear inputs and focus original
        self.txt_original.clear()
        self.txt_translation.clear()
        self.chk_regex.setChecked(False)
        self.txt_original.setFocus()
        
    def _refresh_table(self):
        self.table.setRowCount(0)
        self.table.setRowCount(len(self.glossary))
        
        # self.glossary.terms is now {key: {translation, is_regex}}
        for i, (orig, data) in enumerate(self.glossary.terms.items()):
            translation = data['translation']
            is_regex = data['is_regex']
            
            item_orig = QTableWidgetItem(orig)
            item_trans = QTableWidgetItem(translation)
            item_type = QTableWidgetItem("Regex" if is_regex else "Text")
            
            self.table.setItem(i, 0, item_orig)
            self.table.setItem(i, 1, item_trans)
            self.table.setItem(i, 2, item_type)
            
        self.lbl_status.setText(f"Total Terms: {len(self.glossary)}")
        
    def load_glossary(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Glossary", "", "JSON Files (*.json)"
        )
        if file_path:
            if self.glossary.load(file_path):
                self.current_file_path = file_path
                self._refresh_table()
                self.glossary_selected.emit(file_path)
                InfoBar.success("Success", f"Loaded glossary from {os.path.basename(file_path)}", parent=self)
            else:
                InfoBar.error("Error", "Failed to load glossary.", parent=self)

    def save_glossary(self):
        if not self.current_file_path:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save Glossary", "glossary.json", "JSON Files (*.json)"
            )
            if not file_path:
                return
            self.current_file_path = file_path
        
        if self.glossary.save(self.current_file_path):
            InfoBar.success("Success", "Glossary saved successfully.", parent=self)
            self.glossary_selected.emit(self.current_file_path)
        else:
            InfoBar.error("Error", "Failed to save glossary.", parent=self)
            
    def create_sample(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Create Sample Glossary", "sample_glossary.json", "JSON Files (*.json)"
        )
        if file_path:
            create_sample_glossary(file_path)
            self.load_glossary_from_path(file_path)
            
    def load_glossary_from_path(self, path):
        if self.glossary.load(path):
            self.current_file_path = path
            self._refresh_table()
            InfoBar.success("Success", f"Loaded sample glossary.", parent=self)

    def clear_glossary(self):
        self.glossary.terms.clear()
        self._refresh_table()
        InfoBar.info("Cleared", "Glossary has been cleared.", parent=self)

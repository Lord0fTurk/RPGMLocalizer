from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from qfluentwidgets import (ScrollArea, SettingCardGroup, SwitchSettingCard, 
                            OptionsSettingCard, PushSettingCard, FluentIcon as FIF,
                            TextEdit, CardWidget, StrongBodyLabel, CaptionLabel,
                            Slider, SettingCard)
from PyQt6.QtCore import Qt

class SliderSettingCard(SettingCard):
    """
    Custom SettingCard with a Slider and Value Label, independent of qconfig.
    """
    def __init__(self, icon, title, content=None, parent=None):
        super().__init__(icon, title, content, parent)
        
        self.valueLabel = QLabel(self)
        self.slider = Slider(Qt.Orientation.Horizontal, self)
        
        # Add to layout
        self.hBoxLayout.addWidget(self.valueLabel)
        self.hBoxLayout.addSpacing(10)
        self.hBoxLayout.addWidget(self.slider)
        self.hBoxLayout.addSpacing(16)
        
        # Style
        self.slider.setFixedWidth(200)
        self.valueLabel.setObjectName("valueLabel")
        
        # Connect
        self.slider.valueChanged.connect(self._on_value_changed)
        
    def _on_value_changed(self, value):
        self.valueLabel.setText(str(value))
        
    def setValue(self, value):
        self.slider.setValue(value)
        self.valueLabel.setText(str(value))
        
    def value(self):
        return self.slider.value()
        
    def setRange(self, min_val, max_val):
        self.slider.setRange(min_val, max_val)

class SettingsInterface(ScrollArea):
    """
    Settings interface with grouped options.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scrollWidget = QWidget()
        self.expandLayout = QVBoxLayout(self.scrollWidget)
        self.setObjectName("SettingsInterface")

        # Parser Settings Group
        self.parserGroup = SettingCardGroup("Parser Options", self.scrollWidget)
        
        self.chk_translate_comments = SwitchSettingCard(
            FIF.CHAT,
            "Translate comments",
            "Identify and translate comments marked as event commands (Code 108/408)",
            parent=self.parserGroup
        )
        self.chk_translate_comments.setChecked(True)
        
        self.chk_translate_notes = SwitchSettingCard(
            FIF.EDIT,
            "Translate 'note' fields",
            "Include database 'note' fields (Caution: may break plugins)",
            parent=self.parserGroup
        )
        self.chk_translate_notes.setChecked(False)
        
        self.parserGroup.addSettingCard(self.chk_translate_comments)
        self.parserGroup.addSettingCard(self.chk_translate_notes)
        
        # Pipeline Settings Group
        self.pipelineGroup = SettingCardGroup("Translation Pipeline", self.scrollWidget)
        
        self.chk_backup = SwitchSettingCard(
            FIF.SAVE,
            "Create Backups",
            "Automatically create backups of original files before overwriting",
            parent=self.pipelineGroup
        )
        self.chk_backup.setChecked(True)
        
        self.chk_cache = SwitchSettingCard(
            FIF.SPEED_HIGH,
            "Use Cache",
            "Skip previously translated strings to save time",
            parent=self.pipelineGroup
        )
        self.chk_cache.setChecked(True)
        
        self.btn_clear_cache = PushSettingCard(
            "Clear Cache",
            FIF.DELETE,
            "Clear Translation Cache",
            "Remove all cached translations to force a fresh translation",
            self.pipelineGroup
        )
        
        self.pipelineGroup.addSettingCard(self.chk_backup)
        self.pipelineGroup.addSettingCard(self.chk_cache)
        self.pipelineGroup.addSettingCard(self.btn_clear_cache)

        # Performance Group
        self.performanceGroup = SettingCardGroup("Performance", self.scrollWidget)
        
        self.slider_batch_size = SliderSettingCard(
            icon=FIF.SPEED_HIGH,
            title="Batch Processing Size",
            content="Number of text entries to merge per request (1=safest, 10=fast, 50+=risky)",
            parent=self.performanceGroup
        )
        self.slider_batch_size.setRange(1, 200)
        self.slider_batch_size.setValue(1)
        
        self.slider_concurrent = SliderSettingCard(
            icon=FIF.PEOPLE,
            title="Concurrent Requests",
            content="Maximum number of parallel translation requests (5-50)",
            parent=self.performanceGroup
        )
        self.slider_concurrent.setRange(5, 50)
        self.slider_concurrent.setValue(20)
        
        self.performanceGroup.addSettingCard(self.slider_batch_size)
        self.performanceGroup.addSettingCard(self.slider_concurrent)

        # Network Group
        self.networkGroup = SettingCardGroup("Network", self.scrollWidget)

        self.chk_multi_endpoint = SwitchSettingCard(
            FIF.SPEED_HIGH,
            "Use Multiple Google Mirrors",
            "Rotate between multiple Google endpoints for stability",
            parent=self.networkGroup
        )
        self.chk_multi_endpoint.setChecked(True)

        self.chk_lingva_fallback = SwitchSettingCard(
            FIF.SPEED_HIGH,
            "Enable Lingva Fallback",
            "Use Lingva as a fallback if Google endpoints fail",
            parent=self.networkGroup
        )
        self.chk_lingva_fallback.setChecked(True)

        self.slider_request_delay = SliderSettingCard(
            icon=FIF.SPEED_HIGH,
            title="Request Delay (ms)",
            content="Delay between requests to reduce rate limits",
            parent=self.networkGroup
        )
        self.slider_request_delay.setRange(0, 1000)
        self.slider_request_delay.setValue(150)

        self.slider_timeout = SliderSettingCard(
            icon=FIF.SPEED_HIGH,
            title="Request Timeout (sec)",
            content="Maximum time to wait for a response",
            parent=self.networkGroup
        )
        self.slider_timeout.setRange(5, 30)
        self.slider_timeout.setValue(15)

        self.slider_max_retries = SliderSettingCard(
            icon=FIF.SPEED_HIGH,
            title="Max Retries",
            content="Retry count for transient failures",
            parent=self.networkGroup
        )
        self.slider_max_retries.setRange(1, 5)
        self.slider_max_retries.setValue(3)

        self.networkGroup.addSettingCard(self.chk_multi_endpoint)
        self.networkGroup.addSettingCard(self.chk_lingva_fallback)
        self.networkGroup.addSettingCard(self.slider_request_delay)
        self.networkGroup.addSettingCard(self.slider_timeout)
        self.networkGroup.addSettingCard(self.slider_max_retries)
        
        # Glossary Group
        self.glossaryGroup = SettingCardGroup("Glossary", self.scrollWidget)
        
        self.chk_glossary = SwitchSettingCard(
            FIF.BOOK_SHELF,
            "Use Glossary",
            "Apply consistent translations for specific terms",
            parent=self.glossaryGroup
        )
        self.chk_glossary.setChecked(False)
        
        self.card_glossary_path = PushSettingCard(
            "Select Glossary",
            FIF.FOLDER,
            "Glossary File",
            "Not selected",
            self.glossaryGroup
        )
        
        self.btn_create_sample = PushSettingCard(
            "Create Sample",
            FIF.ADD,
            "Create Sample Glossary",
            "Generate a sample glossary.json file",
            self.glossaryGroup
        )

        self.glossaryGroup.addSettingCard(self.chk_glossary)
        self.glossaryGroup.addSettingCard(self.card_glossary_path)
        self.glossaryGroup.addSettingCard(self.btn_create_sample)

        # Filtering Group
        self.filterGroup = SettingCardGroup("Filtering Rules", self.scrollWidget)
        
        # Custom card for Regex input
        self.card_regex = CardWidget(self.filterGroup)
        self.card_regex.setFixedHeight(200)  # Explicit height to ensure visibility
        self.v_regex = QVBoxLayout(self.card_regex)
        self.lbl_regex_title = StrongBodyLabel("Regex Blacklist", self.card_regex)
        self.lbl_regex_desc = CaptionLabel("Enter Regex patterns to ignore (one per line). Example: ^System_.*", self.card_regex)
        self.txt_regex = TextEdit(self.card_regex)
        self.txt_regex.setPlaceholderText("^Skip_This_.*\n^<Internal_Code>.*\nActor\\d+")
        
        self.v_regex.addWidget(self.lbl_regex_title)
        self.v_regex.addWidget(self.lbl_regex_desc)
        self.v_regex.addWidget(self.txt_regex)
        self.v_regex.setContentsMargins(16, 16, 16, 16)
        self.v_regex.addStretch(1)
        
        self.filterGroup.addSettingCard(self.card_regex)

        # Add groups to layout
        self.expandLayout.addWidget(self.parserGroup)
        self.expandLayout.addWidget(self.pipelineGroup)
        self.expandLayout.addWidget(self.performanceGroup)
        self.expandLayout.addWidget(self.networkGroup)
        self.expandLayout.addWidget(self.glossaryGroup)
        self.expandLayout.addWidget(self.filterGroup)
        self.expandLayout.addStretch(1)
        
        # Style
        self.scrollWidget.setObjectName("scrollWidget")
        self.setStyleSheet("QWidget{background-color: transparent;}")
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Connect signals
        self.card_glossary_path.clicked.connect(self._select_glossary)
        self.btn_create_sample.clicked.connect(self._create_sample)

        self.glossary_path = ""

    def _select_glossary(self):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Glossary File", "", "JSON Files (*.json)"
        )
        if path:
            self.glossary_path = path
            self.card_glossary_path.setContent(path)
            self.chk_glossary.setChecked(True)

    def _create_sample(self):
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        import json
        
        path, _ = QFileDialog.getSaveFileName(
            self, "Create Sample Glossary", "glossary.json", "JSON Files (*.json)"
        )
        if path:
            sample = {
                "Potion": "İksir",
                "Sword": "Kılıç", 
                "Dragon": "Ejderha"
            }
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(sample, f, ensure_ascii=False, indent=2)
                
                self.glossary_path = path
                self.card_glossary_path.setContent(path)
                self.chk_glossary.setChecked(True)
                
                QMessageBox.information(self, "Success", f"Sample glossary created at:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create file:\n{e}")

    def set_glossary_path(self, path: str):
        """Update the glossary path from external source."""
        if path:
            self.glossary_path = path
            self.card_glossary_path.setContent(path)
            self.chk_glossary.setChecked(True)

    def apply_settings(self, settings: dict):
        if not settings:
            return

        self.chk_translate_comments.setChecked(settings.get("translate_comments", True))
        self.chk_translate_notes.setChecked(settings.get("translate_notes", False))

        self.chk_backup.setChecked(settings.get("backup_enabled", True))
        self.chk_cache.setChecked(settings.get("use_cache", True))

        self.slider_batch_size.setValue(settings.get("batch_size", self.slider_batch_size.value()))
        self.slider_concurrent.setValue(settings.get("concurrent_requests", self.slider_concurrent.value()))

        self.chk_multi_endpoint.setChecked(settings.get("use_multi_endpoint", True))
        self.chk_lingva_fallback.setChecked(settings.get("enable_lingva_fallback", True))
        self.slider_request_delay.setValue(settings.get("request_delay_ms", self.slider_request_delay.value()))
        self.slider_timeout.setValue(settings.get("request_timeout", self.slider_timeout.value()))
        self.slider_max_retries.setValue(settings.get("max_retries", self.slider_max_retries.value()))

        regex_list = settings.get("regex_blacklist")
        if isinstance(regex_list, list):
            self.txt_regex.setPlainText("\n".join(regex_list))

        glossary_path = settings.get("glossary_path", "")
        if glossary_path:
            self.set_glossary_path(glossary_path)
            self.chk_glossary.setChecked(settings.get("use_glossary", True))

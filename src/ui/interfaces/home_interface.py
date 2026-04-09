import os
from typing import Optional
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QLabel
from PyQt6.QtCore import Qt, pyqtSignal as Signal
from qfluentwidgets import (LineEdit, PrimaryPushButton, PushButton, ComboBox, 
                            StrongBodyLabel, CaptionLabel, CardWidget, BodyLabel,
                            TransparentToolButton, FluentIcon as FIF, ProgressBar,
                            InfoBar, InfoBarPosition)

class HomeInterface(QWidget):
    """
    Main interface for selecting game and starting translation.
    """
    ENCRYPTED_ARCHIVE_EXTENSIONS = ('.rgss3a', '.rpgmvp', '.rpgmvo', '.rpgmvm')

    start_requested = Signal(dict)
    stop_requested = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HomeInterface")
        
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(36, 36, 36, 36)
        self.vBoxLayout.setSpacing(20)

        self._current_project_path = ""
        self._current_source_code = "auto"
        self._current_target_code = "tr"
        self._current_running = False

        # 0. Overview Card
        self.card_overview = CardWidget(self)
        self.l_overview = QVBoxLayout(self.card_overview)

        self.lbl_overview_title = StrongBodyLabel("Quick Overview", self.card_overview)
        self.lbl_overview_project = CaptionLabel("Project: not selected", self.card_overview)
        self.lbl_overview_languages = CaptionLabel("Languages: auto → Turkish", self.card_overview)
        self.lbl_overview_status = CaptionLabel("Status: ready", self.card_overview)

        for label in (self.lbl_overview_project, self.lbl_overview_languages, self.lbl_overview_status):
            label.setWordWrap(True)

        self.l_overview.addWidget(self.lbl_overview_title)
        self.l_overview.addWidget(self.lbl_overview_project)
        self.l_overview.addWidget(self.lbl_overview_languages)
        self.l_overview.addWidget(self.lbl_overview_status)

        self.vBoxLayout.addWidget(self.card_overview)
        
        # 1. Project Selection Card
        self.card_project = CardWidget(self)
        self.l_project = QVBoxLayout(self.card_project)
        
        self.lbl_project_title = StrongBodyLabel("Game Project", self.card_project)
        self.lbl_project_desc = CaptionLabel("Select the RPG Maker game project folder", self.card_project)
        
        self.h_project_input = QHBoxLayout()
        self.txt_path = LineEdit(self.card_project)
        self.txt_path.setPlaceholderText("C:/Games/MyGame")
        self.btn_browse = PushButton("Browse", self.card_project, FIF.FOLDER)
        self.btn_browse.clicked.connect(self._browse_folder)
        
        self.h_project_input.addWidget(self.txt_path)
        self.h_project_input.addWidget(self.btn_browse)
        
        self.l_project.addWidget(self.lbl_project_title)
        self.l_project.addWidget(self.lbl_project_desc)
        self.l_project.addLayout(self.h_project_input)
        
        self.vBoxLayout.addWidget(self.card_project)
        
        # 2. Language Selection
        self.card_lang = CardWidget(self)
        self.l_lang = QVBoxLayout(self.card_lang)
        
        self.lbl_lang_title = StrongBodyLabel("Languages", self.card_lang)
        
        self.h_lang = QHBoxLayout()
        
        # Language dictionaries: Display Name -> Code
        self.source_languages = {
            "Auto Detect": "auto",
            "Arabic": "ar",
            "Bulgarian": "bg",
            "Bengali": "bn",
            "Chinese (Simplified)": "zh-CN",
            "Chinese (Traditional)": "zh-TW",
            "Czech": "cs",
            "Danish": "da",
            "Dutch": "nl",
            "English": "en",
            "Estonian": "et",
            "Finnish": "fi",
            "French": "fr",
            "German": "de",
            "Greek": "el",
            "Hebrew": "he",
            "Hindi": "hi",
            "Hungarian": "hu",
            "Indonesian": "id",
            "Italian": "it",
            "Japanese": "ja",
            "Korean": "ko",
            "Malay": "ms",
            "Norwegian": "no",
            "Persian": "fa",
            "Polish": "pl",
            "Portuguese": "pt",
            "Romanian": "ro",
            "Russian": "ru",
            "Slovak": "sk",
            "Spanish": "es",
            "Swedish": "sv",
            "Thai": "th",
            "Turkish": "tr",
            "Ukrainian": "uk",
            "Vietnamese": "vi",
        }
        
        self.target_languages = {
            "Turkish": "tr",
            "Arabic": "ar",
            "Bengali": "bn",
            "Bulgarian": "bg",
            "Chinese (Simplified)": "zh-CN",
            "Chinese (Traditional)": "zh-TW",
            "Croatian": "hr",
            "Czech": "cs",
            "Danish": "da",
            "Dutch": "nl",
            "English": "en",
            "Estonian": "et",
            "Filipino": "tl",
            "Finnish": "fi",
            "French": "fr",
            "German": "de",
            "Greek": "el",
            "Gujarati": "gu",
            "Hebrew": "he",
            "Hindi": "hi",
            "Hungarian": "hu",
            "Indonesian": "id",
            "Italian": "it",
            "Japanese": "ja",
            "Kannada": "kn",
            "Korean": "ko",
            "Latvian": "lv",
            "Lithuanian": "lt",
            "Malay": "ms",
            "Malayalam": "ml",
            "Marathi": "mr",
            "Norwegian": "no",
            "Persian": "fa",
            "Polish": "pl",
            "Portuguese": "pt",
            "Portuguese (Brazil)": "pt-BR",
            "Romanian": "ro",
            "Russian": "ru",
            "Serbian": "sr",
            "Slovak": "sk",
            "Slovenian": "sl",
            "Spanish": "es",
            "Swedish": "sv",
            "Tamil": "ta",
            "Telugu": "te",
            "Thai": "th",
            "Ukrainian": "uk",
            "Urdu": "ur",
            "Vietnamese": "vi",
        }
        
        # Source
        self.v_source = QVBoxLayout()
        self.lbl_source = BodyLabel("Source Language", self.card_lang)
        self.cmb_source = ComboBox(self.card_lang)
        self.cmb_source.addItems(list(self.source_languages.keys()))
        self.cmb_source.currentTextChanged.connect(self._on_language_changed)
        self.v_source.addWidget(self.lbl_source)
        self.v_source.addWidget(self.cmb_source)
        
        # Target
        self.v_target = QVBoxLayout()
        self.lbl_target = BodyLabel("Target Language", self.card_lang)
        self.cmb_target = ComboBox(self.card_lang)
        self.cmb_target.addItems(list(self.target_languages.keys()))
        self.cmb_target.currentTextChanged.connect(self._on_language_changed)
        self.v_target.addWidget(self.lbl_target)
        self.v_target.addWidget(self.cmb_target)
        
        self.h_lang.addLayout(self.v_source)
        self.h_lang.addSpacing(20)
        self.h_lang.addLayout(self.v_target)
        
        self.l_lang.addWidget(self.lbl_lang_title)
        self.l_lang.addLayout(self.h_lang)
        
        self.vBoxLayout.addWidget(self.card_lang)

        # 3. Scope Note
        self.card_scope = CardWidget(self)
        self.l_scope = QVBoxLayout(self.card_scope)

        self.lbl_scope_title = StrongBodyLabel("Localization Scope", self.card_scope)
        self.lbl_scope_line1 = CaptionLabel(
            "Best results come from standard RPG Maker project structures.",
            self.card_scope,
        )
        self.lbl_scope_line2 = CaptionLabel(
            "Custom plugin-driven structures may need manual review.",
            self.card_scope,
        )
        self.lbl_scope_line3 = CaptionLabel(
            "Use the coverage audit when you want to check for missed text surfaces.",
            self.card_scope,
        )

        for label in (self.lbl_scope_line1, self.lbl_scope_line2, self.lbl_scope_line3):
            label.setWordWrap(True)

        self.l_scope.addWidget(self.lbl_scope_title)
        self.l_scope.addWidget(self.lbl_scope_line1)
        self.l_scope.addWidget(self.lbl_scope_line2)
        self.l_scope.addWidget(self.lbl_scope_line3)

        self.vBoxLayout.addWidget(self.card_scope)
        
        # 4. Actions & Status
        self.card_actions = CardWidget(self)
        self.l_actions = QVBoxLayout(self.card_actions)
        
        self.btn_start = PrimaryPushButton("Start Translation", self.card_actions, FIF.PLAY)
        self.btn_start.clicked.connect(self._on_start)
        
        self.btn_stop = PushButton("Stop", self.card_actions, FIF.PAUSE)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop)
        
        self.progress_bar = ProgressBar(self.card_actions)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        
        self.lbl_status = CaptionLabel("Ready", self.card_actions)
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.h_btns = QHBoxLayout()
        self.h_btns.addWidget(self.btn_start)
        self.h_btns.addWidget(self.btn_stop)
        
        self.l_actions.addWidget(self.lbl_status)
        self.l_actions.addWidget(self.progress_bar)
        self.l_actions.addLayout(self.h_btns)
        
        self.vBoxLayout.addWidget(self.card_actions)
        self.vBoxLayout.addStretch(1)

        self._refresh_overview()

    def _browse_folder(self):
        directory = QFileDialog.getExistingDirectory(
            self, 
            "Select Game Project Folder",
            self.txt_path.text().strip() or "",
        )
        normalized_path = self._normalize_project_path(directory)
        if normalized_path:
            self.txt_path.setText(normalized_path)
            self._current_project_path = normalized_path
            self._refresh_overview()
            self._check_encrypted_game(normalized_path)

    @staticmethod
    def _normalize_project_path(path: str) -> str:
        """Normalize user-selected project input into a project directory path."""
        if not isinstance(path, str):
            return ""
        normalized = path.strip().strip('"')
        if not normalized:
            return ""
        if os.path.isfile(normalized):
            return os.path.dirname(normalized)
        return normalized
            
    def _find_child_case_insensitive(self, parent_dir: str, target_name: str) -> Optional[str]:
        if not parent_dir or not os.path.isdir(parent_dir):
            return None
        target_lower = target_name.lower()
        try:
            with os.scandir(parent_dir) as entries:
                for entry in entries:
                    if entry.is_dir() and entry.name.lower() == target_lower:
                        return entry.path
        except OSError:
            return None
        return None

    def _check_encrypted_game(self, path: str) -> None:
        """Check for potentially encrypted game files and warn user."""
        try:
            # Common encrypted archive extensions
            encrypted = False
            enc_files = []
            
            # Check root and standard subfolders
            to_check = [path]
            www_dir = self._find_child_case_insensitive(path, "www")
            if www_dir:
                to_check.append(www_dir)
                
            for p in to_check:
                if not os.path.exists(p): continue
                found = [f for f in os.listdir(p) if f.lower().endswith(self.ENCRYPTED_ARCHIVE_EXTENSIONS)]
                if found:
                    encrypted = True
                    enc_files.extend(found)
            
            # If encrypted files exist, check if we can find open Data files
            has_data = False
            data_dirs = []
            root_data_dir = self._find_child_case_insensitive(path, "data")
            if root_data_dir:
                data_dirs.append(root_data_dir)
            if www_dir:
                www_data_dir = self._find_child_case_insensitive(www_dir, "data")
                if www_data_dir:
                    data_dirs.append(www_data_dir)
            
            for d in data_dirs:
                if os.path.exists(d) and os.path.isdir(d):
                    # Check if it has readable content
                    json_or_rb = [f for f in os.listdir(d) if f.lower().endswith(('.json', '.rvdata2', '.rxdata'))]
                    if json_or_rb:
                        has_data = True
                        break
            
            if encrypted and not has_data:
                InfoBar.warning(
                    title="Åifreli Oyun Tespit Edildi",
                    content=f"Bu oyun ÅŸifreli dosyalara ({enc_files[0]} vb.) sahip ve aÃ§Ä±k 'Data' klasÃ¶rÃ¼ bulunamadÄ±.\n"
                            "LÃ¼tfen Ã¶nce bir 'RPG Maker Decrypter' aracÄ± ile oyun dosyalarÄ±nÄ± aÃ§Ä±nÄ±z, aksi halde Ã§eviri yapÄ±lamaz.",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=10000,
                    parent=self
                )
                
        except Exception as e:
            print(f"Error checking encryption: {e}")
            
    def _on_start(self):
        path = self._normalize_project_path(self.txt_path.text())
        if path:
            self.txt_path.setText(path)
            self._current_project_path = path
        
        # Convert display names to language codes
        source_name = self.cmb_source.currentText()
        target_name = self.cmb_target.currentText()
        source_code = self.source_languages.get(source_name, "auto")
        target_code = self.target_languages.get(target_name, "tr")

        self._current_source_code = source_code
        self._current_target_code = target_code
        self._current_running = True
        self._refresh_overview()
        
        data = {
            "project_path": path,
            "source_lang": source_code,
            "target_lang": target_code
        }
        self.start_requested.emit(data)
        
    def _on_stop(self):
        self.stop_requested.emit()
        
    def update_status(self, text, progress=None):
        self.lbl_status.setText(text)
        if progress is not None:
            self.progress_bar.show()
            self.progress_bar.setValue(progress)
            
    def set_running(self, running: bool):
        self._current_running = running
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        if not running:
            self.progress_bar.hide()
        self._refresh_overview()

    def apply_settings(self, settings: dict):
        if not settings:
            return

        project_path = settings.get("project_path", "")
        if project_path:
            normalized = self._normalize_project_path(project_path)
            self.txt_path.setText(normalized)
            self._current_project_path = normalized

        source_code = settings.get("source_lang")
        if source_code:
            self._set_combo_by_code(self.cmb_source, self.source_languages, source_code)
            self._current_source_code = source_code

        target_code = settings.get("target_lang")
        if target_code:
            self._set_combo_by_code(self.cmb_target, self.target_languages, target_code)
            self._current_target_code = target_code

        self._refresh_overview()

    def _on_language_changed(self, _text: str) -> None:
        self._current_source_code = self.source_languages.get(self.cmb_source.currentText(), "auto")
        self._current_target_code = self.target_languages.get(self.cmb_target.currentText(), "tr")
        self._refresh_overview()

    def _refresh_overview(self) -> None:
        project_text = self._current_project_path or self._normalize_project_path(self.txt_path.text()) or "not selected"
        source_name = self._language_name_from_code(self.source_languages, self._current_source_code)
        target_name = self._language_name_from_code(self.target_languages, self._current_target_code)
        run_text = "running" if self._current_running else "ready"

        self.lbl_overview_project.setText(f"Project: {project_text}")
        self.lbl_overview_languages.setText(f"Languages: {source_name} → {target_name}")
        self.lbl_overview_status.setText(f"Status: {run_text}")

    @staticmethod
    def _language_name_from_code(mapping: dict, code: str) -> str:
        for name, value in mapping.items():
            if value == code:
                return name
        return code or "unknown"

    def _set_combo_by_code(self, combo, mapping: dict, code: str):
        for name, value in mapping.items():
            if value == code:
                combo.setCurrentText(name)
                return

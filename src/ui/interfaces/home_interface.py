import os
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
    start_requested = Signal(dict)
    stop_requested = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HomeInterface")
        
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(36, 36, 36, 36)
        self.vBoxLayout.setSpacing(20)
        
        # 1. Project Selection Card
        self.card_project = CardWidget(self)
        self.l_project = QVBoxLayout(self.card_project)
        
        self.lbl_project_title = StrongBodyLabel("Game Project", self.card_project)
        self.lbl_project_desc = CaptionLabel("Select the RPG Maker game executable (Game.exe)", self.card_project)
        
        self.h_project_input = QHBoxLayout()
        self.txt_path = LineEdit(self.card_project)
        self.txt_path.setPlaceholderText("C:/Games/MyGame/Game.exe")
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
        self.v_source.addWidget(self.lbl_source)
        self.v_source.addWidget(self.cmb_source)
        
        # Target
        self.v_target = QVBoxLayout()
        self.lbl_target = BodyLabel("Target Language", self.card_lang)
        self.cmb_target = ComboBox(self.card_lang)
        self.cmb_target.addItems(list(self.target_languages.keys()))
        self.v_target.addWidget(self.lbl_target)
        self.v_target.addWidget(self.cmb_target)
        
        self.h_lang.addLayout(self.v_source)
        self.h_lang.addSpacing(20)
        self.h_lang.addLayout(self.v_target)
        
        self.l_lang.addWidget(self.lbl_lang_title)
        self.l_lang.addLayout(self.h_lang)
        
        self.vBoxLayout.addWidget(self.card_lang)
        
        # 3. Actions & Status
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

    def _browse_folder(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Select Game Executable", 
            "", 
            "Game Executable (*.exe);;All Files (*.*)"
        )
        if file_path:
            # We save the directory containing the exe as the project path
            directory = os.path.dirname(file_path)
            self.txt_path.setText(directory)
            self._check_encrypted_game(directory)
            
    def _check_encrypted_game(self, path):
        """Check for potentially encrypted game files and warn user."""
        try:
            # Common encrypted archive extensions
            encrypted = False
            enc_files = []
            
            # Check root and standard subfolders
            to_check = [path]
            if os.path.isdir(os.path.join(path, "www")):
                to_check.append(os.path.join(path, "www"))
                
            for p in to_check:
                if not os.path.exists(p): continue
                found = [f for f in os.listdir(p) if f.lower().endswith(('.rgss3a', '.rpgmvp', '.rpgmwo', '.rpgmvm'))]
                if found:
                    encrypted = True
                    enc_files.extend(found)
            
            # If encrypted files exist, check if we can find open Data files
            has_data = False
            data_dirs = [os.path.join(path, "Data"), os.path.join(path, "data"), os.path.join(path, "www", "data")]
            
            for d in data_dirs:
                if os.path.exists(d) and os.path.isdir(d):
                    # Check if it has readable content
                    json_or_rb = [f for f in os.listdir(d) if f.lower().endswith(('.json', '.rvdata2', '.rxdata'))]
                    if json_or_rb:
                        has_data = True
                        break
            
            if encrypted and not has_data:
                InfoBar.warning(
                    title="Şifreli Oyun Tespit Edildi",
                    content=f"Bu oyun şifreli dosyalara ({enc_files[0]} vb.) sahip ve açık 'Data' klasörü bulunamadı.\n"
                            "Lütfen önce bir 'RPG Maker Decrypter' aracı ile oyun dosyalarını açınız, aksi halde çeviri yapılamaz.",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=10000,
                    parent=self
                )
                
        except Exception as e:
            print(f"Error checking encryption: {e}")
            
    def _on_start(self):
        path = self.txt_path.text().strip()
        
        # Convert display names to language codes
        source_name = self.cmb_source.currentText()
        target_name = self.cmb_target.currentText()
        source_code = self.source_languages.get(source_name, "auto")
        target_code = self.target_languages.get(target_name, "tr")
        
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
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        if not running:
            self.progress_bar.hide()

import os
from typing import Optional
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFileDialog,
                             QSplitter, QFrame)
from PyQt6.QtCore import Qt, pyqtSignal as Signal, QSize
from qfluentwidgets import (LineEdit, PrimaryPushButton, PushButton, ComboBox,
                            StrongBodyLabel, CaptionLabel, CardWidget, BodyLabel,
                            FluentIcon as FIF, ProgressBar, InfoBar, InfoBarPosition,
                            SimpleCardWidget, HeaderCardWidget)

from src.ui.components.console_log import ConsoleLog


class _LogCard(CardWidget):
    """Card wrapping a ConsoleLog widget for the dashboard."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(200)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        # Dashboard console: smaller buffer, no separate label
        self.console = ConsoleLog(self, show_label=False)
        self.console.MAX_LINES = 150
        layout.addWidget(self.console)


class HomeInterface(QWidget):
    """
    Dashboard: project + languages + controls on left,
    progress + live console log on right.
    """
    ENCRYPTED_ARCHIVE_EXTENSIONS = ('.rgss3a', '.rpgmvp', '.rpgmvo', '.rpgmvm')

    start_requested = Signal(dict)
    stop_requested = Signal()

    # Google Translate supports 130+ languages.
    # Source list has "Auto Detect" prepended; target list is pure.
    _ALL_LANGS = {
        "Afrikaans": "af", "Albanian": "sq", "Amharic": "am",
        "Arabic": "ar", "Armenian": "hy", "Assamese": "as",
        "Aymara": "ay", "Azerbaijani": "az", "Bambara": "bm",
        "Basque": "eu", "Belarusian": "be", "Bengali": "bn",
        "Bhojpuri": "bho", "Bosnian": "bs", "Bulgarian": "bg",
        "Catalan": "ca", "Cebuano": "ceb", "Chinese (Simplified)": "zh-CN",
        "Chinese (Traditional)": "zh-TW", "Corsican": "co",
        "Croatian": "hr", "Czech": "cs", "Danish": "da",
        "Dhivehi": "dv", "Dogri": "doi", "Dutch": "nl",
        "English": "en", "Esperanto": "eo", "Estonian": "et",
        "Ewe": "ee", "Filipino": "tl", "Finnish": "fi",
        "French": "fr", "Frisian": "fy", "Galician": "gl",
        "Georgian": "ka", "German": "de", "Greek": "el",
        "Guarani": "gn", "Gujarati": "gu", "Haitian Creole": "ht",
        "Hausa": "ha", "Hawaiian": "haw", "Hebrew": "he",
        "Hindi": "hi", "Hmong": "hmn", "Hungarian": "hu",
        "Icelandic": "is", "Igbo": "ig", "Ilocano": "ilo",
        "Indonesian": "id", "Irish": "ga", "Italian": "it",
        "Japanese": "ja", "Javanese": "jv", "Kannada": "kn",
        "Kazakh": "kk", "Khmer": "km", "Kinyarwanda": "rw",
        "Konkani": "gom", "Korean": "ko", "Krio": "kri",
        "Kurdish": "ku", "Kurdish (Sorani)": "ckb", "Kyrgyz": "ky",
        "Lao": "lo", "Latin": "la", "Latvian": "lv",
        "Lingala": "ln", "Lithuanian": "lt", "Luganda": "lg",
        "Luxembourgish": "lb", "Macedonian": "mk", "Maithili": "mai",
        "Malagasy": "mg", "Malay": "ms", "Malayalam": "ml",
        "Maltese": "mt", "Maori": "mi", "Marathi": "mr",
        "Meiteilon (Manipuri)": "mni", "Mizo": "lus", "Mongolian": "mn",
        "Myanmar (Burmese)": "my", "Nepali": "ne", "Norwegian": "no",
        "Nyanja (Chichewa)": "ny", "Odia (Oriya)": "or", "Oromo": "om",
        "Pashto": "ps", "Persian": "fa", "Polish": "pl",
        "Portuguese": "pt", "Portuguese (Brazil)": "pt-BR",
        "Punjabi": "pa", "Quechua": "qu", "Romanian": "ro",
        "Russian": "ru", "Samoan": "sm", "Sanskrit": "sa",
        "Scots Gaelic": "gd", "Serbian": "sr", "Sesotho": "st",
        "Shona": "sn", "Sindhi": "sd", "Sinhala": "si",
        "Slovak": "sk", "Slovenian": "sl", "Somali": "so",
        "Spanish": "es", "Sundanese": "su", "Swahili": "sw",
        "Swedish": "sv", "Tajik": "tg", "Tamil": "ta",
        "Tatar": "tt", "Telugu": "te", "Thai": "th",
        "Tigrinya": "ti", "Tsonga": "ts", "Turkish": "tr",
        "Turkmen": "tk", "Twi (Akan)": "ak", "Ukrainian": "uk",
        "Urdu": "ur", "Uyghur": "ug", "Uzbek": "uz",
        "Vietnamese": "vi", "Welsh": "cy", "Xhosa": "xh",
        "Yiddish": "yi", "Yoruba": "yo", "Zulu": "zu",
    }

    SOURCE_LANGUAGES = {"Auto Detect": "auto", **_ALL_LANGS}
    TARGET_LANGUAGES = dict(_ALL_LANGS)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HomeInterface")

        self._current_project_path = ""
        self._current_source_code = "auto"
        self._current_target_code = "tr"
        self._current_running = False

        # Root: horizontal splitter (left panel | right panel)
        root = QHBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(20)

        # ───── Left column ─────
        left = QVBoxLayout()
        left.setSpacing(16)

        # Project card
        self.card_project = SimpleCardWidget(self)
        lp = QVBoxLayout(self.card_project)
        lp.setSpacing(12)
        lbl_proj = StrongBodyLabel("Game Project")
        desc_proj = CaptionLabel("Select the RPG Maker game project folder")
        self.txt_path = LineEdit(self.card_project)
        import sys as _sys
        self.txt_path.setPlaceholderText(
            "C:/Games/MyGame" if _sys.platform == "win32" else "~/Games/MyGame"
        )
        self.btn_browse = PushButton("Browse", self, FIF.FOLDER)
        self.btn_browse.clicked.connect(self._browse_folder)
        h = QHBoxLayout()
        h.addWidget(self.txt_path)
        h.addWidget(self.btn_browse)
        lp.addWidget(lbl_proj)
        lp.addWidget(desc_proj)
        lp.addLayout(h)
        left.addWidget(self.card_project)

        # Languages card
        self.card_lang = SimpleCardWidget(self)
        ll = QVBoxLayout(self.card_lang)
        ll.setSpacing(12)
        ll.addWidget(StrongBodyLabel("Languages"))
        hl = QHBoxLayout()
        vs = QVBoxLayout()
        vs.addWidget(BodyLabel("Source"))
        self.cmb_source = ComboBox(self.card_lang)
        self.cmb_source.addItems(list(self.SOURCE_LANGUAGES.keys()))
        self.cmb_source.currentTextChanged.connect(self._on_language_changed)
        vs.addWidget(self.cmb_source)
        vt = QVBoxLayout()
        vt.addWidget(BodyLabel("Target"))
        self.cmb_target = ComboBox(self.card_lang)
        self.cmb_target.addItems(list(self.TARGET_LANGUAGES.keys()))
        self.cmb_target.setCurrentText("Turkish")
        self.cmb_target.currentTextChanged.connect(self._on_language_changed)
        vt.addWidget(self.cmb_target)
        hl.addLayout(vs)
        hl.addSpacing(16)
        hl.addLayout(vt)
        ll.addLayout(hl)
        left.addWidget(self.card_lang)

        # Controls card
        self.card_ctrl = SimpleCardWidget(self)
        lc = QVBoxLayout(self.card_ctrl)
        lc.setSpacing(12)

        self.lbl_status = BodyLabel("Ready")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.progress_bar = ProgressBar(self.card_ctrl)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()

        self.btn_start = PrimaryPushButton("Start Translation", self, FIF.PLAY)
        self.btn_start.clicked.connect(self._on_start)

        self.btn_stop = PushButton("Stop", self, FIF.PAUSE)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop)

        hb = QHBoxLayout()
        hb.addWidget(self.btn_start)
        hb.addWidget(self.btn_stop)

        lc.addWidget(self.lbl_status)
        lc.addWidget(self.progress_bar)
        lc.addLayout(hb)
        left.addWidget(self.card_ctrl)
        left.addStretch()

        # ───── Right column: console log ─────
        self.card_log = _LogCard(self)

        # ───── Splitter ─────
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        left_frame = QWidget()
        left_frame.setLayout(left)
        splitter.addWidget(left_frame)
        splitter.addWidget(self.card_log)
        splitter.setSizes([400, 500])
        splitter.setHandleWidth(1)

        root.addWidget(splitter)

        self._refresh_overview()

    # ── public helpers (called from MainWindow) ──

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
        path = settings.get("project_path", "")
        if path:
            self.txt_path.setText(path)
            self._current_project_path = path
        sc = settings.get("source_lang")
        if sc:
            self._set_combo_by_code(self.cmb_source, self.SOURCE_LANGUAGES, sc)
            self._current_source_code = sc
        tc = settings.get("target_lang")
        if tc:
            self._set_combo_by_code(self.cmb_target, self.TARGET_LANGUAGES, tc)
            self._current_target_code = tc
        self._refresh_overview()

    # ── internals ──

    def _browse_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Select Game Project Folder",
                                             self.txt_path.text().strip() or "")
        p = self._normalize_project_path(d)
        if p:
            self.txt_path.setText(p)
            self._current_project_path = p
            self._refresh_overview()
            self._check_encrypted_game(p)

    @staticmethod
    def _normalize_project_path(path: str) -> str:
        if not isinstance(path, str):
            return ""
        n = path.strip().strip('"')
        if not n:
            return ""
        return os.path.dirname(n) if os.path.isfile(n) else n

    def _on_start(self):
        path = self._normalize_project_path(self.txt_path.text())
        if path:
            self.txt_path.setText(path)
            self._current_project_path = path
        sc = self.SOURCE_LANGUAGES.get(self.cmb_source.currentText(), "auto")
        tc = self.TARGET_LANGUAGES.get(self.cmb_target.currentText(), "tr")
        self._current_source_code = sc
        self._current_target_code = tc
        self._current_running = True
        self._refresh_overview()
        self.start_requested.emit({"project_path": path, "source_lang": sc, "target_lang": tc})

    def _on_stop(self):
        self.stop_requested.emit()

    def _on_language_changed(self, _text=None):
        self._current_source_code = self.SOURCE_LANGUAGES.get(self.cmb_source.currentText(), "auto")
        self._current_target_code = self.TARGET_LANGUAGES.get(self.cmb_target.currentText(), "tr")
        self._refresh_overview()

    def _refresh_overview(self):
        pass  # status is shown in control card label

    @staticmethod
    def _set_combo_by_code(combo, mapping: dict, code: str):
        for name, value in mapping.items():
            if value == code:
                combo.setCurrentText(name)
                return

    def _find_child_case_insensitive(self, parent_dir: str, target_name: str) -> Optional[str]:
        if not parent_dir or not os.path.isdir(parent_dir):
            return None
        tl = target_name.lower()
        try:
            with os.scandir(parent_dir) as es:
                for e in es:
                    if e.is_dir() and e.name.lower() == tl:
                        return e.path
        except OSError:
            return None
        return None

    def _check_encrypted_game(self, path: str) -> None:
        try:
            encrypted = False
            enc_files = []
            to_check = [path]
            www = self._find_child_case_insensitive(path, "www")
            if www:
                to_check.append(www)
            for p in to_check:
                if not os.path.exists(p):
                    continue
                found = [f for f in os.listdir(p)
                         if f.lower().endswith(self.ENCRYPTED_ARCHIVE_EXTENSIONS)]
                if found:
                    encrypted = True
                    enc_files.extend(found)
            has_data = False
            data_dirs = []
            rdd = self._find_child_case_insensitive(path, "data")
            if rdd:
                data_dirs.append(rdd)
            if www:
                wdd = self._find_child_case_insensitive(www, "data")
                if wdd:
                    data_dirs.append(wdd)
            for d in data_dirs:
                if os.path.exists(d) and os.path.isdir(d):
                    if [f for f in os.listdir(d) if f.lower().endswith(('.json', '.rvdata2', '.rxdata'))]:
                        has_data = True
                        break
            if encrypted and not has_data:
                InfoBar.warning(
                    title="Encrypted Game Detected",
                    content=f"This game contains encrypted files ({enc_files[0]}…).\n"
                            "Please decrypt first, otherwise translation cannot continue.",
                    orient=Qt.Orientation.Horizontal, isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT, duration=10000, parent=self,
                )
        except Exception:
            pass

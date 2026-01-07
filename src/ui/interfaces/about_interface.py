from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QFont
from qfluentwidgets import (ScrollArea, CardWidget, StrongBodyLabel, CaptionLabel, 
                            PrimaryPushButton, FluentIcon as FIF, BodyLabel, HyperlinkButton)

from version import VERSION

class AboutInterface(ScrollArea):
    """ About Interface displaying app info and credits """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scrollWidget = QWidget()
        self.expandLayout = QVBoxLayout(self.scrollWidget)
        self.setObjectName("AboutInterface")
        
        # Main Layout settings
        self.expandLayout.setSpacing(20)
        self.expandLayout.setContentsMargins(36, 36, 36, 36)
        
        # 1. Header Section (Icon + Title)
        self.v_header = QVBoxLayout()
        self.v_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.v_header.setSpacing(10)
        
        # Icon
        self.lbl_icon = QLabel()
        # Ensure we have an icon, otherwise fallback
        from src.utils.paths import resource_path
        import os
        
        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path)
            self.lbl_icon.setPixmap(pixmap.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.lbl_icon.setText("RL")
            self.lbl_icon.setStyleSheet("font-size: 48px; font-weight: bold; color: white;")
            
        # Title
        self.lbl_title = QLabel("RPGMLocalizer")
        self.lbl_title.setStyleSheet("font-size: 24px; font-weight: bold;")
        
        # Version
        self.lbl_version = CaptionLabel(f"Version {VERSION}")
        
        self.v_header.addWidget(self.lbl_icon, 0, Qt.AlignmentFlag.AlignCenter)
        self.v_header.addWidget(self.lbl_title, 0, Qt.AlignmentFlag.AlignCenter)
        self.v_header.addWidget(self.lbl_version, 0, Qt.AlignmentFlag.AlignCenter)
        
        # 2. Description Card
        self.card_desc = CardWidget(self.scrollWidget)
        self.v_desc = QVBoxLayout(self.card_desc)
        
        desc_text = (
            "RPGMLocalizer is an automated translation tool designed for RPG Maker games.\n"
            "It supports RPG Maker XP, VX, VX Ace, MV, and MZ.\n"
            "Using advanced heuristics and Google Translate, it localizes game content while "
            "preserving game scripts and control codes."
        )
        self.lbl_desc = BodyLabel(desc_text, self.card_desc)
        self.lbl_desc.setWordWrap(True)
        
        self.v_desc.addWidget(self.lbl_desc)
        self.v_desc.setContentsMargins(20, 20, 20, 20)
        
        # 3. Actions Card (Support)
        self.card_actions = CardWidget(self.scrollWidget)
        self.v_actions = QVBoxLayout(self.card_actions)
        
        self.lbl_support_title = StrongBodyLabel("Support Development", self.card_actions)
        self.lbl_support_desc = CaptionLabel("If you find this tool useful, consider supporting me on Patreon.", self.card_actions)
        
        self.btn_patreon = PrimaryPushButton(FIF.HEART, "Support on Patreon", self.card_actions)
        self.btn_patreon.clicked.connect(self._open_patreon)
        
        self.v_actions.addWidget(self.lbl_support_title)
        self.v_actions.addWidget(self.lbl_support_desc)
        self.v_actions.addSpacing(10)
        self.v_actions.addWidget(self.btn_patreon)
        self.v_actions.setContentsMargins(20, 20, 20, 20)
        
        # 4. License Info
        self.lbl_license = CaptionLabel("Licensed under GNU GPLv3", self.scrollWidget)
        self.lbl_license.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        import datetime
        current_year = datetime.datetime.now().year
        self.lbl_copyright = CaptionLabel(f"Copyright © {current_year} LordOfTurk. All rights reserved.", self.scrollWidget)
        self.lbl_copyright.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Add to main layout
        self.expandLayout.addLayout(self.v_header)
        self.expandLayout.addSpacing(20)
        self.expandLayout.addWidget(self.card_desc)
        self.expandLayout.addWidget(self.card_actions)
        self.expandLayout.addSpacing(20)
        self.expandLayout.addWidget(self.lbl_license)
        self.expandLayout.addWidget(self.lbl_copyright)
        self.expandLayout.addStretch(1)
        
        # Set main widget
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        
    def _open_patreon(self):
        import webbrowser
        webbrowser.open("https://www.patreon.com/cw/LordOfTurk")

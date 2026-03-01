# -*- mode: python ; coding: utf-8 -*-

import os

project_dir = os.path.abspath(os.getcwd())
icon_path = os.path.join(project_dir, 'icon.ico')

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[project_dir],
    binaries=[],
    datas=[
        (icon_path, '.'),
        (os.path.join(project_dir, 'LICENSE'), '.'),
    ],
    hiddenimports=[
        'src',
        'src.core',
        'src.core.parsers',
        'src.core.parsers.json_parser',
        'src.core.parsers.ruby_parser',
        'src.core.translator',
        'src.core.glossary',
        'src.core.cache',
        'src.core.parser_factory',
        'src.core.enums',
        'src.core.export_import',
        'src.ui',
        'src.ui.main_window',
        'src.ui.components.console_log',
        'src.ui.interfaces.home_interface',
        'src.ui.interfaces.settings_interface',
        'src.ui.interfaces.export_interface',
        'src.ui.interfaces.about_interface',
        'src.ui.interfaces.glossary_interface',
        'src.utils',
        'src.utils.backup',
        'src.utils.paths',
        'src.utils.settings_store',
        'src.utils.placeholder',
        'src.utils.file_ops',
        'rubymarshal',
        'aiohttp',
        'qfluentwidgets',
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'tkinter', 'pandas', 'scipy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='RPGMLocalizer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)

import sys
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='RPGMLocalizer.app',
        icon=icon_path,
        bundle_identifier='com.rpgmlocalizer.app',
        version='0.6.2',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'LSBackgroundOnly': 'False'
        }
    )

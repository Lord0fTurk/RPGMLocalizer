# -*- mode: python ; coding: utf-8 -*-

import os
import sys

from PyQt6.QtCore import QLibraryInfo

spec_path = os.path.abspath(globals().get('SPEC', os.path.join(os.getcwd(), 'RPGMLocalizer.spec')))
project_dir = os.path.dirname(spec_path)
icon_path = os.path.join(project_dir, 'icon.ico')
icon_png_path = os.path.join(project_dir, 'icon.png')
icon_icns_path = os.path.join(project_dir, 'icon.icns')
qt_bin_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.BinariesPath)
software_opengl_dll = os.path.join(qt_bin_dir, 'opengl32sw.dll')

version_ns = {}
with open(os.path.join(project_dir, 'version.py'), 'r', encoding='utf-8') as f:
    exec(f.read(), version_ns)
app_version = version_ns.get('VERSION', '0.6.3')

datas = [
    (os.path.join(project_dir, 'LICENSE'), '.'),
]
if os.path.exists(icon_png_path):
    datas.append((icon_png_path, '.'))
if os.path.exists(icon_path):
    datas.append((icon_path, '.'))

binaries = []
if sys.platform == 'win32' and os.path.exists(software_opengl_dll):
    binaries.append((software_opengl_dll, '.'))

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[project_dir],
    binaries=binaries,
    datas=datas,
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
    icon=icon_path if sys.platform == 'win32' and os.path.exists(icon_path) else None,
)

import sys
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='RPGMLocalizer.app',
        icon=icon_icns_path if os.path.exists(icon_icns_path) else None,
        bundle_identifier='com.rpgmlocalizer.app',
        version=app_version,
        info_plist={
            'NSHighResolutionCapable': 'True',
            'LSBackgroundOnly': 'False'
        }
    )

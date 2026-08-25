# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — 单文件 EXE 打包"""
# Build: pyinstaller build.spec
# 或:    pyinstaller --clean build.spec

import sys
from pathlib import Path

block_cipher = None
APP_NAME = "DBManager"

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('app/resources', 'app/resources'),
    ],
    hiddenimports=[
        'polars',
        'fastexcel',
        'sqlparse',
        'qtawesome',
        'PySide6.QtSvg',
        'PySide6.QtSvgWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib',
        'pandas', 'duckdb',
        'PySide6.QtWebEngine', 'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.Qt3D', 'PySide6.QtCharts',
        'PySide6.QtDataVisualization', 'PySide6.QtMultimedia',
        'PySide6.QtNetwork', 'PySide6.QtSql', 'PySide6.QtTest',
        'PySide6.QtBluetooth', 'PySide6.QtNfc',
        'PySide6.QtPositioning', 'PySide6.QtSensors',
        'PySide6.QtSerialPort', 'PySide6.QtWebSockets',
        'PySide6.QtXml', 'PySide6.QtPdf',
    ],
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
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,   # GUI, no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='app/resources/icons/app.ico',  # 可选
)

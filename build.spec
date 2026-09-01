# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — 单文件 EXE 打包
针对 Python 3.13 + PySide6 6.11:
- 精细白名单(只收必要 PySide6 子集)
- excludes 不碰任何 PySide6 模块(避免误删导致 DLL load failed)
- upx=False 避免压坏 Qt DLL
- collect_data_files 收 polars / fastexcel / shiboken6 的 native 库
Build: pyinstaller --clean build.spec
"""
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None
APP_NAME = "DBManager"

# 必要 PySide6 白名单(包含核心 + QtSvg + QtPrintSupport + QtNetwork)
PYSIDE6_NEEDED = [
    'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
    'PySide6.QtSvg', 'PySide6.QtSvgWidgets', 'PySide6.QtPrintSupport',
    'PySide6.QtNetwork',
    'shiboken6',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('app/resources', 'app/resources'),
        ('app/ui', 'app/ui'),
        ('app/core', 'app/core'),
    ] + collect_data_files('polars', include_py_files=False)
      + collect_data_files('fastexcel', include_py_files=False)
      + collect_data_files('shiboken6', include_py_files=False),
    hiddenimports=[
        'polars', 'fastexcel', 'sqlparse', 'qtawesome',
    ] + PYSIDE6_NEEDED,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 只排除真正无用的大第三方;**绝不 excludes 任何 PySide6 模块**
    excludes=[
        'tkinter', 'matplotlib', 'pandas', 'duckdb',
        'scipy', 'sympy', 'PIL', 'Pillow',
        'PyQt5', 'PyQt6', 'IPython', 'jupyter', 'notebook',
        'numpy.tests', 'numpy.testing', 'numpy.distutils',
        'numpy.f2py', 'numpy.fft.tests', 'numpy.linalg.tests',
        'numpy.random.tests',
        'setuptools', 'pip', 'wheel', 'pkg_resources',
        'test', 'unittest', 'pydoc', 'doctest',
        'email', 'html', 'http', 'xmlrpc', 'pdb',
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
    upx=False,         # 关 UPX(避免压坏 Qt DLL)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

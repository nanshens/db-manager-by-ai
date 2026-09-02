# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — 单文件 EXE 打包
针对 Python 3.13 + PySide6 6.11 + polars 1.44 (native 在 _polars_runtime_32 命名空间包):

核心策略:
- 显式列 binaries 路径(用 sysconfig 找 venv site-packages)
  - 不用 collect_data_files(polars 命名空间包布局会漏)
  - 不用 collect_submodules / collect_all(会把 excludes 拉回来)
- excludes 不碰 PySide6(避免 DLL load failed)
- upx=False(避免压坏 Qt DLL)
- hiddenimports 精确列出
"""
import sys
import os
import sysconfig
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
APP_NAME = "DBManager"

# venv site-packages 路径(显式,不靠 collect_data_files)
SITE_PACKAGES = Path(sysconfig.get_paths()['purelib'])
PYSIDE6_DIR = SITE_PACKAGES / 'PySide6'
SHIBOKEN6_DIR = SITE_PACKAGES / 'shiboken6'
POLARS_RUNTIME_DIR = SITE_PACKAGES / '_polars_runtime_32'
FASTEXCEL_DIR = SITE_PACKAGES / 'fastexcel'


def _gather_dlls(directory: Path, pattern: str = '*.dll') -> list[tuple[str, str]]:
    """收集目录下所有匹配 pattern 的 DLL,返回 [(src, dest_subdir)] 列表"""
    if not directory.is_dir():
        return []
    return [(str(p), str(p.parent.name)) for p in directory.glob(pattern)]


def _first_existing(*paths) -> Path | None:
    for p in paths:
        if p.is_file():
            return p
    return None


# 显式列所有需要的二进制文件
binaries: list[tuple[str, str]] = []

# PySide6 Qt6 DLL(显式列核心,hook 也会自动加)
for dll_name in ('Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Widgets.dll',
                 'Qt6Svg.dll', 'Qt6SvgWidgets.dll', 'Qt6PrintSupport.dll',
                 'Qt6Network.dll', 'pyside6.abi3.dll'):
    src = PYSIDE6_DIR / dll_name
    if src.is_file():
        binaries.append((str(src), 'PySide6'))

# shiboken6
for dll_name in ('shiboken6.abi3.dll',):
    src = SHIBOKEN6_DIR / dll_name
    if src.is_file():
        binaries.append((str(src), 'shiboken6'))

# polars native(.pyd 在 _polars_runtime_32 命名空间包)
for pyd_name in ('_polars_runtime.pyd',):
    src = POLARS_RUNTIME_DIR / pyd_name
    if src.is_file():
        binaries.append((str(src), '_polars_runtime_32'))

# fastexcel native
for pyd_name in ('_fastexcel.pyd',):
    src = FASTEXCEL_DIR / pyd_name
    if src.is_file():
        binaries.append((str(src), 'fastexcel'))

# hiddenimports:精确列出,避免 collect_submodules 把 excludes 拉回来
PYSIDE6_NEEDED = [
    'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
    'PySide6.QtSvg', 'PySide6.QtSvgWidgets', 'PySide6.QtPrintSupport',
    'PySide6.QtNetwork', 'shiboken6',
]

# polars 内部子模块(动态加载,需要 hiddenimports)
POLARS_NEEDED = collect_submodules('polars')

FASTEXCEL_NEEDED = collect_submodules('fastexcel')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=[
        ('app/resources', 'app/resources'),
        ('app/ui', 'app/ui'),
        ('app/core', 'app/core'),
    ],
    hiddenimports=[
        'sqlparse', 'qtawesome',
        'polars', 'fastexcel',
    ] + PYSIDE6_NEEDED + POLARS_NEEDED + FASTEXCEL_NEEDED,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 只排除真正大且不用的第三方;**绝不 excludes 任何 PySide6 模块**
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

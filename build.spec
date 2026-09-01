# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — 单文件 EXE 打包
针对 Python 3.13 + PySide6 6.11 优化:
- 关闭 UPX(避免压坏 Qt DLL)
- excludes 加宽(去掉 numpy.testing / PyQt5 / IPython / setuptools 等无用包)
- 用 collect_data_files 收 polars / fastexcel / shiboken6 的 native 库
- hiddenimports 显式列 PySide6 必要子集(避免 collect_submodules 把 excludes 拉回来)
Build: pyinstaller --clean build.spec
"""
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
APP_NAME = "DBManager"

# 必要 PySide6 子集(白名单,避免 collect 把 excludes 拉回来)
PYSIDE6_NEEDED = [
    'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
    'PySide6.QtSvg', 'PySide6.QtSvgWidgets', 'PySide6.QtPrintSupport',
    'PySide6.QtNetwork',  # 一些 Qt 内部用
    'shiboken6',
]
# polars / fastexcel 显式子集(不 collect 全部,避免拉回 numpy.testing 等)
POLARS_NEEDED = [
    'polars', 'polars._cpu_lz4_dec', 'polars._cpu_lz4_enc',
    'polars._zstd_compress', 'polars._zstd_decompress',
    'polars.polars', 'polars._polars_runtime_ffi',
    'fastexcel', 'fastexcel.fastexcel',
]

# 收齐 native 数据文件(.pyd / .dll / .so)
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
    ] + PYSIDE6_NEEDED + POLARS_NEEDED,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 排除无用大包(减肥)
    excludes=[
        # 巨型无用第三方
        'tkinter', 'matplotlib', 'pandas', 'duckdb',
        'scipy', 'sympy', 'PIL', 'Pillow',
        'PyQt5', 'PyQt6', 'IPython', 'jupyter', 'notebook',
        'numpy.tests', 'numpy.testing', 'numpy.distutils',
        'numpy.f2py', 'numpy.fft.tests', 'numpy.linalg.tests',
        'numpy.random.tests',
        'setuptools', 'pip', 'wheel', 'pkg_resources',
        'test', 'unittest', 'pydoc', 'doctest',
        # PySide6 大模块(我们用不到)
        'PySide6.QtWebEngine', 'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets', 'PySide6.Qt3D',
        'PySide6.Qt3DCore', 'PySide6.Qt3DRender',
        'PySide6.QtCharts', 'PySide6.QtDataVisualization',
        'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
        'PySide6.QtNetworkAuth',
        'PySide6.QtSql', 'PySide6.QtTest',
        'PySide6.QtBluetooth', 'PySide6.QtNfc',
        'PySide6.QtPositioning', 'PySide6.QtSensors',
        'PySide6.QtSerialPort', 'PySide6.QtWebSockets',
        'PySide6.QtXml', 'PySide6.QtPdf',
        'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuick3D',
        'PySide6.QtQuickWidgets', 'PySide6.QtRemoteObjects',
        'PySide6.QtScxml', 'PySide6.QtStateMachine',
        'PySide6.QtTextToSpeech', 'PySide6.QtWebChannel',
        'PySide6.QtDBus', 'PySide6.QtDesigner',
        'PySide6.QtHelp', 'PySide6.QtLocation', 'PySide6.QtOpenGL',
        'PySide6.QtConcurrent', 'PySide6.QtSvg',
        # stdlib 无用
        'email', 'html', 'http', 'unittest', 'xmlrpc',
        'pdb',
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
    upx=False,         # 关 UPX(UPX 经常压坏 Qt DLL,导致 "DLL load failed")
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,     # GUI, no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='app/resources/icons/app.ico',  # 可选
)

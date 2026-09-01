"""跨平台路径解析"""
from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path


APP_NAME = "DBManager"


def _data_root() -> Path:
    """应用数据根目录。

    优先级:
    1. 环境变量 DBMANAGER_DATA_DIR 显式覆盖(测试 / 临时目录用)
    2. PyInstaller 打包后 (`sys.frozen`):exe 同目录下的 `DBManagerData/`,方便打包传输
    3. 开发模式:OS 标准位置
       - Windows: %APPDATA%/DBManager
       - macOS:  ~/Library/Application Support/DBManager
       - Linux:  $XDG_DATA_HOME/DBManager 或 ~/.local/share/DBManager
    """
    override = os.environ.get("DBMANAGER_DATA_DIR")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        # 打包后(单文件 exe 或 one-folder):走 exe 同目录,便于复制/打包传输
        return Path(sys.executable).parent / f"{APP_NAME}Data"
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / APP_NAME


def app_data_dir() -> Path:
    """工具自身数据目录(配置文件、SQLite DB、i18n 缓存)"""
    return _data_root()


def db_path() -> Path:
    return app_data_dir() / "dbmanager.db"


def log_path() -> Path:
    return app_data_dir() / "dbmanager.log"


def ensure_dirs() -> None:
    app_data_dir().mkdir(parents=True, exist_ok=True)

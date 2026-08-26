"""跨平台路径解析"""
from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path


APP_NAME = "DBManager"


def _data_root() -> Path:
    """应用数据根目录。

    默认走 OS 标准位置;但 DBMANAGER_DATA_DIR 可以覆盖 — 测试场景用临时目录。
    """
    override = os.environ.get("DBMANAGER_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roading"))
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

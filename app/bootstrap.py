"""启动初始化:日志 + DB + 服务注册中心"""
from __future__ import annotations
import logging
from pathlib import Path

from app.paths import ensure_dirs, db_path, log_path
from app import config as app_config
from app.services.registry import Registry


def setup_logging() -> None:
    ensure_dirs()
    log_file = log_path()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("PySide6").setLevel(logging.WARNING)


def bootstrap() -> tuple[Path, str, str, Registry]:
    """应用启动初始化;返回 (db_path, theme, lang, registry)"""
    setup_logging()
    ensure_dirs()

    db = db_path()
    registry = Registry.init(db)
    logging.info(f"DB initialized: {db}")
    logging.info(f"Services registered: project/table/version/sql/cmp-config/excel/diff")

    theme = app_config.get_theme()
    lang = app_config.get_lang()
    logging.info(f"Config: theme={theme}, lang={lang}, sidebar={app_config.get_sidebar()}")

    return db, theme, lang, registry

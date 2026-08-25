"""QSS 主题加载 + 应用"""
from __future__ import annotations
from pathlib import Path
from PySide6.QtWidgets import QApplication


def qss_dir() -> Path:
    dev = Path(__file__).resolve().parent.parent / "resources" / "qss"
    if dev.exists():
        return dev
    from app.paths import app_data_dir
    return app_data_dir() / "qss"


def load_qss(theme: str) -> str:
    """加载指定主题的 QSS;失败返回空字符串"""
    if theme not in ("dark", "light"):
        theme = "dark"
    path = qss_dir() / f"{theme}.qss"
    if not path.exists():
        print(f"[theme] QSS not found: {path}")
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"[theme] Failed to load QSS: {e}")
        return ""


def apply_theme(app: QApplication, theme: str) -> None:
    """应用主题到 QApplication"""
    qss = load_qss(theme)
    app.setStyleSheet(qss)

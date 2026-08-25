"""DBManager — 入口"""
from __future__ import annotations
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from app.bootstrap import bootstrap
from app.ui import i18n, theme as theme_mod
from app.ui.main_window import MainWindow
from app.ui.native_chrome import apply_titlebar_theme
from app import config as app_config


def _setup_app() -> QApplication:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QApplication.setOrganizationName("DBManager")
    QApplication.setApplicationName("DBManager")
    app = QApplication(sys.argv)
    # 字体:Segoe UI + 中文 fallback
    font = QFont("Microsoft YaHei UI, Microsoft YaHei, Segoe UI, PingFang SC", 10)
    app.setFont(font)
    return app


def main() -> int:
    # 1) 启动初始化
    try:
        db_path, init_theme, init_lang, _registry = bootstrap()
    except Exception as e:
        traceback.print_exc()
        QMessageBox.critical(None, "DBManager 启动失败", f"初始化失败:\n{e}")
        return 1

    # 2) 加载 i18n
    i18n.load(init_lang)

    # 3) 创建 QApplication
    app = _setup_app()

    # 4) 应用主题
    theme_mod.apply_theme(app, init_theme)

    # 5) 创建主窗口
    win = MainWindow(initial_theme=init_theme, initial_lang=init_lang)

    # 6) 连接主题/语言切换
    def on_theme_change(theme: str) -> None:
        theme_mod.apply_theme(app, theme)
        win.set_theme_external(theme)
        apply_titlebar_theme(win, theme)  # 同步原生标题栏
        app_config.set_theme(theme)

    def on_lang_change(lang: str) -> None:
        i18n.load(lang)
        win.set_lang_external(lang)
        app_config.set_lang(lang)

    win.theme_change_requested.connect(on_theme_change)
    win.language_change_requested.connect(on_lang_change)

    # 7) 显示
    win.show()
    apply_titlebar_theme(win, init_theme)  # 启动时把原生标题栏染深/染浅

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

"""冒烟测试 — 启动后模拟一些操作,看是否崩溃"""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.bootstrap import bootstrap
from app.ui import i18n, theme as theme_mod
from app.ui.main_window import MainWindow
from app.services.registry import reg
from app.repos.project_repo import Project


def main():
    print("=== 启动 ===")
    db_path, theme, lang, registry = bootstrap()
    i18n.load(lang)

    app = QApplication(sys.argv)
    theme_mod.apply_theme(app, theme)
    win = MainWindow(initial_theme=theme, initial_lang=lang)
    win.show()
    QApplication.processEvents()
    print(f"window: {win.windowTitle()}, {win.size().width()}x{win.size().height()}")
    print(f"pages: {win.stack.count()}")
    print(f"nav: {len(win.nav_buttons)}")
    print(f"db tables ready")

    # 测试创建项目
    print("\n=== 创建项目 ===")
    try:
        p = registry.project_service.create(
            "测试项目", "自动化测试", "#3b82f6"
        )
        print(f"created project: id={p.id}, name={p.name}")
    except Exception as e:
        print(f"create error: {e}")
        return 1

    # 测试创建表
    print("\n=== 创建表 ===")
    try:
        from app.repos.table_repo import Column
        t = registry.table_service.create(
            p.id, "users", "用户表",
            [Column(name="id", type="INTEGER", nullable=False, pk=True),
             Column(name="email", type="VARCHAR(100)"),
             Column(name="created_at", type="DATETIME")],
        )
        print(f"created table: id={t.id}, name={t.name}, cols={len(t.columns)}")
    except Exception as e:
        print(f"create table error: {e}")
        return 1

    # 测试 SQL 库
    print("\n=== 创建 SQL 片段 ===")
    try:
        s = registry.sql_lib_service.create(
            "查用户", "SELECT * FROM users WHERE id = ?", "查单个用户", "user,select", None
        )
        print(f"created snippet: id={s.id}, title={s.title}")
    except Exception as e:
        print(f"create snippet error: {e}")
        return 1

    # 测试 Excel 模板
    print("\n=== 创建 Excel 模板 ===")
    try:
        t = registry.excel_template_service.create(
            None, "财务季度初版", "总览", "A", "B", 2, 3, "测试"
        )
        print(f"created template: id={t.id}, name={t.template_name}")
    except Exception as e:
        print(f"create template error: {e}")
        return 1

    # 测试对比配置
    print("\n=== 创建对比配置 ===")
    try:
        from app.repos.compare_config_repo import CompareConfig
        c = registry.compare_config_service.create(
            p.id, "users", "忽略时间",
            pk_columns=["id"],
            compare_columns=["id", "email"],
            ignore_columns=["created_at"],
            case_sensitive=False, trim_whitespace=True, is_default=True,
        )
        print(f"created compare config: id={c.id}, name={c.config_name}")
    except Exception as e:
        print(f"create compare config error: {e}")
        return 1

    # 切换到项目详情
    print("\n=== 打开项目详情 ===")
    win._open_project(p.id)
    QApplication.processEvents()
    print(f"stack current index: {win.stack.currentIndex()}")

    # 切换页 + 主题 + 语言
    print("\n=== 切换主题/语言/页 ===")
    win._toggle_theme()  # dark → light
    QApplication.processEvents()
    print(f"theme: {win.current_theme()}")
    win._toggle_theme()  # light → dark
    QApplication.processEvents()

    win._cycle_language()  # zh → en
    QApplication.processEvents()
    print(f"lang: {win.current_lang()}")
    win._cycle_language()  # en → ja
    QApplication.processEvents()
    win._cycle_language()  # ja → zh
    QApplication.processEvents()

    # 切换所有页
    from app.ui.main_window import PageId
    for pid in [PageId.HOME, PageId.PROJECTS, PageId.SQLLIB, PageId.EXCEL_TPL, PageId.SETTINGS]:
        win._switch_page(pid)
        QApplication.processEvents()
        print(f"switched to {pid.value}")

    # 刷新所有页(模拟重新进入项目)
    print("\n=== 刷新所有页 ===")
    win.projects_page.refresh()
    win.home_page.refresh()
    win.sqllib_page.refresh()
    win.excel_tpl_page.refresh()
    win._open_project(p.id)
    QApplication.processEvents()
    print("all pages refreshed")

    # 折叠侧边栏
    print("\n=== 折叠侧边栏 ===")
    win._toggle_sidebar()
    QApplication.processEvents()
    print(f"sidebar: {win.sidebar.width()}px (collapsed: {win._is_collapsed})")
    win._toggle_sidebar()
    QApplication.processEvents()
    print(f"sidebar: {win.sidebar.width()}px (collapsed: {win._is_collapsed})")

    # 关
    QTimer.singleShot(100, app.quit)
    print("\n=== 全部通过 ===")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main() or 0)

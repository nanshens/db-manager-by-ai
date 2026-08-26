"""生成多张 UI 截图"""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
# 截图用唯一临时 DB
os.environ['DBMANAGER_DATA_DIR'] = os.path.join(
    os.environ.get('TEMP', '.'),
    f'dbmanager_screenshot_{os.getpid()}'
)
import sys
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.bootstrap import bootstrap
from app.ui import i18n, theme as theme_mod
from app.ui.main_window import MainWindow, PageId
from app.services.registry import reg
from app.repos.table_repo import Column

OUT_DIR = Path(r"D:\project\ai\dbmanager\screenshots")
OUT_DIR.mkdir(exist_ok=True)


def grab(widget, name: str):
    widget.repaint()
    QApplication.processEvents()
    img = widget.grab().toImage()
    path = OUT_DIR / f"{name}.png"
    img.save(str(path), "PNG")
    print(f"  {name}.png ({path.stat().st_size // 1024} KB)")


def main():
    db_path, theme, lang, _ = bootstrap()
    i18n.load(lang)
    app = QApplication(sys.argv)
    theme_mod.apply_theme(app, theme)
    win = MainWindow(initial_theme=theme, initial_lang=lang)

    def on_theme_change(t):
        theme_mod.apply_theme(app, t)
        win.set_theme_external(t)
    def on_lang_change(l):
        i18n.load(l)
        win.set_lang_external(l)
    win.theme_change_requested.connect(on_theme_change)
    win.language_change_requested.connect(on_lang_change)

    win.resize(1400, 850)
    win.show()
    QApplication.processEvents()

    # 创建测试数据
    p1 = reg().project_service.create("电商核心库", "订单/商品/库存主表", "#3b82f6")
    p2 = reg().project_service.create("用户中心", "用户/权限/组织", "#a855f7")
    p3 = reg().project_service.create("CRM 系统", "客户/线索/商机", "#10b981")

    reg().table_service.create(p1.id, "orders", "订单主表", [
        Column(name="id", type="INTEGER", nullable=False, pk=True),
        Column(name="user_id", type="BIGINT", nullable=False),
        Column(name="total_amount", type="DECIMAL(10,2)"),
        Column(name="status", type="VARCHAR(20)"),
        Column(name="created_at", type="DATETIME"),
    ])
    reg().table_service.create(p1.id, "products", "商品表", [
        Column(name="id", type="INTEGER", nullable=False, pk=True),
        Column(name="name", type="VARCHAR(200)"),
        Column(name="price", type="DECIMAL(10,2)"),
        Column(name="stock", type="INTEGER"),
    ])

    reg().sql_lib_service.create(
        "查今日订单", "SELECT * FROM orders WHERE created_at >= CURRENT_DATE",
        "查所有今日下的订单", "orders, daily", p1.id,
    )
    reg().sql_lib_service.create(
        "清空测试数据", "TRUNCATE TABLE test_orders;",
        "小心使用", "danger, ddl", None,
    )

    reg().excel_template_service.create(
        p1.id, "财务季度初版", "总览", "A", "B", 2, 3, "5 张表"
    )
    reg().excel_template_service.create(
        None, "通用日报", "目录", "表名", "Sheet", 1, 2, "通用格式"
    )

    reg().compare_config_service.create(
        p1.id, "orders", "忽略时间列",
        pk_columns=["id"],
        compare_columns=["id", "user_id", "total_amount", "status"],
        ignore_columns=["created_at"],
        case_sensitive=False, trim_whitespace=True, is_default=True,
    )

    win.projects_page.refresh()
    win.sqllib_page.refresh()
    win.excel_tpl_page.refresh()
    QApplication.processEvents()

    # 截图 — 默认就停在项目页
    grab(win, "01_projects_dark")

    # 演示搜索行为(测试修复后的搜索)
    win.projects_page.search.setText("CRM")
    QApplication.processEvents()
    grab(win, "02_projects_search")
    win.projects_page.search.clear()

    win._open_project(p1.id)
    QApplication.processEvents()
    QTimer.singleShot(50, lambda: None)
    QApplication.processEvents()
    grab(win, "03_project_detail_dark")

    win._switch_page(PageId.SQLLIB)
    QApplication.processEvents()
    grab(win, "04_sqllib_dark")

    win._switch_page(PageId.EXCEL_TPL)
    QApplication.processEvents()
    grab(win, "05_excel_dark")

    # Light
    win._on_theme_change_requested("light")
    win._switch_page(PageId.PROJECTS)
    QApplication.processEvents()
    grab(win, "06_projects_light")

    # English
    win._on_theme_change_requested("dark")
    win._on_language_change_requested("en")
    win._switch_page(PageId.PROJECTS)
    QApplication.processEvents()
    grab(win, "07_projects_en")

    # Japanese
    win._on_language_change_requested("ja")
    QApplication.processEvents()
    grab(win, "08_projects_ja")

    # Back to zh
    win._on_language_change_requested("zh")
    QApplication.processEvents()
    grab(win, "09_projects_zh")

    # Sidebar collapsed
    win._toggle_sidebar()
    win._switch_page(PageId.PROJECTS)
    QApplication.processEvents()
    QTimer.singleShot(300, lambda: None)
    QApplication.processEvents()
    grab(win, "10_sidebar_collapsed")

    # Detail page - tables tab
    win._toggle_sidebar()
    win._open_project(p1.id)
    QApplication.processEvents()
    QTimer.singleShot(50, lambda: None)
    QApplication.processEvents()
    grab(win, "11_detail_tables")

    # Detail page - sqlgen tab
    win.project_detail_page.tabs.setCurrentIndex(2)
    QApplication.processEvents()
    grab(win, "12_detail_sqlgen")

    QTimer.singleShot(100, app.quit)
    return app.exec()


if __name__ == "__main__":
    rc = main()
    print(f"Done. Exit code: {rc}")

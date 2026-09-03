"""DBManager 项目结构生成器

用途:在另一台电脑(无 venv / 无依赖)快速建立完整项目结构(空文件占位),
后续按文件名自己 copy 代码填充。

用法:
    python init_project.py [目标目录]
    # 不传参数 → 当前目录下创建 dbmanager/ 子目录
    # 传参数   → 在指定目录下创建项目(目录必须已存在)

特性:
- 0 字节占位文件(用户自己填代码,不会和真实内容冲突)
- 跨平台(Windows / macOS / Linux)
- 纯 stdlib,无任何依赖
- 已存在的文件**不覆盖**(让你可以增量填)
- 输出每个文件的创建状态
"""
from __future__ import annotations
import sys
from pathlib import Path

# ============================================================
# 完整文件清单(相对项目根)
# ============================================================
FILES: list[str] = [
    # ---- 根 ----
    ".gitignore",
    "main.py",
    "build.bat",
    "build.spec",
    "run.bat",
    "README.md",
    "requirements.txt",
    "requirements2.txt",

    # ---- app/ 包 ----
    "app/__init__.py",
    "app/bootstrap.py",
    "app/config.py",
    "app/paths.py",
    "app/native_chrome.py",   # 如果你那边有
    # app/core/
    "app/core/__init__.py",
    "app/core/ddl_parser.py",
    "app/core/diff_engine.py",
    "app/core/excel_parser.py",
    "app/core/file_convert.py",
    "app/core/file_reader.py",
    "app/core/sql_vocab.py",
    "app/core/sqlgen.py",
    # app/repos/
    "app/repos/__init__.py",
    "app/repos/compare_config_repo.py",
    "app/repos/data_version_repo.py",
    "app/repos/db.py",
    "app/repos/db_link_repo.py",
    "app/repos/diff_record_repo.py",
    "app/repos/excel_template_repo.py",
    "app/repos/project_repo.py",
    "app/repos/sql_snippet_repo.py",
    "app/repos/table_repo.py",
    # app/services/
    "app/services/__init__.py",
    "app/services/compare_config_service.py",
    "app/services/data_version_service.py",
    "app/services/diff_service.py",
    "app/services/excel_template_service.py",
    "app/services/project_service.py",
    "app/services/registry.py",
    "app/services/sql_lib_service.py",
    "app/services/table_service.py",
    # app/ui/
    "app/ui/__init__.py",
    "app/ui/i18n.py",
    "app/ui/main_window.py",
    "app/ui/theme.py",
    # app/ui/dialogs/
    "app/ui/dialogs/__init__.py",
    "app/ui/dialogs/column_editor_dialog.py",
    "app/ui/dialogs/compare_config_dialog.py",
    "app/ui/dialogs/excel_parse_dialog.py",
    "app/ui/dialogs/excel_template_dialog.py",
    "app/ui/dialogs/import_sql_dialog.py",
    "app/ui/dialogs/new_project_dialog.py",
    "app/ui/dialogs/new_version_dialog.py",
    "app/ui/dialogs/schema_check_dialog.py",
    "app/ui/dialogs/sql_snippet_dialog.py",
    "app/ui/dialogs/table_dialog.py",
    # app/ui/pages/
    "app/ui/pages/__init__.py",
    "app/ui/pages/base_page.py",
    "app/ui/pages/db_links_page.py",
    "app/ui/pages/excel_templates_page.py",
    "app/ui/pages/file_convert_page.py",
    "app/ui/pages/project_detail_page.py",
    "app/ui/pages/projects_page.py",
    "app/ui/pages/settings_page.py",
    "app/ui/pages/sqllib_page.py",
    "app/ui/pages/__deprecated_home_page.py.bak",  # 旧版备份(如有)
    # app/ui/pages/project_detail/
    "app/ui/pages/project_detail/__init__.py",
    "app/ui/pages/project_detail/diff_tab.py",
    "app/ui/pages/project_detail/overview_tab.py",
    "app/ui/pages/project_detail/sqlgen_tab.py",
    "app/ui/pages/project_detail/tables_tab.py",
    "app/ui/pages/project_detail/versions_tab.py",
    # app/ui/widgets/
    "app/ui/widgets/__init__.py",
    "app/ui/widgets/empty_state.py",
    "app/ui/widgets/sql_autocomplete.py",
    "app/ui/widgets/syntax_highlight.py",
    "app/ui/widgets/toast.py",

    # ---- app/resources/ ----
    "app/resources/i18n/en.json",
    "app/resources/i18n/ja.json",
    "app/resources/i18n/zh.json",
    "app/resources/qss/dark.qss",
    "app/resources/qss/light.qss",

    # ---- docs/ ----
    "docs/DEV_DOC.md",
    "docs/DEV_DOC.html",
]


# ============================================================
# 主体逻辑
# ============================================================
def main() -> int:
    if len(sys.argv) > 1:
        target = Path(sys.argv[1]).resolve()
        if not target.is_dir():
            print(f"ERROR: 目标目录不存在: {target}")
            return 1
    else:
        target = Path.cwd() / "dbmanager"
        target.mkdir(parents=True, exist_ok=True)
        print(f"未指定目标目录,在当前目录下创建: {target}")

    print(f"开始生成项目结构 → {target}")
    print("-" * 60)

    created = 0
    skipped = 0
    for relpath in FILES:
        fp = target / relpath
        fp.parent.mkdir(parents=True, exist_ok=True)
        if fp.exists():
            skipped += 1
            print(f"  [skip] {relpath}  (已存在)")
        else:
            fp.touch()  # 0 字节占位
            created += 1
            print(f"  [new]  {relpath}")

    print("-" * 60)
    print(f"完成:新建 {created} 个文件,跳过 {skipped} 个(已存在)")
    print(f"目录: {target}")
    print()
    print("下一步:")
    print("  1. 在 venv 里 pip install -r requirements.txt")
    print("  2. 按文件名顺序 copy 真实代码到对应文件")
    print("  3. python main.py 跑起来")
    return 0


if __name__ == "__main__":
    sys.exit(main())

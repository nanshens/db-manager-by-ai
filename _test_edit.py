"""测一下 TableDialog 编辑入口 — 走 import 流程创建一张表,再打开编辑弹窗"""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['DBMANAGER_DATA_DIR'] = os.path.join(os.environ.get('TEMP', '.'), f'dbmanager_e2e_{os.getpid()}')

import sys
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))

from PySide6.QtWidgets import QApplication
from app.bootstrap import bootstrap
from app.services.registry import reg
from app.repos.table_repo import Column
from app.ui.dialogs import TableDialog
from app.core.ddl_parser import parse_ddl_text


SAMPLE = """
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL
);
"""


def main():
    db, theme, lang, _ = bootstrap()
    app = QApplication(sys.argv)
    proj = reg().project_service.create("e2e_edit", "edit test", "#3b82f6")

    # 走解析+创建流程
    tables, _ = parse_ddl_text(SAMPLE, "postgres")
    pt = tables[0]
    cols = [Column(name=c.name, type=c.type, nullable=c.nullable,
                   default=c.default, pk=c.pk, comment=c.comment) for c in pt.columns]
    created = reg().table_service.create(proj.id, pt.name, "", cols)
    print(f"created: {created.name}  id={created.id}")

    # 模拟双击 — 打开编辑弹窗
    print("opening edit dialog...")
    dlg = TableDialog(table=created, project_id=proj.id)
    print(f"  dialog opened OK, title={dlg.windowTitle()}")
    print(f"  current name: {dlg.name_edit.text()}")
    print(f"  column count: {dlg.col_table.rowCount()}")
    dlg.close()
    print("edit dialog test PASSED")


if __name__ == "__main__":
    main()

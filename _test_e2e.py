"""_test_e2e.py — 端到端测试: 解析 SQL → 调用 service.create → 验证表入库"""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['DBMANAGER_DATA_DIR'] = os.path.join(os.environ.get('TEMP', '.'), 'dbmanager_e2e')

import sys
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))

from app.core.ddl_parser import parse_ddl_text
from app.bootstrap import bootstrap
from app.services.registry import reg
from app.repos.table_repo import Column


SAMPLE = """
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL,
    age INTEGER DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    total NUMERIC(10,2) NOT NULL,
    note TEXT
);

CREATE TABLE order_items (
    item_id INTEGER NOT NULL,
    order_id INTEGER NOT NULL,
    qty INTEGER NOT NULL,
    PRIMARY KEY (item_id, order_id)
);
"""


def main():
    db, theme, lang, _ = bootstrap()
    proj = reg().project_service.create("e2e_test", "import test", "#3b82f6")
    print(f"created project: {proj.id}")

    tables, errs = parse_ddl_text(SAMPLE, "postgres")
    print(f"parsed {len(tables)} tables, {len(errs)} errors")
    for t in tables:
        cols = [Column(name=c.name, type=c.type, nullable=c.nullable,
                       default=c.default, pk=c.pk, comment=c.comment) for c in t.columns]
        try:
            created = reg().table_service.create(proj.id, t.name, "", cols)
            print(f"  OK  {created.name}  ({len(created.columns)} cols)")
        except Exception as e:
            print(f"  FAIL {t.name}: {e}")

    listed = reg().table_service.list_by_project(proj.id)
    print(f"\nproject now has {len(listed)} tables:")
    for t in listed:
        print(f"  - {t.name} ({len(t.columns)} cols)")


if __name__ == "__main__":
    main()

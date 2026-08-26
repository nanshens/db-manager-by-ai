"""_test_ddl.py — 测一下 DDL parser"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))

from app.core.ddl_parser import parse_ddl_text

sample = """
-- 用户表
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL,
    age INTEGER DEFAULT 0,
    bio TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deletedAt" TIMESTAMP
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    total NUMERIC(10,2) NOT NULL,
    note TEXT,
    PRIMARY KEY (id),
    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE order_items (
    item_id INTEGER NOT NULL,
    order_id INTEGER NOT NULL,
    qty INTEGER NOT NULL,
    PRIMARY KEY (item_id, order_id)
);

CREATE TABLE products (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '产品 ID',
    name VARCHAR(200) NOT NULL COMMENT '产品名',
    price DECIMAL(10,2) NOT NULL
);

-- 注释和无用语句忽略
SELECT * FROM foo;
INSERT INTO bar VALUES (1);
"""

for dialect in ("postgres", "mysql", "oracle"):
    print(f"\n========== {dialect} ==========")
    tables, errs = parse_ddl_text(sample, dialect)
    print(f"parsed: {len(tables)}, errors: {len(errs)}")
    for t in tables:
        print(f"\n  Table: {t.name}  (err: {t.parse_error or '—'})")
        for c in t.columns:
            print(f"    {c.name:20s} {c.type:25s} null={c.nullable!s:5s} pk={c.pk!s:5s} default={c.default!r:15s} comment={c.comment!r}")
    for e in errs:
        print(f"  ERR: {e}")

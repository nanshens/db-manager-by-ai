"""Debug DDL parser"""
import sqlparse
from app.core.ddl_parser import _parse_one, _clean, _CREATE_RE

sample = '''CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL,
    age INTEGER DEFAULT 0,
    bio TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deletedAt" TIMESTAMP
);

CREATE TABLE orders ( id INT PRIMARY KEY );'''
stmts = sqlparse.split(sample)
print(f'got {len(stmts)} statements')
for i, s in enumerate(stmts):
    s = s.strip().rstrip(";").strip()
    if not s:
        print(f'--- stmt[{i}] (empty) ---')
        continue
    print(f'--- stmt[{i}] starts with CREATE? {s.upper().startswith("CREATE")} ---')
    print(f'  first 80 chars: {s[:80]!r}')
    t = _parse_one(s)
    if t:
        print(f'  -> {t.name}, {len(t.columns)} cols, err={t.parse_error!r}')
    else:
        print(f'  -> None')

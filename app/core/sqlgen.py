"""SQL 批量生成(纯函数,无 Qt / DB 依赖)"""
from __future__ import annotations
from typing import Iterable


def _quote_ident(s: str) -> str:
    """Postgres / MySQL 通用:反引号 / 双引号包裹标识符"""
    if not s:
        return '""'
    # 简单判断:全字母数字下划线且不以数字开头 → 不引
    if s.replace("_", "").isalnum() and not s[0].isdigit():
        return s
    return '"' + s.replace('"', '""') + '"'


def _value(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def generate_insert(table: str, columns: Iterable[str], placeholder: str = "?",
                    batch_size: int = 1) -> str:
    """生成 INSERT 模板;placeholder: ? / %(name)s / '{val}'"""
    cols = list(columns)
    quoted_cols = ", ".join(_quote_ident(c) for c in cols)
    if placeholder == "?":  # 参数化
        placeholders = "(" + ", ".join(["?"] * len(cols)) + ")"
    elif placeholder == "%(name)s":  # psycopg2 风格
        placeholders = "(" + ", ".join(f"%({c})s" for c in cols) + ")"
    else:  # 字面值
        placeholders = "(" + ", ".join(["'value'"] * len(cols)) + ")"
    return f"INSERT INTO {_quote_ident(table)} ({quoted_cols}) VALUES {placeholders};"


def generate_delete(table: str, pk_column: str = "id") -> str:
    return f"DELETE FROM {_quote_ident(table)} WHERE {_quote_ident(pk_column)} = ?;"


def generate_copy(table: str, columns: Iterable[str], file_path: str) -> str:
    """PostgreSQL COPY FROM csv"""
    cols = ", ".join(_quote_ident(c) for c in columns)
    return f"COPY {_quote_ident(table)} ({cols}) FROM '{file_path}' (FORMAT csv, HEADER true);"


def generate_csv_export(table: str, columns: Iterable[str], file_path: str) -> str:
    """PostgreSQL COPY TO csv"""
    cols = ", ".join(_quote_ident(c) for c in columns)
    return f"COPY {_quote_ident(table)} ({cols}) TO '{file_path}' (FORMAT csv, HEADER true);"


def generate_bulk_insert_pg(table: str, columns: Iterable[str], values: list[list]) -> str:
    """PostgreSQL 风格多行 INSERT(values 是数据)"""
    cols = list(columns)
    col_list = ", ".join(_quote_ident(c) for c in cols)
    val_rows = []
    for row in values:
        val_rows.append("(" + ", ".join(_value(v) for v in row) + ")")
    return f"INSERT INTO {_quote_ident(table)} ({col_list}) VALUES\n  " + ",\n  ".join(val_rows) + ";"

"""SQL 重新生成(纯函数,不依赖 Qt / DB)"""
from __future__ import annotations
from typing import Iterable


def _quote_ident(s: str) -> str:
    """Postgres / MySQL 通用:反引号/双引号包标识符"""
    if not s:
        return '""'
    # 简单判断:全字数/数字/下划线且不以数字开头 → 不引
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
    if placeholder == "?":
        placeholders = "(" + ", ".join(["?"] * len(cols)) + ")"
    elif placeholder == "%(name)s":
        placeholders = "(" + ", ".join(f"%({c})s" for c in cols) + ")"
    else:  # 字面值
        placeholders = "(" + ", ".join(["'value'"] * len(cols)) + ")"
    return f"INSERT INTO {_quote_ident(table)} ({quoted_cols}) VALUES {placeholders};"


def generate_delete(table: str, pk_column: str = "id") -> str:
    return f"DELETE FROM {_quote_ident(table)} WHERE {_quote_ident(pk_column)} = ?;"


# ---------------------------------------------------------------------------
# COPY (PostgreSQL) — Import / Export CSV/TSV
# ---------------------------------------------------------------------------
def _format_options(fmt: str, with_header: bool) -> str:
    """FORMAT csv/HEADER true/DELIMITER E'\\t' 这种 options 字符串。"""
    parts = [f"FORMAT {fmt}"]
    if with_header:
        parts.append("HEADER")
    if fmt == "tsv":
        parts.append(r"DELIMITER E'\t'")
    return "(" + ", ".join(parts) + ")"


def generate_copy(
    table: str,
    columns: Iterable[str],
    file_path: str,
    fmt: str = "csv",
    with_columns: bool = True,
    with_header: bool = True,
) -> str:
    """PostgreSQL COPY FROM:导入 CSV/TSV 到表。

    - with_columns=False: 不指定列名(全列导入,顺序按表定义)
    - fmt='tsv': 加 DELIMITER E'\\t'
    - with_header=False: 不加 HEADER(目标表里也不期望 header 行被插)
    """
    cols = list(columns) if with_columns else []
    cols_str = f"({', '.join(_quote_ident(c) for c in cols)})" if cols else ""
    options = _format_options(fmt, with_header)
    return f"COPY {_quote_ident(table)} {cols_str} FROM '{file_path}' {options};"


def generate_csv_export(
    table: str,
    columns: Iterable[str],
    file_path: str,
    fmt: str = "csv",
    with_columns: bool = True,
    with_header: bool = True,
) -> str:
    """PostgreSQL COPY TO:导出 CSV/TSV。参数同 generate_copy。"""
    cols = list(columns) if with_columns else []
    cols_str = f"({', '.join(_quote_ident(c) for c in cols)})" if cols else ""
    options = _format_options(fmt, with_header)
    return f"COPY {_quote_ident(table)} {cols_str} TO '{file_path}' {options};"


def generate_bulk_insert_pg(table: str, columns: Iterable[str], values: list[list]) -> str:
    """PostgreSQL 风格多行 INSERT(values 是数据)"""
    cols = list(columns)
    col_list = ", ".join(_quote_ident(c) for c in cols)
    val_rows = []
    for row in values:
        val_rows.append("(" + ", ".join(_value(v) for v in row) + ")")
    return f"INSERT INTO {_quote_ident(table)} ({col_list}) VALUES\n  " + ",\n  ".join(val_rows) + ";"

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


def generate_create(table: str, raw_ddl: str = "", fk_ddl: str = "", index_ddl: str = "") -> str:
    """生成 CREATE DDL 文本块。

    - raw_ddl 非空 → 直接使用原 CREATE TABLE 文本(可能含 ; 收尾,直接输出)
    - raw_ddl 为空 → 抛错(由调用方在生成前自行构建,本函数不重造)
    - fk_ddl / index_ddl 各自独立追加在 CREATE 后(以 `\n\n` 分隔)

    设计原则:不重新生成 CREATE — 用户改完列后 ddl_text 是权威原 CREATE。
    """
    parts: list[str] = []
    raw = (raw_ddl or "").rstrip().rstrip(";").rstrip()
    if not raw:
        # 兜底:给个空 CREATE 占位,不至于无声失败
        parts.append(f"-- ⚠ 表 {table!r} 暂无 CREATE TABLE DDL")
    else:
        parts.append(raw + ";")
    if fk_ddl.strip():
        parts.append(fk_ddl.strip().rstrip(";") + ";")
    if index_ddl.strip():
        parts.append(index_ddl.strip().rstrip(";") + ";")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# COPY (PostgreSQL) — Import / Export CSV/TSV
# ---------------------------------------------------------------------------
def _format_options(fmt: str, with_header: bool) -> str:
    """FORMAT csv/HEADER true/DELIMITER E'\\t' 这种 options 字符串。"""
    parts = [f"FORMAT csv"]
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
    return f"\COPY {_quote_ident(table)} {cols_str} FROM '{file_path}' {options};"


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
    return f"\COPY {_quote_ident(table)} {cols_str} TO '{file_path}' {options};"


def generate_bulk_insert_pg(table: str, columns: Iterable[str], values: list[list]) -> str:
    """PostgreSQL 风格多行 INSERT(values 是数据)"""
    cols = list(columns)
    col_list = ", ".join(_quote_ident(c) for c in cols)
    val_rows = []
    for row in values:
        val_rows.append("(" + ", ".join(_value(v) for v in row) + ")")
    return f"INSERT INTO {_quote_ident(table)} ({col_list}) VALUES\n  " + ",\n  ".join(val_rows) + ";"


# ---------------------------------------------------------------------------
# Export Insert SQL (命令行) — 用 pg_dump / mysqldump / expdp 把表数据导出为 INSERT SQL
# ---------------------------------------------------------------------------
def _shell_quote(s: str) -> str:
    """shell 安全引号包裹(单引号,内嵌单引号转义为 '\\'')"""
    if not s:
        return "''"
    return "'" + s.replace("'", "'\\''") + "'"


def _shell_quote_double(s: str) -> str:
    """双引号包裹(用于 expdp 的连接串)"""
    if not s:
        return '""'
    return '"' + s.replace('"', '\\"').replace('\\', '\\\\') + '"'


def generate_export_insert(
    table: str,
    db_type: str,
    host: str,
    port: int,
    username: str,
    password: str,
    database: str,
    schema: str,
    service_name: str = "",
    out_dir: str = ".",
) -> str:
    """生成导出表数据为 INSERT SQL 的命令行(不执行,只生成命令文本)。

    postgres:
        pg_dump -h {host} -p {port} -U {user} -d {db} -t {schema}.{table}
                --data-only --inserts > {out_dir}/{table}.sql

    mysql:
        mysqldump -h {host} -P {port} -u {user} -p{password} {db} {table}
                --no-create-info --complete-insert --skip-comments
                > {out_dir}/{table}.sql

    oracle (expdp / Data Pump):
        expdp {user}/\"{password}\"@{host}:{port}/{service}
                TABLES={schema}.{table} DIRECTORY=DATA_PUMP_DIR
                DUMPFILE={table}.dmp CONTENT=DATA_ONLY
                (再 impdp 还原时加参数,生成 .sql 的等价做法不在 expdp 标准能力内)
    """
    safe_table = _shell_quote(table)
    out_path = f"{out_dir.rstrip('/').rstrip('\\\\') or '.'}/{table}.sql"
    quoted_out = _shell_quote(out_path)
    if db_type == "postgres":
        host_q = _shell_quote(host)
        user_q = _shell_quote(username)
        db_q = _shell_quote(database)
        # schema.table 作为 -t 参数,需要 shell 安全的 schema+table
        sch_table_q = _shell_quote(f"{schema}.{table}")
        return (
            f"pg_dump -h {host_q} -p {int(port) or 5432} -U {user_q} -d {db_q} "
            f"-t {sch_table_q} --data-only --inserts > {quoted_out}"
        )
    if db_type == "mysql":
        # mysqldump -p 直接接密码(无空格),或用 --defaults-file
        # 简单做法: -p{password} 紧贴(无空格),password 内不能含空格
        pwd_inline = password  # mysqldump 兼容
        host_q = _shell_quote(host)
        db_q = _shell_quote(database)
        tbl_q = _shell_quote(table)
        return (
            f"mysqldump -h {host_q} -P {int(port) or 3306} -u {_shell_quote(username)} "
            f"-p{pwd_inline} {db_q} {tbl_q} "
            f"--no-create-info --complete-insert --skip-comments --default-character-set=utf8mb4 "
            f"> {quoted_out}"
        )
    if db_type == "oracle":
        # expdp 不直接生成 INSERT SQL 文件,默认导 .dmp(用 CONTENT=DATA_ONLY 只导数据)
        # 想真正生成 .sql(INSERT 语句),用 SQL*Plus 的 spool 路线
        conn = f"{_shell_quote_double(username)}/{_shell_quote_double(password)}@{host}:{int(port) or 1521}/{service_name}"
        return (
            f"expdp {conn} TABLES={schema}.{table} DIRECTORY=DATA_PUMP_DIR "
            f"DUMPFILE={table}.dmp CONTENT=DATA_ONLY LOGFILE={table}_expdp.log"
        )
    raise ValueError(f"Unsupported db_type: {db_type!r}")


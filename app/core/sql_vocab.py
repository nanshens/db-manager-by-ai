"""SQL 联想词库 — 给 SQL 编辑器做自动补全

数据源:
- SQL 基本关键字(各方言通用)
- 方言特定关键字(目前只 PostgreSQL 列了详尽)
- PostgreSQL 常用函数 / 数据类型
- 项目下的表/列(动态注入)
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# SQL 通用关键字(大写匹配)
# ---------------------------------------------------------------------------
SQL_KEYWORDS: list[str] = [
    # DML
    "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "IN", "IS", "NULL",
    "INSERT", "INTO", "VALUES", "UPDATE", "SET", "DELETE",
    # DDL
    "CREATE", "TABLE", "INDEX", "VIEW", "DROP", "ALTER", "ADD", "COLUMN",
    "PRIMARY", "KEY", "FOREIGN", "REFERENCES", "UNIQUE", "DEFAULT",
    # 修饰
    "AS", "ON", "JOIN", "INNER", "LEFT", "RIGHT", "OUTER", "FULL", "CROSS",
    "GROUP", "BY", "ORDER", "HAVING", "LIMIT", "OFFSET", "DISTINCT",
    "UNION", "ALL", "INTERSECT", "EXCEPT", "EXISTS", "BETWEEN", "LIKE",
    "ILIKE", "CASE", "WHEN", "THEN", "ELSE", "END", "WITH", "RECURSIVE",
    # 事务
    "BEGIN", "COMMIT", "ROLLBACK", "TRANSACTION", "SAVEPOINT",
    # 条件
    "IF", "ELSEIF", "WHILE", "LOOP", "RETURN", "RETURNS",
    # 杂项
    "USE", "DATABASE", "SCHEMA", "TRUNCATE", "RENAME", "TO", "EXPLAIN",
    "ANALYZE", "VACUUM", "GRANT", "REVOKE", "COMMENT",
    "ASC", "DESC", "NULLS", "FIRST", "LAST", "ONLY",
    # 类型关键词
    "INT", "INTEGER", "BIGINT", "SMALLINT", "DECIMAL", "NUMERIC",
    "VARCHAR", "CHAR", "TEXT", "DATE", "TIME", "DATETIME", "TIMESTAMP",
    "BOOLEAN", "BOOL", "FLOAT", "REAL", "DOUBLE", "BLOB", "JSON",
    "SERIAL", "BIGSERIAL", "SMALLSERIAL",
    "ARRAY", "ENUM", "UUID",
    # COPY
    "COPY", "FROM", "TO", "WITH", "FORMAT", "CSV", "HEADER",
    "DELIMITER", "QUOTE", "ESCAPE", "ENCODING",
    # PostgreSQL 特定
    "RETURNING", "CONFLICT", "DO", "NOTHING", "UPSERT",
    "OVER", "PARTITION", "WINDOW", "RANGE", "ROWS", "PRECEDING",
    "FOLLOWING", "UNBOUNDED", "CURRENT", "EXCLUDE",
    "ARRAY_AGG", "JSON_AGG", "JSONB_AGG", "STRING_AGG",
    "LATERAL", "WITH", "RECURSIVE",
    # MySQL 特定
    "DUPLICATE", "KEY", "AUTO_INCREMENT",
    # Oracle 特定
    "ROWNUM", "ROWID", "SYSDATE", "DUAL", "CONNECT", "BY", "LEVEL",
    "START", "CONNECT_BY_ROOT", "CONNECT_BY_ISCYCLE", "CONNECT_BY_ISLEAF",
    "PRIOR", "SIBLINGS", "MINUS",
]


# ---------------------------------------------------------------------------
# PostgreSQL 常用函数(常用 ~120 个,够用)
# ---------------------------------------------------------------------------
PG_FUNCTIONS: list[tuple[str, str]] = [
    # 聚合
    ("COUNT(*)", "聚合:行数"),
    ("COUNT(col)", "聚合:列非空数"),
    ("SUM(col)", "聚合:求和"),
    ("AVG(col)", "聚合:平均"),
    ("MIN(col)", "聚合:最小"),
    ("MAX(col)", "聚合:最大"),
    ("ARRAY_AGG(col)", "聚合:数组"),
    ("STRING_AGG(col, ',')", "聚合:字符串拼接"),
    ("JSON_AGG(col)", "聚合:JSON 数组"),
    ("STDDEV(col)", "聚合:标准差"),
    ("VARIANCE(col)", "聚合:方差"),
    # 数学
    ("ABS(x)", "绝对值"),
    ("CEIL(x)", "向上取整"),
    ("FLOOR(x)", "向下取整"),
    ("ROUND(x, n)", "四舍五入"),
    ("MOD(a, b)", "取模"),
    ("POWER(a, b)", "幂"),
    ("SQRT(x)", "平方根"),
    # 字符串
    ("LENGTH(s)", "字符串长度"),
    ("UPPER(s)", "转大写"),
    ("LOWER(s)", "转小写"),
    ("TRIM(s)", "去首尾空白"),
    ("LTRIM(s)", "去左空白"),
    ("RTRIM(s)", "去右空白"),
    ("SUBSTRING(s, i, n)", "子串"),
    ("LEFT(s, n)", "左侧 n 字符"),
    ("RIGHT(s, n)", "右侧 n 字符"),
    ("REPLACE(s, old, new)", "替换"),
    ("CONCAT(a, b, ...)", "拼接"),
    ("CONCAT_WS(sep, a, b)", "带分隔符拼接"),
    ("POSITION(needle IN haystack)", "查找位置"),
    ("REVERSE(s)", "反转"),
    ("REPEAT(s, n)", "重复 n 次"),
    ("LPAD(s, n, pad)", "左填充"),
    ("RPAD(s, n, pad)", "右填充"),
    # 日期
    ("NOW()", "当前时间"),
    ("CURRENT_DATE", "当前日期"),
    ("CURRENT_TIME", "当前时间"),
    ("CURRENT_TIMESTAMP", "当前时间戳"),
    ("DATE_TRUNC('day', ts)", "截断到日"),
    ("EXTRACT(YEAR FROM ts)", "提取年/月/日"),
    ("AGE(ts1, ts2)", "间隔"),
    ("DATE_PART('year', ts)", "取部分"),
    ("TO_CHAR(ts, 'YYYY-MM-DD')", "转字符串"),
    ("TO_DATE(s, 'YYYY-MM-DD')", "转日期"),
    ("TO_TIMESTAMP(s, 'YYYY-MM-DD HH24:MI:SS')", "转时间戳"),
    ("INTERVAL '1 day'", "时间间隔"),
    # 类型转换
    ("CAST(x AS TYPE)", "类型转换"),
    ("x::TYPE", "PG 简写转换"),
    ("TO_CHAR(n, 'FM999,999.00')", "数字转字符串"),
    # 条件
    ("COALESCE(a, b, c)", "返回第一个非空"),
    ("NULLIF(a, b)", "相等返回 NULL"),
    ("GREATEST(a, b, c)", "最大值"),
    ("LEAST(a, b, c)", "最小值"),
    # 窗口
    ("ROW_NUMBER() OVER (ORDER BY col)", "行号"),
    ("RANK() OVER (ORDER BY col)", "排名"),
    ("DENSE_RANK() OVER (ORDER BY col)", "密集排名"),
    ("LAG(col) OVER (ORDER BY col)", "上一行"),
    ("LEAD(col) OVER (ORDER BY col)", "下一行"),
    ("FIRST_VALUE(col) OVER (...)", "窗口首个值"),
    ("LAST_VALUE(col) OVER (...)", "窗口最后值"),
    # JSON
    ("row_to_json(r)", "行转 JSON"),
    ("jsonb_pretty(j)", "美化 JSON"),
    ("jsonb_extract_path(j, 'k')", "JSON 路径取值"),
    ("->>", "JSON 字段取值(text)"),
    ("->", "JSON 字段取值(json)"),
    ("#>", "JSON 路径(text)"),
    # 系统
    ("gen_random_uuid()", "随机 UUID"),
    ("now()", "当前时间"),
    ("current_user", "当前用户"),
    ("session_user", "会话用户"),
    # DDL/管理
    ("pg_typeof(x)", "取类型"),
    ("pg_size_pretty(n)", "格式化大小"),
    ("version()", "PG 版本"),
    # 集合/数组
    ("UNNEST(arr)", "数组转行"),
    ("ARRAY[1, 2, 3]", "数组字面量"),
    ("ARRAY_LENGTH(arr, 1)", "数组长度"),
]


def get_vocab(dialect: str = "postgres") -> list[str]:
    """返回该方言下的关键字 + 函数名(扁平字符串列表)。"""
    vocab = list(SQL_KEYWORDS)
    if dialect == "postgres":
        vocab.extend(name for name, _ in PG_FUNCTIONS)
    elif dialect == "mysql":
        # MySQL 函数(简化版)
        vocab.extend([
            "NOW()", "CURDATE()", "CURTIME()", "DATE_FORMAT(d, fmt)",
            "DATEDIFF(d1, d2)", "IFNULL(a, b)", "IF(cond, a, b)",
            "GROUP_CONCAT(col)", "CONCAT(a, b)", "LENGTH(s)", "CHAR_LENGTH(s)",
            "SUBSTRING(s, i, n)", "REPLACE(s, old, new)", "TRIM(s)",
            "LIMIT n OFFSET m", "AUTO_INCREMENT", "UNSIGNED",
        ])
    elif dialect == "oracle":
        vocab.extend([
            "SYSDATE", "SYSTIMESTAMP", "DUAL", "ROWNUM", "ROWID",
            "NVL(a, b)", "NVL2(a, b, c)", "DECODE(col, k, v, ...)",
            "TO_CHAR(x, fmt)", "TO_DATE(s, fmt)", "TO_NUMBER(s, fmt)",
            "INSTR(s, sub)", "SUBSTR(s, i, n)", "LENGTH(s)",
            "LPAD(s, n, pad)", "RPAD(s, n, pad)",
            "MOD(a, b)", "CEIL(x)", "FLOOR(x)", "ROUND(x, n)",
            "CONNECT BY", "START WITH", "LEVEL", "ROWNUM",
        ])
    return vocab


def get_function_help() -> dict[str, str]:
    """返回函数名 → 简短说明 的字典(用于 tooltip)。"""
    out: dict[str, str] = {}
    for name, desc in PG_FUNCTIONS:
        # 提取函数主名(去括号)
        key = name.split("(")[0].strip().upper()
        if key and key not in out:
            out[key] = desc
    return out


# 项目相关联想词(动态收集)
def collect_project_vocab(project_id: int | None) -> tuple[set[str], dict[str, str]]:
    """根据 project_id 收集可用表名和列名。

    返回 (all_identifiers, identifier_to_type)
    - all_identifiers: 全部表名 + 列名(用于联想匹配)
    - identifier_to_type: "users" → "table" / "id" → "col:users"
    """
    from app.services.registry import reg

    ids: set[str] = set()
    types: dict[str, str] = {}

    try:
        if project_id is None:
            # 全局:列所有项目的表+列
            projects = reg().project_service.list_all()
            for p in projects:
                _add_project_tables(p.id, ids, types)
        else:
            _add_project_tables(project_id, ids, types)
    except Exception:
        pass
    return ids, types


def _add_project_tables(project_id: int, ids: set[str], types: dict[str, str]) -> None:
    from app.services.registry import reg
    tables = reg().table_service.list_by_project(project_id)
    for t in tables:
        tname = t.name
        ids.add(tname)
        types[tname] = "table"
        for c in t.columns:
            ids.add(c.name)
            types[c.name] = f"col:{tname}"
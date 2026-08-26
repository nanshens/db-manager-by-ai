"""DDL 解析器 — 从 CREATE TABLE 脚本中提取表结构。

支持方言:
- postgres (默认): 双引号包标识符,SERIAL/BIGSERIAL
- mysql:           反引号包标识符,INT AUTO_INCREMENT
- oracle:          双引号包标识符,NUMBER(p,s)/VARCHAR2/CLOB

解析流程:
1. 用 sqlparse.split 切分多条语句
2. 找 CREATE TABLE ... ( ... ) 主体
3. 顶层逗号切分 column def 和 table-level constraint
4. column def: name type [NOT NULL] [DEFAULT ...] [PRIMARY KEY] [COMMENT '...']
5. table-level PRIMARY KEY (a, b): 把这些列标记为 pk

不解析的内容: FOREIGN KEY / UNIQUE / INDEX / CHECK 约束 — 这些不是 Column 模型字段,丢掉即可。
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional

import sqlparse
from sqlparse.tokens import Keyword, DDL, Punctuation, Whitespace, Name, Literal


DIALECTS = ("postgres", "mysql", "oracle")


@dataclass
class ParsedColumn:
    name: str
    type: str
    nullable: bool = True
    default: str = ""
    pk: bool = False
    comment: str = ""


@dataclass
class ParsedTable:
    name: str
    columns: list[ParsedColumn] = field(default_factory=list)
    raw_ddl: str = ""            # 原始 DDL,导入时存进 ddl_text 备用
    parse_error: str = ""        # 解析失败原因;空 = 成功


# ---------------------------------------------------------------------------
# 工具:去除 SQL 注释 + 标准化空白
# ---------------------------------------------------------------------------
_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _clean(sql: str) -> str:
    """去注释,统一空白。"""
    sql = _BLOCK_COMMENT.sub(" ", sql)
    sql = _LINE_COMMENT.sub(" ", sql)
    sql = sql.replace("\r\n", "\n").replace("\r", "\n")
    # 合并多余空白
    sql = re.sub(r"\s+", " ", sql)
    return sql.strip()


# ---------------------------------------------------------------------------
# 工具:按顶层逗号切分(忽略括号/字符串内的逗号)
# ---------------------------------------------------------------------------
def _split_top_level(body: str) -> list[str]:
    """把 '(col1 int, col2 varchar(10,2), col3 text)' 切成 ['col1 int', 'col2 varchar(10,2)', 'col3 text']"""
    parts: list[str] = []
    depth = 0
    in_str: Optional[str] = None  # 当前字符串分隔符 ' "
    cur: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if in_str:
            cur.append(ch)
            if ch == in_str and (i == 0 or body[i - 1] != "\\"):
                in_str = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            in_str = ch
            cur.append(ch)
            i += 1
            continue
        if ch == "(":
            depth += 1
            cur.append(ch)
            i += 1
            continue
        if ch == ")":
            depth -= 1
            cur.append(ch)
            i += 1
            continue
        if ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    if cur:
        last = "".join(cur).strip()
        if last:
            parts.append(last)
    return parts


# ---------------------------------------------------------------------------
# 工具:剥离引号
# ---------------------------------------------------------------------------
def _unquote(name: str) -> str:
    name = name.strip()
    if len(name) >= 2 and name[0] in ('"', "`") and name[-1] == name[0]:
        return name[1:-1]
    return name


# ---------------------------------------------------------------------------
# 单条 CREATE TABLE 解析
# ---------------------------------------------------------------------------
_CREATE_RE = re.compile(
    r"""^\s*CREATE\s+TABLE\s+
        (?:IF\s+NOT\s+EXISTS\s+)?       # 可选 IF NOT EXISTS
        (?P<name>["`\[]?[A-Za-z_][\w$]*["`\]]?  # 标识符(可选 schema.table)
        (?:(?:\s*\.\s*)?["`\[]?[A-Za-z_][\w$]*["`\]]?)?)
        \s*\(""",
    re.IGNORECASE | re.VERBOSE,
)


def _parse_one(stmt: str) -> Optional[ParsedTable]:
    """解析单条语句,不是 CREATE TABLE 返回 None。"""
    cleaned = _clean(stmt)
    m = _CREATE_RE.match(cleaned)
    if not m:
        return None

    table_name = _unquote(m.group("name"))
    # 不允许 schema.table(简化),如果带 . 只取后半
    if "." in table_name:
        table_name = table_name.split(".")[-1].strip('"').strip("`")
        # 但用户可能想 schema.table 都保留 — 算了,只取 table name

    # 找 (...) 范围
    open_paren = cleaned.find("(", m.end() - 1)
    if open_paren < 0:
        return None
    # 找匹配的右括号
    depth = 0
    in_str: Optional[str] = None
    close_paren = -1
    for i in range(open_paren, len(cleaned)):
        ch = cleaned[i]
        if in_str:
            if ch == in_str and (i == 0 or cleaned[i - 1] != "\\"):
                in_str = None
            continue
        if ch in ("'", '"', "`"):
            in_str = ch
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                close_paren = i
                break
    if close_paren < 0:
        return None

    body = cleaned[open_paren + 1:close_paren]
    parts = _split_top_level(body)

    cols: list[ParsedColumn] = []
    table_pks: set[str] = set()  # 表级 PRIMARY KEY (col, col) 累积

    for part in parts:
        p = part.strip().rstrip(",").strip()
        if not p:
            continue
        upper = p.upper()
        # 表级约束,只关心 PRIMARY KEY
        if upper.startswith("PRIMARY KEY"):
            # PRIMARY KEY (a, b) 或 PRIMARY KEY (a)
            mm = re.search(r"\(([^)]*)\)", p)
            if mm:
                for c in mm.group(1).split(","):
                    c = _unquote(c.strip())
                    if c:
                        table_pks.add(c)
            continue
        # 其他表级(FOREIGN/UNIQUE/INDEX/CHECK/CONSTRAINT) 跳过
        if upper.startswith(("FOREIGN", "UNIQUE", "INDEX", "KEY", "CHECK", "CONSTRAINT")):
            continue
        # LIKE/AS select 子句(CTAS)— 不支持,跳过
        if upper.startswith("LIKE ") or upper.startswith("AS "):
            return ParsedTable(
                name=table_name, raw_ddl=stmt.strip(),
                parse_error="CTAS (CREATE TABLE AS/LIKE) 不支持",
            )
        # 列定义
        col = _parse_column(p)
        if col:
            cols.append(col)

    # 应用表级 PK
    for c in cols:
        if c.name in table_pks:
            c.pk = True

    return ParsedTable(name=table_name, columns=cols, raw_ddl=stmt.strip())


def _parse_column(part: str) -> Optional[ParsedColumn]:
    """单列定义: 'name TYPE [NOT NULL] [DEFAULT v] [PRIMARY KEY] [COMMENT '...']'"""
    # 找到第一个空白,前面是列名
    m = re.match(r'^\s*(?P<name>["`\[]?[\w$]+["`\]]?)\s+(?P<rest>.*)$', part, re.DOTALL)
    if not m:
        return None
    name = _unquote(m.group("name"))
    rest = m.group("rest").strip()
    if not rest:
        return None

    # 先抽 COMMENT '...' 或 COMMENT "..." (Postgres / MySQL)
    comment = ""
    cm = re.search(r"""\bCOMMENT\s+(['"])(.*?)\1""", rest, re.IGNORECASE)
    if cm:
        comment = cm.group(2)
        rest = (rest[:cm.start()] + rest[cm.end():]).strip()

    # 抽 PRIMARY KEY
    pk = False
    if re.search(r"\bPRIMARY\s+KEY\b", rest, re.IGNORECASE):
        pk = True
        rest = re.sub(r"\bPRIMARY\s+KEY\b", "", rest, flags=re.IGNORECASE).strip()

    # 抽 NOT NULL
    nullable = True
    if re.search(r"\bNOT\s+NULL\b", rest, re.IGNORECASE):
        nullable = False
        rest = re.sub(r"\bNOT\s+NULL\b", "", rest, flags=re.IGNORECASE).strip()
    # NULL(显式) — 也算可空
    if re.match(r"^\s*NULL\b", rest, re.IGNORECASE):
        nullable = True
        rest = re.sub(r"^\s*NULL\b", "", rest, flags=re.IGNORECASE).strip()

    # 抽 DEFAULT
    default = ""
    dm = re.search(
        r"""\bDEFAULT\s+('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|[^\s,()]+)""",
        rest, re.IGNORECASE
    )
    if dm:
        default = dm.group(1)
        rest = (rest[:dm.start()] + rest[dm.end():]).strip()

    # 抽 UNIQUE / CHECK / REFERENCES / COLLATE 等(忽略)
    for kw in ("UNIQUE", "CHECK", "REFERENCES", "COLLATE", "GENERATED",
               r"ON\s+UPDATE", "AUTO_INCREMENT", "AUTOINCREMENT"):
        rest = re.sub(rf"\b{kw}\b.*$", "", rest, flags=re.IGNORECASE).strip()
    # 简化:把剩余的 AUTO_INCREMENT / GENERATED ALWAYS AS 之类吃掉
    rest = re.sub(r"\bAUTO_INCREMENT\b", "", rest, flags=re.IGNORECASE).strip()
    rest = re.sub(r"\bGENERATED\s+ALWAYS\s+AS\s+\S+.*$", "", rest, flags=re.IGNORECASE).strip()
    rest = re.sub(r"\bREFERENCES\s+\S+.*$", "", rest, flags=re.IGNORECASE).strip()
    rest = re.sub(r"\bCHECK\s*\([^)]*\)", "", rest, flags=re.IGNORECASE).strip()
    rest = re.sub(r"\bCOLLATE\s+\S+", "", rest, flags=re.IGNORECASE).strip()
    rest = re.sub(r"\s+", " ", rest).strip()

    # 现在 rest 应该就剩 type 了(可能带 (precision) / [] / unsigned / 等)
    # 去掉 type 末尾的 unsigned / 等
    rest = re.sub(r"\bUNSIGNED\b", "", rest, flags=re.IGNORECASE).strip()
    rest = re.sub(r"\bZEROFILL\b", "", rest, flags=re.IGNORECASE).strip()
    # 多个空格合一
    rest = re.sub(r"\s+", " ", rest).strip()

    if not rest:
        rest = "TEXT"

    return ParsedColumn(
        name=name,
        type=rest.upper(),  # 统一大写
        nullable=nullable,
        default=default,
        pk=pk,
        comment=comment,
    )


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------
def parse_ddl_file(path: str, dialect: str = "postgres") -> tuple[list[ParsedTable], list[str]]:
    """解析 .sql 文件,返回 (parsed_tables, error_messages)。

    - parsed_tables: 成功解析的表(含可能失败的,看 parse_error)
    - error_messages: 整条语句无法识别的错误(原 DDL 摘录)
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return parse_ddl_text(text, dialect)


def parse_ddl_text(text: str, dialect: str = "postgres") -> tuple[list[ParsedTable], list[str]]:
    """解析 SQL 文本。返回 (parsed_tables, errors)。"""
    if dialect not in DIALECTS:
        dialect = "postgres"
    # 先整体去注释,避免 -- 开头跳过 CREATE 语句
    cleaned_text = _clean(text)
    raw_stmts = sqlparse.split(cleaned_text)
    parsed: list[ParsedTable] = []
    errors: list[str] = []
    for stmt in raw_stmts:
        s = stmt.strip().rstrip(";").strip()
        if not s:
            continue
        # 快速嗅探:必须以 CREATE 开头
        if not re.match(r"^\s*CREATE\b", s, re.IGNORECASE):
            continue
        try:
            t = _parse_one(s)
        except Exception as e:
            errors.append(f"{s[:60]!r}... 解析异常: {e}")
            continue
        if t is None:
            errors.append(f"{s[:60]!r}... 不是 CREATE TABLE 或解析失败")
            continue
        if not t.columns and not t.parse_error:
            t.parse_error = "未识别到列"
        parsed.append(t)
    return parsed, errors

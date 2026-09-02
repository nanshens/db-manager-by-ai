"""SQLite 连接 + 建表迁移"""
from __future__ import annotations
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

# 所有 DDL — 启动时按顺序执行(IF NOT EXISTS 幂等)
SCHEMA_SQL = """
-- 项目
CREATE TABLE IF NOT EXISTS project (
  id           INTEGER PRIMARY KEY,
  name         TEXT NOT NULL UNIQUE,
  description  TEXT,
  color        TEXT,
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
);

-- 表结构
CREATE TABLE IF NOT EXISTS db_table (
  id           INTEGER PRIMARY KEY,
  project_id   INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  comment      TEXT,
  columns_json TEXT NOT NULL,
  ddl_text     TEXT NOT NULL,
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL,
  UNIQUE(project_id, name)
);

-- 数据版本
CREATE TABLE IF NOT EXISTS data_version (
  id              INTEGER PRIMARY KEY,
  project_id      INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  version_name    TEXT NOT NULL,
  description     TEXT,
  source_files    TEXT NOT NULL,
  created_at      TEXT NOT NULL,
  UNIQUE(project_id, version_name)
);

-- 常用 SQL
CREATE TABLE IF NOT EXISTS sql_snippet (
  id           INTEGER PRIMARY KEY,
  title        TEXT NOT NULL,
  description  TEXT,
  sql_text     TEXT NOT NULL,
  tags         TEXT,
  project_id   INTEGER REFERENCES project(id) ON DELETE SET NULL,
  dialect      TEXT NOT NULL DEFAULT 'postgres',
  use_count    INTEGER DEFAULT 0,
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
);

-- 对比历史
CREATE TABLE IF NOT EXISTS diff_record (
  id              INTEGER PRIMARY KEY,
  project_id      INTEGER REFERENCES project(id) ON DELETE SET NULL,
  left_label      TEXT NOT NULL,
  right_label     TEXT NOT NULL,
  left_meta_json  TEXT,
  right_meta_json TEXT,
  result_json     TEXT,
  config_id       INTEGER REFERENCES compare_config(id) ON DELETE SET NULL,
  created_at      TEXT NOT NULL
);

-- 对比配置
CREATE TABLE IF NOT EXISTS compare_config (
  id               INTEGER PRIMARY KEY,
  project_id       INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  table_name       TEXT NOT NULL,
  config_name      TEXT NOT NULL,
  pk_columns_json  TEXT NOT NULL,
  compare_columns_json TEXT,
  ignore_columns_json  TEXT,
  case_sensitive   INTEGER DEFAULT 1,
  trim_whitespace  INTEGER DEFAULT 1,
  is_default       INTEGER DEFAULT 0,
  created_at       TEXT NOT NULL,
  updated_at       TEXT NOT NULL,
  UNIQUE(project_id, table_name, config_name)
);

-- Excel 解析模板
CREATE TABLE IF NOT EXISTS excel_template (
  id                 INTEGER PRIMARY KEY,
  project_id         INTEGER REFERENCES project(id) ON DELETE CASCADE,
  template_name      TEXT NOT NULL,
  config_sheet_name  TEXT NOT NULL DEFAULT '',
  table_name_col     TEXT NOT NULL DEFAULT '',
  sheet_name_col     TEXT NOT NULL DEFAULT '',
  header_row         INTEGER DEFAULT 1,
  data_start_row     INTEGER DEFAULT 2,
  column_start       INTEGER DEFAULT 1,
  parse_mode         TEXT DEFAULT 'mapping',  -- mapping / sheet_name / chinese_name
  name_mapping       TEXT DEFAULT '{}',       -- JSON {中文sheet名: 英文表名}
  description        TEXT,
  use_count          INTEGER DEFAULT 0,
  created_at         TEXT NOT NULL,
  updated_at         TEXT NOT NULL,
  UNIQUE(project_id, template_name)
);

-- 兼容老库: 如果 excel_template 已存在但没有新列,补加
-- (用 try/except 包,IF NOT EXISTS SQLite 不支持 ALTER COLUMN)

-- 数据库链接(管理 db 连接信息,用于生成 pg_dump/mysqldump/expdp 命令)
CREATE TABLE IF NOT EXISTS db_link (
  id             INTEGER PRIMARY KEY,
  name           TEXT NOT NULL UNIQUE,
  db_type        TEXT NOT NULL,        -- postgres / mysql / oracle
  host           TEXT NOT NULL DEFAULT '',
  port           INTEGER NOT NULL DEFAULT 0,
  username       TEXT NOT NULL DEFAULT '',
  password       TEXT NOT NULL DEFAULT '',   -- 明文存储(自用工具,本地 SQLite)
  database       TEXT NOT NULL DEFAULT '',   -- pg: database, mysql: db name, oracle: 留空
  schema         TEXT NOT NULL DEFAULT 'public',  -- pg/mysql schema, oracle: user/owner
  service_name   TEXT NOT NULL DEFAULT '',   -- 仅 oracle 用(oracle service name / SID)
  description    TEXT,
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL
);

-- 表标签(多对多,一张表可打多个标签,一个标签可含多张表)
-- 用 project 作用域:同名 tag 在不同 project 是不同的(避免冲突)
CREATE TABLE IF NOT EXISTS tag (
  id           INTEGER PRIMARY KEY,
  project_id   INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  color        TEXT NOT NULL DEFAULT '#64748b',  -- 标签颜色(可选)
  description  TEXT,
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL,
  UNIQUE(project_id, name)
);

CREATE TABLE IF NOT EXISTS table_tag (
  tag_id     INTEGER NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
  table_id   INTEGER NOT NULL REFERENCES db_table(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tag_id, table_id)
);
CREATE INDEX IF NOT EXISTS idx_table_tag_table ON table_tag(table_id);
CREATE INDEX IF NOT EXISTS idx_table_tag_tag ON table_tag(tag_id);

-- Schema 迁移 — 用单独的 init_db 调,这里只放 DDL


-- SQL FTS5
CREATE VIRTUAL TABLE IF NOT EXISTS sql_snippet_fts USING fts5(
  title, description, sql_text, tags,
  content='sql_snippet', content_rowid='id'
);

-- FTS 触发器(增删改自动同步)
CREATE TRIGGER IF NOT EXISTS sql_snippet_ai AFTER INSERT ON sql_snippet BEGIN
  INSERT INTO sql_snippet_fts(rowid, title, description, sql_text, tags)
  VALUES (new.id, new.title, new.description, new.sql_text, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS sql_snippet_ad AFTER DELETE ON sql_snippet BEGIN
  INSERT INTO sql_snippet_fts(sql_snippet_fts, rowid, title, description, sql_text, tags)
  VALUES ('delete', old.id, old.title, old.description, old.sql_text, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS sql_snippet_au AFTER UPDATE ON sql_snippet BEGIN
  INSERT INTO sql_snippet_fts(sql_snippet_fts, rowid, title, description, sql_text, tags)
  VALUES ('delete', old.id, old.title, old.description, old.sql_text, old.tags);
  INSERT INTO sql_snippet_fts(rowid, title, description, sql_text, tags)
  VALUES (new.id, new.title, new.description, new.sql_text, new.tags);
END;

-- 应用配置(轻量 KV,后续可考虑用 QSettings 完全替代)
CREATE TABLE IF NOT EXISTS app_config (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_db_table_project ON db_table(project_id);
CREATE INDEX IF NOT EXISTS idx_data_version_project ON data_version(project_id);
CREATE INDEX IF NOT EXISTS idx_sql_snippet_project ON sql_snippet(project_id);
CREATE INDEX IF NOT EXISTS idx_compare_config_project_table ON compare_config(project_id, table_name);
CREATE INDEX IF NOT EXISTS idx_excel_template_project ON excel_template(project_id);
CREATE INDEX IF NOT EXISTS idx_tag_project ON tag(project_id);
"""


_local = threading.local()


def get_connection(db_path: Path) -> sqlite3.Connection:
    """获取当前线程的 SQLite 连接(线程局部)"""
    if not hasattr(_local, "conn") or _local.db_path != str(db_path):
        conn = sqlite3.connect(
            str(db_path),
            detect_types=sqlite3.PARSE_DECLTYPES,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        _local.conn = conn
        _local.db_path = str(db_path)
    return _local.conn


@contextmanager
def transaction(db_path: Path):
    """事务上下文管理器"""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db(db_path: Path) -> None:
    """初始化数据库(创建表 + 迁移)"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    conn.executescript(SCHEMA_SQL)
    # 迁移:给老库加 dialect 列(SQLite ALTER 不支持 IF NOT EXISTS,要先查)
    _migrate_add_dialect(conn)
    # 迁移:给老 excel_template 加 3 列(parse_mode / column_start / name_mapping)
    _migrate_excel_template(conn)
    conn.commit()


def _migrate_add_dialect(conn: sqlite3.Connection) -> None:
    """如果 sql_snippet 表没有 dialect 列,加上(默认 'postgres')。"""
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(sql_snippet)").fetchall()]
    if "dialect" not in cols:
        conn.execute(
            "ALTER TABLE sql_snippet ADD COLUMN dialect TEXT NOT NULL DEFAULT 'postgres'"
        )


def _migrate_excel_template(conn: sqlite3.Connection) -> None:
    """给老 excel_template 补 3 列:parse_mode / column_start / name_mapping"""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(excel_template)").fetchall()}
    if "parse_mode" not in cols:
        conn.execute("ALTER TABLE excel_template ADD COLUMN parse_mode TEXT DEFAULT 'mapping'")
    if "column_start" not in cols:
        conn.execute("ALTER TABLE excel_template ADD COLUMN column_start INTEGER DEFAULT 1")
    if "name_mapping" not in cols:
        conn.execute("ALTER TABLE excel_template ADD COLUMN name_mapping TEXT DEFAULT '{}'")
    # 老 schema 里 config_sheet_name / table_name_col / sheet_name_col 是 NOT NULL,
    # 改成允许空(mode 2/3 不需要这些字段)
    for col in ("config_sheet_name", "table_name_col", "sheet_name_col"):
        # 检查表结构,NOT NULL 老行没值会失败;SQLite 不支持改 NOT NULL 约束,只能:
        # 1) 不改约束,让 model 层默认空字符串
        # 2) 实际数据 INSERT 时强制给空字符串默认值
        # 这里选方案 1 — model 层 dataclass default=""
        pass

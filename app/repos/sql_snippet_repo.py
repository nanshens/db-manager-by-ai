"""SQL Snippet Repository"""
from __future__ import annotations
import sqlite3
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional

from app.repos.db import get_connection, transaction


# 支持的 SQL 方言(跟 DDL parser 同步)
DIALECTS = ("postgres", "mysql", "oracle")


@dataclass
class SqlSnippet:
    id: Optional[int]
    title: str
    description: str = ""
    sql_text: str = ""
    tags: str = ""                # 逗号分隔
    project_id: Optional[int] = None  # NULL = 全局
    dialect: str = "postgres"     # postgres / mysql / oracle
    use_count: int = 0
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class SqlSnippetRepo:
    def __init__(self, db_path):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self.db_path)

    def list_all(self, project_id: Optional[int] = None,
                 include_global: bool = True,
                 dialect: Optional[str] = None) -> list[SqlSnippet]:
        sql = "SELECT id, title, description, sql_text, tags, project_id, dialect, use_count, created_at, updated_at FROM sql_snippet"
        params: list = []
        clauses = []
        if project_id is not None and include_global:
            clauses.append("(project_id = ? OR project_id IS NULL)")
            params.append(project_id)
        elif project_id is not None:
            clauses.append("project_id = ?")
            params.append(project_id)
        elif include_global is False:
            # 仅全局
            clauses.append("project_id IS NULL")
        if dialect:
            clauses.append("dialect = ?")
            params.append(dialect)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        # 排序:用得多的在上面;同次数按最近更新
        sql += " ORDER BY use_count DESC, updated_at DESC"
        rows = self._conn().execute(sql, params).fetchall()
        return [SqlSnippet(**dict(r)) for r in rows]

    def search(self, query: str, project_id: Optional[int] = None,
               dialect: Optional[str] = None) -> list[SqlSnippet]:
        """FTS5 搜索;空 query 返回 list_all"""
        if not query.strip():
            return self.list_all(project_id=project_id, dialect=dialect)
        like = f"%{query.strip()}%"
        sql = (
            "SELECT id, title, description, sql_text, tags, project_id, dialect, use_count, created_at, updated_at "
            "FROM sql_snippet "
            "WHERE (title LIKE ? OR description LIKE ? OR sql_text LIKE ? OR tags LIKE ?)"
        )
        params: list = [like, like, like, like]
        if project_id is not None:
            sql += " AND (project_id = ? OR project_id IS NULL)"
            params.append(project_id)
        if dialect:
            sql += " AND dialect = ?"
            params.append(dialect)
        sql += " ORDER BY use_count DESC, updated_at DESC"
        rows = self._conn().execute(sql, params).fetchall()
        return [SqlSnippet(**dict(r)) for r in rows]

    def get(self, snippet_id: int) -> Optional[SqlSnippet]:
        r = self._conn().execute(
            "SELECT id, title, description, sql_text, tags, project_id, dialect, use_count, created_at, updated_at "
            "FROM sql_snippet WHERE id = ?",
            (snippet_id,),
        ).fetchone()
        return SqlSnippet(**dict(r)) if r else None

    def create(self, s: SqlSnippet) -> int:
        now = _now()
        with transaction(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO sql_snippet (title, description, sql_text, tags, project_id, dialect, use_count, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (s.title, s.description, s.sql_text, s.tags, s.project_id,
                 s.dialect or "postgres", s.use_count, now, now),
            )
            return cur.lastrowid

    def update(self, s: SqlSnippet) -> None:
        with transaction(self.db_path) as conn:
            conn.execute(
                "UPDATE sql_snippet SET title=?, description=?, sql_text=?, tags=?, project_id=?, dialect=?, updated_at=? WHERE id=?",
                (s.title, s.description, s.sql_text, s.tags, s.project_id,
                 s.dialect or "postgres", _now(), s.id),
            )

    def delete(self, snippet_id: int) -> None:
        with transaction(self.db_path) as conn:
            conn.execute("DELETE FROM sql_snippet WHERE id = ?", (snippet_id,))

    def increment_use_count(self, snippet_id: int) -> None:
        with transaction(self.db_path) as conn:
            conn.execute(
                "UPDATE sql_snippet SET use_count = use_count + 1, updated_at = updated_at WHERE id = ?",
                (snippet_id,),
            )

    def count(self) -> int:
        r = self._conn().execute("SELECT COUNT(*) AS n FROM sql_snippet").fetchone()
        return r["n"]

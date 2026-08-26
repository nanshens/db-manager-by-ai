"""SQL Lib Service"""
from __future__ import annotations
from typing import Optional

from app.repos.sql_snippet_repo import SqlSnippetRepo, SqlSnippet, DIALECTS


class SqlLibService:
    def __init__(self, repo: SqlSnippetRepo):
        self.repo = repo

    def list(self, project_id: Optional[int] = None, include_global: bool = True,
             dialect: Optional[str] = None) -> list[SqlSnippet]:
        return self.repo.list_all(
            project_id=project_id, include_global=include_global, dialect=dialect
        )

    def search(self, query: str, project_id: Optional[int] = None,
               dialect: Optional[str] = None) -> list[SqlSnippet]:
        return self.repo.search(query, project_id=project_id, dialect=dialect)

    def get(self, snippet_id: int) -> Optional[SqlSnippet]:
        return self.repo.get(snippet_id)

    def create(self, title: str, sql_text: str, description: str = "", tags: str = "",
               project_id: Optional[int] = None,
               dialect: str = "postgres") -> SqlSnippet:
        title = title.strip()
        sql_text = sql_text.strip()
        if not title:
            raise ValueError("标题不能为空")
        if not sql_text:
            raise ValueError("SQL 内容不能为空")
        if dialect not in DIALECTS:
            dialect = "postgres"
        s = SqlSnippet(
            id=None, title=title, description=description.strip(), sql_text=sql_text,
            tags=tags.strip(), project_id=project_id, dialect=dialect, use_count=0,
        )
        sid = self.repo.create(s)
        return self.repo.get(sid)

    def update(self, snippet_id: int, **kwargs) -> SqlSnippet:
        existing = self.repo.get(snippet_id)
        if not existing:
            raise ValueError("SQL 片段不存在")
        for k, v in kwargs.items():
            if k in ("title", "description", "sql_text", "tags") and isinstance(v, str):
                v = v.strip()
            if k == "dialect" and v not in DIALECTS:
                continue
            if hasattr(existing, k):
                setattr(existing, k, v)
        self.repo.update(existing)
        return self.repo.get(snippet_id)

    def delete(self, snippet_id: int) -> None:
        self.repo.delete(snippet_id)

    def increment_use(self, snippet_id: int) -> None:
        self.repo.increment_use_count(snippet_id)

    def count(self) -> int:
        return self.repo.count()

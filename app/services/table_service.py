"""TableService — 表结构业务逻辑"""
from __future__ import annotations
import re
from typing import Optional

from app.repos.table_repo import TableRepo, Table, Column, _build_ddl


_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _valid_ident(name: str) -> bool:
    return bool(_NAME_RE.match(name))


class TableService:
    def __init__(self, repo: TableRepo):
        self.repo = repo

    def list_by_project(self, project_id: int) -> list[Table]:
        return self.repo.list_by_project(project_id)

    def get(self, table_id: int) -> Optional[Table]:
        return self.repo.get(table_id)

    def create(self, project_id: int, name: str, comment: str, columns: list[Column]) -> Table:
        name = name.strip()
        if not _valid_ident(name):
            raise ValueError(f"表名不合法: {name!r} (字母/下划线开头,只含字母数字下划线)")
        if not columns:
            raise ValueError("至少需要 1 列")
        # 重名校验
        existing = self.repo.list_by_project(project_id)
        if any(t.name == name for t in existing):
            raise ValueError(f"表名已存在: {name}")
        # 列名校验
        col_names = [c.name for c in columns]
        if len(set(col_names)) != len(col_names):
            raise ValueError("列名重复")
        for c in columns:
            if not _valid_ident(c.name):
                raise ValueError(f"列名不合法: {c.name!r}")
        # PK 校验
        pks = [c for c in columns if c.pk]
        if len(pks) > 1 and any(not c.nullable for c in pks):
            pass  # SQLite composite key OK

        t = Table(
            id=None, project_id=project_id, name=name, comment=comment.strip(),
            columns=columns, ddl_text="",
        )
        tid = self.repo.create(t)
        return self.repo.get(tid)

    def update(self, table_id: int, name: str, comment: str, columns: list[Column]) -> Table:
        existing = self.repo.get(table_id)
        if not existing:
            raise ValueError(f"表不存在: {table_id}")
        name = name.strip()
        if not _valid_ident(name):
            raise ValueError(f"表名不合法: {name!r}")
        if not columns:
            raise ValueError("至少需要 1 列")
        col_names = [c.name for c in columns]
        if len(set(col_names)) != len(col_names):
            raise ValueError("列名重复")
        for c in columns:
            if not _valid_ident(c.name):
                raise ValueError(f"列名不合法: {c.name!r}")
        existing.name = name
        existing.comment = comment.strip()
        existing.columns = columns
        self.repo.update(existing)
        return self.repo.get(table_id)

    def delete(self, table_id: int) -> None:
        self.repo.delete(table_id)

    def generate_ddl(self, name: str, columns: list[Column]) -> str:
        return _build_ddl(name, columns)

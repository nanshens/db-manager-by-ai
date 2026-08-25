"""ProjectService — 项目业务逻辑"""
from __future__ import annotations
from typing import Optional

from app.repos.project_repo import ProjectRepo, Project
from app.repos.table_repo import TableRepo


class ProjectService:
    def __init__(self, project_repo: ProjectRepo, table_repo: TableRepo):
        self.projects = project_repo
        self.tables = table_repo

    def list_all(self) -> list[Project]:
        return self.projects.list_all()

    def get(self, project_id: int) -> Optional[Project]:
        return self.projects.get(project_id)

    def create(self, name: str, description: str = "", color: str = "#3b82f6") -> Project:
        name = name.strip()
        if not name:
            raise ValueError("项目名不能为空")
        if self.projects.get_by_name(name):
            raise ValueError(f"项目名已存在: {name}")
        p = Project(id=None, name=name, description=description.strip(), color=color)
        pid = self.projects.create(p)
        p.id = pid
        return self.projects.get(pid)

    def update(self, project_id: int, name: str, description: str = "", color: str = "#3b82f6") -> Project:
        existing = self.projects.get(project_id)
        if not existing:
            raise ValueError(f"项目不存在: {project_id}")
        existing.name = name.strip()
        existing.description = description.strip()
        existing.color = color
        self.projects.update(existing)
        return self.projects.get(project_id)

    def delete(self, project_id: int) -> None:
        # CASCADE 删表 / 版本 / diff / compare_config / excel_template
        self.projects.delete(project_id)

    def get_with_stats(self, project_id: int) -> Optional[dict]:
        """返回项目 + 表数 / 版本数 / SQL 数等统计"""
        p = self.projects.get(project_id)
        if not p:
            return None
        from app.repos.db import get_connection
        conn = get_connection(self.projects.db_path)
        table_count = self.tables.count_by_project(project_id)
        version_count = conn.execute(
            "SELECT COUNT(*) AS n FROM data_version WHERE project_id = ?", (project_id,)
        ).fetchone()["n"]
        snippet_count = conn.execute(
            "SELECT COUNT(*) AS n FROM sql_snippet WHERE project_id = ?", (project_id,)
        ).fetchone()["n"]
        return {
            "project": p,
            "table_count": table_count,
            "version_count": version_count,
            "snippet_count": snippet_count,
        }

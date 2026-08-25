"""Project Repository — CRUD for project table"""
from __future__ import annotations
import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

from app.repos.db import get_connection, transaction


@dataclass
class Project:
    id: Optional[int]
    name: str
    description: str = ""
    color: str = "#3b82f6"
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class ProjectRepo:
    def __init__(self, db_path):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self.db_path)

    def list_all(self) -> list[Project]:
        rows = self._conn().execute(
            "SELECT id, name, description, color, created_at, updated_at "
            "FROM project ORDER BY updated_at DESC"
        ).fetchall()
        return [Project(**dict(r)) for r in rows]

    def get(self, project_id: int) -> Optional[Project]:
        r = self._conn().execute(
            "SELECT id, name, description, color, created_at, updated_at "
            "FROM project WHERE id = ?",
            (project_id,),
        ).fetchone()
        return Project(**dict(r)) if r else None

    def get_by_name(self, name: str) -> Optional[Project]:
        r = self._conn().execute(
            "SELECT id, name, description, color, created_at, updated_at "
            "FROM project WHERE name = ?",
            (name,),
        ).fetchone()
        return Project(**dict(r)) if r else None

    def create(self, project: Project) -> int:
        now = _now()
        with transaction(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO project (name, description, color, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (project.name, project.description, project.color, now, now),
            )
            return cur.lastrowid

    def update(self, project: Project) -> None:
        with transaction(self.db_path) as conn:
            conn.execute(
                "UPDATE project SET name=?, description=?, color=?, updated_at=? WHERE id=?",
                (project.name, project.description, project.color, _now(), project.id),
            )

    def delete(self, project_id: int) -> None:
        with transaction(self.db_path) as conn:
            conn.execute("DELETE FROM project WHERE id = ?", (project_id,))

    def count(self) -> int:
        r = self._conn().execute("SELECT COUNT(*) AS n FROM project").fetchone()
        return r["n"]

    def touch(self, project_id: int) -> None:
        with transaction(self.db_path) as conn:
            conn.execute("UPDATE project SET updated_at=? WHERE id=?", (_now(), project_id))

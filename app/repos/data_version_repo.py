"""Data Version Repository — 存文件元数据(不存文件本身)"""
from __future__ import annotations
import json
import sqlite3
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional

from app.repos.db import get_connection, transaction


@dataclass
class SourceFile:
    table_name: str
    format: str            # csv / tsv / xlsx
    local_path: str
    rows: int = 0
    sha256: str = ""
    uploaded_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DataVersion:
    id: Optional[int]
    project_id: int
    version_name: str
    description: str = ""
    source_files: list[SourceFile] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source_files"] = [f.to_dict() for f in self.source_files]
        return d


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class DataVersionRepo:
    def __init__(self, db_path):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self.db_path)

    def list_by_project(self, project_id: int) -> list[DataVersion]:
        rows = self._conn().execute(
            "SELECT id, project_id, version_name, description, source_files, created_at FROM data_version "
            "WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
        return [self._row_to_version(r) for r in rows]

    def _row_to_version(self, r: sqlite3.Row) -> DataVersion:
        files = [SourceFile(**f) for f in json.loads(r["source_files"] or "[]")]
        return DataVersion(
            id=r["id"], project_id=r["project_id"],
            version_name=r["version_name"], description=r["description"] or "",
            source_files=files, created_at=r["created_at"], updated_at=r["created_at"],
        )

    def get(self, version_id: int) -> Optional[DataVersion]:
        r = self._conn().execute(
            "SELECT id, project_id, version_name, description, source_files, created_at "
            "FROM data_version WHERE id = ?",
            (version_id,),
        ).fetchone()
        return self._row_to_version(r) if r else None

    def get_by_name(self, project_id: int, name: str) -> Optional[DataVersion]:
        r = self._conn().execute(
            "SELECT id, project_id, version_name, description, source_files, created_at "
            "FROM data_version WHERE project_id = ? AND version_name = ?",
            (project_id, name),
        ).fetchone()
        return self._row_to_version(r) if r else None

    def create(self, v: DataVersion) -> int:
        now = _now()
        files_json = json.dumps([f.to_dict() for f in v.source_files], ensure_ascii=False)
        with transaction(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO data_version (project_id, version_name, description, source_files, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (v.project_id, v.version_name, v.description, files_json, now),
            )
            return cur.lastrowid

    def update(self, v: DataVersion) -> None:
        files_json = json.dumps([f.to_dict() for f in v.source_files], ensure_ascii=False)
        with transaction(self.db_path) as conn:
            conn.execute(
                "UPDATE data_version SET version_name=?, description=?, source_files=? WHERE id=?",
                (v.version_name, v.description, files_json, v.id),
            )

    def delete(self, version_id: int) -> None:
        with transaction(self.db_path) as conn:
            conn.execute("DELETE FROM data_version WHERE id = ?", (version_id,))

    def count_by_project(self, project_id: int) -> int:
        r = self._conn().execute(
            "SELECT COUNT(*) AS n FROM data_version WHERE project_id = ?", (project_id,)
        ).fetchone()
        return r["n"]

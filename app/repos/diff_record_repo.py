"""Diff Record Repository — diff 历史"""
from __future__ import annotations
import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

from app.repos.db import get_connection, transaction


@dataclass
class DiffRecord:
    id: Optional[int]
    left_label: str
    right_label: str
    left_meta_json: str = "{}"
    right_meta_json: str = "{}"
    result_json: str = "{}"
    project_id: Optional[int] = None
    config_id: Optional[int] = None
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class DiffRecordRepo:
    def __init__(self, db_path):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self.db_path)

    def list_recent(self, limit: int = 50) -> list[DiffRecord]:
        rows = self._conn().execute(
            "SELECT * FROM diff_record ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [DiffRecord(**dict(r)) for r in rows]

    def get(self, record_id: int) -> Optional[DiffRecord]:
        r = self._conn().execute("SELECT * FROM diff_record WHERE id = ?", (record_id,)).fetchone()
        return DiffRecord(**dict(r)) if r else None

    def create(self, r: DiffRecord) -> int:
        now = _now()
        with transaction(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO diff_record (project_id, left_label, right_label, left_meta_json, "
                "right_meta_json, result_json, config_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (r.project_id, r.left_label, r.right_label, r.left_meta_json, r.right_meta_json,
                 r.result_json, r.config_id, now),
            )
            return cur.lastrowid

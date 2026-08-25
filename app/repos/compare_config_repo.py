"""Compare Config Repository — 对比配置"""
from __future__ import annotations
import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

from app.repos.db import get_connection, transaction


@dataclass
class CompareConfig:
    id: Optional[int]
    project_id: int
    table_name: str
    config_name: str = "默认配置"
    pk_columns: list[str] = None
    compare_columns: list[str] = None  # None = 全列
    ignore_columns: list[str] = None
    case_sensitive: bool = False
    trim_whitespace: bool = True
    is_default: bool = False
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["pk_columns"] = self.pk_columns or []
        d["compare_columns"] = self.compare_columns or []
        d["ignore_columns"] = self.ignore_columns or []
        return d

    def __post_init__(self):
        if self.pk_columns is None:
            self.pk_columns = []
        if self.compare_columns is None:
            self.compare_columns = []
        if self.ignore_columns is None:
            self.ignore_columns = []


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class CompareConfigRepo:
    def __init__(self, db_path):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self.db_path)

    def list_by_project_table(self, project_id: int, table_name: str) -> list[CompareConfig]:
        rows = self._conn().execute(
            "SELECT * FROM compare_config WHERE project_id = ? AND table_name = ? ORDER BY is_default DESC, config_name",
            (project_id, table_name),
        ).fetchall()
        return [self._row_to_cfg(r) for r in rows]

    def list_by_project(self, project_id: int) -> list[CompareConfig]:
        rows = self._conn().execute(
            "SELECT * FROM compare_config WHERE project_id = ? ORDER BY table_name, is_default DESC, config_name",
            (project_id,),
        ).fetchall()
        return [self._row_to_cfg(r) for r in rows]

    def _row_to_cfg(self, r: sqlite3.Row) -> CompareConfig:
        return CompareConfig(
            id=r["id"], project_id=r["project_id"], table_name=r["table_name"],
            config_name=r["config_name"],
            pk_columns=json.loads(r["pk_columns_json"] or "[]"),
            compare_columns=json.loads(r["compare_columns_json"] or "null"),
            ignore_columns=json.loads(r["ignore_columns_json"] or "[]"),
            case_sensitive=bool(r["case_sensitive"]),
            trim_whitespace=bool(r["trim_whitespace"]),
            is_default=bool(r["is_default"]),
            created_at=r["created_at"], updated_at=r["updated_at"],
        )

    def get(self, config_id: int) -> Optional[CompareConfig]:
        r = self._conn().execute("SELECT * FROM compare_config WHERE id = ?", (config_id,)).fetchone()
        return self._row_to_cfg(r) if r else None

    def get_default(self, project_id: int, table_name: str) -> Optional[CompareConfig]:
        r = self._conn().execute(
            "SELECT * FROM compare_config WHERE project_id = ? AND table_name = ? AND is_default = 1 LIMIT 1",
            (project_id, table_name),
        ).fetchone()
        return self._row_to_cfg(r) if r else None

    def create(self, c: CompareConfig) -> int:
        now = _now()
        # 若设为默认,先清除该表其他默认
        if c.is_default:
            self._clear_defaults(c.project_id, c.table_name)
        with transaction(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO compare_config (project_id, table_name, config_name, pk_columns_json, "
                "compare_columns_json, ignore_columns_json, case_sensitive, trim_whitespace, "
                "is_default, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (c.project_id, c.table_name, c.config_name,
                 json.dumps(c.pk_columns),
                 json.dumps(c.compare_columns) if c.compare_columns is not None else None,
                 json.dumps(c.ignore_columns),
                 int(c.case_sensitive), int(c.trim_whitespace), int(c.is_default), now, now),
            )
            return cur.lastrowid

    def update(self, c: CompareConfig) -> None:
        if c.is_default:
            self._clear_defaults(c.project_id, c.table_name, exclude_id=c.id)
        with transaction(self.db_path) as conn:
            conn.execute(
                "UPDATE compare_config SET config_name=?, pk_columns_json=?, compare_columns_json=?, "
                "ignore_columns_json=?, case_sensitive=?, trim_whitespace=?, is_default=?, updated_at=? "
                "WHERE id=?",
                (c.config_name,
                 json.dumps(c.pk_columns),
                 json.dumps(c.compare_columns) if c.compare_columns is not None else None,
                 json.dumps(c.ignore_columns),
                 int(c.case_sensitive), int(c.trim_whitespace), int(c.is_default), _now(), c.id),
            )

    def _clear_defaults(self, project_id: int, table_name: str, exclude_id: Optional[int] = None) -> None:
        with transaction(self.db_path) as conn:
            sql = "UPDATE compare_config SET is_default=0 WHERE project_id=? AND table_name=? AND is_default=1"
            params = [project_id, table_name]
            if exclude_id is not None:
                sql += " AND id != ?"
                params.append(exclude_id)
            conn.execute(sql, params)

    def delete(self, config_id: int) -> None:
        with transaction(self.db_path) as conn:
            conn.execute("DELETE FROM compare_config WHERE id = ?", (config_id,))

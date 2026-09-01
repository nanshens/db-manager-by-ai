"""Excel Template Repository"""
from __future__ import annotations
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

from app.repos.db import get_connection, transaction


@dataclass
class ExcelTemplate:
    id: Optional[int]
    template_name: str
    # mode 1 (mapping): 用下面 3 个字段
    config_sheet_name: str = ""
    table_name_col: str = ""
    sheet_name_col: str = ""
    project_id: Optional[int] = None  # NULL = 全局
    header_row: int = 1
    data_start_row: int = 2
    column_start: int = 1
    # 解析模式: mapping / sheet_name / chinese_name
    parse_mode: str = "mapping"
    # JSON: {中文sheet名: 英文表名} — mode 3 用
    name_mapping: str = "{}"
    description: str = ""
    use_count: int = 0
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def get_name_mapping(self) -> dict[str, str]:
        """name_mapping JSON → dict"""
        import json
        try:
            m = json.loads(self.name_mapping or "{}")
            return m if isinstance(m, dict) else {}
        except Exception:
            return {}

    def set_name_mapping(self, m: dict[str, str]) -> None:
        import json
        self.name_mapping = json.dumps(m, ensure_ascii=False)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class ExcelTemplateRepo:
    def __init__(self, db_path):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self.db_path)

    def list_all(self, project_id: Optional[int] = None, include_global: bool = True) -> list[ExcelTemplate]:
        sql = "SELECT * FROM excel_template"
        params: list = []
        clauses = []
        if project_id is not None and include_global:
            clauses.append("(project_id = ? OR project_id IS NULL)")
            params.append(project_id)
        elif project_id is not None:
            clauses.append("project_id = ?")
            params.append(project_id)
        elif include_global is False:
            clauses.append("project_id IS NULL")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY use_count DESC, updated_at DESC"
        rows = self._conn().execute(sql, params).fetchall()
        return [ExcelTemplate(**dict(r)) for r in rows]

    def get(self, template_id: int) -> Optional[ExcelTemplate]:
        r = self._conn().execute("SELECT * FROM excel_template WHERE id = ?", (template_id,)).fetchone()
        return ExcelTemplate(**dict(r)) if r else None

    def get_by_name(self, name: str, project_id: Optional[int]) -> Optional[ExcelTemplate]:
        if project_id is None:
            r = self._conn().execute(
                "SELECT * FROM excel_template WHERE template_name = ? AND project_id IS NULL",
                (name,),
            ).fetchone()
        else:
            r = self._conn().execute(
                "SELECT * FROM excel_template WHERE template_name = ? AND (project_id = ? OR project_id IS NULL) LIMIT 1",
                (name, project_id),
            ).fetchone()
        return ExcelTemplate(**dict(r)) if r else None

    def create(self, t: ExcelTemplate) -> int:
        now = _now()
        with transaction(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO excel_template (project_id, template_name, config_sheet_name, "
                "table_name_col, sheet_name_col, header_row, data_start_row, column_start, "
                "parse_mode, name_mapping, description, use_count, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (t.project_id, t.template_name, t.config_sheet_name,
                 t.table_name_col, t.sheet_name_col, t.header_row, t.data_start_row,
                 t.column_start, t.parse_mode, t.name_mapping,
                 t.description, t.use_count, now, now),
            )
            return cur.lastrowid

    def update(self, t: ExcelTemplate) -> None:
        with transaction(self.db_path) as conn:
            conn.execute(
                "UPDATE excel_template SET project_id=?, template_name=?, config_sheet_name=?, "
                "table_name_col=?, sheet_name_col=?, header_row=?, data_start_row=?, column_start=?, "
                "parse_mode=?, name_mapping=?, description=?, updated_at=? WHERE id=?",
                (t.project_id, t.template_name, t.config_sheet_name,
                 t.table_name_col, t.sheet_name_col, t.header_row, t.data_start_row,
                 t.column_start, t.parse_mode, t.name_mapping,
                 t.description, _now(), t.id),
            )

    def delete(self, template_id: int) -> None:
        with transaction(self.db_path) as conn:
            conn.execute("DELETE FROM excel_template WHERE id = ?", (template_id,))

    def increment_use_count(self, template_id: int) -> None:
        with transaction(self.db_path) as conn:
            conn.execute("UPDATE excel_template SET use_count = use_count + 1 WHERE id = ?", (template_id,))

    def count(self) -> int:
        r = self._conn().execute("SELECT COUNT(*) AS n FROM excel_template").fetchone()
        return r["n"]

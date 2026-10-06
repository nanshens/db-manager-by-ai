"""Table Repository — CRUD for db_table"""
from __future__ import annotations
import json
import sqlite3
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional

from app.repos.db import get_connection, transaction


@dataclass
class Column:
    name: str
    type: str = "TEXT"
    nullable: bool = True
    default: str = ""
    pk: bool = False
    comment: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Table:
    id: Optional[int]
    project_id: int
    name: str
    comment: str = ""
    columns: list[Column] = field(default_factory=list)
    ddl_text: str = ""
    fk_ddl_text: str = ""        # FOREIGN KEY 约束 DDL(可空)
    index_ddl_text: str = ""     # INDEX 约束 DDL(可空)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["columns"] = [c.to_dict() for c in self.columns]
        return d


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _row_to_table(r: sqlite3.Row) -> Table:
    cols = [Column(**c) for c in json.loads(r["columns_json"] or "[]")]
    return Table(
        id=r["id"],
        project_id=r["project_id"],
        name=r["name"],
        comment=r["comment"] or "",
        columns=cols,
        ddl_text=r["ddl_text"] or "",
        fk_ddl_text=r["fk_ddl_text"] or "",
        index_ddl_text=r["index_ddl_text"] or "",
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


def _build_ddl(table_name: str, columns: list[Column]) -> str:
    """生成 CREATE TABLE DDL"""
    if not columns:
        return f"CREATE TABLE {table_name} ();"

    lines = []
    pks = [c.name for c in columns if c.pk]
    for c in columns:
        parts = [c.name, c.type]
        if c.pk:
            parts.append("PRIMARY KEY")
        if not c.nullable and not c.pk:
            parts.append("NOT NULL")
        if c.default:
            parts.append(f"DEFAULT {c.default}")
        if c.comment:
            parts.append(f"-- {c.comment}")
        lines.append("  " + " ".join(parts) + ("," if c != columns[-1] or len(pks) > 1 else ""))
    if len(pks) > 1:
        lines.append(f"  PRIMARY KEY ({', '.join(pks)})")
    return f"CREATE TABLE {table_name} (\n" + "\n".join(lines) + "\n);"


class TableRepo:
    def __init__(self, db_path):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self.db_path)

    def list_by_project(self, project_id: int) -> list[Table]:
        rows = self._conn().execute(
            "SELECT id, project_id, name, comment, columns_json, ddl_text, "
            "fk_ddl_text, index_ddl_text, created_at, updated_at "
            "FROM db_table WHERE project_id = ? ORDER BY name",
            (project_id,),
        ).fetchall()
        return [_row_to_table(r) for r in rows]

    def get(self, table_id: int) -> Optional[Table]:
        r = self._conn().execute(
            "SELECT id, project_id, name, comment, columns_json, ddl_text, "
            "fk_ddl_text, index_ddl_text, created_at, updated_at "
            "FROM db_table WHERE id = ?",
            (table_id,),
        ).fetchone()
        return _row_to_table(r) if r else None

    def count_by_project(self, project_id: int) -> int:
        r = self._conn().execute(
            "SELECT COUNT(*) AS n FROM db_table WHERE project_id = ?", (project_id,)
        ).fetchone()
        return r["n"]

    def create(self, table: Table) -> int:
        now = _now()
        cols_json = json.dumps([c.to_dict() for c in table.columns], ensure_ascii=False)
        ddl = table.ddl_text or _build_ddl(table.name, table.columns)
        with transaction(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO db_table "
                "(project_id, name, comment, columns_json, ddl_text, fk_ddl_text, index_ddl_text, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    table.project_id, table.name, table.comment,
                    cols_json, ddl,
                    table.fk_ddl_text or "", table.index_ddl_text or "",
                    now, now,
                ),
            )
            return cur.lastrowid

    def update(self, table: Table) -> None:
        cols_json = json.dumps([c.to_dict() for c in table.columns], ensure_ascii=False)
        ddl = _build_ddl(table.name, table.columns)
        with transaction(self.db_path) as conn:
            conn.execute(
                "UPDATE db_table SET name=?, comment=?, columns_json=?, ddl_text=?, "
                "fk_ddl_text=?, index_ddl_text=?, updated_at=? WHERE id=?",
                (
                    table.name, table.comment, cols_json, ddl,
                    table.fk_ddl_text or "", table.index_ddl_text or "",
                    _now(), table.id,
                ),
            )

    def delete(self, table_id: int) -> None:
        with transaction(self.db_path) as conn:
            conn.execute("DELETE FROM db_table WHERE id = ?", (table_id,))

    def delete_by_project(self, project_id: int) -> int:
        with transaction(self.db_path) as conn:
            cur = conn.execute("DELETE FROM db_table WHERE project_id = ?", (project_id,))
            return cur.rowcount

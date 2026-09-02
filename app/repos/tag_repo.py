"""Tag Repository — 表标签(多对多)

- tag 表:project 作用域,UNIQUE(project_id, name)
- table_tag 表:多对多关联 db_table

设计要点:
- 同名 tag 在不同 project 是不同行(避免冲突)
- 一张表可打多个 tag,一个 tag 可含多张表
- tag color 字段保留(预留 UI 标签彩色显示)
- 删除 tag 自动级联删除 table_tag(ON DELETE CASCADE)
- 删除 db_table 自动级联删除 table_tag(ON DELETE CASCADE)
"""
from __future__ import annotations
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

from app.repos.db import get_connection, transaction


# 一些好看的默认颜色(可让用户选,也可自己改)
TAG_COLORS = [
    "#64748b",  # 默认灰
    "#ef4444",  # 红
    "#f97316",  # 橙
    "#eab308",  # 黄
    "#22c55e",  # 绿
    "#06b6d4",  # 青
    "#3b82f6",  # 蓝
    "#8b5cf6",  # 紫
    "#ec4899",  # 粉
]


@dataclass
class Tag:
    id: Optional[int]
    project_id: int
    name: str
    color: str = "#64748b"
    description: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _row_to_tag(r: sqlite3.Row) -> Tag:
    return Tag(
        id=r["id"],
        project_id=r["project_id"],
        name=r["name"],
        color=r["color"] or "#64748b",
        description=r["description"] or "",
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


class TagRepo:
    def __init__(self, db_path):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self.db_path)

    # ============== tag CRUD ==============
    def list_by_project(self, project_id: int) -> list[Tag]:
        rows = self._conn().execute(
            "SELECT * FROM tag WHERE project_id = ? ORDER BY name",
            (project_id,),
        ).fetchall()
        return [_row_to_tag(r) for r in rows]

    def get(self, tag_id: int) -> Optional[Tag]:
        r = self._conn().execute("SELECT * FROM tag WHERE id = ?", (tag_id,)).fetchone()
        return _row_to_tag(r) if r else None

    def get_by_name(self, project_id: int, name: str) -> Optional[Tag]:
        r = self._conn().execute(
            "SELECT * FROM tag WHERE project_id = ? AND name = ?",
            (project_id, name),
        ).fetchone()
        return _row_to_tag(r) if r else None

    def create(self, tag: Tag) -> int:
        with transaction(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO tag (project_id, name, color, description, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (tag.project_id, tag.name, tag.color or "#64748b",
                 tag.description, _now(), _now()),
            )
            return cur.lastrowid

    def update(self, tag: Tag) -> None:
        with transaction(self.db_path) as conn:
            conn.execute(
                "UPDATE tag SET name=?, color=?, description=?, updated_at=? WHERE id=?",
                (tag.name, tag.color or "#64748b", tag.description, _now(), tag.id),
            )

    def delete(self, tag_id: int) -> None:
        with transaction(self.db_path) as conn:
            conn.execute("DELETE FROM tag WHERE id = ?", (tag_id,))

    # ============== table_tag 多对多 ==============
    def add_table_to_tag(self, tag_id: int, table_id: int) -> None:
        """幂等:重复添加不报错"""
        with transaction(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO table_tag (tag_id, table_id, created_at) VALUES (?, ?, ?)",
                (tag_id, table_id, _now()),
            )

    def remove_table_from_tag(self, tag_id: int, table_id: int) -> None:
        with transaction(self.db_path) as conn:
            conn.execute(
                "DELETE FROM table_tag WHERE tag_id = ? AND table_id = ?",
                (tag_id, table_id),
            )

    def set_table_tags(self, table_id: int, tag_ids: list[int]) -> None:
        """替换表的所有 tag(用于 TagDialog 的多选保存)"""
        with transaction(self.db_path) as conn:
            conn.execute("DELETE FROM table_tag WHERE table_id = ?", (table_id,))
            for tid in tag_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO table_tag (tag_id, table_id, created_at) VALUES (?, ?, ?)",
                    (tid, table_id, _now()),
                )

    def get_tags_for_table(self, table_id: int) -> list[Tag]:
        rows = self._conn().execute(
            "SELECT t.* FROM tag t JOIN table_tag tt ON tt.tag_id = t.id "
            "WHERE tt.table_id = ? ORDER BY t.name",
            (table_id,),
        ).fetchall()
        return [_row_to_tag(r) for r in rows]

    def get_table_ids_for_tag(self, tag_id: int) -> list[int]:
        rows = self._conn().execute(
            "SELECT table_id FROM table_tag WHERE tag_id = ?",
            (tag_id,),
        ).fetchall()
        return [r["table_id"] for r in rows]

    def get_tables_for_tag(self, tag_id: int) -> list[int]:
        """跟 get_table_ids_for_tag 同义,语义更清楚"""
        return self.get_table_ids_for_tag(tag_id)

    def get_table_tags_map(self, project_id: int) -> dict[int, list[Tag]]:
        """返回 {table_id: [Tag, ...]} 映射,用于批量显示表列表时给每张表附加 tag

        实现:一次 join 查询,避免 N+1
        """
        rows = self._conn().execute(
            "SELECT tt.table_id, t.* FROM tag t "
            "JOIN table_tag tt ON tt.tag_id = t.id "
            "JOIN db_table dt ON dt.id = tt.table_id "
            "WHERE dt.project_id = ? "
            "ORDER BY t.name",
            (project_id,),
        ).fetchall()
        out: dict[int, list[Tag]] = {}
        for r in rows:
            tid = r["table_id"]
            out.setdefault(tid, []).append(_row_to_tag(r))
        return out

"""DB Link Repository — 管理数据库连接信息(postgres / mysql / oracle)

用途:在 SQL 生成器里选 db 链接,生成 pg_dump / mysqldump / expdp 命令,
把数据库表数据导出为 INSERT SQL。
"""
from __future__ import annotations
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

from app.repos.db import get_connection, transaction


# 端口默认值
DEFAULT_PORTS = {
    "postgres": 5432,
    "mysql": 3306,
    "oracle": 1521,
}


@dataclass
class DbLink:
    id: Optional[int]
    name: str
    db_type: str  # postgres / mysql / oracle
    host: str = ""
    port: int = 0
    username: str = ""
    password: str = ""
    database: str = ""  # pg: db name, mysql: db name, oracle: 留空
    schema: str = "public"  # pg/mysql schema, oracle: user/owner
    service_name: str = ""  # 仅 oracle 用(SID 或 service name)
    description: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def default_port(self) -> int:
        return DEFAULT_PORTS.get(self.db_type, 0) or self.port


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class DbLinkRepo:
    def __init__(self, db_path):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self.db_path)

    def list_all(self) -> list[DbLink]:
        rows = self._conn().execute(
            "SELECT * FROM db_link ORDER BY updated_at DESC"
        ).fetchall()
        return [DbLink(**dict(r)) for r in rows]

    def get(self, link_id: int) -> Optional[DbLink]:
        r = self._conn().execute(
            "SELECT * FROM db_link WHERE id = ?", (link_id,)
        ).fetchone()
        return DbLink(**dict(r)) if r else None

    def get_by_name(self, name: str) -> Optional[DbLink]:
        r = self._conn().execute(
            "SELECT * FROM db_link WHERE name = ?", (name,)
        ).fetchone()
        return DbLink(**dict(r)) if r else None

    def create(self, link: DbLink) -> int:
        now = _now()
        # 端口为空时填默认
        if not link.port and link.db_type in DEFAULT_PORTS:
            link.port = DEFAULT_PORTS[link.db_type]
        with transaction(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO db_link (name, db_type, host, port, username, password, "
                "database, schema, service_name, description, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (link.name, link.db_type, link.host, link.port, link.username, link.password,
                 link.database, link.schema, link.service_name, link.description, now, now),
            )
            return cur.lastrowid

    def update(self, link: DbLink) -> None:
        if not link.port and link.db_type in DEFAULT_PORTS:
            link.port = DEFAULT_PORTS[link.db_type]
        with transaction(self.db_path) as conn:
            conn.execute(
                "UPDATE db_link SET name=?, db_type=?, host=?, port=?, username=?, password=?, "
                "database=?, schema=?, service_name=?, description=?, updated_at=? WHERE id=?",
                (link.name, link.db_type, link.host, link.port, link.username, link.password,
                 link.database, link.schema, link.service_name, link.description,
                 _now(), link.id),
            )

    def delete(self, link_id: int) -> None:
        with transaction(self.db_path) as conn:
            conn.execute("DELETE FROM db_link WHERE id = ?", (link_id,))

    def count(self) -> int:
        r = self._conn().execute("SELECT COUNT(*) AS n FROM db_link").fetchone()
        return r["n"]

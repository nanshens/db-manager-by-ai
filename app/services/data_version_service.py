"""Data Version Service — 文件元数据管理"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
from typing import Optional
from datetime import datetime

from app.repos.data_version_repo import DataVersionRepo, DataVersion, SourceFile
from app.repos.table_repo import TableRepo


def _sha256_of_file(path: str, chunk: int = 64 * 1024) -> str:
    """流式算 sha256,避免大文件读入内存"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _detect_format(path: str) -> str:
    p = path.lower()
    if p.endswith(".csv"):
        return "csv"
    if p.endswith(".tsv"):
        return "tsv"
    if p.endswith(".xlsx"):
        return "xlsx"
    if p.endswith(".xls"):
        return "xls"
    return "unknown"


def _count_rows(path: str, fmt: str) -> int:
    """轻量估算行数(不全读)"""
    try:
        if fmt in ("csv", "tsv"):
            # 快速数 \n
            with open(path, "rb") as f:
                buf = f.read(64 * 1024)
                # 取第一个换行符的位置作为行长度估算
                first_nl = buf.find(b"\n")
                if first_nl <= 0:
                    return -1
                est = os.path.getsize(path) // (first_nl + 1)
                return est
        # xlsx 不快速数,返回 -1
        return -1
    except OSError:
        return -1


class DataVersionService:
    def __init__(self, repo: DataVersionRepo, table_repo: TableRepo):
        self.repo = repo
        self.table_repo = table_repo

    def list_by_project(self, project_id: int) -> list[DataVersion]:
        return self.repo.list_by_project(project_id)

    def get(self, version_id: int) -> Optional[DataVersion]:
        return self.repo.get(version_id)

    def create(self, project_id: int, version_name: str, description: str,
               file_paths: dict[str, str]) -> DataVersion:
        """file_paths: {table_name: local_path}"""
        version_name = version_name.strip()
        if not version_name:
            raise ValueError("版本名不能为空")
        if not file_paths:
            raise ValueError("至少需要一个文件")

        if self.repo.get_by_name(project_id, version_name):
            raise ValueError(f"版本名已存在: {version_name}")

        files = []
        for table_name, path in file_paths.items():
            if not os.path.exists(path):
                raise ValueError(f"文件不存在: {path}")
            fmt = _detect_format(path)
            files.append(SourceFile(
                table_name=table_name.strip(),
                format=fmt,
                local_path=str(Path(path).resolve()),
                rows=_count_rows(path, fmt),
                sha256=_sha256_of_file(path),
                uploaded_at=datetime.now().isoformat(timespec="seconds"),
            ))

        v = DataVersion(
            id=None, project_id=project_id, version_name=version_name,
            description=description.strip(), source_files=files,
        )
        vid = self.repo.create(v)
        return self.repo.get(vid)

    def delete(self, version_id: int) -> None:
        self.repo.delete(version_id)

    def count_by_project(self, project_id: int) -> int:
        return self.repo.count_by_project(project_id)

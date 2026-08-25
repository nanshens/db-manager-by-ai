"""Diff Service — 业务编排层;具体算法在 core/diff_engine"""
from __future__ import annotations
import json
from dataclasses import asdict
from typing import Optional

from app.repos.diff_record_repo import DiffRecordRepo, DiffRecord
from app.repos.table_repo import TableRepo
from app.repos.compare_config_repo import CompareConfigRepo


class DiffService:
    def __init__(self, diff_repo: DiffRecordRepo, table_repo: TableRepo,
                 config_repo: CompareConfigRepo):
        self.diff_repo = diff_repo
        self.table_repo = table_repo
        self.config_repo = config_repo

    def list_recent(self, limit: int = 50) -> list[DiffRecord]:
        return self.diff_repo.list_recent(limit=limit)

    def save_record(self, project_id: Optional[int], left_label: str, right_label: str,
                    left_meta: dict, right_meta: dict, result: dict,
                    config_id: Optional[int] = None) -> int:
        r = DiffRecord(
            id=None, project_id=project_id,
            left_label=left_label, right_label=right_label,
            left_meta_json=json.dumps(left_meta, ensure_ascii=False),
            right_meta_json=json.dumps(right_meta, ensure_ascii=False),
            result_json=json.dumps(result, ensure_ascii=False, default=str),
            config_id=config_id,
        )
        return self.diff_repo.create(r)

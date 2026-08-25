"""Compare Config Service — 对比配置管理"""
from __future__ import annotations
from typing import Optional

from app.repos.compare_config_repo import CompareConfigRepo, CompareConfig


class CompareConfigService:
    def __init__(self, repo: CompareConfigRepo):
        self.repo = repo

    def list_for_table(self, project_id: int, table_name: str) -> list[CompareConfig]:
        return self.repo.list_by_project_table(project_id, table_name)

    def list_for_project(self, project_id: int) -> list[CompareConfig]:
        return self.repo.list_by_project(project_id)

    def get_default(self, project_id: int, table_name: str) -> CompareConfig:
        """返回该表的默认对比配置;若无,返回临时内存配置(全列严格)"""
        c = self.repo.get_default(project_id, table_name)
        if c:
            return c
        return CompareConfig(
            id=None, project_id=project_id, table_name=table_name,
            config_name="__builtin_strict__",
            pk_columns=[], compare_columns=None, ignore_columns=[],
            case_sensitive=True, trim_whitespace=False, is_default=False,
        )

    def get(self, config_id: int) -> Optional[CompareConfig]:
        return self.repo.get(config_id)

    def create(self, project_id: int, table_name: str, config_name: str,
               pk_columns: list[str], compare_columns: Optional[list[str]] = None,
               ignore_columns: Optional[list[str]] = None,
               case_sensitive: bool = False, trim_whitespace: bool = True,
               is_default: bool = False) -> CompareConfig:
        config_name = config_name.strip()
        if not config_name:
            raise ValueError("配置名不能为空")
        if not pk_columns:
            raise ValueError("至少需要 1 个主键列")
        c = CompareConfig(
            id=None, project_id=project_id, table_name=table_name,
            config_name=config_name, pk_columns=pk_columns,
            compare_columns=compare_columns, ignore_columns=ignore_columns or [],
            case_sensitive=case_sensitive, trim_whitespace=trim_whitespace,
            is_default=is_default,
        )
        cid = self.repo.create(c)
        return self.repo.get(cid)

    def update(self, config_id: int, **kwargs) -> CompareConfig:
        existing = self.repo.get(config_id)
        if not existing:
            raise ValueError("配置不存在")
        for k, v in kwargs.items():
            if hasattr(existing, k):
                setattr(existing, k, v)
        self.repo.update(existing)
        return self.repo.get(config_id)

    def delete(self, config_id: int) -> None:
        self.repo.delete(config_id)

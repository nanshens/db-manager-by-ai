"""Service Registry — 全局服务访问点(简化版 DI)"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal

from app.repos.db import init_db, get_connection
from app.repos.project_repo import ProjectRepo
from app.repos.table_repo import TableRepo
from app.repos.data_version_repo import DataVersionRepo
from app.repos.sql_snippet_repo import SqlSnippetRepo
from app.repos.compare_config_repo import CompareConfigRepo
from app.repos.excel_template_repo import ExcelTemplateRepo
from app.repos.diff_record_repo import DiffRecordRepo
from app.repos.db_link_repo import DbLinkRepo
from app.services.project_service import ProjectService
from app.services.table_service import TableService
from app.services.data_version_service import DataVersionService
from app.services.sql_lib_service import SqlLibService
from app.services.compare_config_service import CompareConfigService
from app.services.excel_template_service import ExcelTemplateService
from app.services.diff_service import DiffService


class _EventBus(QObject):
    """全局事件总线 — 用于跨 tab 通知(如版本变化时刷新 diff 页面)"""
    data_version_changed = Signal()  # 数据版本列表变了(创建/删除)
    table_changed = Signal()         # 表列表变了(创建/删除/字段改动)


class Registry:
    """单例服务注册表,启动时初始化一次"""
    _instance: Optional["Registry"] = None

    def __init__(self, db_path: Path):
        self.db_path = db_path
        init_db(db_path)

        # 全局事件总线
        self.bus = _EventBus()

        # Repos
        self.project_repo = ProjectRepo(db_path)
        self.table_repo = TableRepo(db_path)
        self.data_version_repo = DataVersionRepo(db_path)
        self.sql_snippet_repo = SqlSnippetRepo(db_path)
        self.compare_config_repo = CompareConfigRepo(db_path)
        self.excel_template_repo = ExcelTemplateRepo(db_path)
        self.diff_record_repo = DiffRecordRepo(db_path)
        self.db_link_repo = DbLinkRepo(db_path)

        # Services
        self.project_service = ProjectService(self.project_repo, self.table_repo)
        self.table_service = TableService(self.table_repo)
        self.data_version_service = DataVersionService(self.data_version_repo, self.table_repo)
        self.sql_lib_service = SqlLibService(self.sql_snippet_repo)
        self.compare_config_service = CompareConfigService(self.compare_config_repo)
        self.excel_template_service = ExcelTemplateService(self.excel_template_repo)
        self.diff_service = DiffService(
            self.diff_record_repo,
            self.table_repo,
            self.compare_config_repo,
        )

    @classmethod
    def init(cls, db_path: Path) -> "Registry":
        if cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance

    @classmethod
    def instance(cls) -> "Registry":
        if cls._instance is None:
            raise RuntimeError("Registry not initialized. Call Registry.init(db_path) first.")
        return cls._instance


def reg() -> Registry:
    return Registry.instance()

"""Excel Template Service"""
from __future__ import annotations
from typing import Optional

from app.repos.excel_template_repo import ExcelTemplateRepo, ExcelTemplate


class ExcelTemplateService:
    def __init__(self, repo: ExcelTemplateRepo):
        self.repo = repo

    def list(self, project_id: Optional[int] = None, include_global: bool = True) -> list[ExcelTemplate]:
        return self.repo.list_all(project_id=project_id, include_global=include_global)

    def get(self, template_id: int) -> Optional[ExcelTemplate]:
        return self.repo.get(template_id)

    def get_by_name(self, name: str, project_id: Optional[int]) -> Optional[ExcelTemplate]:
        return self.repo.get_by_name(name, project_id)

    def create(self, project_id: Optional[int], template_name: str,
               config_sheet_name: str = "",
               table_name_col: str = "",
               sheet_name_col: str = "",
               header_row: int = 1, data_start_row: int = 2,
               column_start: int = 1,
               parse_mode: str = "mapping",
               name_mapping: str = "{}",
               description: str = "") -> ExcelTemplate:
        template_name = template_name.strip()
        config_sheet_name = config_sheet_name.strip()
        table_name_col = table_name_col.strip()
        sheet_name_col = sheet_name_col.strip()
        if not template_name:
            raise ValueError("模板名不能为空")
        # mode 1 才需要下面 3 个字段
        if parse_mode == "mapping":
            if not config_sheet_name:
                raise ValueError("模式 1 需要配置 sheet 名")
            if not table_name_col:
                raise ValueError("模式 1 需要英文表名列")
            if not sheet_name_col:
                raise ValueError("模式 1 需要 sheet 名称列")
        # mode 3 才需要 name_mapping 不为空
        if parse_mode == "chinese_name":
            import json as _json
            try:
                m = _json.loads(name_mapping or "{}")
            except Exception:
                m = {}
            if not m:
                raise ValueError("模式 3 至少要有一条 sheet→英文表名映射")
        if header_row < 1 or data_start_row < 1 or column_start < 1:
            raise ValueError("行号/列号必须 >= 1")
        if data_start_row < header_row:
            raise ValueError("数据起始行必须 >= header 行")

        t = ExcelTemplate(
            id=None, project_id=project_id, template_name=template_name,
            config_sheet_name=config_sheet_name,
            table_name_col=table_name_col, sheet_name_col=sheet_name_col,
            header_row=header_row, data_start_row=data_start_row,
            column_start=column_start,
            parse_mode=parse_mode, name_mapping=name_mapping,
            description=description.strip(),
        )
        tid = self.repo.create(t)
        return self.repo.get(tid)

    def update(self, template_id: int, **kwargs) -> ExcelTemplate:
        existing = self.repo.get(template_id)
        if not existing:
            raise ValueError("模板不存在")
        for k, v in kwargs.items():
            if hasattr(existing, k):
                setattr(existing, k, v)
        self.repo.update(existing)
        return self.repo.get(template_id)

    def delete(self, template_id: int) -> None:
        self.repo.delete(template_id)

    def increment_use(self, template_id: int) -> None:
        self.repo.increment_use_count(template_id)

    def count(self) -> int:
        return self.repo.count()

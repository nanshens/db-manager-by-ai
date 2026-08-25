"""Overview Tab — 项目概览"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QFrame, QGridLayout, QWidget,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.services.registry import reg


class StatBox(QFrame):
    def __init__(self, icon_name: str, label: str, value: str = "0", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumHeight(80)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        self.icon_label = QLabel()
        self.icon_label.setPixmap(qta.icon(icon_name, color="#3b82f6").pixmap(28, 28))
        layout.addWidget(self.icon_label)

        info = QVBoxLayout()
        info.setSpacing(2)
        l = QLabel(label)
        l.setObjectName("Secondary")
        l.setStyleSheet("font-size: 11px;")
        info.addWidget(l)
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet("font-size: 20px; font-weight: 700;")
        info.addWidget(self.value_label)
        layout.addLayout(info, 1)

    def set_value(self, v) -> None:
        self.value_label.setText(str(v))


class OverviewTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_id: Optional[int] = None
        self._build()
        self.refresh()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Stats grid
        self.grid = QGridLayout()
        self.grid.setSpacing(12)

        self.box_tables = StatBox("mdi6.table", tr("home.stat.tables"))
        self.box_versions = StatBox("mdi6.package-variant", tr("home.stat.versions"))
        self.box_snippets = StatBox("mdi6.code-tags", tr("home.stat.snippets"))
        self.box_configs = StatBox("mdi6.cog-outline", "对比配置")

        self.grid.addWidget(self.box_tables, 0, 0)
        self.grid.addWidget(self.box_versions, 0, 1)
        self.grid.addWidget(self.box_snippets, 0, 2)
        self.grid.addWidget(self.box_configs, 0, 3)

        grid_container = QFrame()
        grid_container.setLayout(self.grid)
        layout.addWidget(grid_container)

        # 项目信息卡
        self.info_card = QFrame()
        self.info_card.setObjectName("Card")
        ic = QVBoxLayout(self.info_card)
        ic.setContentsMargins(20, 16, 20, 16)
        ic.setSpacing(8)

        self.info_title = QLabel(tr("settings.about"))
        self.info_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        ic.addWidget(self.info_title)
        self.info_content = QLabel("")
        self.info_content.setObjectName("Secondary")
        self.info_content.setWordWrap(True)
        ic.addWidget(self.info_content)

        layout.addWidget(self.info_card)
        layout.addStretch()

    def retranslate(self) -> None:
        self.box_tables.set_value(self.box_tables.value_label.text())
        self.box_versions.set_value(self.box_versions.value_label.text())
        self.box_snippets.set_value(self.box_snippets.value_label.text())
        self.box_configs.set_value(self.box_configs.value_label.text())
        self.info_title.setText(tr("settings.about"))
        if self._project_id:
            self.refresh()

    def set_project(self, project_id: int) -> None:
        self._project_id = project_id
        self.refresh()

    def refresh(self) -> None:
        if self._project_id is None:
            return
        stats = reg().project_service.get_with_stats(self._project_id) or {}
        self.box_tables.set_value(stats.get("table_count", 0))
        self.box_versions.set_value(stats.get("version_count", 0))
        self.box_snippets.set_value(stats.get("snippet_count", 0))
        cfg_count = len(reg().compare_config_service.list_for_project(self._project_id))
        self.box_configs.set_value(cfg_count)
        p = stats.get("project")
        if p:
            text = (
                f"{tr('project_detail.created')}: {p.created_at}\n"
                f"{tr('project_detail.updated')}: {p.updated_at}"
            )
            if p.description:
                text = f"{p.description}\n\n{text}"
            self.info_content.setText(text)

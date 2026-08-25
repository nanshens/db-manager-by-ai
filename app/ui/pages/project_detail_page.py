"""项目详情页 — 5 个 Tab 容器"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QFrame, QTabWidget,
    QMessageBox, QWidget,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.ui.widgets import show_toast
from app.services.registry import reg
from app.ui.dialogs import NewProjectDialog
from app.repos.project_repo import Project
from app.ui.pages.project_detail.tables_tab import TablesTab
from app.ui.pages.project_detail.versions_tab import VersionsTab
from app.ui.pages.project_detail.sqlgen_tab import SqlGenTab
from app.ui.pages.project_detail.diff_tab import DiffTab
from app.ui.pages.project_detail.overview_tab import OverviewTab


class ProjectDetailPage(QWidget):
    """项目详情页 — 顶栏(项目名/描述/编辑) + 5 个 Tab"""
    back_clicked = Signal()  # 返回项目列表
    project_updated = Signal()  # 项目被改名/改色,通知其他页

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_id: Optional[int] = None
        self._project: Optional[Project] = None
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Top header
        self.header = QFrame()
        self.header.setObjectName("PageHeader")
        h = QHBoxLayout(self.header)
        h.setContentsMargins(24, 14, 24, 14)
        h.setSpacing(8)

        back_btn = QPushButton()
        back_btn.setIcon(qta.icon("mdi6.arrow-left", color="#94a3b8"))
        back_btn.setFixedSize(32, 32)
        back_btn.clicked.connect(self.back_clicked)
        h.addWidget(back_btn)

        self._color_bar = QFrame()
        self._color_bar.setFixedSize(4, 28)
        h.addWidget(self._color_bar)

        self._name_label = QLabel("—")
        self._name_label.setStyleSheet("font-size: 18px; font-weight: 700;")
        h.addWidget(self._name_label)

        self._meta_label = QLabel("")
        self._meta_label.setObjectName("Muted")
        h.addWidget(self._meta_label, 1)

        edit_btn = QPushButton(tr("action.edit"))
        edit_btn.setObjectName("Ghost")
        edit_btn.setIcon(qta.icon("mdi6.pencil", color="#94a3b8"))
        edit_btn.clicked.connect(self._on_edit)
        h.addWidget(edit_btn)
        outer.addWidget(self.header)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(False)

        # Tabs (order: tables / versions / sqlgen / diff / overview)
        self.tables_tab = TablesTab()
        self.versions_tab = VersionsTab()
        self.sqlgen_tab = SqlGenTab()
        self.diff_tab = DiffTab()
        self.overview_tab = OverviewTab()

        self.tabs.addTab(self.tables_tab, qta.icon("mdi6.table", color="#94a3b8"), tr("project_detail.tabs.tables"))
        self.tabs.addTab(self.versions_tab, qta.icon("mdi6.package-variant", color="#94a3b8"), tr("project_detail.tabs.versions"))
        self.tabs.addTab(self.sqlgen_tab, qta.icon("mdi6.code-tags", color="#94a3b8"), tr("project_detail.tabs.sqlgen"))
        self.tabs.addTab(self.diff_tab, qta.icon("mdi6.swap-horizontal", color="#94a3b8"), tr("project_detail.tabs.diff"))
        self.tabs.addTab(self.overview_tab, qta.icon("mdi6.information-outline", color="#94a3b8"), tr("project_detail.tabs.overview"))
        outer.addWidget(self.tabs, 1)

    def set_project(self, project_id: int) -> None:
        self._project_id = project_id
        self._project = reg().project_service.get(project_id)
        if not self._project:
            return
        self._refresh_header()
        # 通知所有 tab
        self.tables_tab.set_project(project_id)
        self.versions_tab.set_project(project_id)
        self.sqlgen_tab.set_project(project_id)
        self.diff_tab.set_project(project_id)
        self.overview_tab.set_project(project_id)

    def _refresh_header(self) -> None:
        if not self._project:
            return
        self._color_bar.setStyleSheet(
            f"background-color: {self._project.color}; border-radius: 2px;"
        )
        self._name_label.setText(self._project.name)
        if self._project.description:
            self._meta_label.setText(self._project.description)
        else:
            self._meta_label.setText(tr("project_detail.created") + ": " + self._project.created_at)

    def retranslate(self) -> None:
        # 重新设置 tab 文本
        self.tabs.setTabText(0, tr("project_detail.tabs.tables"))
        self.tabs.setTabText(1, tr("project_detail.tabs.versions"))
        self.tabs.setTabText(2, tr("project_detail.tabs.sqlgen"))
        self.tabs.setTabText(3, tr("project_detail.tabs.diff"))
        self.tabs.setTabText(4, tr("project_detail.tabs.overview"))
        # 各 tab 翻译
        for t in (self.tables_tab, self.versions_tab, self.sqlgen_tab,
                  self.diff_tab, self.overview_tab):
            if hasattr(t, "retranslate"):
                t.retranslate()
        self._refresh_header()

    def _on_edit(self) -> None:
        if not self._project:
            return
        dlg = NewProjectDialog(project=self._project, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            v = dlg.get_values()
            try:
                reg().project_service.update(self._project_id, v["name"], v["description"], v["color"])
                self._project = reg().project_service.get(self._project_id)
                self._refresh_header()
                self.project_updated.emit()
                show_toast(tr("toast.saved"), "success")
            except ValueError as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

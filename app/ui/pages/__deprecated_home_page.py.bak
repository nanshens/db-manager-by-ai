"""仪表盘 — 统计 + 最近项目"""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout, QListWidget,
    QListWidgetItem, QSplitter, QWidget,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.ui.pages.base_page import BasePage
from app.ui.widgets import EmptyState
from app.services.registry import reg


class StatCard(QFrame):
    def __init__(self, label_key: str, value: str = "0", accent: str = "#3b82f6", parent=None):
        super().__init__(parent)
        self.setObjectName("StatCard")
        self.setMinimumHeight(90)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        self._label_key = label_key
        self.label = QLabel(tr(label_key))
        self.label.setObjectName("StatLabel")
        layout.addWidget(self.label)
        self.value = QLabel(value)
        self.value.setObjectName("StatValue")
        self.value.setStyleSheet(f"color: {accent};")
        layout.addWidget(self.value)
        layout.addStretch()

    def set_value(self, v) -> None:
        self.value.setText(str(v))

    def retranslate(self) -> None:
        self.label.setText(tr(self._label_key))


class HomePage(BasePage):
    def __init__(self, parent=None):
        super().__init__("home.welcome", "home.subtitle", parent)
        self._build()
        self.refresh()

    def _build(self) -> None:
        # Stats grid
        self.grid = QGridLayout()
        self.grid.setSpacing(16)

        self.stat_projects = StatCard("home.stat.projects", "0", "#3b82f6")
        self.stat_tables = StatCard("home.stat.tables", "0", "#a855f7")
        self.stat_versions = StatCard("home.stat.versions", "0", "#10b981")
        self.stat_snippets = StatCard("home.stat.snippets", "0", "#f59e0b")

        self.grid.addWidget(self.stat_projects, 0, 0)
        self.grid.addWidget(self.stat_tables, 0, 1)
        self.grid.addWidget(self.stat_versions, 0, 2)
        self.grid.addWidget(self.stat_snippets, 0, 3)

        grid_container = QFrame()
        grid_container.setLayout(self.grid)
        self.body_layout.addWidget(grid_container)

        # Recent projects
        recent_label = QLabel(tr("home.recent_projects"))
        recent_label.setStyleSheet("font-weight: 600; font-size: 14px;")
        self.body_layout.addWidget(recent_label)

        self.recent_list = QListWidget()
        self.recent_list.itemDoubleClicked.connect(self._on_recent_open)
        self.body_layout.addWidget(self.recent_list, 1)

        # Empty state
        self.empty = EmptyState(
            icon_name="mdi6.folder-plus-outline",
            title=tr("home.no_projects"),
        )
        self.body_layout.addWidget(self.empty)
        self.empty.hide()

    def retranslate(self) -> None:
        super().retranslate()
        self.stat_projects.retranslate()
        self.stat_tables.retranslate()
        self.stat_versions.retranslate()
        self.stat_snippets.retranslate()
        for i in range(self.recent_list.count()):
            item = self.recent_list.item(i)
            item.setText(tr("recent.unused"))

    def refresh(self) -> None:
        # 统计
        projects = reg().project_service.list_all()
        table_count = 0
        version_count = 0
        for p in projects:
            stats = reg().project_service.get_with_stats(p.id) or {}
            table_count += stats.get("table_count", 0)
            version_count += stats.get("version_count", 0)
        self.stat_projects.set_value(len(projects))
        self.stat_tables.set_value(table_count)
        self.stat_versions.set_value(version_count)
        self.stat_snippets.set_value(reg().sql_lib_service.count())

        # 最近项目
        self.recent_list.clear()
        if not projects:
            self.recent_list.hide()
            self.empty.show()
        else:
            self.empty.hide()
            self.recent_list.show()
            for p in projects[:10]:
                item = QListWidgetItem(f"📁 {p.name}")
                item.setData(Qt.ItemDataRole.UserRole, p.id)
                self.recent_list.addItem(item)

    def _on_recent_open(self, item: QListWidgetItem) -> None:
        pid = item.data(Qt.ItemDataRole.UserRole)
        if pid:
            # 通知 main_window
            if self.parent() and hasattr(self.parent(), "parent"):
                mw = self.parent().parent()
                if mw and hasattr(mw, "_open_project"):
                    mw._open_project(pid)

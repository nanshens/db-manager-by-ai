"""项目列表页 — 显示项目 + 新建/编辑/删除"""
from __future__ import annotations
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QPushButton, QLineEdit, QFrame, QLabel,
    QGridLayout, QMessageBox, QSizePolicy, QWidget, QScrollArea,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.ui.pages.base_page import BasePage
from app.ui.widgets import EmptyState, show_toast
from app.ui.dialogs import NewProjectDialog
from app.services.registry import reg
from app.repos.project_repo import Project


class ProjectCard(QFrame):
    """单张项目卡"""
    open_clicked = Signal(int)
    edit_clicked = Signal(int)
    delete_clicked = Signal(int)

    def __init__(self, project: Project, table_count: int = 0, version_count: int = 0, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # 不用 QSS setStyleSheet(改用 QSS 选择器 + dynamic property) — 简化:直接用 QSS
        self._project = project
        self._build(table_count, version_count)

    def _build(self, table_count, version_count):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        # Title row: color bar + name
        title_row = QHBoxLayout()
        color_bar = QFrame()
        color_bar.setFixedSize(4, 24)
        color_bar.setStyleSheet(f"background-color: {self._project.color}; border-radius: 2px;")
        title_row.addWidget(color_bar)

        name_label = QLabel(self._project.name)
        name_label.setStyleSheet("font-weight: 700; font-size: 15px;")
        title_row.addWidget(name_label, 1)

        layout.addLayout(title_row)

        # Description
        if self._project.description:
            desc = QLabel(self._project.description)
            desc.setObjectName("Secondary")
            desc.setWordWrap(True)
            desc.setMaximumHeight(40)
            layout.addWidget(desc)

        # Stats row
        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)
        t1 = QLabel(f"📊 {table_count} {tr('home.stat.tables')}")
        t1.setObjectName("Muted")
        stats_row.addWidget(t1)
        t2 = QLabel(f"📦 {version_count} {tr('home.stat.versions')}")
        t2.setObjectName("Muted")
        stats_row.addWidget(t2)
        stats_row.addStretch()
        layout.addLayout(stats_row)

        # Action row
        action_row = QHBoxLayout()
        action_row.setSpacing(4)
        open_btn = QPushButton(tr("action.open"))
        open_btn.setObjectName("Primary")
        open_btn.setIcon(qta.icon("mdi6.arrow-right", color="white"))
        open_btn.clicked.connect(lambda: self.open_clicked.emit(self._project.id))
        action_row.addWidget(open_btn)

        edit_btn = QPushButton()
        edit_btn.setIcon(qta.icon("mdi6.pencil", color="#94a3b8"))
        edit_btn.setFixedSize(32, 32)
        edit_btn.clicked.connect(lambda: self.edit_clicked.emit(self._project.id))
        action_row.addWidget(edit_btn)

        del_btn = QPushButton()
        del_btn.setIcon(qta.icon("mdi6.trash-can-outline", color="#ef4444"))
        del_btn.setFixedSize(32, 32)
        del_btn.clicked.connect(lambda: self.delete_clicked.emit(self._project.id))
        action_row.addWidget(del_btn)
        action_row.addStretch()

        layout.addLayout(action_row)

    def mouseDoubleClickEvent(self, event) -> None:
        self.open_clicked.emit(self._project.id)
        super().mouseDoubleClickEvent(event)


class ProjectsPage(BasePage):
    new_project_clicked = Signal()
    open_project_clicked = Signal(int)   # project_id

    def __init__(self, parent=None):
        super().__init__("projects.title", "", parent)
        self._new_btn = None
        self._new_btn_empty = None
        self._build()
        self.refresh()

    def _build(self) -> None:
        # Toolbar
        toolbar = QFrame()
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(0, 0, 0, 0)
        tb_layout.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("projects.search_placeholder"))
        self.search.setMaximumWidth(320)
        self.search.textChanged.connect(self._on_search)
        tb_layout.addWidget(self.search)
        tb_layout.addStretch()

        new_btn = QPushButton(tr("projects.new"))
        new_btn.setObjectName("Primary")
        new_btn.setIcon(qta.icon("mdi6.plus", color="white"))
        new_btn.clicked.connect(self._on_new)
        self._new_btn = new_btn
        tb_layout.addWidget(new_btn)
        self.body_layout.addWidget(toolbar)

        # Grid container
        self._grid_container = QFrame()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(16)
        self.body_layout.addWidget(self._grid_container)
        self.body_layout.addStretch()

        # Empty state
        self.empty = EmptyState(
            icon_name="mdi6.folder-multiple-outline",
            title=tr("projects.empty.title"),
            description=tr("projects.empty.desc"),
            primary_text=tr("projects.new"),
        )
        self._new_btn_empty = self.empty.primary_btn
        self.empty.primary_clicked.connect(self._on_new)
        self.body_layout.addWidget(self.empty)
        self.empty.hide()

    def retranslate(self) -> None:
        super().retranslate()
        self.search.setPlaceholderText(tr("projects.search_placeholder"))
        if self._new_btn:
            self._new_btn.setText(tr("projects.new"))
        if self._new_btn_empty:
            self._new_btn_empty.setText(tr("projects.new"))

    def refresh(self) -> None:
        """从 DB 读项目并刷新网格"""
        # 清空网格:先取出 widget 引用,再 setParent + deleteLater
        # (直接连续两次调 itemAt(i).widget() 会因为第一次 setParent 后 layout item 已无 widget)
        for i in reversed(range(self._grid_layout.count())):
            item = self._grid_layout.itemAt(i)
            widget = item.widget() if item else None
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        projects = reg().project_service.list_all()
        # 搜索过滤
        q = self.search.text().strip().lower()
        if q:
            projects = [p for p in projects if q in p.name.lower() or q in (p.description or "").lower()]

        if not projects:
            self._grid_container.hide()
            self.empty.show()
            if not q:
                self.empty.title_label.setText(tr("projects.empty.title"))
                self.empty.desc_label.setText(tr("projects.empty.desc"))
            else:
                self.empty.title_label.setText(tr("projects.empty.search.title"))
                self.empty.desc_label.setText(tr("projects.empty.search.desc"))
        else:
            self.empty.hide()
            self._grid_container.show()
            # 3 列网格
            for i, p in enumerate(projects):
                stats = reg().project_service.get_with_stats(p.id) or {}
                card = ProjectCard(
                    p,
                    table_count=stats.get("table_count", 0),
                    version_count=stats.get("version_count", 0),
                )
                card.open_clicked.connect(self._on_open)
                card.edit_clicked.connect(self._on_edit)
                card.delete_clicked.connect(self._on_delete)
                row, col = divmod(i, 3)
                self._grid_layout.addWidget(card, row, col)

    def _on_search(self) -> None:
        self.refresh()

    def _on_new(self) -> None:
        dlg = NewProjectDialog(parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            v = dlg.get_values()
            try:
                p = reg().project_service.create(v["name"], v["description"], v["color"])
                show_toast(tr("toast.saved"), "success")
                self.refresh()
            except ValueError as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

    def _on_open(self, project_id: int) -> None:
        self.open_project_clicked.emit(project_id)

    def _on_edit(self, project_id: int) -> None:
        p = reg().project_service.get(project_id)
        if not p:
            return
        dlg = NewProjectDialog(project=p, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            v = dlg.get_values()
            try:
                reg().project_service.update(project_id, v["name"], v["description"], v["color"])
                show_toast(tr("toast.saved"), "success")
                self.refresh()
            except ValueError as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

    def _on_delete(self, project_id: int) -> None:
        p = reg().project_service.get(project_id)
        if not p:
            return
        if QMessageBox.question(
            self, tr("dlg.confirm.delete_project.title"),
            tr("dlg.confirm.delete_project.msg").format(name=p.name)
        ) == QMessageBox.StandardButton.Yes:
            try:
                reg().project_service.delete(project_id)
                show_toast(tr("toast.deleted"), "success")
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

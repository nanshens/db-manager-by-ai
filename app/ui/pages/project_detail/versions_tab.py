"""Versions Tab — 数据版本管理(M3 简化版:只列出版本)"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QFrame, QListWidget,
    QListWidgetItem, QMessageBox, QWidget, QFileDialog, QPlainTextEdit, QSplitter,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.ui.widgets import EmptyState, show_toast
from app.ui.dialogs import NewVersionDialog
from app.services.registry import reg
from app.repos.data_version_repo import DataVersion


class VersionsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_id: Optional[int] = None
        self._current: Optional[DataVersion] = None
        self._build()
        self.refresh()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QFrame()
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(16, 12, 16, 12)
        self.new_btn = QPushButton(tr("versions_tab.new_version"))
        self.new_btn.setObjectName("Primary")
        self.new_btn.setIcon(qta.icon("mdi6.plus", color="white"))
        self.new_btn.clicked.connect(self._on_new)
        tb.addWidget(self.new_btn)
        tb.addStretch()
        layout.addWidget(toolbar)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)
        layout.addWidget(self.splitter, 1)

        # Left: version list
        left = QFrame()
        left.setMinimumWidth(200)
        left.setMaximumWidth(280)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8, 8, 8, 8)
        self.version_list = QListWidget()
        self.version_list.itemSelectionChanged.connect(self._on_selection)
        ll.addWidget(self.version_list)

        # Right: detail
        right = QFrame()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(16, 12, 16, 12)
        rl.setSpacing(8)
        self.detail_name = QLabel("—")
        self.detail_name.setStyleSheet("font-size: 15px; font-weight: 700;")
        rl.addWidget(self.detail_name)
        self.detail_desc = QLabel("")
        self.detail_desc.setObjectName("Secondary")
        self.detail_desc.setWordWrap(True)
        rl.addWidget(self.detail_desc)

        # File list
        files_label = QLabel(tr("dlg.version.files"))
        files_label.setObjectName("Muted")
        files_label.setStyleSheet("font-size: 11px;")
        rl.addWidget(files_label)
        self.files_view = QPlainTextEdit()
        self.files_view.setReadOnly(True)
        self.files_view.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 11px; "
            "background: #0b1220; color: #e2e8f0; border: 1px solid #334155; border-radius: 6px;"
        )
        rl.addWidget(self.files_view, 1)

        # Action row
        act_row = QHBoxLayout()
        act_row.addStretch()
        self.del_btn = QPushButton(tr("action.delete"))
        self.del_btn.setObjectName("Ghost")
        self.del_btn.setIcon(qta.icon("mdi6.trash-can-outline", color="#ef4444"))
        self.del_btn.clicked.connect(self._on_delete)
        act_row.addWidget(self.del_btn)
        rl.addLayout(act_row)

        # Empty state — 纯展示,按钮走工具栏(避免重复)
        self.empty = EmptyState(
            icon_name="mdi6.package-variant",
            title=tr("versions_tab.empty.title"),
            description=tr("versions_tab.empty.desc"),
            primary_text="",
        )
        # 即便没按钮,连一下信号保持兼容
        self.empty.primary_clicked.connect(self._on_new)

        # Splitter assignment
        empty_holder = QFrame()
        eh_layout = QVBoxLayout(empty_holder)
        eh_layout.setContentsMargins(0, 0, 0, 0)
        eh_layout.addWidget(self.empty)
        eh_layout.addStretch()

        self.splitter.addWidget(left)
        self.splitter.addWidget(empty_holder)
        self.splitter.setSizes([220, 700])

        self._right_holder = empty_holder
        self._right_widget = right
        self._files_label = files_label
        self._detail_widgets = [self.detail_name, self.detail_desc, self.files_view, self.del_btn, files_label]
        self._init_state()

    def _init_state(self) -> None:
        for w in self._detail_widgets:
            w.hide()

    def retranslate(self) -> None:
        self.new_btn.setText(tr("versions_tab.new_version"))
        self.empty.title_label.setText(tr("versions_tab.empty.title"))
        self.empty.desc_label.setText(tr("versions_tab.empty.desc"))
        self._files_label.setText(tr("dlg.version.files"))

    def set_project(self, project_id: int) -> None:
        self._project_id = project_id
        self.refresh()

    def refresh(self) -> None:
        if self._project_id is None:
            return
        self.version_list.clear()
        self._init_state()
        versions = reg().data_version_service.list_by_project(self._project_id)
        if not versions:
            self._show_empty()
            return
        self._show_list()
        for v in versions:
            item = QListWidgetItem(f"📦 {v.version_name}")
            item.setData(Qt.ItemDataRole.UserRole, v.id)
            self.version_list.addItem(item)
        if self.version_list.count() > 0:
            self.version_list.setCurrentRow(0)

    def _show_empty(self) -> None:
        self.empty.show()
        # 隐藏 detail widgets
        for w in self._detail_widgets:
            w.hide()

    def _show_list(self) -> None:
        self.empty.hide()

    def _on_selection(self) -> None:
        items = self.version_list.selectedItems()
        if not items:
            self._current = None
            self._init_state()
            return
        vid = items[0].data(Qt.ItemDataRole.UserRole)
        v = reg().data_version_service.get(vid)
        self._current = v
        if not v:
            return
        for w in self._detail_widgets:
            w.show()
        self.detail_name.setText(f"📦 {v.version_name}")
        self.detail_desc.setText(v.description or "")
        lines = []
        for f in v.source_files:
            lines.append(f"📄 {f.table_name}  [{f.format.upper()}]  rows={f.rows}")
            lines.append(f"   {f.local_path}")
            lines.append(f"   sha256: {f.sha256[:16]}…")
            lines.append("")
        self.files_view.setPlainText("\n".join(lines))

    def _on_new(self) -> None:
        if self._project_id is None:
            return
        tables = reg().table_service.list_by_project(self._project_id)
        if not tables:
            QMessageBox.information(
                self, tr("common.info") if False else tr("versions_tab.empty.title"),
                tr("versions_tab.no_tables"),
            )
            return
        # 建议默认版本名 v1.0 / v1.1 / ...
        existing = reg().data_version_service.list_by_project(self._project_id)
        n = len(existing) + 1
        default_name = f"v1.{n - 1}" if n > 1 else "v1.0"
        dlg = NewVersionDialog(tables=tables, default_version_name=default_name, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            v = dlg.get_values()
            try:
                reg().data_version_service.create(
                    self._project_id, v["version_name"], v["description"], v["files"],
                )
                show_toast(tr("toast.saved"), "success")
                self.refresh()
            except ValueError as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

    def _on_delete(self) -> None:
        if not self._current:
            return
        if QMessageBox.question(
            self, tr("action.confirm_delete"),
            f"Delete version \"{self._current.version_name}\"?"
        ) == QMessageBox.StandardButton.Yes:
            try:
                reg().data_version_service.delete(self._current.id)
                show_toast(tr("toast.deleted"), "success")
                self._current = None
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

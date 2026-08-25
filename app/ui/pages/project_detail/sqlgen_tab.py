"""SQL Generator Tab — 批量生成 INSERT/DELETE/COPY"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QFrame, QComboBox, QCheckBox,
    QPlainTextEdit, QListWidget, QListWidgetItem, QMessageBox, QWidget, QSplitter,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.ui.widgets import EmptyState, show_toast
from app.ui.dialogs import SqlSnippetDialog
from app.services.registry import reg
from app.core.sqlgen import (
    generate_insert, generate_delete, generate_copy, generate_csv_export,
)


class SqlGenTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_id: Optional[int] = None
        self._tables_data: list = []  # list of (Table, [selected_col_names])
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)
        layout.addWidget(self.splitter, 1)

        # Left: table + column selector
        left = QFrame()
        left.setMinimumWidth(260)
        left.setMaximumWidth(360)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(12, 12, 12, 12)
        ll.setSpacing(8)

        ll.addWidget(QLabel(tr("sqlgen_tab.table")))
        self.table_combo = QComboBox()
        self.table_combo.currentIndexChanged.connect(self._on_table_change)
        ll.addWidget(self.table_combo)

        # Column list with checkboxes
        ll.addWidget(QLabel(tr("dlg.table.columns")))
        self.col_list = QListWidget()
        self.col_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        ll.addWidget(self.col_list, 1)

        # Operation checkboxes
        op_label = QLabel(tr("sqlgen_tab.ops"))
        op_label.setStyleSheet("font-weight: 600;")
        ll.addWidget(op_label)
        self.op_insert = QCheckBox("INSERT")
        self.op_insert.setChecked(True)
        self.op_delete = QCheckBox("DELETE")
        self.op_copy = QCheckBox("COPY (PostgreSQL)")
        self.op_export = QCheckBox("Export CSV")
        ll.addWidget(self.op_insert)
        ll.addWidget(self.op_delete)
        ll.addWidget(self.op_copy)
        ll.addWidget(self.op_export)

        # Generate + Copy + Save
        gen_btn = QPushButton(tr("sqlgen_tab.generate"))
        gen_btn.setObjectName("Primary")
        gen_btn.setIcon(qta.icon("mdi6.play", color="white"))
        gen_btn.clicked.connect(self._on_generate)
        ll.addWidget(gen_btn)

        # Right: SQL output
        right = QFrame()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(12, 12, 12, 12)
        rl.setSpacing(8)

        h = QHBoxLayout()
        h.addWidget(QLabel(tr("sqlgen_tab.output")))
        h.addStretch()
        copy_btn = QPushButton(tr("action.copy"))
        copy_btn.setObjectName("Ghost")
        copy_btn.setIcon(qta.icon("mdi6.content-copy", color="#94a3b8"))
        copy_btn.clicked.connect(self._on_copy)
        h.addWidget(copy_btn)
        save_btn = QPushButton(tr("action.save"))
        save_btn.setObjectName("Ghost")
        save_btn.setIcon(qta.icon("mdi6.content-save", color="#94a3b8"))
        save_btn.clicked.connect(self._on_save)
        h.addWidget(save_btn)
        rl.addLayout(h)

        self.sql_view = QPlainTextEdit()
        self.sql_view.setReadOnly(True)
        self.sql_view.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 12px; "
            "background: #0b1220; color: #e2e8f0; border: 1px solid #334155; border-radius: 6px;"
        )
        rl.addWidget(self.sql_view, 1)

        self.splitter.addWidget(left)
        self.splitter.addWidget(right)
        self.splitter.setSizes([300, 800])

    def retranslate(self) -> None:
        pass

    def set_project(self, project_id: int) -> None:
        self._project_id = project_id
        self.table_combo.blockSignals(True)
        self.table_combo.clear()
        tables = reg().table_service.list_by_project(project_id)
        for t in tables:
            self.table_combo.addItem(t.name, t.id)
        self.table_combo.blockSignals(False)
        if tables:
            self._on_table_change(0)
        else:
            self.col_list.clear()
            self.sql_view.clear()

    def _on_table_change(self, idx: int) -> None:
        self.col_list.clear()
        if idx < 0 or self._project_id is None:
            return
        tid = self.table_combo.itemData(idx)
        t = reg().table_service.get(tid)
        if not t:
            return
        for c in t.columns:
            item = QListWidgetItem(c.name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.col_list.addItem(item)

    def _get_selected_columns(self) -> list[str]:
        cols = []
        for i in range(self.col_list.count()):
            item = self.col_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                cols.append(item.text())
        return cols

    def _on_generate(self) -> None:
        idx = self.table_combo.currentIndex()
        if idx < 0:
            return
        tid = self.table_combo.itemData(idx)
        t = reg().table_service.get(tid)
        if not t:
            return
        cols = self._get_selected_columns()
        if not cols:
            QMessageBox.information(self, tr("common.error"), "Select at least 1 column")
            return

        parts = []
        if self.op_insert.isChecked():
            parts.append(generate_insert(t.name, cols))
        if self.op_delete.isChecked():
            parts.append(generate_delete(t.name, t.columns[0].name if t.columns else "id"))
        if self.op_copy.isChecked():
            parts.append(generate_copy(t.name, cols, f"D:\\data\\{t.name}.csv"))
        if self.op_export.isChecked():
            parts.append(generate_csv_export(t.name, cols, f"D:\\export\\{t.name}.csv"))
        self.sql_view.setPlainText("\n\n".join(parts))

    def _on_copy(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.sql_view.toPlainText())
        show_toast(tr("toast.copied"), "success", 1500)

    def _on_save(self) -> None:
        idx = self.table_combo.currentIndex()
        if idx < 0:
            return
        dlg = SqlSnippetDialog(
            projects=reg().project_service.list_all(),
            default_project_id=self._project_id,
            parent=self,
        )
        # 预填 SQL 内容
        dlg.sql_edit.setPlainText(self.sql_view.toPlainText())
        if dlg.exec() == dlg.DialogCode.Accepted:
            v = dlg.get_values()
            try:
                reg().sql_lib_service.create(
                    title=v["title"], sql_text=v["sql_text"],
                    description=v["description"], tags=v["tags"],
                    project_id=v["project_id"],
                )
                show_toast(tr("toast.saved"), "success")
            except ValueError as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

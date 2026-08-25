"""新建/编辑表 对话框"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QHeaderView, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QMessageBox,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.ui.dialogs.column_editor_dialog import ColumnEditorDialog
from app.repos.table_repo import Table, Column


COL_NAME = 0
COL_TYPE = 1
COL_NULL = 2
COL_DEFAULT = 3
COL_PK = 4
COL_COMMENT = 5
COL_OPS = 6


class TableDialog(QDialog):
    def __init__(self, table: Optional[Table] = None, project_id: Optional[int] = None, parent=None):
        super().__init__(parent)
        self._table = table
        self._project_id = project_id
        self.setWindowTitle(tr("dlg.new_table.title") if table is None else tr("dlg.edit_table.title"))
        self.setMinimumSize(800, 600)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # Name + Comment
        grid_row = QHBoxLayout()
        grid_row.setSpacing(12)

        name_col = QVBoxLayout()
        name_col.addWidget(QLabel(tr("dlg.table.name") + " *"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("dlg.table.name.placeholder"))
        if self._table:
            self.name_edit.setText(self._table.name)
        name_col.addWidget(self.name_edit)
        grid_row.addLayout(name_col, 2)

        cmt_col = QVBoxLayout()
        cmt_col.addWidget(QLabel(tr("dlg.table.comment")))
        self.comment_edit = QLineEdit()
        self.comment_edit.setPlaceholderText(tr("dlg.table.comment.placeholder"))
        if self._table:
            self.comment_edit.setText(self._table.comment or "")
        cmt_col.addWidget(self.comment_edit)
        grid_row.addLayout(cmt_col, 3)
        layout.addLayout(grid_row)

        # Columns header
        col_header = QHBoxLayout()
        col_title = QLabel(tr("dlg.table.columns"))
        col_title.setStyleSheet("font-weight: 600; font-size: 13px;")
        col_header.addWidget(col_title)
        col_header.addStretch()
        col_count_lbl = QLabel("")
        col_count_lbl.setObjectName("Secondary")
        self._col_count_label = col_count_lbl
        col_header.addWidget(col_count_lbl)
        layout.addLayout(col_header)

        # Columns table
        self.col_table = QTableWidget(0, 7)
        self.col_table.setHorizontalHeaderLabels([
            tr("dlg.column.name"), tr("dlg.column.type"),
            tr("dlg.column.nullable"), tr("dlg.column.default"),
            tr("dlg.column.pk"), tr("dlg.column.comment"),
            "",
        ])
        self.col_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.col_table.horizontalHeader().setSectionResizeMode(COL_OPS, QHeaderView.ResizeMode.Fixed)
        self.col_table.setColumnWidth(COL_OPS, 90)
        self.col_table.verticalHeader().setVisible(False)
        self.col_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.col_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.col_table.setAlternatingRowColors(True)
        layout.addWidget(self.col_table, 1)

        # Add column button
        add_row = QHBoxLayout()
        add_btn = QPushButton(tr("dlg.table.add_column"))
        add_btn.setObjectName("Primary")
        add_btn.setIcon(qta.icon("mdi6.plus", color="white"))
        add_btn.clicked.connect(self._add_column)
        add_row.addWidget(add_btn)
        add_row.addStretch()
        layout.addLayout(add_row)

        # Error
        self.error_label = QLabel("")
        self.error_label.setObjectName("Danger")
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton(tr("action.cancel"))
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        ok = QPushButton(tr("action.save"))
        ok.setObjectName("Primary")
        ok.clicked.connect(self._on_accept)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

        # Load existing columns
        if self._table and self._table.columns:
            for c in self._table.columns:
                self._add_column_row(c)

    def _add_column(self) -> None:
        """打开列编辑器弹窗,完成后追加行"""
        existing = [self._row_to_column(r) for r in range(self.col_table.rowCount())]
        dlg = ColumnEditorDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            col = dlg.get_column()
            # 重名检查
            if any(c.name == col.name for c in existing):
                QMessageBox.warning(self, tr("common.error"), tr("dlg.column.error.duplicate"))
                return
            self._add_column_row(col)

    def _edit_column(self, row: int) -> None:
        col = self._row_to_column(row)
        dlg = ColumnEditorDialog(column=col, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_col = dlg.get_column()
            # 重名检查
            for r in range(self.col_table.rowCount()):
                if r == row:
                    continue
                if self.col_table.item(r, COL_NAME).text() == new_col.name:
                    QMessageBox.warning(self, tr("common.error"), tr("dlg.column.error.duplicate"))
                    return
            self._fill_row(row, new_col)

    def _delete_column(self, row: int) -> None:
        if QMessageBox.question(
            self, tr("common.confirm"),
            tr("dlg.confirm.delete_table.msg").format(name=self.col_table.item(row, COL_NAME).text())
        ) == QMessageBox.StandardButton.Yes:
            self.col_table.removeRow(row)
            self._update_col_count()

    def _row_to_column(self, row: int) -> Column:
        name = self.col_table.item(row, COL_NAME).text()
        type_ = self.col_table.item(row, COL_TYPE).text()
        nullable = self.col_table.item(row, COL_NULL).text() == "✓"
        default = self.col_table.item(row, COL_DEFAULT).text()
        pk = self.col_table.item(row, COL_PK).text() == "✓"
        comment = self.col_table.item(row, COL_COMMENT).text()
        return Column(name=name, type=type_, nullable=nullable, default=default, pk=pk, comment=comment)

    def _add_column_row(self, col: Column) -> None:
        row = self.col_table.rowCount()
        self.col_table.insertRow(row)
        self._fill_row(row, col)
        # 添加操作按钮
        ops = QWidget()
        ops_lay = QHBoxLayout(ops)
        ops_lay.setContentsMargins(2, 2, 2, 2)
        ops_lay.setSpacing(4)
        edit_btn = QPushButton()
        edit_btn.setIcon(qta.icon("mdi6.pencil", color="#94a3b8"))
        edit_btn.setFixedSize(28, 28)
        edit_btn.clicked.connect(lambda _checked, r=row: self._edit_column(r))
        ops_lay.addWidget(edit_btn)
        del_btn = QPushButton()
        del_btn.setIcon(qta.icon("mdi6.trash-can-outline", color="#ef4444"))
        del_btn.setFixedSize(28, 28)
        del_btn.clicked.connect(lambda _checked, r=row: self._delete_column(r))
        ops_lay.addWidget(del_btn)
        ops_lay.addStretch()
        self.col_table.setCellWidget(row, COL_OPS, ops)
        self._update_col_count()

    def _fill_row(self, row: int, col: Column) -> None:
        self.col_table.setItem(row, COL_NAME, QTableWidgetItem(col.name))
        self.col_table.setItem(row, COL_TYPE, QTableWidgetItem(col.type))
        self.col_table.setItem(row, COL_NULL, QTableWidgetItem("✓" if col.nullable else "✗"))
        self.col_table.setItem(row, COL_DEFAULT, QTableWidgetItem(col.default or ""))
        self.col_table.setItem(row, COL_PK, QTableWidgetItem("✓" if col.pk else ""))
        self.col_table.setItem(row, COL_COMMENT, QTableWidgetItem(col.comment or ""))
        # 居中显示布尔值
        for c in (COL_NULL, COL_PK):
            item = self.col_table.item(row, c)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

    def _update_col_count(self) -> None:
        n = self.col_table.rowCount()
        self._col_count_label.setText(f"{n} {tr('dlg.table.column_count')}")

    def _on_accept(self) -> None:
        if not self.name_edit.text().strip():
            self.error_label.setText(tr("dlg.table.error.name_required"))
            self.error_label.setVisible(True)
            return
        if self.col_table.rowCount() == 0:
            self.error_label.setText(tr("dlg.table.error.cols_required"))
            self.error_label.setVisible(True)
            return
        self.accept()

    def get_table(self) -> Table:
        cols = [self._row_to_column(r) for r in range(self.col_table.rowCount())]
        return Table(
            id=self._table.id if self._table else None,
            project_id=self._table.project_id if self._table else (self._project_id or 0),
            name=self.name_edit.text().strip(),
            comment=self.comment_edit.text().strip(),
            columns=cols,
            ddl_text="",
        )

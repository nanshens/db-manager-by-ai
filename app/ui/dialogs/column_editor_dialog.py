"""列编辑器 — 单列添加/编辑"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QCheckBox, QGridLayout, QSpinBox,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.repos.table_repo import Column


# 常用 SQL 类型
SQL_TYPES = [
    "INTEGER", "BIGINT", "SMALLINT", "TINYINT",
    "DECIMAL(10,2)", "NUMERIC(10,2)",
    "REAL", "DOUBLE", "FLOAT",
    "VARCHAR(50)", "VARCHAR(100)", "VARCHAR(255)", "TEXT",
    "DATE", "TIME", "DATETIME", "TIMESTAMP",
    "BOOLEAN", "BLOB", "JSON",
]


class ColumnEditorDialog(QDialog):
    def __init__(self, column: Optional[Column] = None, parent=None):
        super().__init__(parent)
        self._column = column
        self.setWindowTitle(tr("dlg.column.title"))
        self.setMinimumWidth(400)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # Name
        layout.addWidget(QLabel(tr("dlg.column.name") + " *"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. user_id")
        if self._column:
            self.name_edit.setText(self._column.name)
        layout.addWidget(self.name_edit)

        # Type
        layout.addWidget(QLabel(tr("dlg.column.type") + " *"))
        self.type_combo = QComboBox()
        self.type_combo.setEditable(True)
        self.type_combo.addItems(SQL_TYPES)
        if self._column:
            # 找到匹配的,否则直接 setText
            idx = self.type_combo.findText(self._column.type)
            if idx >= 0:
                self.type_combo.setCurrentIndex(idx)
            else:
                self.type_combo.setCurrentText(self._column.type)
        layout.addWidget(self.type_combo)

        # Default / Nullable / PK row
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        grid.addWidget(QLabel(tr("dlg.column.default")), 0, 0)
        self.default_edit = QLineEdit()
        self.default_edit.setPlaceholderText("(optional)")
        if self._column and self._column.default:
            self.default_edit.setText(self._column.default)
        grid.addWidget(self.default_edit, 0, 1)

        grid.addWidget(QLabel(tr("dlg.column.nullable")), 1, 0)
        self.nullable_chk = QCheckBox()
        self.nullable_chk.setChecked(self._column.nullable if self._column else True)
        grid.addWidget(self.nullable_chk, 1, 1)

        grid.addWidget(QLabel(tr("dlg.column.pk")), 2, 0)
        self.pk_chk = QCheckBox()
        self.pk_chk.setChecked(self._column.pk if self._column else False)
        grid.addWidget(self.pk_chk, 2, 1)

        layout.addLayout(grid)

        # Comment
        layout.addWidget(QLabel(tr("dlg.column.comment")))
        self.comment_edit = QLineEdit()
        self.comment_edit.setPlaceholderText("(optional)")
        if self._column and self._column.comment:
            self.comment_edit.setText(self._column.comment)
        layout.addWidget(self.comment_edit)

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

        self.name_edit.setFocus()

    def _on_accept(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            self._show_error(tr("dlg.column.error.name_required"))
            return
        self.accept()

    def _show_error(self, msg: str) -> None:
        self.error_label.setText(msg)
        self.error_label.setVisible(True)

    def get_column(self) -> Column:
        return Column(
            name=self.name_edit.text().strip(),
            type=self.type_combo.currentText().strip() or "TEXT",
            nullable=self.nullable_chk.isChecked(),
            default=self.default_edit.text().strip(),
            pk=self.pk_chk.isChecked(),
            comment=self.comment_edit.text().strip(),
        )

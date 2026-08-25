"""Excel 模板编辑对话框"""
from __future__ import annotations
from typing import Optional, Iterable
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QSpinBox, QComboBox, QFormLayout,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.repos.excel_template_repo import ExcelTemplate
from app.repos.project_repo import Project


class ExcelTemplateDialog(QDialog):
    def __init__(self, template: Optional[ExcelTemplate] = None,
                 projects: Optional[Iterable[Project]] = None,
                 parent=None):
        super().__init__(parent)
        self._template = template
        self.setWindowTitle(tr("dlg.excel.new") if template is None else tr("dlg.excel.edit"))
        self.setMinimumWidth(540)
        self._build(projects)

    def _build(self, projects):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        # Name
        self.name_edit = QLineEdit()
        if self._template:
            self.name_edit.setText(self._template.template_name)
        form.addRow(tr("dlg.excel.name") + " *", self.name_edit)

        # Project
        self.project_combo = QComboBox()
        self.project_combo.addItem(tr("sqllib.project_filter_global"), None)
        if projects:
            for p in projects:
                self.project_combo.addItem(p.name, p.id)
        if self._template and self._template.project_id is not None:
            idx = self.project_combo.findData(self._template.project_id)
            if idx >= 0:
                self.project_combo.setCurrentIndex(idx)
        form.addRow(tr("dlg.excel.project"), self.project_combo)

        # Config sheet name
        self.sheet_edit = QLineEdit()
        self.sheet_edit.setPlaceholderText("总览 / 目录 / Config")
        if self._template:
            self.sheet_edit.setText(self._template.config_sheet_name)
        form.addRow(tr("dlg.excel.config_sheet") + " *", self.sheet_edit)

        # Table name col
        self.tn_col_edit = QLineEdit()
        self.tn_col_edit.setPlaceholderText("A / 表名 / table_name")
        if self._template:
            self.tn_col_edit.setText(self._template.table_name_col)
        form.addRow(tr("dlg.excel.table_name_col") + " *", self.tn_col_edit)

        # Sheet name col
        self.sn_col_edit = QLineEdit()
        self.sn_col_edit.setPlaceholderText("B / 数据 sheet / sheet_name")
        if self._template:
            self.sn_col_edit.setText(self._template.sheet_name_col)
        form.addRow(tr("dlg.excel.sheet_name_col") + " *", self.sn_col_edit)

        # Header row
        self.header_spin = QSpinBox()
        self.header_spin.setRange(1, 9999)
        self.header_spin.setValue(self._template.header_row if self._template else 1)
        form.addRow(tr("dlg.excel.header_row"), self.header_spin)

        # Data start row
        self.data_spin = QSpinBox()
        self.data_spin.setRange(1, 9999)
        self.data_spin.setValue(self._template.data_start_row if self._template else 2)
        form.addRow(tr("dlg.excel.data_start_row"), self.data_spin)

        layout.addLayout(form)

        # Description
        layout.addWidget(QLabel(tr("dlg.excel.desc")))
        self.desc_edit = QTextEdit()
        self.desc_edit.setMaximumHeight(60)
        if self._template and self._template.description:
            self.desc_edit.setPlainText(self._template.description)
        layout.addWidget(self.desc_edit)

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
        if not self.name_edit.text().strip():
            self._show_err(tr("dlg.excel.error.name_required"))
            return
        if not self.sheet_edit.text().strip():
            self._show_err(tr("dlg.excel.error.sheet_required"))
            return
        if not self.tn_col_edit.text().strip():
            self._show_err(tr("dlg.excel.error.tn_col_required"))
            return
        if not self.sn_col_edit.text().strip():
            self._show_err(tr("dlg.excel.error.sn_col_required"))
            return
        if self.data_spin.value() < self.header_spin.value():
            self._show_err(tr("dlg.excel.error.data_before_header"))
            return
        self.accept()

    def _show_err(self, msg: str) -> None:
        self.error_label.setText(msg)
        self.error_label.setVisible(True)

    def get_template(self) -> dict:
        return {
            "template_name": self.name_edit.text().strip(),
            "project_id": self.project_combo.currentData(),
            "config_sheet_name": self.sheet_edit.text().strip(),
            "table_name_col": self.tn_col_edit.text().strip(),
            "sheet_name_col": self.sn_col_edit.text().strip(),
            "header_row": self.header_spin.value(),
            "data_start_row": self.data_spin.value(),
            "description": self.desc_edit.toPlainText().strip(),
        }

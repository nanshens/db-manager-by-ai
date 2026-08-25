"""对比配置编辑对话框"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QCheckBox,
    QPushButton, QListWidget, QListWidgetItem, QGroupBox, QRadioButton, QButtonGroup,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.repos.compare_config_repo import CompareConfig


class CompareConfigDialog(QDialog):
    def __init__(self, config: Optional[CompareConfig] = None,
                 all_columns: Optional[list[str]] = None,
                 project_id: Optional[int] = None,
                 table_name: Optional[str] = None,
                 parent=None):
        super().__init__(parent)
        self._config = config
        self._all_columns = all_columns or []
        self._project_id = project_id
        self._table_name = table_name or (config.table_name if config else "")
        self.setWindowTitle(tr("dlg.compare.new") if config is None else tr("dlg.compare.edit"))
        self.setMinimumSize(560, 600)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # Name
        layout.addWidget(QLabel(tr("dlg.compare.name") + " *"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("dlg.compare.name.placeholder"))
        if self._config:
            self.name_edit.setText(self._config.config_name)
        layout.addWidget(self.name_edit)

        # PK columns
        layout.addWidget(QLabel(tr("dlg.compare.pk") + " *"))
        self.pk_list = QListWidget()
        self.pk_list.setMaximumHeight(110)
        self.pk_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        for col in self._all_columns:
            item = QListWidgetItem(col)
            self.pk_list.addItem(item)
            if self._config and col in (self._config.pk_columns or []):
                item.setSelected(True)
        # 提示
        info = QLabel(tr("dlg.compare.pk.hint"))
        info.setObjectName("Muted")
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addWidget(self.pk_list)

        # Compare columns (vs ignore)
        layout.addWidget(QLabel(tr("dlg.compare.cols")))
        self.col_list = QListWidget()
        self.col_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        for col in self._all_columns:
            item = QListWidgetItem(col)
            self.col_list.addItem(item)
            # 默认全选(若没有 ignore 概念);若有 compare_columns 配置,按它选
            if self._config:
                if self._config.compare_columns is None:
                    item.setSelected(True)
                elif col in self._config.compare_columns:
                    item.setSelected(True)
            else:
                item.setSelected(True)  # 新建默认全选
        layout.addWidget(self.col_list, 1)

        # Advanced
        adv = QHBoxLayout()
        self.case_chk = QCheckBox(tr("dlg.compare.case_sensitive"))
        self.case_chk.setChecked(self._config.case_sensitive if self._config else False)
        self.trim_chk = QCheckBox(tr("dlg.compare.trim"))
        self.trim_chk.setChecked(self._config.trim_whitespace if self._config else True)
        adv.addWidget(self.case_chk)
        adv.addWidget(self.trim_chk)
        adv.addStretch()
        layout.addLayout(adv)

        # Default
        self.default_chk = QCheckBox(tr("dlg.compare.is_default"))
        self.default_chk.setChecked(self._config.is_default if self._config else False)
        layout.addWidget(self.default_chk)

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

    def _on_accept(self) -> None:
        if not self.name_edit.text().strip():
            self.error_label.setText(tr("dlg.compare.error.name_required"))
            self.error_label.setVisible(True)
            return
        pk_cols = [item.text() for item in self.pk_list.selectedItems()]
        if not pk_cols:
            self.error_label.setText(tr("dlg.compare.error.pk_required"))
            self.error_label.setVisible(True)
            return
        self.accept()

    def get_config(self) -> dict:
        compare_cols = [item.text() for item in self.col_list.selectedItems()]
        pk_cols = [item.text() for item in self.pk_list.selectedItems()]
        return {
            "config_name": self.name_edit.text().strip(),
            "pk_columns": pk_cols,
            "compare_columns": compare_cols,  # 全选 = 实际上等价 None
            "case_sensitive": self.case_chk.isChecked(),
            "trim_whitespace": self.trim_chk.isChecked(),
            "is_default": self.default_chk.isChecked(),
        }

"""新建/编辑项目 对话框"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QColorDialog, QFrame, QGridLayout,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.repos.project_repo import Project


class NewProjectDialog(QDialog):
    """新建 / 编辑 项目(同一对话框)"""
    def __init__(self, project: Optional[Project] = None, parent=None):
        super().__init__(parent)
        self._project = project
        self._is_edit = project is not None
        self.setWindowTitle(tr("dlg.new_project.title") if not self._is_edit else tr("dlg.edit_project.title"))
        self.setMinimumWidth(480)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Name
        layout.addWidget(QLabel(tr("dlg.project.name") + " *"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("dlg.project.name.placeholder"))
        if self._project:
            self.name_edit.setText(self._project.name)
        layout.addWidget(self.name_edit)

        # Description
        layout.addWidget(QLabel(tr("dlg.project.desc")))
        self.desc_edit = QTextEdit()
        self.desc_edit.setMaximumHeight(80)
        self.desc_edit.setPlaceholderText(tr("dlg.project.desc.placeholder"))
        if self._project and self._project.description:
            self.desc_edit.setPlainText(self._project.description)
        layout.addWidget(self.desc_edit)

        # Color
        layout.addWidget(QLabel(tr("dlg.project.color")))
        color_row = QHBoxLayout()
        self.color_swatch = QFrame()
        self.color_swatch.setFixedSize(32, 32)
        self._color = self._project.color if self._project else "#3b82f6"
        self._apply_color(self._color)
        color_row.addWidget(self.color_swatch)

        color_btn = QPushButton(tr("dlg.project.color.pick"))
        color_btn.setObjectName("Ghost")
        color_btn.setIcon(qta.icon("mdi6.palette", color="#94a3b8"))
        color_btn.clicked.connect(self._pick_color)
        color_row.addWidget(color_btn)
        color_row.addStretch()
        layout.addLayout(color_row)

        # Error label
        self.error_label = QLabel("")
        self.error_label.setObjectName("Danger")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton(tr("action.cancel"))
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        self.ok_btn = QPushButton(tr("action.save") if self._is_edit else tr("action.create"))
        self.ok_btn.setObjectName("Primary")
        self.ok_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(self.ok_btn)
        layout.addLayout(btn_row)

        self.name_edit.setFocus()

    def _apply_color(self, color: str) -> None:
        self.color_swatch.setStyleSheet(
            f"background-color: {color}; border: 1px solid #475569; border-radius: 6px;"
        )
        self._color = color

    def _pick_color(self) -> None:
        c = QColorDialog.getColor()
        if c.isValid():
            self._apply_color(c.name())

    def _on_accept(self) -> None:
        self.error_label.setVisible(False)
        try:
            # 校验在 service 里做,这里只取值
            self.accept()
        except Exception as e:
            self.error_label.setText(str(e))
            self.error_label.setVisible(True)

    def get_values(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "description": self.desc_edit.toPlainText().strip(),
            "color": self._color,
        }

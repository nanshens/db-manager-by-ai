"""SQL 片段编辑对话框"""
from __future__ import annotations
from typing import Optional, Iterable
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QComboBox, QCheckBox, QWidget,
)

from app.ui.i18n import tr
from app.repos.sql_snippet_repo import SqlSnippet
from app.repos.project_repo import Project


class SqlSnippetDialog(QDialog):
    """新建 / 编辑 SQL 片段"""
    def __init__(self, snippet: Optional[SqlSnippet] = None,
                 projects: Optional[Iterable[Project]] = None,
                 default_project_id: Optional[int] = None,
                 parent=None):
        super().__init__(parent)
        self._snippet = snippet
        self.setWindowTitle(tr("dlg.sql.new") if snippet is None else tr("dlg.sql.edit"))
        self.setMinimumSize(640, 480)
        self._build(projects, default_project_id)

    def _build(self, projects, default_project_id):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Title
        layout.addWidget(QLabel(tr("dlg.sql.title") + " *"))
        self.title_edit = QLineEdit()
        if self._snippet:
            self.title_edit.setText(self._snippet.title)
        self.title_edit.setPlaceholderText(tr("dlg.sql.title.placeholder"))
        layout.addWidget(self.title_edit)

        # Description
        layout.addWidget(QLabel(tr("dlg.sql.desc")))
        self.desc_edit = QLineEdit()
        if self._snippet:
            self.desc_edit.setText(self._snippet.description or "")
        layout.addWidget(self.desc_edit)

        # Tags
        layout.addWidget(QLabel(tr("dlg.sql.tags")))
        self.tags_edit = QLineEdit()
        if self._snippet:
            self.tags_edit.setText(self._snippet.tags or "")
        self.tags_edit.setPlaceholderText("select, user, daily")
        layout.addWidget(self.tags_edit)

        # Project binding
        layout.addWidget(QLabel(tr("dlg.sql.project")))
        self.project_combo = QComboBox()
        self.project_combo.addItem(tr("sqllib.project_filter_global"), None)  # 全局
        if projects:
            for p in projects:
                self.project_combo.addItem(p.name, p.id)
        if self._snippet:
            idx = self.project_combo.findData(self._snippet.project_id)
            if idx >= 0:
                self.project_combo.setCurrentIndex(idx)
        elif default_project_id is not None:
            idx = self.project_combo.findData(default_project_id)
            if idx >= 0:
                self.project_combo.setCurrentIndex(idx)
        layout.addWidget(self.project_combo)

        # SQL content
        layout.addWidget(QLabel(tr("dlg.sql.content") + " *"))
        self.sql_edit = QTextEdit()
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.sql_edit.setFont(mono)
        self.sql_edit.setStyleSheet("font-family: Consolas, monospace; font-size: 12px;")
        if self._snippet:
            self.sql_edit.setPlainText(self._snippet.sql_text)
        layout.addWidget(self.sql_edit, 1)

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

        self.title_edit.setFocus()

    def _on_accept(self) -> None:
        if not self.title_edit.text().strip():
            self.error_label.setText(tr("dlg.sql.error.title_required"))
            self.error_label.setVisible(True)
            return
        if not self.sql_edit.toPlainText().strip():
            self.error_label.setText(tr("dlg.sql.error.content_required"))
            self.error_label.setVisible(True)
            return
        self.accept()

    def get_values(self) -> dict:
        return {
            "title": self.title_edit.text().strip(),
            "description": self.desc_edit.text().strip(),
            "tags": self.tags_edit.text().strip(),
            "sql_text": self.sql_edit.toPlainText().strip(),
            "project_id": self.project_combo.currentData(),
        }

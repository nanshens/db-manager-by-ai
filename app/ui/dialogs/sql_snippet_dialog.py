"""SQL 片段编辑对话框 — 支持方言选择 + 自动联想"""
from __future__ import annotations
from typing import Optional, Iterable
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QComboBox, QWidget,
)

from app.ui.i18n import tr
from app.ui.widgets import SqlHighlighter, SqlAutocomplete
from app.repos.sql_snippet_repo import SqlSnippet, DIALECTS
from app.repos.project_repo import Project


_DIALECT_LABELS = {
    "postgres": "PostgreSQL",
    "mysql":    "MySQL",
    "oracle":   "Oracle",
}


class SqlSnippetDialog(QDialog):
    """新建 / 编辑 SQL 片段,带方言选择和自动联想。"""
    def __init__(self, snippet: Optional[SqlSnippet] = None,
                 projects: Optional[Iterable[Project]] = None,
                 default_project_id: Optional[int] = None,
                 default_dialect: str = "postgres",
                 parent=None):
        super().__init__(parent)
        self._snippet = snippet
        self._projects = list(projects) if projects else []
        self.setWindowTitle(tr("dlg.sql.new") if snippet is None else tr("dlg.sql.edit"))
        self.setMinimumSize(720, 540)
        self._build(default_project_id, default_dialect)

    def _build(self, default_project_id, default_dialect):
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

        # 方言 + 项目 一行
        meta_row = QHBoxLayout()
        meta_row.setSpacing(12)

        meta_row.addWidget(QLabel(tr("dlg.sql.dialect")))
        self.dialect_combo = QComboBox()
        for d in DIALECTS:
            self.dialect_combo.addItem(_DIALECT_LABELS[d], d)
        # 默认 postgres
        if self._snippet:
            idx = self.dialect_combo.findData(self._snippet.dialect or "postgres")
            if idx >= 0:
                self.dialect_combo.setCurrentIndex(idx)
        else:
            idx = self.dialect_combo.findData(default_dialect)
            if idx >= 0:
                self.dialect_combo.setCurrentIndex(idx)
        self.dialect_combo.currentIndexChanged.connect(self._on_dialect_change)
        meta_row.addWidget(self.dialect_combo)

        meta_row.addSpacing(20)
        meta_row.addWidget(QLabel(tr("dlg.sql.project")))
        self.project_combo = QComboBox()
        self.project_combo.addItem(tr("sqllib.scope.unbound"), None)  # 全局共享
        for p in self._projects:
            self.project_combo.addItem(p.name, p.id)
        if self._snippet:
            idx = self.project_combo.findData(self._snippet.project_id)
            if idx >= 0:
                self.project_combo.setCurrentIndex(idx)
        elif default_project_id is not None:
            idx = self.project_combo.findData(default_project_id)
            if idx >= 0:
                self.project_combo.setCurrentIndex(idx)
        self.project_combo.currentIndexChanged.connect(self._on_project_change)
        meta_row.addWidget(self.project_combo, 1)
        layout.addLayout(meta_row)

        # SQL content
        sql_lbl_row = QHBoxLayout()
        sql_lbl_row.addWidget(QLabel(tr("dlg.sql.content") + " *"))
        sql_lbl_row.addStretch()
        tip = QLabel(tr("dlg.sql.content.tip"))
        tip.setObjectName("Muted")
        tip.setStyleSheet("font-size: 11px;")
        sql_lbl_row.addWidget(tip)
        layout.addLayout(sql_lbl_row)

        self.sql_edit = QTextEdit()
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.sql_edit.setFont(mono)
        # 设浅色前景(默认是黑色,在深色弹窗里看不见)
        # 关键字/字符串/数字/注释会由 highlighter 用各自颜色覆盖
        self.sql_edit.setStyleSheet(
            "QTextEdit {"
            "  font-family: Consolas, monospace;"
            "  font-size: 12px;"
            "  color: #e2e8f0;"
            "  background: #0b1220;"
            "  border: 1px solid #334155;"
            "  border-radius: 6px;"
            "  padding: 6px;"
            "}"
        )
        self._sql_highlighter = SqlHighlighter(self.sql_edit.document())
        if self._snippet:
            self.sql_edit.setPlainText(self._snippet.sql_text)
        layout.addWidget(self.sql_edit, 1)

        # 联想弹窗(需要编辑器已建好)
        self._autocomplete = SqlAutocomplete(
            self.sql_edit,
            dialect_getter=lambda: self.dialect_combo.currentData() or "postgres",
        )
        self._on_dialect_change()  # 初始化静态词库
        self._on_project_change()  # 初始化项目词库

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
        ok.setDefault(True)
        ok.clicked.connect(self._on_accept)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

        self.title_edit.setFocus()

    # ============== 槽 ==============
    def _on_dialect_change(self) -> None:
        """切换方言 → 重新加载静态词库。"""
        if hasattr(self, "_autocomplete"):
            self._autocomplete.retranslate_static()

    def _on_project_change(self) -> None:
        """切换项目 → 重新加载表/列词库。"""
        if hasattr(self, "_autocomplete"):
            self._autocomplete.set_project(self.project_combo.currentData())

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
            "dialect": self.dialect_combo.currentData() or "postgres",
        }

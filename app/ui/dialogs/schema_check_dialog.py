"""Schema Check Dialog — 显示数据版本表结构校验结果"""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
import qtawesome as qta

from app.ui.i18n import tr


# 状态色
_STATUS_COLOR = {
    "✓": "#22c55e",
    "⚠": "#f59e0b",
    "❌": "#ef4444",
}


class SchemaCheckDialog(QDialog):
    """显示版本表结构校验结果 — 3 列:状态 / 表名 / 描述"""

    def __init__(self, version_name: str, report: list[tuple[str, str, str]], parent=None):
        """
        report: [(status, table_name, desc), ...]
        """
        super().__init__(parent)
        self.setWindowTitle(tr("versions_tab.check.title"))
        self.resize(640, 380)
        self.setMinimumSize(520, 280)
        self._build(version_name, report)

    def _build(self, version_name: str, report):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # 标题
        title = QLabel(f"📦 {version_name}  —  {tr('versions_tab.check.title')}")
        title.setStyleSheet("font-size: 14px; font-weight: 700;")
        layout.addWidget(title)

        # 汇总
        n_ok = sum(1 for s, _, _ in report if s == "✓")
        n_warn = sum(1 for s, _, _ in report if s == "⚠")
        n_err = sum(1 for s, _, _ in report if s == "❌")
        summary = QLabel(
            f"{tr('versions_tab.check.summary').format(ok=n_ok, warn=n_warn, err=n_err, total=len(report))}"
        )
        summary.setObjectName("Muted")
        summary.setStyleSheet("font-size: 12px;")
        layout.addWidget(summary)

        # 表格
        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels([
            tr("versions_tab.check.col.status"),
            tr("versions_tab.check.col.table"),
            tr("versions_tab.check.col.detail"),
        ])
        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setStyleSheet(
            "QTableWidget {"
            "  background: #0b1220; color: #e2e8f0;"
            "  border: 1px solid #334155; border-radius: 6px;"
            "  gridline-color: #1e293b;"
            "}"
            "QHeaderView::section {"
            "  background: #1e293b; color: #cbd5e1;"
            "  border: none; border-right: 1px solid #334155;"
            "  padding: 6px 10px; font-weight: 600;"
            "}"
            "QTableWidget::item { padding: 6px 10px; }"
            "QTableWidget::item:selected { background: #1d4ed8; color: white; }"
        )
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        table.setFont(mono)
        for status, tname, desc in report:
            r = table.rowCount()
            table.insertRow(r)
            s_item = QTableWidgetItem(status)
            color = _STATUS_COLOR.get(status, "#94a3b8")
            s_item.setForeground(QColor(color))
            table.setItem(r, 0, s_item)
            table.setItem(r, 1, QTableWidgetItem(tname))
            table.setItem(r, 2, QTableWidgetItem(desc))
        layout.addWidget(table, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton(tr("action.close"))
        close_btn.setObjectName("Primary")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

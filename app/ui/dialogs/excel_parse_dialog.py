"""Excel 解析预览对话框"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFrame,
    QListWidget, QListWidgetItem, QPlainTextEdit, QSplitter, QFileDialog,
    QMessageBox, QWidget, QTableWidget, QTableWidgetItem, QHeaderView,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.core.excel_parser import parse_excel, ParseResult
from app.repos.excel_template_repo import ExcelTemplate


class ExcelParseDialog(QDialog):
    def __init__(self, template: ExcelTemplate, parent=None):
        super().__init__(parent)
        self._template = template
        self._results: list[ParseResult] = []
        self._errors: list[str] = []
        self.setWindowTitle(tr("dlg.excel_parse.title"))
        self.setMinimumSize(1000, 600)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # Template info
        info = QLabel(f"📑 {self._template.template_name}  ·  {tr('dlg.excel_parse.config_sheet')}: {self._template.config_sheet_name}")
        info.setStyleSheet("font-weight: 600; font-size: 14px;")
        layout.addWidget(info)

        # File picker
        file_row = QHBoxLayout()
        file_row.addWidget(QLabel(tr("dlg.excel_parse.file") + ":"))
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(tr("dlg.version.file.placeholder"))
        file_row.addWidget(self.path_edit, 1)
        browse_btn = QPushButton(tr("action.browse"))
        browse_btn.setObjectName("Ghost")
        browse_btn.clicked.connect(self._browse)
        file_row.addWidget(browse_btn)
        parse_btn = QPushButton(tr("dlg.excel_parse.parse"))
        parse_btn.setObjectName("Primary")
        parse_btn.setIcon(qta.icon("mdi6.play", color="white"))
        parse_btn.clicked.connect(self._on_parse)
        file_row.addWidget(parse_btn)
        layout.addLayout(file_row)

        # Splitter: left table list / right preview
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)
        layout.addWidget(self.splitter, 1)

        # Left
        left = QFrame()
        left.setMinimumWidth(220)
        left.setMaximumWidth(280)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(4)
        ll.addWidget(QLabel(tr("dlg.excel_parse.tables")))
        self.table_list = QListWidget()
        self.table_list.itemSelectionChanged.connect(self._on_table_select)
        ll.addWidget(self.table_list)

        # Right
        right = QFrame()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        self.detail_title = QLabel("—")
        self.detail_title.setStyleSheet("font-size: 14px; font-weight: 700;")
        rl.addWidget(self.detail_title)

        self.detail_meta = QLabel("")
        self.detail_meta.setObjectName("Muted")
        self.detail_meta.setWordWrap(True)
        rl.addWidget(self.detail_meta)

        self.preview_table = QTableWidget()
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.preview_table.verticalHeader().setVisible(False)
        rl.addWidget(self.preview_table, 1)

        self._detail_widgets = [self.detail_title, self.detail_meta, self.preview_table]
        for w in self._detail_widgets:
            w.hide()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton(tr("action.close"))
        close_btn.setObjectName("Ghost")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.splitter.addWidget(left)
        self.splitter.addWidget(right)
        self.splitter.setSizes([240, 760])

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("dlg.version.browse_title"),
            "", "Excel files (*.xlsx *.xls);;All files (*)",
        )
        if path:
            self.path_edit.setText(path)
            self._on_parse()

    def _on_parse(self) -> None:
        path = self.path_edit.text().strip()
        if not path:
            QMessageBox.information(self, tr("common.error"), tr("dlg.excel_parse.no_file"))
            return
        self._results, self._errors = parse_excel(path, self._template)
        # 填充列表
        self.table_list.clear()
        for r in self._results:
            status = "✓" if not r.error else "✗"
            item = QListWidgetItem(f"{status}  {r.table_name}  ({r.sheet_name}, {r.rows} 行)")
            item.setData(Qt.ItemDataRole.UserRole, r.table_name)
            self.table_list.addItem(item)
        if self._results:
            self.table_list.setCurrentRow(0)
        if self._errors:
            QMessageBox.warning(self, tr("common.warning"),
                                tr("dlg.excel_parse.errors") + "\n" + "\n".join(self._errors[:5]))

    def _on_table_select(self) -> None:
        items = self.table_list.selectedItems()
        if not items:
            for w in self._detail_widgets:
                w.hide()
            return
        name = items[0].data(Qt.ItemDataRole.UserRole)
        r = next((x for x in self._results if x.table_name == name), None)
        if not r:
            return
        for w in self._detail_widgets:
            w.show()
        self.detail_title.setText(f"📄 {r.table_name}")
        meta = f"Sheet: {r.sheet_name} · {r.rows} 行 · {len(r.columns)} 列"
        if r.error:
            meta += f"  · ❌ {r.error}"
        self.detail_meta.setText(meta)
        # 填表
        if r.error:
            self.preview_table.setRowCount(0)
            self.preview_table.setColumnCount(0)
            return
        cols = r.columns
        self.preview_table.setColumnCount(len(cols))
        self.preview_table.setRowCount(len(r.sample_rows or []))
        self.preview_table.setHorizontalHeaderLabels(cols)
        for i, row in enumerate(r.sample_rows or []):
            for j, val in enumerate(row):
                self.preview_table.setItem(i, j, QTableWidgetItem(str(val)))

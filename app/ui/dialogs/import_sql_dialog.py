"""从 SQL 文件 / 直接粘贴导入表结构 — 对话框

两种输入方式,二选一:
1. 选择 .sql 文件
2. 直接粘贴 CREATE TABLE 脚本
"""
from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QListWidget, QListWidgetItem, QFileDialog, QMessageBox,
    QPlainTextEdit, QFrame, QSizePolicy, QTabWidget, QWidget,
)

from app.ui.i18n import tr
from app.core.ddl_parser import parse_ddl_file, parse_ddl_text, DIALECTS, ParsedTable


_DIALECT_LABELS = {
    "postgres": "PostgreSQL",
    "mysql":    "MySQL",
    "oracle":   "Oracle",
}


class _TableItem(QListWidgetItem):
    """带勾选状态的表项 + 解析错误展示。"""
    def __init__(self, parsed: ParsedTable, parent=None):
        super().__init__(parent)
        self.parsed = parsed
        self.setFlags(self.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        # 默认勾选(除非解析失败)
        checked = not parsed.parse_error and bool(parsed.columns)
        self.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        # 显示文本
        err = f"  ⚠ {parsed.parse_error}" if parsed.parse_error else ""
        cols = len(parsed.columns)
        self.setText(f"{parsed.name}    ({cols} 列){err}")


class ImportSqlDialog(QDialog):
    """从 .sql 文件 / 直接粘贴批量导入表结构。

    流程:选输入方式(文件 / 粘贴) → 选方言 → 解析 → 勾选要导入的表 → 确认。
    """
    def __init__(self, parent=None, default_dialect: str = "postgres"):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg.import_sql.title"))
        self.resize(720, 560)
        self.setMinimumSize(560, 440)
        self._parsed_tables: list[ParsedTable] = []
        self._build(default_dialect)

    def _build(self, default_dialect: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # 1) 输入方式 tabs: 文件 / 粘贴
        self.tabs = QTabWidget()
        # 1a) 文件 tab
        file_tab = QWidget()
        ft = QHBoxLayout(file_tab)
        ft.setContentsMargins(0, 8, 0, 8)
        ft.setSpacing(8)
        ft.addWidget(QLabel(tr("dlg.import_sql.file")))
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(tr("dlg.import_sql.file.placeholder"))
        ft.addWidget(self.path_edit, 1)
        browse_btn = QPushButton(tr("action.browse"))
        browse_btn.clicked.connect(self._on_browse)
        ft.addWidget(browse_btn)
        self.tabs.addTab(file_tab, tr("dlg.import_sql.tab.file"))
        # 1b) 粘贴 tab
        paste_tab = QWidget()
        pt = QVBoxLayout(paste_tab)
        pt.setContentsMargins(0, 8, 0, 8)
        pt.setSpacing(6)
        self.paste_edit = QPlainTextEdit()
        self.paste_edit.setPlaceholderText(tr("dlg.import_sql.paste.placeholder"))
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.paste_edit.setFont(mono)
        self.paste_edit.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 12px; "
            "background: #0b1220; color: #e2e8f0; border: 1px solid #334155; border-radius: 6px;"
        )
        # 粘贴模式下输入会触发自动解析(用 250ms 防抖)
        self._paste_timer = QTimer(self)
        self._paste_timer.setSingleShot(True)
        self._paste_timer.setInterval(250)
        self._paste_timer.timeout.connect(self._do_parse)
        self.paste_edit.textChanged.connect(lambda: self._paste_timer.start())
        pt.addWidget(self.paste_edit, 1)
        self.tabs.addTab(paste_tab, tr("dlg.import_sql.tab.paste"))
        self.tabs.currentChanged.connect(self._on_tab_change)
        layout.addWidget(self.tabs)

        # 2) 方言
        dialect_row = QHBoxLayout()
        dialect_row.setSpacing(8)
        dialect_row.addWidget(QLabel(tr("dlg.import_sql.dialect")))
        self.dialect_combo = QComboBox()
        for d in DIALECTS:
            self.dialect_combo.addItem(_DIALECT_LABELS[d], d)
        idx = self.dialect_combo.findData(default_dialect)
        if idx >= 0:
            self.dialect_combo.setCurrentIndex(idx)
        self.dialect_combo.currentIndexChanged.connect(self._on_dialect_change)
        dialect_row.addWidget(self.dialect_combo)
        dialect_row.addStretch()
        # 重新解析按钮(粘贴模式下可手动触发)
        self.reparse_btn = QPushButton(tr("dlg.import_sql.reparse"))
        self.reparse_btn.setObjectName("Ghost")
        self.reparse_btn.clicked.connect(self._do_parse)
        dialect_row.addWidget(self.reparse_btn)
        layout.addLayout(dialect_row)

        # 3) 全选/反选 + 计数
        sel_row = QHBoxLayout()
        sel_row.setSpacing(8)
        sel_row.addWidget(QLabel(tr("dlg.import_sql.tables")))
        sel_row.addStretch()
        self.select_all_btn = QPushButton(tr("action.select_all"))
        self.select_all_btn.setObjectName("Ghost")
        self.select_all_btn.clicked.connect(self._on_select_all)
        sel_row.addWidget(self.select_all_btn)
        self.deselect_btn = QPushButton(tr("action.deselect_all"))
        self.deselect_btn.setObjectName("Ghost")
        self.deselect_btn.clicked.connect(self._on_deselect_all)
        sel_row.addWidget(self.deselect_btn)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        sel_row.addWidget(self.count_label)
        layout.addLayout(sel_row)

        # 4) 表列表(多选)
        self.table_list = QListWidget()
        self.table_list.setMinimumHeight(160)
        layout.addWidget(self.table_list, 1)

        # 5) 错误/警告区
        self.error_view = QPlainTextEdit()
        self.error_view.setReadOnly(True)
        self.error_view.setMaximumHeight(96)
        self.error_view.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 11px; "
            "color: #f59e0b; background: #1f1300; border: 1px solid #b45309; border-radius: 4px;"
        )
        self.error_view.setVisible(False)
        layout.addWidget(self.error_view)

        # 6) 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton(tr("action.cancel"))
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        self.import_btn = QPushButton(tr("dlg.import_sql.import"))
        self.import_btn.setObjectName("Primary")
        self.import_btn.setDefault(True)
        self.import_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(self.import_btn)
        layout.addLayout(btn_row)

    # ============== 槽 ==============
    def _on_browse(self):
        start = str(Path(self.path_edit.text()).parent) if self.path_edit.text() else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, tr("dlg.import_sql.browse_title"), start,
            "SQL files (*.sql);;All files (*.*)"
        )
        if path:
            self.path_edit.setText(path)
            self._do_parse()

    def _on_dialect_change(self):
        self._do_parse()

    def _on_tab_change(self, _idx: int):
        # 切到粘贴 tab 时立即解析已有内容
        self._do_parse()

    def _on_select_all(self):
        for i in range(self.table_list.count()):
            item = self.table_list.item(i)
            if item.parsed.parse_error or not item.parsed.columns:
                continue
            item.setCheckState(Qt.CheckState.Checked)
        self._update_count()

    def _on_deselect_all(self):
        for i in range(self.table_list.count()):
            self.table_list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self._update_count()

    def _do_parse(self):
        dialect = self.dialect_combo.currentData() or "postgres"
        if self.tabs.currentIndex() == 0:
            # 文件模式
            path = self.path_edit.text().strip()
            if not path:
                return
            if not Path(path).is_file():
                self.error_view.setPlainText(f"文件不存在: {path}")
                self.error_view.setVisible(True)
                return
            try:
                tables, errs = parse_ddl_file(path, dialect)
            except Exception as e:
                QMessageBox.warning(self, tr("common.error"), f"解析失败: {e}")
                return
        else:
            # 粘贴模式
            text = self.paste_edit.toPlainText()
            if not text.strip():
                self._parsed_tables = []
                self.table_list.clear()
                self.error_view.setVisible(False)
                self._update_count()
                return
            try:
                tables, errs = parse_ddl_text(text, dialect)
            except Exception as e:
                QMessageBox.warning(self, tr("common.error"), f"解析失败: {e}")
                return

        self._parsed_tables = tables
        self.table_list.clear()
        for t in tables:
            self.table_list.addItem(_TableItem(t))
        if errs:
            self.error_view.setPlainText("\n".join(errs))
            self.error_view.setVisible(True)
        elif not tables:
            self.error_view.setPlainText(tr("dlg.import_sql.no_table_found"))
            self.error_view.setVisible(True)
        else:
            self.error_view.setVisible(False)
        self._update_count()

    def _update_count(self):
        total = self.table_list.count()
        sel = sum(
            1 for i in range(total)
            if self.table_list.item(i).checkState() == Qt.CheckState.Checked
        )
        self.count_label.setText(f"{sel} / {total}")

    def _on_accept(self):
        # 收集选中的表
        selected = []
        for i in range(self.table_list.count()):
            item = self.table_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.parsed)
        if not selected:
            QMessageBox.information(
                self, tr("common.info"),
                tr("dlg.import_sql.empty_selection"),
            )
            return
        self._selected_tables = selected
        self.accept()

    # ============== 公开 ==============
    def get_selected_tables(self) -> list[ParsedTable]:
        """返回用户勾选的 ParsedTable 列表(每张表含 columns)。"""
        return getattr(self, "_selected_tables", [])

    def set_paste_text(self, text: str) -> None:
        """公开:预填粘贴内容 + 切到粘贴 tab + 立即解析。"""
        self.paste_edit.setPlainText(text)
        self.tabs.setCurrentIndex(1)
        self._do_parse()

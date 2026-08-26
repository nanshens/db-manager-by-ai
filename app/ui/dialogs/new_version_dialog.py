"""新建数据版本 对话框(选表 + 选文件)"""
from __future__ import annotations
import os
from typing import Optional
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QListWidget, QListWidgetItem, QFileDialog, QHBoxLayout,
    QMessageBox, QSizePolicy, QFrame, QGridLayout,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.repos.table_repo import Table
from app.core.file_reader import detect_format


class FileRow(QFrame):
    """单张表 + 一个文件路径 — 表格网格布局,列名不会被截断。"""
    path_changed = Signal()

    def __init__(self, table: Table, parent=None):
        super().__init__(parent)
        self._table = table
        self.setFrameShape(QFrame.Shape.StyledPanel)
        # 用 QGridLayout — 表名列固定宽度,路径列弹性伸缩,操作列固定
        layout = QGridLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(4)

        # 第 0 列(表名) — 加表格 emoji 让"表 vs 文件路径"区分开
        lbl = QLabel(f"📄 {table.name}")
        lbl.setMinimumWidth(180)
        lbl.setMaximumWidth(200)
        lbl.setStyleSheet("font-weight: 600; font-size: 13px;")
        lbl.setToolTip(table.name)
        layout.addWidget(lbl, 0, 0, Qt.AlignmentFlag.AlignVCenter)

        # 第 1 列(路径)— 显眼的输入框,等宽字体,稍高
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(tr("dlg.version.file.placeholder"))
        self.path_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.path_edit.setMinimumHeight(34)
        # 等宽字体让文件路径更可读
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.path_edit.setFont(mono)
        self.path_edit.setStyleSheet(
            "QLineEdit { padding: 6px 10px; border-radius: 4px; }"
        )
        layout.addWidget(self.path_edit, 0, 1)

        # 第 2 列(浏览)
        browse_btn = QPushButton(tr("action.browse"))
        browse_btn.setObjectName("Ghost")
        browse_btn.setIcon(qta.icon("mdi6.folder-open-outline", color="#94a3b8"))
        browse_btn.clicked.connect(self._browse)
        layout.addWidget(browse_btn, 0, 2)

        # 第 3 列(清除)
        clear_btn = QPushButton()
        clear_btn.setIcon(qta.icon("mdi6.close", color="#94a3b8"))
        clear_btn.setFixedSize(34, 34)
        clear_btn.setToolTip("清除")
        clear_btn.clicked.connect(lambda: self.path_edit.clear())
        layout.addWidget(clear_btn, 0, 3)

        # 副标题行:列数 + 格式提示
        info_lbl = QLabel(f"({len(table.columns)} cols · {tr('dlg.version.file.format_hint')})")
        info_lbl.setObjectName("Muted")
        info_lbl.setStyleSheet("font-size: 11px; color: #64748b;")
        layout.addWidget(info_lbl, 1, 0, 1, 4)
        layout.setRowStretch(0, 1)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("dlg.version.browse_title"),
            "", "Data files (*.csv *.tsv *.xlsx *.xls);;All files (*)",
        )
        if path:
            self.path_edit.setText(path)
            self.path_changed.emit()

    def get_path(self) -> str:
        return self.path_edit.text().strip()

    def get_table(self) -> Table:
        return self._table


class NewVersionDialog(QDialog):
    def __init__(self, tables: list[Table], default_version_name: str = "v1.0", parent=None):
        super().__init__(parent)
        self._tables = tables
        self.setWindowTitle(tr("dlg.version.title"))
        # 表多时也要好用 — 初始 960x720,允许更大
        self.resize(960, 720)
        self.setMinimumSize(800, 560)
        self._build(default_version_name)

    def _build(self, default_name):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # Version name + description
        layout.addWidget(QLabel(tr("dlg.version.name") + " *"))
        self.name_edit = QLineEdit()
        self.name_edit.setText(default_name)
        layout.addWidget(self.name_edit)

        layout.addWidget(QLabel(tr("dlg.version.desc")))
        self.desc_edit = QLineEdit()
        layout.addWidget(self.desc_edit)

        # File mapping
        layout.addWidget(QLabel(tr("dlg.version.files")))
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        # 关键:让 list 内部每一项都展开 — 不然 FileRow 会被裁切
        self.file_list.setUniformItemSizes(False)
        # 让 list 内部上下没空白,行与行紧贴
        self.file_list.setSpacing(0)
        # 去掉 list 自己的边框(每行 QFrame 已经有 StyledPanel)
        self.file_list.setFrameShape(QListWidget.Shape.NoFrame)
        self._row_widgets: list[FileRow] = []
        for t in self._tables:
            item = QListWidgetItem(self.file_list)
            row = FileRow(t)
            self._row_widgets.append(row)
            # 强制行高 76,适配新增的副标题行
            item.setSizeHint(QSize(0, 76))
            self.file_list.addItem(item)
            self.file_list.setItemWidget(item, row)
        layout.addWidget(self.file_list, 1)

        # Tip
        tip = QLabel(tr("dlg.version.tip"))
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        layout.addWidget(tip)

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
        ok = QPushButton(tr("action.create"))
        ok.setObjectName("Primary")
        ok.clicked.connect(self._on_accept)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

        self.name_edit.setFocus()

    def _on_accept(self) -> None:
        if not self.name_edit.text().strip():
            self._err(tr("dlg.version.error.name_required"))
            return
        files = {}
        for row in self._row_widgets:
            p = row.get_path()
            if p:
                if not os.path.exists(p):
                    self._err(tr("dlg.version.error.file_not_exist").format(path=p))
                    return
                fmt = detect_format(p)
                if fmt == "unknown":
                    self._err(tr("dlg.version.error.unsupported_format").format(path=p))
                    return
                files[row.get_table().name] = p
        if not files:
            self._err(tr("dlg.version.error.no_files"))
            return
        self.accept()

    def _err(self, msg: str) -> None:
        self.error_label.setText(msg)
        self.error_label.setVisible(True)

    def get_values(self) -> dict:
        files = {}
        for row in self._row_widgets:
            p = row.get_path()
            if p:
                files[row.get_table().name] = p
        return {
            "version_name": self.name_edit.text().strip(),
            "description": self.desc_edit.text().strip(),
            "files": files,
        }

"""新建数据版本 对话框 — 支持两种模式:
- manual: 手动为每张表选一个文件(原版)
- batch:  批量选文件 / 选目录,自动按文件名匹配表名(忽略大小写),
         未匹配的可以手动指定目标表;创建时所有文件必须都已分配
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QListWidget, QListWidgetItem, QFileDialog,
    QMessageBox, QSizePolicy, QFrame, QGridLayout,
    QRadioButton, QButtonGroup, QStackedWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QComboBox, QWidget,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.repos.table_repo import Table
from app.core.file_reader import detect_format


# 批量模式里"未分配"的占位项 — i18n 单独处理
UNMATCHED_KEY = "__unmatched__"


class FileRow(QFrame):
    """手动模式:单张表 + 一个文件路径 — 表格网格布局,列名不会被截断。"""
    path_changed = Signal()

    def __init__(self, table: Table, parent=None):
        super().__init__(parent)
        self._table = table
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QGridLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(4)

        lbl = QLabel(f"📄 {table.name}")
        lbl.setMinimumWidth(180)
        lbl.setMaximumWidth(200)
        lbl.setStyleSheet("font-weight: 600; font-size: 13px;")
        lbl.setToolTip(table.name)
        layout.addWidget(lbl, 0, 0, Qt.AlignmentFlag.AlignVCenter)

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(tr("dlg.version.file.placeholder"))
        self.path_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.path_edit.setMinimumHeight(34)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.path_edit.setFont(mono)
        self.path_edit.setStyleSheet(
            "QLineEdit { padding: 6px 10px; border-radius: 4px; }"
        )
        layout.addWidget(self.path_edit, 0, 1)

        browse_btn = QPushButton(tr("action.browse"))
        browse_btn.setObjectName("Ghost")
        browse_btn.setIcon(qta.icon("mdi6.folder-open-outline", color="#94a3b8"))
        browse_btn.setMinimumHeight(34)  # 跟 path_edit 对齐
        browse_btn.clicked.connect(self._browse)
        layout.addWidget(browse_btn, 0, 2)

        clear_btn = QPushButton()
        clear_btn.setIcon(qta.icon("mdi6.close", color="#94a3b8"))
        clear_btn.setFixedSize(34, 34)
        clear_btn.setToolTip(tr("action.clear"))
        clear_btn.clicked.connect(lambda: self.path_edit.clear())
        layout.addWidget(clear_btn, 0, 3)

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

        # ----- 模式选择 -----
        mode_row = QHBoxLayout()
        mode_row.setSpacing(16)
        mode_lbl = QLabel(tr("dlg.version.mode"))
        mode_lbl.setObjectName("Secondary")
        mode_row.addWidget(mode_lbl)
        self.manual_radio = QRadioButton(tr("dlg.version.mode.manual"))
        self.batch_radio = QRadioButton(tr("dlg.version.mode.batch"))
        self.manual_radio.setChecked(True)
        self.manual_radio.toggled.connect(self._on_mode_changed)
        mode_row.addWidget(self.manual_radio)
        mode_row.addWidget(self.batch_radio)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        # ----- Stacked 容器:0=手动 1=批量 -----
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_manual_page())   # 0
        self.stack.addWidget(self._build_batch_page())    # 1
        layout.addWidget(self.stack, 1)

        # Tip
        self.tip_label = QLabel(tr("dlg.version.tip"))
        self.tip_label.setObjectName("Muted")
        self.tip_label.setWordWrap(True)
        layout.addWidget(self.tip_label)

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
        self._on_mode_changed()  # 初始化 tip 文本

    # ---------- 手动模式 ----------
    def _build_manual_page(self) -> QWidget:
        w = QFrame()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        v.addWidget(QLabel(tr("dlg.version.files")))
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.file_list.setUniformItemSizes(False)
        self.file_list.setSpacing(0)
        self.file_list.setFrameShape(QListWidget.Shape.NoFrame)
        self._row_widgets: list[FileRow] = []
        for t in self._tables:
            item = QListWidgetItem(self.file_list)
            row = FileRow(t)
            self._row_widgets.append(row)
            item.setSizeHint(QSize(0, 76))
            self.file_list.addItem(item)
            self.file_list.setItemWidget(item, row)
        v.addWidget(self.file_list, 1)
        return w

    # ---------- 批量模式 ----------
    def _build_batch_page(self) -> QWidget:
        w = QFrame()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        # 顶部操作
        btn_row = QHBoxLayout()
        pick_files_btn = QPushButton(tr("dlg.version.batch.pick_files"))
        pick_files_btn.setObjectName("Ghost")
        pick_files_btn.setIcon(qta.icon("mdi6.file-multiple-outline", color="#94a3b8"))
        pick_files_btn.clicked.connect(self._batch_pick_files)
        btn_row.addWidget(pick_files_btn)

        pick_dir_btn = QPushButton(tr("dlg.version.batch.pick_dir"))
        pick_dir_btn.setObjectName("Ghost")
        pick_dir_btn.setIcon(qta.icon("mdi6.folder-open-outline", color="#94a3b8"))
        pick_dir_btn.clicked.connect(self._batch_pick_dir)
        btn_row.addWidget(pick_dir_btn)

        clear_btn = QPushButton(tr("dlg.version.batch.clear"))
        clear_btn.setObjectName("Ghost")
        clear_btn.setIcon(qta.icon("mdi6.broom", color="#94a3b8"))
        clear_btn.clicked.connect(self._batch_clear)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        v.addLayout(btn_row)

        # 汇总
        self.batch_summary = QLabel("")
        self.batch_summary.setObjectName("Muted")
        v.addWidget(self.batch_summary)

        # 表格:文件 | 格式 | 状态 | 目标表
        self.batch_table = QTableWidget(0, 4)
        self.batch_table.setHorizontalHeaderLabels([
            tr("dlg.version.col.file"),
            tr("dlg.version.col.format"),
            tr("dlg.version.col.status"),
            tr("dlg.version.col.target_table"),
        ])
        hdr = self.batch_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.batch_table.verticalHeader().setVisible(False)
        # 行高加大 — 否则 QComboBox 塞 cell 里会被裁切,看不清提示词
        self.batch_table.verticalHeader().setDefaultSectionSize(38)
        self.batch_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.batch_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.batch_table.setStyleSheet(
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
        self.batch_table.setFont(mono)
        v.addWidget(self.batch_table, 1)
        return w

    def _on_mode_changed(self) -> None:
        is_batch = self.batch_radio.isChecked()
        self.stack.setCurrentIndex(1 if is_batch else 0)
        # 切换 tip 文案
        if is_batch:
            self.tip_label.setText(tr("dlg.version.tip.batch"))
        else:
            self.tip_label.setText(tr("dlg.version.tip"))

    # ---------- 批量模式操作 ----------
    def _batch_pick_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("dlg.version.batch.pick_files"),
            "", "Data files (*.csv *.tsv *.xlsx *.xls);;All files (*)",
        )
        for p in paths:
            self._batch_add_file(p)

    def _batch_pick_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("dlg.version.batch.pick_dir"))
        if not d:
            return
        exts = (".csv", ".tsv", ".xlsx", ".xls")
        try:
            for name in sorted(os.listdir(d)):
                if name.lower().endswith(exts):
                    self._batch_add_file(os.path.join(d, name))
        except OSError as e:
            self._err(str(e))

    def _batch_clear(self) -> None:
        self.batch_table.setRowCount(0)
        self._batch_refresh_summary()

    def _batch_add_file(self, path: str) -> None:
        # 已经在表里就跳过
        for r in range(self.batch_table.rowCount()):
            if self.batch_table.item(r, 0).data(Qt.ItemDataRole.UserRole) == path:
                return
        fmt = detect_format(path)
        # 推断匹配
        matched = self._auto_match_table(path)
        # 加行
        row = self.batch_table.rowCount()
        self.batch_table.insertRow(row)
        # 0 文件名
        name_item = QTableWidgetItem(os.path.basename(path))
        name_item.setData(Qt.ItemDataRole.UserRole, path)
        name_item.setToolTip(path)
        self.batch_table.setItem(row, 0, name_item)
        # 1 格式
        self.batch_table.setItem(row, 1, QTableWidgetItem(fmt.upper() if fmt != "unknown" else "?"))
        # 2 状态(只读预览:✓ 已匹配 / ⚠ 未匹配)
        status_item = QTableWidgetItem(
            tr("dlg.version.batch.matched") if matched else tr("dlg.version.batch.unmatched")
        )
        if matched:
            status_item.setForeground(QColor("#22c55e"))  # 绿
        else:
            status_item.setForeground(QColor("#f59e0b"))  # 黄
        self.batch_table.setItem(row, 2, status_item)
        # 3 目标表(下拉)
        combo = QComboBox()
        combo.addItem(tr("dlg.version.batch.unmatched"), UNMATCHED_KEY)
        for t in self._tables:
            combo.addItem(t.name, t.name)
        if matched:
            # 选中匹配的表
            idx = combo.findData(matched)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        combo.currentIndexChanged.connect(
            lambda _i, r=row: self._batch_on_table_changed(r)
        )
        self.batch_table.setCellWidget(row, 3, combo)
        self._batch_refresh_summary()

    def _auto_match_table(self, path: str) -> Optional[str]:
        """按文件名(去后缀,小写)和表名(小写)精确匹配。"""
        stem = Path(path).stem.lower()
        for t in self._tables:
            if t.name.lower() == stem:
                return t.name
        return None

    def _batch_on_table_changed(self, row: int) -> None:
        """用户在某行的下拉里选了目标表 — 同步状态图标 + 汇总"""
        combo = self.batch_table.cellWidget(row, 3)
        target = combo.currentData() if combo else UNMATCHED_KEY
        status_item = self.batch_table.item(row, 2)
        if target and target != UNMATCHED_KEY:
            status_item.setText(tr("dlg.version.batch.matched"))
            status_item.setForeground(QColor("#22c55e"))
        else:
            status_item.setText(tr("dlg.version.batch.unmatched"))
            status_item.setForeground(QColor("#f59e0b"))
        self._batch_refresh_summary()

    def _batch_refresh_summary(self) -> None:
        n = self.batch_table.rowCount()
        matched = 0
        for r in range(n):
            combo = self.batch_table.cellWidget(r, 3)
            if combo and combo.currentData() != UNMATCHED_KEY:
                matched += 1
        self.batch_summary.setText(
            tr("dlg.version.batch.summary").format(loaded=n, matched=matched)
        )

    # ---------- 提交 ----------
    def _on_accept(self) -> None:
        if not self.name_edit.text().strip():
            self._err(tr("dlg.version.error.name_required"))
            return
        if self.batch_radio.isChecked():
            files = self._collect_batch()
        else:
            files = self._collect_manual()
        if files is None:
            return  # 已经 _err 过
        if not files:
            self._err(tr("dlg.version.error.no_files"))
            return
        # 批量模式下:如果有未匹配文件,二次确认(只导入已匹配的)
        if self.batch_radio.isChecked():
            unmatched = self._collect_unmatched_files()
            if unmatched:
                # 弹确认
                from PySide6.QtWidgets import QMessageBox
                msg = tr("dlg.version.warn.unmatched").format(
                    n=len(unmatched),
                    files=", ".join(os.path.basename(p) for p, _ in unmatched[:5])
                )
                if len(unmatched) > 5:
                    msg += tr("dlg.version.warn.unmatched_more").format(extra=len(unmatched) - 5)
                reply = QMessageBox.question(
                    self, tr("dlg.version.warn.unmatched_title"),
                    msg,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
        self._files = files
        self.accept()

    def _collect_unmatched_files(self) -> list[tuple[str, str]]:
        """返回 [(path, reason)] — 当前 batch 表格里未匹配的文件"""
        unmatched = []
        for r in range(self.batch_table.rowCount()):
            combo = self.batch_table.cellWidget(r, 3)
            target = combo.currentData() if combo else UNMATCHED_KEY
            if not target or target == UNMATCHED_KEY:
                path = self.batch_table.item(r, 0).data(Qt.ItemDataRole.UserRole)
                unmatched.append((path, "unmatched"))
        return unmatched

    def _collect_manual(self) -> Optional[dict[str, str]]:
        files: dict[str, str] = {}
        for row in self._row_widgets:
            p = row.get_path()
            if not p:
                continue
            if not os.path.exists(p):
                self._err(tr("dlg.version.error.file_not_exist").format(path=p))
                return None
            fmt = detect_format(p)
            if fmt == "unknown":
                self._err(tr("dlg.version.error.unsupported_format").format(path=p))
                return None
            files[row.get_table().name] = p
        return files

    def _collect_batch(self) -> Optional[dict[str, str]]:
        n = self.batch_table.rowCount()
        if n == 0:
            self._err(tr("dlg.version.error.no_files"))
            return None
        files: dict[str, str] = {}
        for r in range(n):
            combo = self.batch_table.cellWidget(r, 3)
            target = combo.currentData() if combo else UNMATCHED_KEY
            path = self.batch_table.item(r, 0).data(Qt.ItemDataRole.UserRole)
            if not target or target == UNMATCHED_KEY:
                fname = self.batch_table.item(r, 0).text()
                self._err(
                    tr("dlg.version.error.file_unmatched").format(file=fname)
                )
                return None
            if not os.path.exists(path):
                self._err(tr("dlg.version.error.file_not_exist").format(path=path))
                return None
            fmt = detect_format(path)
            if fmt == "unknown":
                self._err(tr("dlg.version.error.unsupported_format").format(path=path))
                return None
            if target in files:
                self._err(
                    tr("dlg.version.error.table_duplicated").format(table=target)
                )
                return None
            files[target] = path
        return files

    def _err(self, msg: str) -> None:
        self.error_label.setText(msg)
        self.error_label.setVisible(True)

    def get_values(self) -> dict:
        return {
            "version_name": self.name_edit.text().strip(),
            "description": self.desc_edit.text().strip(),
            "files": getattr(self, "_files", {}),
        }

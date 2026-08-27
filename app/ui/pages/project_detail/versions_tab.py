"""Versions Tab — 数据版本管理(右侧详情 + 文件表格)"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QFrame, QListWidget,
    QListWidgetItem, QMessageBox, QWidget, QFileDialog, QSplitter,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.ui.widgets import EmptyState, show_toast
from app.ui.dialogs import NewVersionDialog
from app.services.registry import reg
from app.repos.data_version_repo import DataVersion


class VersionsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_id: Optional[int] = None
        self._current: Optional[DataVersion] = None
        self._build()
        self.refresh()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QFrame()
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(16, 12, 16, 12)
        self.new_btn = QPushButton(tr("versions_tab.new_version"))
        self.new_btn.setObjectName("Primary")
        self.new_btn.setIcon(qta.icon("mdi6.plus", color="white"))
        self.new_btn.clicked.connect(self._on_new)
        tb.addWidget(self.new_btn)
        tb.addStretch()
        layout.addWidget(toolbar)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)
        layout.addWidget(self.splitter, 1)

        # Left: version list
        left = QFrame()
        left.setMinimumWidth(200)
        left.setMaximumWidth(280)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8, 8, 8, 8)
        self.version_list = QListWidget()
        self.version_list.itemSelectionChanged.connect(self._on_selection)
        ll.addWidget(self.version_list)

        # Right: detail
        right = QFrame()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(16, 12, 16, 12)
        rl.setSpacing(8)
        self.detail_name = QLabel("—")
        self.detail_name.setStyleSheet("font-size: 15px; font-weight: 700;")
        rl.addWidget(self.detail_name)
        self.detail_desc = QLabel("")
        self.detail_desc.setObjectName("Secondary")
        self.detail_desc.setWordWrap(True)
        rl.addWidget(self.detail_desc)

        # Summary line: 多少个文件 / 多少行
        self.detail_summary = QLabel("")
        self.detail_summary.setObjectName("Muted")
        self.detail_summary.setMinimumHeight(20)
        self.detail_summary.setStyleSheet("font-size: 12px; padding: 4px 0;")
        rl.addWidget(self.detail_summary)

        # File list — 用 QTableWidget 替代 QPlainTextEdit,信息更清楚
        files_label = QLabel(tr("dlg.version.files"))
        files_label.setObjectName("Muted")
        files_label.setStyleSheet("font-size: 11px;")
        rl.addWidget(files_label)
        self.files_table = QTableWidget(0, 4)
        self.files_table.setHorizontalHeaderLabels([
            tr("dlg.version.col.table"),
            tr("dlg.version.col.format"),
            tr("dlg.version.col.rows"),
            tr("dlg.version.col.path"),
        ])
        # 列宽:前 3 列按内容,第 4 列伸缩
        hdr = self.files_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.files_table.verticalHeader().setVisible(False)
        self.files_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.files_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.files_table.setStyleSheet(
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
        self.files_table.setFont(mono)
        rl.addWidget(self.files_table, 1)

        # Action row
        act_row = QHBoxLayout()
        act_row.addStretch()
        self.check_btn = QPushButton(tr("versions_tab.check_schema"))
        self.check_btn.setObjectName("Ghost")
        self.check_btn.setIcon(qta.icon("mdi6.check-decagram-outline", color="#22c55e"))
        self.check_btn.clicked.connect(self._on_check_schema)
        act_row.addWidget(self.check_btn)
        self.del_btn = QPushButton(tr("action.delete"))
        self.del_btn.setObjectName("Ghost")
        self.del_btn.setIcon(qta.icon("mdi6.trash-can-outline", color="#ef4444"))
        self.del_btn.clicked.connect(self._on_delete)
        act_row.addWidget(self.del_btn)
        rl.addLayout(act_row)

        # Empty state — 纯展示,按钮走工具栏(避免重复)
        self.empty = EmptyState(
            icon_name="mdi6.package-variant",
            title=tr("versions_tab.empty.title"),
            description=tr("versions_tab.empty.desc"),
            primary_text="",
        )
        # 即便没按钮,连一下信号保持兼容
        self.empty.primary_clicked.connect(self._on_new)

        # Splitter assignment — right 暂不加入,默认显示 empty
        empty_holder = QFrame()
        eh_layout = QVBoxLayout(empty_holder)
        eh_layout.setContentsMargins(0, 0, 0, 0)
        eh_layout.addWidget(self.empty)
        eh_layout.addStretch()

        self.splitter.addWidget(left)
        self.splitter.addWidget(empty_holder)
        self.splitter.setSizes([220, 700])

        self._right_holder = empty_holder
        self._right_widget = right
        self._files_label = files_label
        self._detail_widgets = [
            self.detail_name, self.detail_desc, self.detail_summary,
            self.files_table, self.del_btn, files_label,
        ]
        self._init_state()

    def _init_state(self) -> None:
        for w in self._detail_widgets:
            w.hide()

    def retranslate(self) -> None:
        self.new_btn.setText(tr("versions_tab.new_version"))
        self.empty.title_label.setText(tr("versions_tab.empty.title"))
        self.empty.desc_label.setText(tr("versions_tab.empty.desc"))
        self._files_label.setText(tr("dlg.version.files"))
        # 表头重译
        if hasattr(self, "files_table"):
            self.files_table.setHorizontalHeaderLabels([
                tr("dlg.version.col.table"),
                tr("dlg.version.col.format"),
                tr("dlg.version.col.rows"),
                tr("dlg.version.col.path"),
            ])
        # 当前选中的 summary 重译
        if self._current:
            self._refresh_summary(self._current)

    def set_project(self, project_id: int) -> None:
        self._project_id = project_id
        self.refresh()

    def refresh(self) -> None:
        if self._project_id is None:
            return
        self.version_list.clear()
        self._init_state()
        versions = reg().data_version_service.list_by_project(self._project_id)
        if not versions:
            self._show_empty()
            return
        self._show_list()
        for v in versions:
            item = QListWidgetItem(f"📦 {v.version_name}")
            item.setData(Qt.ItemDataRole.UserRole, v.id)
            self.version_list.addItem(item)
        if self.version_list.count() > 0:
            self.version_list.setCurrentRow(0)

    def _show_empty(self) -> None:
        self.empty.show()
        # 关键:把 right 从 splitter 移走,加 empty_holder
        if self._right_widget.parent() is not None:
            self._right_widget.setParent(None)
        if self._right_holder.parent() is None:
            self.splitter.addWidget(self._right_holder)
        for w in self._detail_widgets:
            w.hide()

    def _show_list(self) -> None:
        self.empty.hide()
        # 关键:把 right 加到 splitter(替换 empty_holder)
        if self._right_holder.parent() is not None:
            self._right_holder.setParent(None)
        if self._right_widget.parent() is None:
            self.splitter.addWidget(self._right_widget)
            self.splitter.setSizes([220, 700])

    def _on_selection(self) -> None:
        items = self.version_list.selectedItems()
        if not items:
            self._current = None
            self._init_state()
            return
        vid = items[0].data(Qt.ItemDataRole.UserRole)
        v = reg().data_version_service.get(vid)
        self._current = v
        if not v:
            return
        for w in self._detail_widgets:
            w.show()
        self.detail_name.setText(f"📦 {v.version_name}")
        self.detail_desc.setText(v.description or "")
        self._refresh_summary(v)
        # 填文件表
        self.files_table.setRowCount(0)
        for f in v.source_files:
            row = self.files_table.rowCount()
            self.files_table.insertRow(row)
            self.files_table.setItem(row, 0, QTableWidgetItem(f.table_name))
            self.files_table.setItem(row, 1, QTableWidgetItem(f.format.upper()))
            self.files_table.setItem(row, 2, QTableWidgetItem(
                str(f.rows) if f.rows else "—"
            ))
            path_item = QTableWidgetItem(f.local_path)
            # tooltip 显示完整 sha256
            tip = f.local_path
            if f.sha256:
                tip += f"\nSHA256: {f.sha256}"
            path_item.setToolTip(tip)
            self.files_table.setItem(row, 3, path_item)

    def _refresh_summary(self, v) -> None:
        """重画顶部统计: N 个表 · M 个文件 · 共 K 行"""
        n_files = len(v.source_files)
        n_tables = len({f.table_name for f in v.source_files})
        total_rows = sum((f.rows or 0) for f in v.source_files)
        self.detail_summary.setText(
            tr("versions_tab.summary").format(
                n_tables=n_tables, n_files=n_files, total_rows=total_rows,
            )
        )

    def _on_new(self) -> None:
        if self._project_id is None:
            return
        tables = reg().table_service.list_by_project(self._project_id)
        if not tables:
            QMessageBox.information(
                self, tr("common.info") if False else tr("versions_tab.empty.title"),
                tr("versions_tab.no_tables"),
            )
            return
        # 建议默认版本名 v1.0 / v1.1 / ...
        existing = reg().data_version_service.list_by_project(self._project_id)
        n = len(existing) + 1
        default_name = f"v1.{n - 1}" if n > 1 else "v1.0"
        dlg = NewVersionDialog(tables=tables, default_version_name=default_name, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            v = dlg.get_values()
            try:
                reg().data_version_service.create(
                    self._project_id, v["version_name"], v["description"], v["files"],
                )
                show_toast(tr("toast.saved"), "success")
                self.refresh()
                # 广播:其他 tab(比如 diff)需要刷新版本列表
                reg().bus.data_version_changed.emit()
            except ValueError as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

    def _on_delete(self) -> None:
        if not self._current:
            return
        if QMessageBox.question(
            self, tr("action.confirm_delete"),
            f"Delete version \"{self._current.version_name}\"?"
        ) == QMessageBox.StandardButton.Yes:
            try:
                reg().data_version_service.delete(self._current.id)
                show_toast(tr("toast.deleted"), "success")
                self._current = None
                self.refresh()
                reg().bus.data_version_changed.emit()
            except Exception as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

    def _on_check_schema(self) -> None:
        """扫描当前版本的所有文件,跟表结构(列名/列数)做校验"""
        if not self._current:
            return
        from app.core.file_reader import infer_columns
        v = self._current
        # 找项目的所有表
        tables = reg().table_service.list_by_project(self._project_id)
        table_map = {t.name: t for t in tables}
        report: list[tuple[str, str, str]] = []  # (状态, 表名, 描述)
        for f in v.source_files:
            t = table_map.get(f.table_name)
            if not t:
                report.append(("❌", f.table_name,
                              tr("versions_tab.check.no_table")))
                continue
            try:
                file_cols = infer_columns(f.local_path)
            except Exception as e:
                report.append(("⚠", f.table_name,
                              tr("versions_tab.check.read_error").format(err=str(e))))
                continue
            table_cols = [c.name for c in t.columns]
            # 列数对比
            if len(file_cols) != len(table_cols):
                report.append(("⚠", f.table_name,
                              tr("versions_tab.check.col_count_mismatch").format(
                                  file_n=len(file_cols), table_n=len(table_cols))))
                continue
            # 列名对比(忽略顺序)
            file_set = set(c.lower() for c in file_cols)
            table_set = set(c.lower() for c in table_cols)
            missing = table_set - file_set
            extra = file_set - table_set
            if missing or extra:
                msg = ""
                if missing:
                    msg += tr("versions_tab.check.missing").format(
                        cols=", ".join(sorted(missing)))
                if extra:
                    msg += tr("versions_tab.check.extra").format(
                        cols=", ".join(sorted(extra)))
                report.append(("⚠", f.table_name, msg))
                continue
            report.append(("✓", f.table_name,
                          tr("versions_tab.check.ok")))
        # 弹窗
        from app.ui.dialogs.schema_check_dialog import SchemaCheckDialog
        dlg = SchemaCheckDialog(version_name=v.version_name, report=report, parent=self)
        dlg.exec()

"""Diff Tab — 表数据对比(M4 占位:基础选择 + 对比)"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QFrame, QComboBox, QCheckBox,
    QPlainTextEdit, QListWidget, QListWidgetItem, QMessageBox, QWidget, QFileDialog,
    QProgressBar,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.ui.widgets import EmptyState, show_toast
from app.services.registry import reg
from app.core.file_reader import detect_format
from app.core.diff_engine import DiffEngine, DiffConfig


class DiffWorker(QObject):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, left_path: str, right_path: str, config: DiffConfig):
        super().__init__()
        self.left_path = left_path
        self.right_path = right_path
        self.config = config

    def run(self):
        try:
            engine = DiffEngine()
            result = engine.compute(self.left_path, self.right_path, self.config)
            self.finished.emit(result.to_dict())
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(str(e))


class DiffTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_id: Optional[int] = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Config area
        cfg = QFrame()
        cfg.setStyleSheet("background: transparent; border-bottom: 1px solid #1e293b;")
        cl = QVBoxLayout(cfg)
        cl.setContentsMargins(16, 12, 16, 12)
        cl.setSpacing(8)

        # Row 1: source A / B
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        row1.addWidget(QLabel(tr("diff.source_a")))
        self.left_combo = QComboBox()
        self.left_combo.setMinimumWidth(220)
        row1.addWidget(self.left_combo)
        self.left_browse = QPushButton(tr("action.browse"))
        self.left_browse.setObjectName("Ghost")
        self.left_browse.clicked.connect(lambda: self._browse("left"))
        row1.addWidget(self.left_browse)

        row1.addSpacing(20)
        row1.addWidget(QLabel(tr("diff.source_b")))
        self.right_combo = QComboBox()
        self.right_combo.setMinimumWidth(220)
        row1.addWidget(self.right_combo)
        self.right_browse = QPushButton(tr("action.browse"))
        self.right_browse.setObjectName("Ghost")
        self.right_browse.clicked.connect(lambda: self._browse("right"))
        row1.addWidget(self.right_browse)

        cl.addLayout(row1)

        # Row 2: PK columns + diff options
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(QLabel(tr("diff.pk")))
        self.pk_combo = QComboBox()
        self.pk_combo.setMinimumWidth(180)
        self.pk_combo.setEditable(True)
        row2.addWidget(self.pk_combo)

        self.config_btn = QPushButton(tr("diff.config"))
        self.config_btn.setObjectName("Ghost")
        self.config_btn.setIcon(qta.icon("mdi6.cog", color="#94a3b8"))
        self.config_btn.clicked.connect(self._on_config)
        row2.addWidget(self.config_btn)

        self.case_chk = QCheckBox(tr("diff.case_sensitive"))
        self.trim_chk = QCheckBox(tr("diff.trim"))
        self.trim_chk.setChecked(True)
        row2.addWidget(self.case_chk)
        row2.addWidget(self.trim_chk)
        row2.addStretch()

        self.run_btn = QPushButton(tr("diff.run"))
        self.run_btn.setObjectName("Primary")
        self.run_btn.setIcon(qta.icon("mdi6.play", color="white"))
        self.run_btn.clicked.connect(self._on_run)
        row2.addWidget(self.run_btn)
        cl.addLayout(row2)

        # Progress
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        cl.addWidget(self.progress)

        layout.addWidget(cfg)

        # Results area
        results = QFrame()
        rl = QVBoxLayout(results)
        rl.setContentsMargins(16, 12, 16, 12)
        rl.setSpacing(8)

        # Stats
        stats_row = QHBoxLayout()
        self.stat_left = QLabel("—")
        self.stat_right = QLabel("—")
        self.stat_added = QLabel("—")
        self.stat_deleted = QLabel("—")
        self.stat_modified = QLabel("—")
        for w in (self.stat_left, self.stat_right, self.stat_added, self.stat_deleted, self.stat_modified):
            stats_row.addWidget(w)
            stats_row.addSpacing(20)
        stats_row.addStretch()
        rl.addLayout(stats_row)

        # Result text
        self.result_view = QPlainTextEdit()
        self.result_view.setReadOnly(True)
        self.result_view.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 11px; "
            "background: #0b1220; color: #e2e8f0; border: 1px solid #334155; border-radius: 6px;"
        )
        rl.addWidget(self.result_view, 1)
        layout.addWidget(results, 1)

    def retranslate(self) -> None:
        self.run_btn.setText(tr("diff.run"))
        self.config_btn.setText(tr("diff.config"))
        self.case_chk.setText(tr("diff.case_sensitive"))
        self.trim_chk.setText(tr("diff.trim"))

    def set_project(self, project_id: int) -> None:
        self._project_id = project_id
        self.left_combo.clear()
        self.right_combo.clear()
        # Source options: 各版本 + [上传新文件]
        versions = reg().data_version_service.list_by_project(project_id)
        for v in versions:
            label = f"📦 {v.version_name} ({len(v.source_files)} 表)"
            self.left_combo.addItem(label, ("version", v.id))
            self.right_combo.addItem(label, ("version", v.id))
        # 提示:可上传新文件
        self.left_combo.addItem("📁 上传新文件…", ("upload",))
        self.right_combo.addItem("📁 上传新文件…", ("upload",))

        # 加载表的列名
        tables = reg().table_service.list_by_project(project_id)
        self._all_columns = []
        for t in tables:
            self._all_columns.extend([c.name for c in t.columns])
        self.pk_combo.clear()
        self.pk_combo.addItems(self._all_columns)

    def _browse(self, which: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("diff.browse_title"),
            "", "Data files (*.csv *.tsv *.xlsx *.xls);;All files (*)",
        )
        if path:
            if which == "left":
                self.left_combo.setCurrentText(f"📁 {path}")
                self.left_combo.setCurrentIndex(self.left_combo.count() - 1)
            else:
                self.right_combo.setCurrentText(f"📁 {path}")
                self.right_combo.setCurrentIndex(self.right_combo.count() - 1)

    def _on_config(self) -> None:
        QMessageBox.information(self, tr("common.info") if False else tr("diff.config"), "Coming soon")

    def _on_run(self) -> None:
        # 简化:取左右两个版本里的第一个表,跑 diff
        left_data = self.left_combo.currentData()
        right_data = self.right_combo.currentData()
        if not left_data or not right_data:
            QMessageBox.information(self, tr("common.error"), "Select both sources")
            return
        if left_data[0] != "version" or right_data[0] != "version":
            QMessageBox.information(self, tr("common.error"), "Only version-vs-version supported in this build")
            return
        # 取左右版本的第一个 file
        lv = reg().data_version_service.get(left_data[1])
        rv = reg().data_version_service.get(right_data[1])
        if not lv or not lv.source_files or not rv or not rv.source_files:
            QMessageBox.information(self, tr("common.error"), "No source files")
            return
        # 用共同的表(取交集的第一个)
        lf = lv.source_files[0]
        rf = rv.source_files[0]
        if lf.table_name != rf.table_name:
            QMessageBox.information(self, tr("common.error"), f"Table mismatch: {lf.table_name} vs {rf.table_name}")
            return
        pk = self.pk_combo.currentText().strip() or "id"
        config = DiffConfig(
            pk_columns=[pk],
            case_sensitive=self.case_chk.isChecked(),
            trim_whitespace=self.trim_chk.isChecked(),
        )
        # 起 Worker
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # indeterminate
        self.run_btn.setEnabled(False)
        self.result_view.clear()

        self._thread = QThread()
        self._worker = DiffWorker(lf.local_path, rf.local_path, config)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_diff_done)
        self._worker.error.connect(self._on_diff_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.start()

    def _on_diff_done(self, result: dict) -> None:
        self.progress.setVisible(False)
        self.run_btn.setEnabled(True)
        self.stat_left.setText(f"左: {result['total_left']}")
        self.stat_right.setText(f"右: {result['total_right']}")
        self.stat_added.setText(f"+新增: {len(result['only_right'])}")
        self.stat_deleted.setText(f"-删除: {len(result['only_left'])}")
        self.stat_modified.setText(f"~修改: {len(result['modified'])}")
        # 简单文本展示(前 50 行差异)
        lines = [f"=== Diff Summary ==="]
        lines.append(f"Left: {result['total_left']} rows | Right: {result['total_right']} rows")
        lines.append(f"Added: {len(result['only_right'])} | Removed: {len(result['only_left'])} | Modified: {len(result['modified'])}")
        lines.append(f"Unchanged: {result['unchanged_count']}")
        lines.append("")
        if result['only_right']:
            lines.append("=== Added (first 20) ===")
            for r in result['only_right'][:20]:
                lines.append(f"+ {r['key']}: {r['right_row']}")
        if result['only_left']:
            lines.append("")
            lines.append("=== Removed (first 20) ===")
            for r in result['only_left'][:20]:
                lines.append(f"- {r['key']}: {r['left_row']}")
        if result['modified']:
            lines.append("")
            lines.append("=== Modified (first 20) ===")
            for r in result['modified'][:20]:
                lines.append(f"~ {r['key']}:")
                for cd in r['cell_diffs']:
                    lines.append(f"    {cd['col']}: {cd['left']} → {cd['right']}")
        self.result_view.setPlainText("\n".join(lines))
        show_toast(tr("diff.done"), "success")

    def _on_diff_error(self, msg: str) -> None:
        self.progress.setVisible(False)
        self.run_btn.setEnabled(True)
        QMessageBox.warning(self, tr("common.error"), msg)

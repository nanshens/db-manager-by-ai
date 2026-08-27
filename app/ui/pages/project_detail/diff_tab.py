"""Diff Tab — 表数据对比(M4 增强版)
- 数据源支持: 版本 / 单文件(临时,不需保存为版本)
- 选完两边后弹表匹配面板(A 表 → B 表,默认按表名同名匹配,未匹配可手动选或跳过)
- 多对表并行对比,结果在 QTabWidget 中分类展示
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QFrame, QComboBox, QCheckBox,
    QPlainTextEdit, QListWidget, QListWidgetItem, QMessageBox, QWidget, QFileDialog,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QTabWidget, QSizePolicy,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.ui.widgets import EmptyState, show_toast
from app.services.registry import reg
from app.core.file_reader import detect_format
from app.core.diff_engine import DiffEngine, DiffConfig


# "跳过"映射的占位 data
SKIP_KEY = "__skip__"
UPLOAD_KEY = "__upload__"


@dataclass
class DiffSource:
    """对比源 — 单个版本 或 单个文件"""
    kind: str                # "version" / "file"
    label: str
    # version
    version_id: Optional[int] = None
    files: dict[str, str] = field(default_factory=dict)   # {table_name: path}
    # file
    path: Optional[str] = None
    table_name: Optional[str] = None


class DiffPairWorker(QObject):
    """一对表的 diff — 在 worker thread 跑"""
    finished = Signal(dict)   # {"a_table": str, "b_table": str, "result": dict}
    error = Signal(str, str)  # (a_table, error_msg)

    def __init__(self, a_path: str, b_path: str, a_table: str, b_table: str,
                 config: DiffConfig):
        super().__init__()
        self.a_path = a_path
        self.b_path = b_path
        self.a_table = a_table
        self.b_table = b_table
        self.config = config

    def run(self):
        try:
            engine = DiffEngine()
            res = engine.compute(self.a_path, self.b_path, self.config)
            self.finished.emit({
                "a_table": self.a_table,
                "b_table": self.b_table,
                "result": res.to_dict(),
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(self.a_table, str(e))


class MappingRow(QFrame):
    """一对表匹配行: A 表名 → B 表名下拉(可跳过)"""
    def __init__(self, a_table: str, b_options: list[str], default_b: Optional[str] = None):
        super().__init__()
        self.setFrameShape(QFrame.Shape.NoFrame)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 4, 0, 4)
        h.setSpacing(8)

        # A 表(只读)
        a_lbl = QLabel(f"📄 {a_table}")
        a_lbl.setMinimumWidth(160)
        a_lbl.setStyleSheet("font-weight: 600;")
        h.addWidget(a_lbl)

        h.addWidget(QLabel("→"))

        # B 表(下拉)
        self.b_combo = QComboBox()
        self.b_combo.addItem(tr("diff.mapping.skip"), SKIP_KEY)
        for b in b_options:
            self.b_combo.addItem(b, b)
        if default_b and default_b in b_options:
            self.b_combo.setCurrentText(default_b)
        self.b_combo.setMinimumWidth(180)
        h.addWidget(self.b_combo)

        h.addStretch()

    def get_b(self) -> Optional[str]:
        """返回选中的 B 表名,None = 跳过"""
        data = self.b_combo.currentData()
        if data == SKIP_KEY or not data:
            return None
        return data


class DiffTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_id: Optional[int] = None
        self._left: Optional[DiffSource] = None
        self._right: Optional[DiffSource] = None
        # 上传的文件(临时,本 tab 内,不算版本)
        self._uploaded: dict[str, DiffSource] = {}  # {key(label): source}
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ===== 顶部:数据源选择 (A | VS | B 横排) =====
        src = QFrame()
        src.setObjectName("Card")
        sl = QVBoxLayout(src)
        sl.setContentsMargins(16, 12, 16, 12)
        sl.setSpacing(8)

        # 标题
        src_title = QLabel("📊 " + tr("diff.source.title"))
        src_title.setStyleSheet("font-size: 14px; font-weight: 700;")
        sl.addWidget(src_title)

        # A | VS | B
        row = QHBoxLayout()
        row.setSpacing(12)
        # A 列
        a_col = QVBoxLayout()
        a_col.setSpacing(4)
        a_lbl = QLabel(tr("diff.source_a"))
        a_lbl.setObjectName("Muted")
        a_col.addWidget(a_lbl)
        a_input = QHBoxLayout()
        a_input.setSpacing(4)
        self.left_combo = QComboBox()
        self.left_combo.setMinimumWidth(260)
        self.left_combo.currentIndexChanged.connect(self._on_left_changed)
        a_input.addWidget(self.left_combo, 1)
        left_browse = QPushButton(tr("diff.browse_file"))
        left_browse.setObjectName("Ghost")
        left_browse.setIcon(qta.icon("mdi6.file-plus-outline", color="#94a3b8"))
        left_browse.setToolTip(tr("diff.browse_file.tip"))
        left_browse.clicked.connect(lambda: self._browse_upload("left"))
        a_input.addWidget(left_browse)
        a_col.addLayout(a_input)
        row.addLayout(a_col, 1)

        # VS 分隔
        vs_lbl = QLabel("⚔")
        vs_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vs_lbl.setStyleSheet("font-size: 24px; color: #3b82f6; padding: 0 8px;")
        vs_lbl.setMaximumWidth(40)
        row.addWidget(vs_lbl, 0, Qt.AlignmentFlag.AlignBottom)

        # B 列
        b_col = QVBoxLayout()
        b_col.setSpacing(4)
        b_lbl = QLabel(tr("diff.source_b"))
        b_lbl.setObjectName("Muted")
        b_col.addWidget(b_lbl)
        b_input = QHBoxLayout()
        b_input.setSpacing(4)
        self.right_combo = QComboBox()
        self.right_combo.setMinimumWidth(260)
        self.right_combo.currentIndexChanged.connect(self._on_right_changed)
        b_input.addWidget(self.right_combo, 1)
        right_browse = QPushButton(tr("diff.browse_file"))
        right_browse.setObjectName("Ghost")
        right_browse.setIcon(qta.icon("mdi6.file-plus-outline", color="#94a3b8"))
        right_browse.setToolTip(tr("diff.browse_file.tip"))
        right_browse.clicked.connect(lambda: self._browse_upload("right"))
        b_input.addWidget(right_browse)
        b_col.addLayout(b_input)
        row.addLayout(b_col, 1)
        sl.addLayout(row)

        # 空状态提示(两边都没选时)
        self.src_empty_hint = QLabel(tr("diff.source.empty_hint"))
        self.src_empty_hint.setObjectName("Muted")
        self.src_empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.src_empty_hint.setStyleSheet("padding: 8px 0;")
        sl.addWidget(self.src_empty_hint)

        layout.addWidget(src)

        # ===== 中部:表匹配面板 (选完两边才显示) =====
        self.mapping_panel = QFrame()
        self.mapping_panel.setObjectName("Card")
        self.mapping_panel.setVisible(False)
        ml = QVBoxLayout(self.mapping_panel)
        ml.setContentsMargins(16, 12, 16, 12)
        ml.setSpacing(8)

        # 标题行
        title_row = QHBoxLayout()
        title_lbl = QLabel(tr("diff.mapping.title"))
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 700;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        ml.addLayout(title_row)

        # 提示
        self.mapping_hint = QLabel("")
        self.mapping_hint.setObjectName("Muted")
        self.mapping_hint.setWordWrap(True)
        ml.addWidget(self.mapping_hint)

        # 表对容器(动态加 MappingRow)
        self.mapping_container = QWidget()
        self.mapping_layout = QVBoxLayout(self.mapping_container)
        self.mapping_layout.setContentsMargins(0, 0, 0, 0)
        self.mapping_layout.setSpacing(0)
        ml.addWidget(self.mapping_container)

        # 配置行
        cfg_row = QHBoxLayout()
        cfg_row.setSpacing(8)
        cfg_row.addWidget(QLabel(tr("diff.pk")))
        self.pk_combo = QComboBox()
        self.pk_combo.setMinimumWidth(140)
        self.pk_combo.setEditable(True)
        cfg_row.addWidget(self.pk_combo)
        self.case_chk = QCheckBox(tr("diff.case_sensitive"))
        self.trim_chk = QCheckBox(tr("diff.trim"))
        self.trim_chk.setChecked(True)
        cfg_row.addWidget(self.case_chk)
        cfg_row.addWidget(self.trim_chk)
        cfg_row.addStretch()
        self.run_btn = QPushButton(tr("diff.run"))
        self.run_btn.setObjectName("Primary")
        self.run_btn.setIcon(qta.icon("mdi6.play", color="white"))
        self.run_btn.clicked.connect(self._on_run)
        cfg_row.addWidget(self.run_btn)
        ml.addLayout(cfg_row)

        layout.addWidget(self.mapping_panel)

        # ===== 进度 =====
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # ===== 结果区:QTabWidget(概览/新增/删除/修改) =====
        self.result_tabs = QTabWidget()
        self.result_tabs.setDocumentMode(True)
        self.result_tabs.setVisible(False)

        # 概览
        self.overview_view = QPlainTextEdit()
        self.overview_view.setReadOnly(True)
        self.overview_view.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 11px; "
            "background: #0b1220; color: #e2e8f0; border: 1px solid #334155; border-radius: 6px;"
        )
        self.result_tabs.addTab(self.overview_view, tr("diff.result.overview"))

        # 新增 / 删除 / 修改 — 各自一个表格(每行 = 一对表的差异行)
        for kind, label_key in [
            ("added", "diff.result.added"),
            ("removed", "diff.result.removed"),
            ("modified", "diff.result.modified"),
        ]:
            table = QTableWidget(0, 4)
            table.setHorizontalHeaderLabels([
                tr("diff.result.col.pair"),
                tr("diff.result.col.key"),
                tr("diff.result.col.left"),
                tr("diff.result.col.right"),
            ])
            hdr = table.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
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
            from PySide6.QtGui import QFont
            mono = QFont("Consolas")
            mono.setStyleHint(QFont.StyleHint.Monospace)
            table.setFont(mono)
            setattr(self, f"_{kind}_table", table)
            self.result_tabs.addTab(table, tr(label_key))

        layout.addWidget(self.result_tabs, 1)

    # ===== 槽位 / 数据加载 =====

    def retranslate(self) -> None:
        self.run_btn.setText(tr("diff.run"))
        self.case_chk.setText(tr("diff.case_sensitive"))
        self.trim_chk.setText(tr("diff.trim"))
        # result tab titles
        self.result_tabs.setTabText(0, tr("diff.result.overview"))
        self.result_tabs.setTabText(1, tr("diff.result.added"))
        self.result_tabs.setTabText(2, tr("diff.result.removed"))
        self.result_tabs.setTabText(3, tr("diff.result.modified"))

    def set_project(self, project_id: int) -> None:
        self._project_id = project_id
        # 订阅事件总线 — disconnect 可能抛 warning,静默吞掉
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                reg().bus.data_version_changed.disconnect(self.refresh)
            except (TypeError, RuntimeError, Exception):
                pass
        reg().bus.data_version_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        """重新加载版本列表(可能在 diff tab 不可见时被调)"""
        if self._project_id is None:
            return
        # 记住当前选择
        prev_left = self.left_combo.currentData() if self.left_combo.count() else None
        prev_right = self.right_combo.currentData() if self.right_combo.count() else None
        # 重建
        self.left_combo.blockSignals(True)
        self.right_combo.blockSignals(True)
        self.left_combo.clear()
        self.right_combo.clear()
        # placeholder 提示
        self.left_combo.setPlaceholderText(tr("diff.combo.placeholder"))
        self.right_combo.setPlaceholderText(tr("diff.combo.placeholder"))
        # 添加版本
        versions = reg().data_version_service.list_by_project(self._project_id)
        for v in versions:
            label = f"📦 {v.version_name}  ({len(v.source_files)} 表)"
            for combo in (self.left_combo, self.right_combo):
                combo.addItem(label, ("version", v.id))
        # 加上传文件
        for key, src in self._uploaded.items():
            for combo in (self.left_combo, self.right_combo):
                combo.addItem(f"📁 {src.label}", ("file", key))
        # 恢复选择
        if prev_left is not None:
            idx = self.left_combo.findData(prev_left)
            if idx >= 0:
                self.left_combo.setCurrentIndex(idx)
        if prev_right is not None:
            idx = self.right_combo.findData(prev_right)
            if idx >= 0:
                self.right_combo.setCurrentIndex(idx)
        self.left_combo.blockSignals(False)
        self.right_combo.blockSignals(False)
        # 触发一次同步(用户可能从版本 tab 切回来)
        self._on_left_changed(self.left_combo.currentIndex())
        self._on_right_changed(self.right_combo.currentIndex())

    def _browse_upload(self, side: str) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("diff.browse_title"),
            "", "Data files (*.csv *.tsv *.xlsx *.xls);;All files (*)",
        )
        for p in paths:
            fmt = detect_format(p)
            if fmt == "unknown":
                show_toast(f"Unsupported: {os.path.basename(p)}", "error")
                continue
            tname = Path(p).stem
            label = os.path.basename(p)
            # 用 tname 作为 key,防止重复上传同文件
            if tname in self._uploaded and self._uploaded[tname].path == p:
                continue
            self._uploaded[tname] = DiffSource(
                kind="file", label=label, path=p, table_name=tname,
            )
        # 重新填充 combo
        self.refresh()
        # 自动选最后一个上传的文件
        if paths:
            last = Path(paths[-1]).stem
            data = ("file", last)
            for combo, _side in [(self.left_combo, side), (self.right_combo, side)]:
                idx = combo.findData(data)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

    def _on_left_changed(self, _idx: int) -> None:
        self._left = self._get_source(self.left_combo)
        self._refresh_mapping()

    def _on_right_changed(self, _idx: int) -> None:
        self._right = self._get_source(self.right_combo)
        self._refresh_mapping()

    def _get_source(self, combo: QComboBox) -> Optional[DiffSource]:
        data = combo.currentData()
        if not data or (isinstance(data, tuple) and data == ("upload",)):
            return None
        if isinstance(data, tuple) and data[0] == "version":
            v = reg().data_version_service.get(data[1])
            if not v:
                return None
            return DiffSource(
                kind="version", label=v.version_name, version_id=v.id,
                files={f.table_name: f.local_path for f in v.source_files},
            )
        if isinstance(data, tuple) and data[0] == "file":
            return self._uploaded.get(data[1])
        return None

    def _refresh_mapping(self) -> None:
        """选完两边后,生成表匹配行"""
        # 清空旧 rows
        while self.mapping_layout.count():
            item = self.mapping_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # 提示标签:两边都选了才隐藏
        have_left = self._left is not None
        have_right = self._right is not None
        if self.src_empty_hint is not None:
            self.src_empty_hint.setVisible(not (have_left and have_right))

        if not have_left or not have_right:
            self.mapping_panel.setVisible(False)
            return

        a_tables = list(self._left.files.keys() if self._left.kind == "version" else [self._left.table_name])
        b_tables = list(self._right.files.keys() if self._right.kind == "version" else [self._right.table_name])
        # 自动匹配:同名小写
        b_set_lower = {b.lower(): b for b in b_tables}

        # 列出 A 的所有表,每行一个 mapping row
        for a in a_tables:
            default = b_set_lower.get(a.lower())
            row = MappingRow(a, b_tables, default_b=default)
            self.mapping_layout.addWidget(row)

        # 提示
        auto_matched = sum(1 for a in a_tables if a.lower() in b_set_lower)
        self.mapping_hint.setText(
            tr("diff.mapping.hint").format(
                n_a=len(a_tables), n_b=len(b_tables), n_auto=auto_matched,
            )
        )
        # 加载 PK 选项(取 A 表的列)
        if a_tables:
            self._populate_pk_options(a_tables[0])
        # 显示面板
        self.mapping_panel.setVisible(True)
        # 隐藏旧结果
        self.result_tabs.setVisible(False)

    def _populate_pk_options(self, table_name: str) -> None:
        """从表里读列名填充 PK combo"""
        self.pk_combo.clear()
        if not self._project_id:
            return
        try:
            t = reg().table_service.get_by_name(self._project_id, table_name)
            if t:
                cols = [c.name for c in t.columns]
                self.pk_combo.addItems(cols)
        except Exception:
            pass

    # ===== 跑对比 =====
    def _on_run(self) -> None:
        if not self._left or not self._right:
            QMessageBox.information(self, tr("common.error"), "Select both sources")
            return
        # 收集 (a, b) 对
        pairs: list[tuple[str, str, str, str]] = []  # (a_table, a_path, b_table, b_path)
        a_files = self._left.files if self._left.kind == "version" else {self._left.table_name: self._left.path}
        b_files = self._right.files if self._right.kind == "version" else {self._right.table_name: self._right.path}
        for i in range(self.mapping_layout.count()):
            row_w = self.mapping_layout.itemAt(i).widget()
            if not isinstance(row_w, MappingRow):
                continue
            a_table = row_w.findChild(QLabel).text().replace("📄 ", "").strip()
            b_table = row_w.get_b()
            if not b_table:
                continue
            a_path = a_files.get(a_table)
            b_path = b_files.get(b_table)
            if not a_path or not b_path:
                continue
            if not os.path.exists(a_path) or not os.path.exists(b_path):
                show_toast(f"File missing: {a_table} or {b_table}", "error")
                continue
            pairs.append((a_table, a_path, b_table, b_path))
        if not pairs:
            QMessageBox.information(self, tr("common.error"), tr("diff.error.no_pairs"))
            return

        pk = self.pk_combo.currentText().strip() or "id"
        self._config = DiffConfig(
            pk_columns=[pk],
            case_sensitive=self.case_chk.isChecked(),
            trim_whitespace=self.trim_chk.isChecked(),
        )
        self._pairs = pairs
        self._results: list[dict] = []
        self._error_pairs: list[tuple[str, str]] = []
        self._pair_index = 0

        self.progress.setVisible(True)
        self.progress.setRange(0, len(pairs))
        self.progress.setValue(0)
        self.run_btn.setEnabled(False)
        self.result_tabs.setVisible(True)
        # 清空
        self.overview_view.clear()
        for t in (self._added_table, self._removed_table, self._modified_table):
            t.setRowCount(0)

        # 启动 worker
        self._thread = QThread()
        self._worker = DiffPairWorker(*self._flat_pair(pairs[0]), self._config)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_pair_done)
        self._worker.error.connect(self._on_pair_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.start()

    def _flat_pair(self, p):
        """((a_table, a_path, b_table, b_path)) → (a_path, b_path, a_table, b_table)"""
        return p[1], p[2], p[0], p[3]

    def _on_pair_done(self, payload: dict) -> None:
        self._results.append(payload)
        self.progress.setValue(self.progress.value() + 1)
        # 启动下一对
        self._pair_index += 1
        if self._pair_index < len(self._pairs):
            nxt = self._pairs[self._pair_index]
            self._thread = QThread()
            self._worker = DiffPairWorker(*self._flat_pair(nxt), self._config)
            self._worker.moveToThread(self._thread)
            self._thread.started.connect(self._worker.run)
            self._worker.finished.connect(self._on_pair_done)
            self._worker.error.connect(self._on_pair_error)
            self._worker.finished.connect(self._thread.quit)
            self._worker.error.connect(self._thread.quit)
            self._thread.start()
        else:
            # 全部完成
            self.progress.setVisible(False)
            self.run_btn.setEnabled(True)
            self._render_results()
            show_toast(tr("diff.done"), "success")

    def _on_pair_error(self, a_table: str, msg: str) -> None:
        self._error_pairs.append((a_table, msg))
        self.progress.setValue(self.progress.value() + 1)
        self._pair_index += 1
        if self._pair_index < len(self._pairs):
            nxt = self._pairs[self._pair_index]
            self._thread = QThread()
            self._worker = DiffPairWorker(*self._flat_pair(nxt), self._config)
            self._worker.moveToThread(self._thread)
            self._thread.started.connect(self._worker.run)
            self._worker.finished.connect(self._on_pair_done)
            self._worker.error.connect(self._on_pair_error)
            self._worker.finished.connect(self._thread.quit)
            self._worker.error.connect(self._thread.quit)
            self._thread.start()
        else:
            self.progress.setVisible(False)
            self.run_btn.setEnabled(True)
            self._render_results()

    def _render_results(self) -> None:
        """把 results 渲染到 4 个 tab"""
        # 概览
        lines = []
        total_added = total_removed = total_modified = 0
        for r in self._results:
            res = r["result"]
            pair = f"{r['a_table']} → {r['b_table']}"
            lines.append(f"=== {pair} ===")
            lines.append(f"  Left rows: {res['total_left']}  Right rows: {res['total_right']}")
            lines.append(f"  +Added: {len(res['only_right'])}  -Removed: {len(res['only_left'])}  ~Modified: {len(res['modified'])}")
            lines.append(f"  Unchanged: {res['unchanged_count']}")
            lines.append("")
            total_added += len(res["only_right"])
            total_removed += len(res["only_left"])
            total_modified += len(res["modified"])
        # 错误
        for a, msg in self._error_pairs:
            lines.append(f"=== ❌ {a} ===")
            lines.append(f"  Error: {msg}")
            lines.append("")
        if self._pairs:
            lines.insert(0, f"========= TOTAL ({len(self._results)} pairs ok, {len(self._error_pairs)} error) =========")
            lines.insert(1, f"+Added: {total_added}  -Removed: {total_removed}  ~Modified: {total_modified}")
            lines.insert(2, "")
        self.overview_view.setPlainText("\n".join(lines))
        # tab 标题里加数字
        self.result_tabs.setTabText(0, tr("diff.result.overview"))
        self.result_tabs.setTabText(1, f"{tr('diff.result.added')} ({total_added})")
        self.result_tabs.setTabText(2, f"{tr('diff.result.removed')} ({total_removed})")
        self.result_tabs.setTabText(3, f"{tr('diff.result.modified')} ({total_modified})")
        # 填 3 张表
        for r in self._results:
            res = r["result"]
            pair = f"{r['a_table']} → {r['b_table']}"
            for row in res["only_right"]:
                self._append_table_row(self._added_table, pair, row["key"], "", str(row.get("right_row", "")))
            for row in res["only_left"]:
                self._append_table_row(self._removed_table, pair, row["key"], str(row.get("left_row", "")), "")
            for row in res["modified"]:
                cell_str = "; ".join(
                    f"{cd['col']}: {cd['left']} → {cd['right']}" for cd in row["cell_diffs"]
                )
                self._append_table_row(self._modified_table, pair, row["key"], str(row.get("left_row", "")), cell_str)

    def _append_table_row(self, table: QTableWidget, pair: str, key, left: str, right: str) -> None:
        r = table.rowCount()
        table.insertRow(r)
        table.setItem(r, 0, QTableWidgetItem(pair))
        table.setItem(r, 1, QTableWidgetItem(str(key)))
        table.setItem(r, 2, QTableWidgetItem(left))
        table.setItem(r, 3, QTableWidgetItem(right))

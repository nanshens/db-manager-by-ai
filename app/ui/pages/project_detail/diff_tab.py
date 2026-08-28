"""Diff Tab — 数据对比(M5 重构)

设计:
- 左右各一个数据源列表(SourcePanel),支持多源:
    📄 文件 / 📁 目录 / 📊 Excel 解析(用模板)/ 📦 数据版本
- 表匹配: 列出两边所有虚拟表,自动按同名匹配,未匹配可手动选
- 匹配判别条件: PK + 模式(全列相等 / 指定列相等)
- 结果: 按对列表 + 每对详情(文件内容左右双列 / 差分 / 缺数据 / 多数据)
- 判别条件保存到 app config,下次默认用
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from PySide6.QtCore import Qt, QThreadPool, QRunnable, Signal, QObject
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QFrame, QComboBox, QCheckBox,
    QPlainTextEdit, QListWidget, QListWidgetItem, QMessageBox, QWidget, QFileDialog,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QTabWidget, QSizePolicy, QMenu, QInputDialog, QDialog, QFormLayout,
    QSplitter,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.ui.widgets import EmptyState, show_toast
from app.services.registry import reg
from app.core.file_reader import detect_format
from app.core.diff_engine import DiffEngine, DiffConfig
from app.core.excel_parser import parse_excel
from app.repos.excel_template_repo import ExcelTemplate
from app import config as app_config


# ============================================================
# 数据模型
# ============================================================

# source kind
SK_VERSION = "version"
SK_FILE = "file"
SK_DIR = "directory"
SK_EXCEL = "excel"


@dataclass
class DiffSource:
    """一个数据源 — 统一抽象"""
    kind: str                     # SK_VERSION / SK_FILE / SK_DIR / SK_EXCEL
    label: str                    # 显示名
    # version
    version_id: Optional[int] = None
    # file / dir
    path: Optional[str] = None
    # excel
    excel_path: Optional[str] = None
    template_id: Optional[int] = None
    template_name: Optional[str] = None
    # 抽出的表:{table_name: file_path} — 加载时填
    tables: dict[str, str] = field(default_factory=dict)


@dataclass
class TableMatch:
    """一对匹配的表"""
    a_table: str
    a_source_label: str
    a_path: str
    b_table: str
    b_source_label: str
    b_path: str


# ============================================================
# Worker: 在 QThreadPool 跑一对表的 diff
# ============================================================

class _WorkerSignals(QObject):
    finished = Signal(dict)    # {"match": TableMatch dict, "result": dict}
    error = Signal(str, str)   # (a_table, error_msg)


class DiffPairWorker(QRunnable):
    def __init__(self, match: TableMatch, config: DiffConfig):
        super().__init__()
        self.match = match
        self.config = config
        self.signals = _WorkerSignals()

    def run(self):
        try:
            engine = DiffEngine()
            res, left_rows, right_rows, common_cols = engine.compute(
                self.match.a_path, self.match.b_path, self.config
            )
            self.signals.finished.emit({
                "match": {
                    "a_table": self.match.a_table,
                    "a_source_label": self.match.a_source_label,
                    "a_path": self.match.a_path,
                    "b_table": self.match.b_table,
                    "b_source_label": self.match.b_source_label,
                    "b_path": self.match.b_path,
                },
                "result": res.to_dict(),
                "left_rows": left_rows,
                "right_rows": right_rows,
                "common_cols": common_cols,
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.signals.error.emit(self.match.a_table, str(e))


# ============================================================
# SourcePanel — 一侧数据源列表(支持多源 + 4 种类型)
# ============================================================

class SourcePanel(QFrame):
    """一侧数据源 — QListWidget + 4 个添加按钮 + 删除按钮"""

    changed = Signal()  # 源列表变化时 emit

    def __init__(self, title: str, side: str, parent=None):
        super().__init__(parent)
        self._side = side  # "left" / "right"
        self._sources: list[DiffSource] = []
        self._build(title)

    def _build(self, title: str):
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(8)

        # 标题
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 700;")
        v.addWidget(title_lbl)

        # 源列表
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list.setStyleSheet(
            "QListWidget {"
            "  background: #0b1220; color: #e2e8f0;"
            "  border: 1px solid #334155; border-radius: 6px;"
            "}"
            "QListWidget::item { padding: 6px 10px; border-bottom: 1px solid #1e293b; }"
            "QListWidget::item:selected { background: #1d4ed8; color: white; }"
        )
        v.addWidget(self.list, 1)

        # 添加按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        for icon, label, slot in [
            ("mdi6.file-plus-outline", "diff.src.add_file", lambda: self._add_file()),
            ("mdi6.folder-plus-outline", "diff.src.add_dir", lambda: self._add_dir()),
            ("mdi6.file-table-box-outline", "diff.src.add_excel", lambda: self._add_excel()),
            ("mdi6.package-variant", "diff.src.add_version", lambda: self._add_version()),
        ]:
            btn = QPushButton(qta.icon(icon, color="#94a3b8"), "")
            btn.setToolTip(tr(label))
            btn.setFixedSize(32, 32)
            btn.setObjectName("Ghost")
            btn.clicked.connect(slot)
            btn_row.addWidget(btn)
        btn_row.addStretch()
        # 移除按钮
        del_btn = QPushButton(qta.icon("mdi6.trash-can-outline", color="#ef4444"), "")
        del_btn.setToolTip(tr("action.delete"))
        del_btn.setFixedSize(32, 32)
        del_btn.setObjectName("Ghost")
        del_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(del_btn)
        # 清空
        clr_btn = QPushButton(qta.icon("mdi6.broom", color="#94a3b8"), "")
        clr_btn.setToolTip(tr("diff.src.clear"))
        clr_btn.setFixedSize(32, 32)
        clr_btn.setObjectName("Ghost")
        clr_btn.clicked.connect(self._clear)
        btn_row.addWidget(clr_btn)
        v.addLayout(btn_row)

        # 汇总
        self.summary = QLabel("")
        self.summary.setObjectName("Muted")
        self.summary.setStyleSheet("font-size: 11px;")
        v.addWidget(self.summary)

    # ----- 添加源 -----

    def _add_file(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("diff.browse_title"),
            "", "Data files (*.csv *.tsv *.xlsx *.xls);;All files (*)",
        )
        for p in paths:
            if detect_format(p) == "unknown":
                show_toast(f"Unsupported: {os.path.basename(p)}", "error")
                continue
            tname = Path(p).stem
            src = DiffSource(
                kind=SK_FILE, label=os.path.basename(p), path=p,
                tables={tname: p},
            )
            self._add_source(src)

    def _add_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("diff.src.add_dir"))
        if not d:
            return
        tables = {}
        for name in sorted(os.listdir(d)):
            full = os.path.join(d, name)
            if not os.path.isfile(full):
                continue
            if detect_format(full) == "unknown":
                continue
            tname = Path(full).stem
            tables[tname] = full
        if not tables:
            show_toast(f"No data files in {os.path.basename(d)}", "warning")
            return
        src = DiffSource(
            kind=SK_DIR, label=f"📁 {os.path.basename(d)}", path=d,
            tables=tables,
        )
        self._add_source(src)

    def _add_excel(self) -> None:
        # 1. 选模板
        templates = reg().excel_template_service.list(project_id=self._get_project_id())
        if not templates:
            QMessageBox.information(self, tr("common.info"), tr("diff.src.no_template"))
            return
        names = [t.template_name for t in templates]
        name, ok = QInputDialog.getItem(self, tr("diff.src.choose_template"), "", names, 0, False)
        if not ok:
            return
        tpl = next(t for t in templates if t.template_name == name)
        # 2. 选 Excel 文件
        path, _ = QFileDialog.getOpenFileName(
            self, tr("diff.src.choose_excel"),
            "", "Excel files (*.xlsx *.xls);;All files (*)",
        )
        if not path:
            return
        # 3. 解析
        results, errors = parse_excel(path, tpl)
        if errors:
            show_toast("\n".join(errors[:3]), "warning")
        tables = {}
        for r in results:
            if not r.error:
                # 把解析结果保存为临时 CSV 供 diff 用
                tmp_csv = self._excel_to_tmp_csv(path, r)
                if tmp_csv:
                    tables[r.table_name] = tmp_csv
        if not tables:
            show_toast("No tables parsed successfully", "error")
            return
        src = DiffSource(
            kind=SK_EXCEL, label=f"📊 {os.path.basename(path)} [{tpl.template_name}]",
            excel_path=path, template_id=tpl.id, template_name=tpl.template_name,
            tables=tables,
        )
        self._add_source(src)

    def _excel_to_tmp_csv(self, excel_path: str, parse_result) -> Optional[str]:
        """把 ParseResult 里的表数据写到临时 CSV 供 diff 用"""
        try:
            import tempfile
            import polars as pl
            df = pl.read_excel(excel_path, sheet_name=parse_result.sheet_name)
            # 切 header_row / data_start_row
            if df.height < 1:
                return None
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".csv", delete=False, encoding="utf-8", newline=""
            )
            tmp_path = tmp.name
            tmp.close()
            df.write_csv(tmp_path)
            return tmp_path
        except Exception as e:
            show_toast(f"Convert error: {e}", "error")
            return None

    def _add_version(self) -> None:
        pid = self._get_project_id()
        if not pid:
            return
        versions = reg().data_version_service.list_by_project(pid)
        if not versions:
            QMessageBox.information(self, tr("common.info"), tr("diff.src.no_version"))
            return
        names = [v.version_name for v in versions]
        name, ok = QInputDialog.getItem(self, tr("diff.src.choose_version"), "", names, 0, False)
        if not ok:
            return
        v_obj = next(v for v in versions if v.version_name == name)
        tables = {f.table_name: f.local_path for f in v_obj.source_files}
        src = DiffSource(
            kind=SK_VERSION, label=f"📦 {v_obj.version_name}  ({len(tables)} 表)",
            version_id=v_obj.id, tables=tables,
        )
        self._add_source(src)

    def _get_project_id(self) -> Optional[int]:
        # 从父 widget 链找 project_id
        p = self.parent()
        while p:
            if hasattr(p, "_project_id") and getattr(p, "_project_id", None):
                return p._project_id
            p = p.parent()
        return None

    def _add_source(self, src: DiffSource) -> None:
        # 同一源不能加两次(用 label + path 判重)
        for s in self._sources:
            if s.kind == src.kind and s.path == src.path and s.version_id == src.version_id \
                    and s.excel_path == src.excel_path and s.template_id == src.template_id:
                return
        self._sources.append(src)
        item = QListWidgetItem(src.label)
        item.setData(Qt.ItemDataRole.UserRole, len(self._sources) - 1)
        # tooltip 列出所有表
        if len(src.tables) <= 5:
            item.setToolTip("\n".join(f"📄 {t}" for t in src.tables))
        else:
            tip = "\n".join(f"📄 {t}" for t in list(src.tables)[:5])
            tip += f"\n... (+{len(src.tables) - 5} more)"
            item.setToolTip(tip)
        self.list.addItem(item)
        self._refresh_summary()
        self.changed.emit()

    def _remove_selected(self) -> None:
        rows = sorted({i.row() for i in self.list.selectedIndexes()}, reverse=True)
        if not rows:
            return
        for r in rows:
            del self._sources[r]
            self.list.takeItem(r)
        # 重新设置 user role(因为 index 变了)
        for i in range(self.list.count()):
            self.list.item(i).setData(Qt.ItemDataRole.UserRole, i)
        self._refresh_summary()
        self.changed.emit()

    def _clear(self) -> None:
        if not self._sources:
            return
        self._sources.clear()
        self.list.clear()
        self._refresh_summary()
        self.changed.emit()

    def _refresh_summary(self) -> None:
        n_src = len(self._sources)
        n_tbl = sum(len(s.tables) for s in self._sources)
        if n_src == 0:
            self.summary.setText(tr("diff.src.summary.empty"))
        else:
            self.summary.setText(
                tr("diff.src.summary").format(n_src=n_src, n_tbl=n_tbl)
            )

    def get_sources(self) -> list[DiffSource]:
        return self._sources

    def all_tables(self) -> dict[str, tuple[str, str]]:
        """合并所有 source 的 tables: {table_name: (path, source_label)}"""
        out: dict[str, tuple[str, str]] = {}
        for s in self._sources:
            for t, p in s.tables.items():
                # 同名表用第一个(或最后一个,看具体逻辑)
                if t not in out:
                    out[t] = (p, s.label)
        return out


# ============================================================
# MappingPanel — 表匹配(A 表 → B 表),每行独立判别条件
# ============================================================

# 预设存取 key(QSettings)
_PRESET_PREFIX = "diff/presets/"


def list_presets() -> list[str]:
    """返回所有保存的预设名"""
    from app.config import settings
    keys = settings().allKeys()
    names = []
    for k in keys:
        if k.startswith(_PRESET_PREFIX):
            n = k[len(_PRESET_PREFIX):]
            if n:
                names.append(n)
    return names


def get_preset(name: str) -> Optional[dict]:
    from app.config import settings
    raw = settings().value(_PRESET_PREFIX + name, "", type=str)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def save_preset(name: str, config: dict) -> None:
    from app.config import settings
    settings().setValue(_PRESET_PREFIX + name, json.dumps(config, ensure_ascii=False))


def delete_preset(name: str) -> None:
    from app.config import settings
    settings().remove(_PRESET_PREFIX + name)


class MappingRow(QFrame):
    """一对表匹配: A 表 → B 表(下拉,可跳过) + 单行配置(无展开/无 PK)"""

    def __init__(self, a_table: str, a_label: str, a_columns: list[str],
                 b_options: list[tuple[str, str]],
                 default_b: Optional[str] = None):
        super().__init__()
        self._a_table = a_table
        self._a_columns = a_columns
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "MappingRow { background: #0f172a; border: 1px solid #1e293b;"
            "  border-radius: 6px; margin: 2px; }"
        )

        h = QHBoxLayout(self)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(6)

        # A 表名(加宽,放更多空间)
        a_lbl = QLabel(f"📄 <b>{a_table}</b>")
        a_lbl.setTextFormat(Qt.TextFormat.RichText)
        a_lbl.setMinimumWidth(180)
        a_lbl.setMaximumWidth(240)
        a_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        a_lbl.setToolTip(f"{a_table}\n来源: {a_label}")
        h.addWidget(a_lbl)

        h.addWidget(QLabel("→"))

        # B 表下拉(加宽)
        self.b_combo = QComboBox()
        self.b_combo.addItem(tr("diff.mapping.skip"), None)
        for tn, sl in b_options:
            self.b_combo.addItem(tn, tn)
        if default_b:
            for i in range(self.b_combo.count()):
                if self.b_combo.itemData(i) == default_b:
                    self.b_combo.setCurrentIndex(i)
                    break
        self.b_combo.setMinimumWidth(180)
        self.b_combo.setMaximumWidth(240)
        self.b_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        h.addWidget(self.b_combo)

        # 分隔
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #1e293b;")
        h.addWidget(sep)

        # 判别模式(紧凑)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(tr("diff.match_mode.all"), "all")
        self.mode_combo.addItem(tr("diff.match_mode.selected"), "selected")
        self.mode_combo.setMinimumWidth(80)
        self.mode_combo.setMaximumWidth(100)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        h.addWidget(self.mode_combo)

        # 选列按钮(只在 mode=selected 时启用)
        self.cols_btn = QPushButton(tr("diff.row.pick_cols"))
        self.cols_btn.setObjectName("Ghost")
        self.cols_btn.clicked.connect(self._pick_cols)
        self.cols_btn.setMinimumWidth(72)
        h.addWidget(self.cols_btn)

        # 区分大小写 / trim(默认 false)
        self.case_chk = QCheckBox(tr("diff.row.case"))
        self.trim_chk = QCheckBox(tr("diff.row.trim"))
        h.addWidget(self.case_chk)
        h.addWidget(self.trim_chk)

        h.addStretch()

        # 预设下拉
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(100)
        self.preset_combo.setMaximumWidth(140)
        self._refresh_presets()
        self.preset_combo.currentIndexChanged.connect(self._on_preset_chosen)
        h.addWidget(self.preset_combo)
        # 保存预设
        save_btn = QPushButton(qta.icon("mdi6.content-save-outline", color="#22c55e"), "")
        save_btn.setFixedSize(26, 26)
        save_btn.setObjectName("Ghost")
        save_btn.setToolTip(tr("diff.row.save_preset"))
        save_btn.clicked.connect(self._save_preset)
        h.addWidget(save_btn)
        # 删除预设
        del_btn = QPushButton(qta.icon("mdi6.delete-outline", color="#ef4444"), "")
        del_btn.setFixedSize(26, 26)
        del_btn.setObjectName("Ghost")
        del_btn.setToolTip(tr("diff.row.delete_preset"))
        del_btn.clicked.connect(self._delete_preset)
        h.addWidget(del_btn)

        # 内部状态
        self._selected_cols: list[str] = []
        self._on_mode_changed()

    def _on_mode_changed(self) -> None:
        mode = self.mode_combo.currentData()
        self.cols_btn.setEnabled(mode == "selected")

    def _pick_cols(self) -> None:
        if not self._a_columns:
            return
        dlg = _ColumnPickerDialog(self._a_columns, self._selected_cols, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            self._selected_cols = dlg.get_selected()
            if self._selected_cols:
                self.cols_btn.setText(f"{tr('diff.row.pick_cols')} ({len(self._selected_cols)})")
            else:
                self.cols_btn.setText(tr("diff.row.pick_cols"))

    def _refresh_presets(self) -> None:
        cur = self.preset_combo.currentData() if hasattr(self, "preset_combo") else None
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem(tr("diff.row.preset.none"), None)
        for n in list_presets():
            self.preset_combo.addItem(n, n)
        if cur:
            idx = self.preset_combo.findData(cur)
            if idx >= 0:
                self.preset_combo.setCurrentIndex(idx)
        self.preset_combo.blockSignals(False)

    def _on_preset_chosen(self, _idx: int) -> None:
        name = self.preset_combo.currentData()
        if not name:
            return
        p = get_preset(name)
        if not p:
            return
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(p.get("mode", "all")))
        self.case_chk.setChecked(p.get("case_sensitive", False))
        self.trim_chk.setChecked(p.get("trim", False))
        self._selected_cols = list(p.get("cols", []))
        if self._selected_cols:
            self.cols_btn.setText(f"{tr('diff.row.pick_cols')} ({len(self._selected_cols)})")
        else:
            self.cols_btn.setText(tr("diff.row.pick_cols"))

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(
            self, tr("diff.row.save_preset"),
            tr("diff.row.save_preset.name"),
            text=f"{self._a_table}_default",
        )
        if not ok or not name.strip():
            return
        config = {
            "a_table": self._a_table,
            "mode": self.mode_combo.currentData(),
            "cols": list(self._selected_cols),
            "case_sensitive": self.case_chk.isChecked(),
            "trim": self.trim_chk.isChecked(),
        }
        save_preset(name.strip(), config)
        if self.parent():
            for r in getattr(self.parent(), "_rows", []):
                r._refresh_presets()
        show_toast(tr("diff.row.save_preset.ok").format(name=name), "success")

    def _delete_preset(self) -> None:
        name = self.preset_combo.currentData()
        if not name:
            return
        if QMessageBox.question(
            self, tr("common.confirm"),
            tr("diff.row.delete_preset.confirm").format(name=name),
        ) == QMessageBox.StandardButton.Yes:
            delete_preset(name)
            if self.parent():
                for r in getattr(self.parent(), "_rows", []):
                    r._refresh_presets()

    def get_match(self, a_path: str, a_label: str,
                  b_tables: dict[str, tuple[str, str]]) -> Optional[tuple[TableMatch, DiffConfig]]:
        b_tn = self.b_combo.currentData()
        if not b_tn:
            return None
        b_path, b_label = b_tables[b_tn]
        mode = self.mode_combo.currentData()
        compare_cols = self._selected_cols if mode == "selected" else None
        if mode == "selected" and not compare_cols:
            return None
        cfg = DiffConfig(
            compare_columns=compare_cols,
            case_sensitive=self.case_chk.isChecked(),
            trim_whitespace=self.trim_chk.isChecked(),
        )
        return (TableMatch(
            a_table=self._a_table, a_source_label=a_label, a_path=a_path,
            b_table=b_tn, b_source_label=b_label, b_path=b_path,
        ), cfg)


class _ColumnPickerDialog(QDialog):
    """多选列对话框(点击行/checkbox 都能切换)"""

    def __init__(self, columns: list[str], selected: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("diff.col_picker.title"))
        self.resize(360, 520)
        self._build(columns, selected)

    def _build(self, columns: list[str], selected: list[str]):
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(8)
        v.addWidget(QLabel(tr("diff.col_picker.tip")))
        # 全选/全不选
        btn_row = QHBoxLayout()
        all_btn = QPushButton(tr("diff.col_picker.all"))
        all_btn.clicked.connect(lambda: self._set_all(True))
        none_btn = QPushButton(tr("diff.col_picker.none"))
        none_btn.clicked.connect(lambda: self._set_all(False))
        btn_row.addWidget(all_btn)
        btn_row.addWidget(none_btn)
        btn_row.addStretch()
        v.addLayout(btn_row)
        # 列表
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        # 关键:行点击触发切换
        self.list.itemClicked.connect(self._on_item_clicked)
        sel_set = set(selected)
        self._items: list[QCheckBox] = []
        self._list_items: list[QListWidgetItem] = []
        for c in columns:
            cb = QCheckBox(c)
            cb.setChecked(c in sel_set)
            self._items.append(cb)
            item = QListWidgetItem(self.list)
            self._list_items.append(item)
            self.list.addItem(item)
            self.list.setItemWidget(item, cb)
        v.addWidget(self.list, 1)
        # 按钮
        ok_btn = QPushButton(tr("action.ok"))
        ok_btn.setObjectName("Primary")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(tr("action.cancel"))
        cancel_btn.setObjectName("Ghost")
        cancel_btn.clicked.connect(self.reject)
        btn_row2 = QHBoxLayout()
        btn_row2.addStretch()
        btn_row2.addWidget(cancel_btn)
        btn_row2.addWidget(ok_btn)
        v.addLayout(btn_row2)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """点击列表行 → 切换对应 checkbox"""
        idx = self.list.row(item)
        if 0 <= idx < len(self._items):
            self._items[idx].setChecked(not self._items[idx].isChecked())

    def _set_all(self, checked: bool) -> None:
        for cb in self._items:
            cb.setChecked(checked)

    def get_selected(self) -> list[str]:
        return [cb.text() for cb in self._items if cb.isChecked()]


class MappingPanel(QFrame):
    """表匹配面板 — 每行独立配置"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[MappingRow] = []
        self._build()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(4)

        title = QLabel(tr("diff.mapping.title"))
        title.setStyleSheet("font-size: 13px; font-weight: 700;")
        v.addWidget(title)

        self.hint = QLabel("")
        self.hint.setObjectName("Muted")
        self.hint.setWordWrap(True)
        v.addWidget(self.hint)

        # 表对容器
        self.container = QWidget()
        self.layout_ = QVBoxLayout(self.container)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.layout_.setSpacing(0)
        v.addWidget(self.container, 1)

    def rebuild(self, a_tables: dict[str, tuple[str, str]],
                b_tables: dict[str, tuple[str, str]]) -> None:
        # 清空
        for _ in range(self.layout_.count()):
            item = self.layout_.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._rows.clear()

        if not a_tables:
            self.hint.setText(tr("diff.mapping.empty_left"))
            return
        if not b_tables:
            self.hint.setText(tr("diff.mapping.empty_right"))
            return

        b_options = [(tn, sl) for tn, (path, sl) in b_tables.items()]
        b_set = {tn.lower(): tn for tn in b_tables}

        # 拿 A 表的列(从 project_id 找 table_repo)
        a_columns = self._get_a_columns(a_tables)

        auto = 0
        for a_tn, (a_path, a_label) in a_tables.items():
            default = b_set.get(a_tn.lower())
            if default:
                auto += 1
            row = MappingRow(a_tn, a_label, a_columns, b_options, default_b=default)
            self._rows.append(row)
            self.layout_.addWidget(row)
        # 给 parent 暴露 _rows(预设保存时刷新所有)
        # 已经在 row.parent() 是 MappingPanel

        self.hint.setText(
            tr("diff.mapping.hint").format(
                n_a=len(a_tables), n_b=len(b_tables), n_auto=auto
            )
        )

    def _get_a_columns(self, a_tables: dict[str, tuple[str, str]]) -> list[str]:
        """从 project_id 找第一个 A 表的列名(用做 PK 选项)"""
        # 从父链找 project_id
        p = self.parent()
        pid = None
        while p:
            pid = getattr(p, "_project_id", None)
            if pid:
                break
            p = p.parent()
        if not pid or not a_tables:
            return []
        first_a = list(a_tables.keys())[0]
        tables = reg().table_service.list_by_project(pid)
        for t in tables:
            if t.name == first_a:
                return [c.name for c in t.columns]
        return []

    def collect_match_configs(self, a_tables: dict[str, tuple[str, str]],
                              b_tables: dict[str, tuple[str, str]]
                              ) -> list[tuple[TableMatch, DiffConfig]]:
        out: list[tuple[TableMatch, DiffConfig]] = []
        for i, row in enumerate(self._rows):
            a_tn = list(a_tables.keys())[i] if i < len(a_tables) else None
            if not a_tn:
                continue
            a_path, a_label = a_tables[a_tn]
            mc = row.get_match(a_path, a_label, b_tables)
            if mc:
                out.append(mc)
        return out


# ============================================================
# ResultDialog — 结果弹窗(独立窗口,可最大化)
# ============================================================

class ResultDialog(QDialog):
    """对比结果弹窗 — 5 个 tab 全部用 QTableWidget 真实 cell + 各自文件原始行号"""

    def __init__(self, results: list[dict], errors: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("diff.result.title"))
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMaximizeButtonHint |
            Qt.WindowType.WindowMinimizeButtonHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(1400, 900)
        self._build(results, errors)

    def _build(self, results, errors):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部状态栏
        status = QFrame()
        status.setObjectName("Card")
        st = QHBoxLayout(status)
        st.setContentsMargins(16, 12, 16, 12)
        total_add = sum(len(r["result"]["only_right"]) for r in results)
        total_del = sum(len(r["result"]["only_left"]) for r in results)
        total_unch = sum(r["result"]["unchanged_count"] for r in results)
        n_ok = len(results)
        n_err = len(errors)
        summary_lbl = QLabel(
            tr("diff.result.total").format(
                n_ok=n_ok, n_err=n_err,
                add=total_add, delete=total_del, unchanged=total_unch,
            )
        )
        summary_lbl.setStyleSheet("font-size: 14px; font-weight: 700;")
        st.addWidget(summary_lbl)
        st.addStretch()
        close_btn = QPushButton(tr("action.close"))
        close_btn.setObjectName("Ghost")
        close_btn.clicked.connect(self.accept)
        st.addWidget(close_btn)
        layout.addWidget(status)

        # 主体
        body = QSplitter(Qt.Orientation.Horizontal)
        body.setHandleWidth(1)
        left = QFrame()
        left.setMinimumWidth(220)
        left.setMaximumWidth(360)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8, 8, 8, 8)
        ll.addWidget(QLabel(tr("diff.result.pairs")))
        self.pair_list = QListWidget()
        self.pair_list.itemSelectionChanged.connect(self._on_pair_select)
        ll.addWidget(self.pair_list, 1)
        body.addWidget(left)

        self.detail_tabs = QTabWidget()
        self.detail_tabs.setDocumentMode(True)
        # 5 个 tab 全部 QTableWidget
        self.missing_a_view = self._make_table()
        self.missing_b_view = self._make_table()
        self.content_view = self._make_table()
        self.unchanged_view = self._make_table()
        self.diff_view = self._make_table()
        self.detail_tabs.addTab(self.content_view, tr("diff.result.content"))
        self.detail_tabs.addTab(self.missing_a_view, tr("diff.result.missing_a"))
        self.detail_tabs.addTab(self.missing_b_view, tr("diff.result.missing_b"))
        self.detail_tabs.addTab(self.unchanged_view, tr("diff.result.unchanged"))
        self.detail_tabs.addTab(self.diff_view, tr("diff.result.diff_text"))
        body.addWidget(self.detail_tabs)
        body.setSizes([280, 1120])
        layout.addWidget(body, 1)

        self._results_by_key: dict[str, dict] = {}
        for r in results:
            m = r["match"]
            key = f"{m['a_table']} -> {m['b_table']}"
            self._results_by_key[key] = r
            res = r["result"]
            n_add = len(res["only_right"])
            n_del = len(res["only_left"])
            item = QListWidgetItem(f"OK {key}  (-{n_del}/+{n_add}/={res['unchanged_count']})")
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.pair_list.addItem(item)
        for a, msg in errors:
            item = QListWidgetItem(f"ERR {a}  ({msg[:40]})")
            from PySide6.QtGui import QColor
            item.setForeground(QColor("#ef4444"))
            self.pair_list.addItem(item)
        if self.pair_list.count() > 0:
            self.pair_list.setCurrentRow(0)

    def _make_table(self) -> QTableWidget:
        t = QTableWidget()
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setStyleSheet(
            "QTableWidget { background: #0b1220; color: #e2e8f0;"
            "  border: 1px solid #334155; gridline-color: #1e293b; font-family: Consolas; font-size: 11px; }"
            "QHeaderView::section { background: #1e293b; color: #cbd5e1;"
            "  padding: 8px 12px; font-weight: 600; }"
            "QTableWidget::item { padding: 4px 8px; }"
        )
        return t

    def _on_pair_select(self) -> None:
        items = self.pair_list.selectedItems()
        if not items:
            return
        key = items[0].data(Qt.ItemDataRole.UserRole)
        r = self._results_by_key.get(key)
        if not r:
            return
        self._render_pair(r)

    def _row_key(self, row: dict, common_cols: list[str]) -> tuple:
        return tuple(row.get(c) for c in common_cols)

    def _render_pair(self, r: dict) -> None:
        m = r["match"]
        res = r["result"]
        common_cols = r.get("common_cols", [])
        left_rows = r.get("left_rows", [])
        right_rows = r.get("right_rows", [])
        if not common_cols:
            if left_rows:
                common_cols = list(left_rows[0].keys())
            elif right_rows:
                common_cols = list(right_rows[0].keys())

        n_add = len(res["only_right"])
        n_del = len(res["only_left"])
        n_unch = res["unchanged_count"]
        # tab 标题带数字
        self.detail_tabs.setTabText(0, tr("diff.result.content"))
        self.detail_tabs.setTabText(1, f"{tr('diff.result.missing_a')} ({n_del})")
        self.detail_tabs.setTabText(2, f"{tr('diff.result.missing_b')} ({n_add})")
        self.detail_tabs.setTabText(3, f"{tr('diff.result.unchanged')} ({n_unch})")
        self.detail_tabs.setTabText(4, tr("diff.result.diff_text"))

        # 缺 A
        self._render_diff_table(
            self.missing_a_view,
            [(i + 1, lr) for i, lr in enumerate(left_rows)],
            res["only_left"],
            common_cols,
        )
        # 多 B
        self._render_diff_table(
            self.missing_b_view,
            [(i + 1, rr) for i, rr in enumerate(right_rows)],
            res["only_right"],
            common_cols,
        )
        # 文件内容
        self._render_content_table(left_rows, right_rows, common_cols)
        # 未变
        self._render_summary_table(self.unchanged_view, [
            (tr("diff.result.unchanged"), n_unch),
            (tr("diff.result.missing_a"), n_del),
            (tr("diff.result.missing_b"), n_add),
        ])
        # 差分摘要
        self._render_summary_table(self.diff_view, [
            ("A 表", m["a_table"]),
            ("B 表", m["b_table"]),
            ("A 来源", m.get("a_source_label", "")),
            ("B 来源", m.get("b_source_label", "")),
            ("A 总行数", str(res["total_left"])),
            ("B 总行数", str(res["total_right"])),
            ("缺(A 有 B 无)", str(n_del)),
            ("多(B 有 A 无)", str(n_add)),
            ("未变", str(n_unch)),
        ])

    def _render_diff_table(self, table: QTableWidget,
                           all_rows_with_idx, diff_list,
                           common_cols: list[str]) -> None:
        """把 diff_list 对应到 all_rows 拿到文件原始行号,真实 cell 显示。"""
        table.clear()
        headers = [tr("diff.result.col.row_id")] + list(common_cols)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        # 用 content_key 找匹配的行
        diff_keys = set(tuple(d.get("key", ())) for d in diff_list)
        rows_to_show = []
        for original_idx, row in all_rows_with_idx:
            key = self._row_key(row, common_cols)
            if key in diff_keys:
                rows_to_show.append((original_idx, row))
        rows_to_show = rows_to_show[:1000]
        table.setRowCount(len(rows_to_show))
        from PySide6.QtGui import QColor
        red = QColor("#ef4444")
        muted = QColor("#64748b")
        for r_i, (orig_idx, row) in enumerate(rows_to_show):
            rowid_item = QTableWidgetItem(str(orig_idx))
            rowid_item.setForeground(muted)
            table.setItem(r_i, 0, rowid_item)
            for c_i, c in enumerate(common_cols):
                val = row.get(c)
                item = QTableWidgetItem("" if val is None else str(val))
                item.setForeground(red)
                table.setItem(r_i, 1 + c_i, item)
        if table.columnCount() > 0:
            hdr = table.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            for c in range(1, table.columnCount()):
                hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)

    def _render_content_table(self, left_rows, right_rows, common_cols) -> None:
        """文件内容 tab — 上下两段(A 段 + B 段)。"""
        self.content_view.clear()
        all_cols = common_cols
        if not all_cols:
            if left_rows:
                all_cols = list(left_rows[0].keys())
            elif right_rows:
                all_cols = list(right_rows[0].keys())
        if not all_cols:
            return
        # 列: 行号 | A·col1 | A·col2 | ... | 行号 | B·col1 | B·col2 | ...
        a_col_count = 1 + len(all_cols)
        b_col_count = 1 + len(all_cols)
        total_cols = a_col_count + b_col_count
        total_rows = len(left_rows) + len(right_rows) + 1
        self.content_view.setRowCount(total_rows)
        self.content_view.setColumnCount(total_cols)
        headers = (
            [tr("diff.result.col.row_id")] + [f"A · {c}" for c in all_cols] +
            [tr("diff.result.col.row_id")] + [f"B · {c}" for c in all_cols]
        )
        self.content_view.setHorizontalHeaderLabels(headers)
        from PySide6.QtGui import QColor
        red = QColor("#ef4444")
        green = QColor("#22c55e")
        muted = QColor("#64748b")
        row = 0
        # A 段
        for i, lr in enumerate(left_rows, 1):
            rowid = QTableWidgetItem(str(i))
            rowid.setForeground(muted)
            self.content_view.setItem(row, 0, rowid)
            for c_i, c in enumerate(all_cols):
                val = lr.get(c)
                item = QTableWidgetItem("" if val is None else str(val))
                item.setForeground(green)
                self.content_view.setItem(row, 1 + c_i, item)
            row += 1
        # 分隔
        sep = QTableWidgetItem("--- B 数据 ---")
        sep.setForeground(muted)
        self.content_view.setItem(row, 0, sep)
        for c_i in range(1, total_cols):
            self.content_view.setItem(row, c_i, QTableWidgetItem(""))
        row += 1
        # B 段
        for i, rr in enumerate(right_rows, 1):
            rowid = QTableWidgetItem(str(i))
            rowid.setForeground(muted)
            self.content_view.setItem(row, a_col_count, rowid)
            for c_i, c in enumerate(all_cols):
                val = rr.get(c)
                item = QTableWidgetItem("" if val is None else str(val))
                item.setForeground(red)
                self.content_view.setItem(row, a_col_count + 1 + c_i, item)
            row += 1
        # 列宽
        hdr = self.content_view.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(a_col_count, QHeaderView.ResizeMode.ResizeToContents)
        for c in range(1, a_col_count):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        for c in range(a_col_count + 1, total_cols):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)

    def _render_summary_table(self, table: QTableWidget, rows) -> None:
        """通用:用 QTableWidget 显示 [指标, 值] 二列表。"""
        table.clear()
        table.setColumnCount(2)
        table.setRowCount(len(rows))
        table.setHorizontalHeaderLabels([tr("diff.result.col.metric"), tr("diff.result.col.value")])
        from PySide6.QtGui import QColor
        muted = QColor("#64748b")
        for i, (k, v) in enumerate(rows):
            k_item = QTableWidgetItem(str(k))
            k_item.setForeground(muted)
            table.setItem(i, 0, k_item)
            table.setItem(i, 1, QTableWidgetItem(str(v)))
        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)


# ============================================================
# DiffTab — 主入口
# ============================================================

class DiffTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_id: Optional[int] = None
        self._match_results: list[dict] = []
        self._match_errors: list[tuple[str, str]] = []
        self._pending_matches: list[TableMatch] = []
        self._config: Optional[DiffConfig] = None
        self._build()

    def set_project(self, project_id: int) -> None:
        self._project_id = project_id
        # 订阅事件总线
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                reg().bus.data_version_changed.disconnect(self._on_version_changed)
            except (TypeError, RuntimeError, Exception):
                pass
        reg().bus.data_version_changed.connect(self._on_version_changed)

    def _on_version_changed(self) -> None:
        # 数据源里的版本可能失效 — 简化处理:不动现有源(用户主动管理)
        pass

    def retranslate(self) -> None:
        # 重画简单控件文本
        for btn, key in [
            (self.run_btn, "diff.run"),
        ]:
            if btn:
                btn.setText(tr(key))

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ===== 顶部: 左右数据源 =====
        top = QFrame()
        top.setObjectName("Card")
        tl = QVBoxLayout(top)
        tl.setContentsMargins(8, 8, 8, 8)
        tl.setSpacing(4)
        tl.addWidget(QLabel("📊 " + tr("diff.sources.title")))
        # 左 | 右 横排
        src_row = QHBoxLayout()
        src_row.setSpacing(8)
        self.left_panel = SourcePanel(tr("diff.source.a"), "left")
        self.right_panel = SourcePanel(tr("diff.source.b"), "right")
        self.left_panel.changed.connect(self._refresh_mapping)
        self.right_panel.changed.connect(self._refresh_mapping)
        src_row.addWidget(self.left_panel, 1)
        # 中间 vs
        vs = QLabel("⚔")
        vs.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vs.setStyleSheet("font-size: 22px; color: #3b82f6;")
        vs.setMaximumWidth(40)
        src_row.addWidget(vs, 0, Qt.AlignmentFlag.AlignVCenter)
        src_row.addWidget(self.right_panel, 1)
        tl.addLayout(src_row, 1)
        outer.addWidget(top)

        # ===== 中部: 表匹配(每行配置)+ 开始按钮 =====
        mid = QFrame()
        mid.setObjectName("Card")
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(8, 8, 8, 8)
        ml.setSpacing(4)
        self.mapping_panel = MappingPanel()
        ml.addWidget(self.mapping_panel, 1)
        # 底部: 提示 + 开始
        run_row = QHBoxLayout()
        self.hint_lbl = QLabel(tr("diff.run.hint"))
        self.hint_lbl.setObjectName("Muted")
        self.hint_lbl.setStyleSheet("font-size: 11px;")
        run_row.addWidget(self.hint_lbl, 1)
        # 开始
        self.run_btn = QPushButton(tr("diff.run"))
        self.run_btn.setObjectName("Primary")
        self.run_btn.setIcon(qta.icon("mdi6.play", color="white"))
        self.run_btn.clicked.connect(self._on_run)
        run_row.addWidget(self.run_btn)
        ml.addLayout(run_row)
        outer.addWidget(mid, 1)

        # ===== 进度 =====
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        outer.addWidget(self.progress)

    # ===== 表匹配刷新 =====
    def _refresh_mapping(self) -> None:
        a = self.left_panel.all_tables()
        b = self.right_panel.all_tables()
        self.mapping_panel.rebuild(a, b)

    # ===== 跑对比 =====
    def _on_run(self) -> None:
        a = self.left_panel.all_tables()
        b = self.right_panel.all_tables()
        if not a or not b:
            QMessageBox.information(self, tr("common.error"), tr("diff.error.no_sources"))
            return
        # 收集每行(match, config)
        match_configs = self.mapping_panel.collect_match_configs(a, b)
        # 检查未配对的行(给用户提示)
        a_keys = list(a.keys())
        skipped = []
        for i, row in enumerate(self.mapping_panel._rows):
            if i >= len(a_keys):
                break
            a_tn = a_keys[i]
            a_path, a_label = a[a_tn]
            mc = row.get_match(a_path, a_label, b)
            if not mc:
                b_selected = bool(row.b_combo.currentData())
                mode = row.mode_combo.currentData()
                cols_empty = (mode == "selected" and not row._selected_cols)
                reason = []
                if not b_selected:
                    reason.append(tr("diff.run.err.no_b"))
                if cols_empty:
                    reason.append(tr("diff.run.err.no_cols"))
                skipped.append(f"{a_tn}: {', '.join(reason)}")
        if not match_configs:
            msg = tr("diff.error.no_pairs") + "\n\n" + "\n".join(skipped[:5])
            QMessageBox.warning(self, tr("common.error"), msg)
            return
        if skipped:
            msg = tr("diff.run.warn.skipped") + "\n" + "\n".join(skipped[:5])
            if len(skipped) > 5:
                msg += f"\n... (+{len(skipped) - 5} more)"
            show_toast(msg, "warning")
        self._pending_matches = match_configs
        self._match_results = []
        self._match_errors = []
        self._match_index = 0
        self.progress.setVisible(True)
        self.progress.setRange(0, len(match_configs))
        self.progress.setValue(0)
        self.run_btn.setEnabled(False)
        self._start_next_match()

    def _start_next_match(self) -> None:
        if self._match_index >= len(self._pending_matches):
            return
        match, config = self._pending_matches[self._match_index]
        # 校验文件
        if not os.path.exists(match.a_path) or not os.path.exists(match.b_path):
            self._match_errors.append((match.a_table, "file missing"))
            self._match_index += 1
            self.progress.setValue(self.progress.value() + 1)
            self._start_next_match()
            return
        if detect_format(match.a_path) == "unknown" or detect_format(match.b_path) == "unknown":
            self._match_errors.append((match.a_table, "unsupported format"))
            self._match_index += 1
            self.progress.setValue(self.progress.value() + 1)
            self._start_next_match()
            return
        w = DiffPairWorker(match, config)
        w.signals.finished.connect(self._on_match_done)
        w.signals.error.connect(self._on_match_error)
        QThreadPool.globalInstance().start(w)

    def _on_match_done(self, payload: dict) -> None:
        self._match_results.append(payload)
        self.progress.setValue(self.progress.value() + 1)
        self._match_index += 1
        if self._match_index < len(self._pending_matches):
            self._start_next_match()
        else:
            self._finish()

    def _on_match_error(self, a_table: str, msg: str) -> None:
        self._match_errors.append((a_table, msg))
        self.progress.setValue(self.progress.value() + 1)
        self._match_index += 1
        if self._match_index < len(self._pending_matches):
            self._start_next_match()
        else:
            self._finish()

    def _finish(self) -> None:
        self.progress.setVisible(False)
        self.run_btn.setEnabled(True)
        # 弹独立窗口
        dlg = ResultDialog(self._match_results, self._match_errors, parent=self)
        dlg.show()  # 非模态,可以同时看 diff tab
        show_toast(tr("diff.done"), "success")

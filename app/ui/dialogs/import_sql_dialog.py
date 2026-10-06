"""从 SQL 文件 / 直接粘贴导入表结构 + 外键 + INDEX  DDL  对话框

三大类别(二选一场景 = 单击哪个 tab):
1. CREATE TABLE   从 SQL 中识别出多张表,跟以前一样勾选要导入的表
2. FOREIGN KEY    选多文件 / 粘贴多段,识别每段作用的表,assign 到具体表
3. INDEX DDL      同上,识别作用于哪张表

每种类别内部都有两个输入源:
- 文件(多选,常用于"每个表一个 .sql 文件"的场景)
- 直接粘贴(一段文本,里面可含多条 ALTER TABLE / CREATE INDEX)
"""
from __future__ import annotations
import re
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QListWidget, QListWidgetItem, QFileDialog, QMessageBox,
    QPlainTextEdit, QFrame, QSizePolicy, QTabWidget, QWidget,
    QScrollArea, QTextEdit,
)

from app.ui.i18n import tr
from app.core.ddl_parser import parse_ddl_file, parse_ddl_text, DIALECTS, ParsedTable


_DIALECT_LABELS = {
    "postgres": "PostgreSQL",
    "mysql":    "MySQL",
    "oracle":   "Oracle",
}


# ---------------------------------------------------------------------------
# 从 FK / INDEX 文本里识别作用的表名
# ---------------------------------------------------------------------------
# ALTER TABLE [schema.]table_name ADD CONSTRAINT ... / ADD FOREIGN KEY ...
_RE_ALTER_TABLE = re.compile(
    r"""ALTER\s+TABLE\s+
        (?:["`\w]+\.)?           # 可选 schema.
        (["`\w]+)                # table_name
    """,
    re.IGNORECASE | re.VERBOSE,
)
# CREATE INDEX [name] ON [schema.]table_name / CREATE [UNIQUE] INDEX ...
_RE_CREATE_INDEX = re.compile(
    r"""CREATE\s+(?:UNIQUE\s+)?INDEX\s+\S+\s+ON\s+
        (?:["`\w]+\.)?
        (["`\w]+)
    """,
    re.IGNORECASE | re.VERBOSE,
)
# ALTER TABLE ... ADD INDEX (MySQL) / ADD KEY 也算 INDEX
_RE_ALTER_INDEX = re.compile(
    r"""ALTER\s+TABLE\s+
        (?:["`\w]+\.)?
        (["`\w]+)
        [^;]*?\bADD\s+(?:INDEX|KEY|UNIQUE\s+(?:INDEX|KEY)|FULLTEXT\s+(?:INDEX|KEY))\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _unquote(s: str) -> str:
    """去掉标识符周围的 `"` ` `` ` `[ ] `"""
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("\"", "`"):
        return s[1:-1]
    if len(s) >= 2 and s[0] == "[" and s[-1] == "]":
        return s[1:-1]
    return s


def _detect_table_for_fk(text: str) -> str:
    """从 ALTER TABLE ... ADD FOREIGN KEY 文本里找作用表名"""
    for rx in (_RE_ALTER_TABLE,):
        m = rx.search(text)
        if m:
            return _unquote(m.group(1))
    return ""


def _detect_table_for_index(text: str) -> str:
    """从 CREATE INDEX / ALTER TABLE ADD INDEX 文本里找作用表名"""
    # CREATE INDEX ... ON table 优先级最高(精确匹配)
    m = _RE_CREATE_INDEX.search(text)
    if m:
        return _unquote(m.group(1))
    # ALTER TABLE table ADD INDEX / KEY / UNIQUE / FULLTEXT
    m = _RE_ALTER_INDEX.search(text)
    if m:
        return _unquote(m.group(1))
    # 退化:从 ALTER TABLE 拿(可能不是 ADD INDEX,但 ALTER TABLE 后面就够用)
    m = _RE_ALTER_TABLE.search(text)
    if m:
        return _unquote(m.group(1))
    return ""


def _split_fk_stmts(text: str) -> list[str]:
    """把一大段 FK SQL 切成多条 ALTER TABLE ...; 或 ALTER TABLE ... \n ALTER TABLE ... (分号切分,合并 ALTER 链)"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 简单分号切
    out = []
    buf = []
    in_str = None
    for ch in text:
        if in_str:
            buf.append(ch)
            if ch == in_str and (len(buf) < 2 or buf[-2] != "\\"):
                in_str = None
            continue
        if ch in ("'", '"', "`"):
            in_str = ch
            buf.append(ch)
            continue
        if ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
            continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    # 只保留包含 FOREIGN KEY / REFERENCES / ADD CONSTRAINT 的语句(否则算杂语句忽略)
    keep = []
    for s in out:
        if re.search(r"\b(FOREIGN\s+KEY|REFERENCES|ADD\s+CONSTRAINT)\b", s, re.IGNORECASE):
            keep.append(s)
    return keep


def _split_index_stmts(text: str) -> list[str]:
    """把一大段 INDEX SQL 切成多条 CREATE INDEX ... / ALTER TABLE ADD INDEX ..."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out = []
    buf = []
    in_str = None
    for ch in text:
        if in_str:
            buf.append(ch)
            if ch == in_str and (len(buf) < 2 or buf[-2] != "\\"):
                in_str = None
            continue
        if ch in ("'", '"', "`"):
            in_str = ch
            buf.append(ch)
            continue
        if ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
            continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    keep = []
    for s in out:
        if re.search(r"\b(CREATE\s+(?:UNIQUE\s+)?INDEX|ADD\s+(?:INDEX|KEY|UNIQUE|FULLTEXT))\b", s, re.IGNORECASE):
            keep.append(s)
    return keep


# ---------------------------------------------------------------------------
# Table list item (CREATE 模式用)
# ---------------------------------------------------------------------------
class _TableItem(QListWidgetItem):
    """带勾选状态的表项 + 解析错误展示。"""
    def __init__(self, parsed: ParsedTable, parent=None):
        super().__init__(parent)
        self.parsed = parsed
        self.setFlags(self.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        checked = not parsed.parse_error and bool(parsed.columns)
        self.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        err = f"  ⚠ {parsed.parse_error}" if parsed.parse_error else ""
        cols = len(parsed.columns)
        self.setText(f"{parsed.name}    ({cols} 列){err}")


# ---------------------------------------------------------------------------
# FK / INDEX 模式下的一行:文件/粘贴段 + 自动识别表 + 目标表 combo + 预览按钮
# ---------------------------------------------------------------------------
class _DDLRowWidget(QFrame):
    """FK / INDEX 模式下的单行 UI: [源标签] [识别表] [→目标表 combo] [预览] [删除]"""
    DELETED = None  # 通过 list 维护,行内删除通知外层

    def __init__(self, source_label: str, sql_text: str, detected: str,
                 available_tables: list[str], on_delete, on_change, on_preview,
                 parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: #0f172a; border: 1px solid #334155; border-radius: 4px; padding: 6px; }"
        )
        self._on_delete = on_delete
        self._on_change = on_change
        self._on_preview = on_preview
        self._sql_text = sql_text

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(8)

        self.src_label = QLabel(source_label)
        self.src_label.setMinimumWidth(220)
        self.src_label.setMaximumWidth(260)
        self.src_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self.src_label.setToolTip(source_label)
        lay.addWidget(self.src_label)

        det = detected or "?"
        self.det_label = QLabel(f"识别: {det}")
        self.det_label.setMinimumWidth(120)
        self.det_label.setStyleSheet("color: #64748b; font-size: 11px;")
        lay.addWidget(self.det_label)

        arrow = QLabel("→")
        arrow.setStyleSheet("color: #475569;")
        lay.addWidget(arrow)

        self.target_combo = QComboBox()
        self.target_combo.setMinimumWidth(180)
        self.target_combo.addItem("（未匹配 / 待选）", "")
        for t in available_tables:
            self.target_combo.addItem(t, t)
        # 自动选中
        if detected and detected in available_tables:
            idx = self.target_combo.findData(detected)
            if idx >= 0:
                self.target_combo.setCurrentIndex(idx)
        self.target_combo.currentIndexChanged.connect(lambda _: self._on_change())
        lay.addWidget(self.target_combo, 1)

        preview_btn = QPushButton("预览")
        preview_btn.setObjectName("Ghost")
        preview_btn.setFixedWidth(60)
        preview_btn.clicked.connect(lambda: self._on_preview(self))
        lay.addWidget(preview_btn)

        del_btn = QPushButton("✕")
        del_btn.setObjectName("Ghost")
        del_btn.setFixedWidth(28)
        del_btn.clicked.connect(lambda: self._on_delete(self))
        lay.addWidget(del_btn)

    def target(self) -> str:
        return self.target_combo.currentData() or ""

    def sql(self) -> str:
        return self._sql_text


# ---------------------------------------------------------------------------
# 主 dialog
# ---------------------------------------------------------------------------
class ImportSqlDialog(QDialog):
    """从 SQL 导入表结构 / 外键 / INDEX。

    三个顶层 tab:CREATE TABLE / FOREIGN KEY / INDEX DDL。
    每种 tab 下:文件(可多选) / 直接粘贴 两个子 tab。
    """

    def __init__(self, parent=None, default_dialect: str = "postgres",
                 existing_table_names: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg.import_sql.title"))
        self.resize(820, 600)
        self.setMinimumSize(640, 480)
        self._default_dialect = default_dialect
        self._existing_table_names = list(existing_table_names or [])
        # CREATE 模式结果
        self._selected_tables: list[ParsedTable] = []
        # FK / INDEX 模式结果: dict[target_table_name -> concatenated_sql]
        self._fk_ddls: dict[str, str] = {}
        self._index_ddls: dict[str, str] = {}
        # UI 状态
        self._parsed_create_tables: list[ParsedTable] = []
        self._dialect: str = default_dialect
        # FK / INDEX 行容器(list[QWidget])
        self._fk_rows: list[_DDLRowWidget] = []
        self._index_rows: list[_DDLRowWidget] = []
        self._build()

    # ============ UI 构建 ============
    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # 顶层类别 tabs
        self.kind_tabs = QTabWidget()
        self._build_create_tab()
        self._build_fk_tab()
        self._build_index_tab()
        self.kind_tabs.addTab(self._create_tab_widget, tr("dlg.import_sql.kind.create"))
        self.kind_tabs.addTab(self._fk_tab_widget,    tr("dlg.import_sql.kind.fk"))
        self.kind_tabs.addTab(self._index_tab_widget, tr("dlg.import_sql.kind.index"))
        layout.addWidget(self.kind_tabs)

        # 底部按钮(始终在底部,跟类别无关)
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

        # 默认显示 CREATE 模式
        self.kind_tabs.currentChanged.connect(self._on_kind_changed)

    # ===== CREATE 模式 =====
    def _build_create_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 8, 0, 8)
        v.setSpacing(8)

        # 子 tab:文件 / 粘贴
        self.create_input_tabs = QTabWidget()
        # 文件(多选)
        file_tab = QWidget()
        ft = QVBoxLayout(file_tab)
        ft.setContentsMargins(0, 8, 0, 8)
        ft.setSpacing(6)
        file_row = QHBoxLayout()
        file_row.setSpacing(8)
        file_row.addWidget(QLabel(tr("dlg.import_sql.file")))
        self.create_path_edit = QLineEdit()
        self.create_path_edit.setPlaceholderText(tr("dlg.import_sql.file.placeholder.multi"))
        file_row.addWidget(self.create_path_edit, 1)
        browse_btn = QPushButton(tr("action.browse"))
        browse_btn.clicked.connect(self._on_create_browse)
        file_row.addWidget(browse_btn)
        ft.addLayout(file_row)
        ft.addWidget(QLabel(tr("dlg.import_sql.file.tip")))
        self.create_input_tabs.addTab(file_tab, tr("dlg.import_sql.tab.file"))
        # 粘贴
        paste_tab = QWidget()
        pt = QVBoxLayout(paste_tab)
        pt.setContentsMargins(0, 8, 0, 8)
        pt.setSpacing(6)
        self.create_paste_edit = QPlainTextEdit()
        self.create_paste_edit.setPlaceholderText(tr("dlg.import_sql.paste.placeholder"))
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.create_paste_edit.setFont(mono)
        self.create_paste_edit.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 12px; "
            "background: #0b1220; color: #e2e8f0; border: 1px solid #334155; border-radius: 6px;"
        )
        self._create_paste_timer = QTimer(self)
        self._create_paste_timer.setSingleShot(True)
        self._create_paste_timer.setInterval(250)
        self._create_paste_timer.timeout.connect(self._do_create_parse)
        self.create_paste_edit.textChanged.connect(lambda: self._create_paste_timer.start())
        pt.addWidget(self.create_paste_edit, 1)
        self.create_input_tabs.addTab(paste_tab, tr("dlg.import_sql.tab.paste"))
        self.create_input_tabs.currentChanged.connect(self._do_create_parse)
        v.addWidget(self.create_input_tabs)

        # 方言 + 重解析
        dialect_row = QHBoxLayout()
        dialect_row.setSpacing(8)
        dialect_row.addWidget(QLabel(tr("dlg.import_sql.dialect")))
        self.create_dialect_combo = QComboBox()
        for d in DIALECTS:
            self.create_dialect_combo.addItem(_DIALECT_LABELS[d], d)
        idx = self.create_dialect_combo.findData(self._default_dialect)
        if idx >= 0:
            self.create_dialect_combo.setCurrentIndex(idx)
        self.create_dialect_combo.currentIndexChanged.connect(self._do_create_parse)
        dialect_row.addWidget(self.create_dialect_combo)
        dialect_row.addStretch()
        reparse_btn = QPushButton(tr("dlg.import_sql.reparse"))
        reparse_btn.setObjectName("Ghost")
        reparse_btn.clicked.connect(self._do_create_parse)
        dialect_row.addWidget(reparse_btn)
        v.addLayout(dialect_row)

        # 全选/反选 + 计数
        sel_row = QHBoxLayout()
        sel_row.setSpacing(8)
        sel_row.addWidget(QLabel(tr("dlg.import_sql.tables")))
        sel_row.addStretch()
        sel_all = QPushButton(tr("action.select_all"))
        sel_all.setObjectName("Ghost")
        sel_all.clicked.connect(self._on_create_select_all)
        sel_row.addWidget(sel_all)
        desel = QPushButton(tr("action.deselect_all"))
        desel.setObjectName("Ghost")
        desel.clicked.connect(self._on_create_deselect_all)
        sel_row.addWidget(desel)
        self.create_count_label = QLabel("")
        self.create_count_label.setObjectName("Muted")
        sel_row.addWidget(self.create_count_label)
        v.addLayout(sel_row)

        # 表列表
        self.create_table_list = QListWidget()
        self.create_table_list.setMinimumHeight(160)
        v.addWidget(self.create_table_list, 1)

        # 错误区
        self.create_error_view = QPlainTextEdit()
        self.create_error_view.setReadOnly(True)
        self.create_error_view.setMaximumHeight(72)
        self.create_error_view.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 11px; "
            "color: #f59e0b; background: #1f1300; border: 1px solid #b45309; border-radius: 4px;"
        )
        self.create_error_view.setVisible(False)
        v.addWidget(self.create_error_view)

        self._create_tab_widget = w

    def _on_create_browse(self):
        start = str(Path(self.create_path_edit.text()).parent) if self.create_path_edit.text() else str(Path.home())
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("dlg.import_sql.browse_title"), start,
            "SQL files (*.sql);;All files (*.*)",
        )
        if paths:
            # 多文件用 ; 或换行分隔展示(便于复制)
            sep = ";\n"
            self.create_path_edit.setText(sep.join(paths))
            self._do_create_parse()

    def _on_create_select_all(self):
        for i in range(self.create_table_list.count()):
            it = self.create_table_list.item(i)
            if it.parsed.parse_error or not it.parsed.columns:
                continue
            it.setCheckState(Qt.CheckState.Checked)
        self._update_create_count()

    def _on_create_deselect_all(self):
        for i in range(self.create_table_list.count()):
            self.create_table_list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self._update_create_count()

    def _do_create_parse(self):
        dialect = self.create_dialect_combo.currentData() or "postgres"
        self._dialect = dialect
        if self.create_input_tabs.currentIndex() == 0:
            # 文件(多选)模式:把多文件内容拼起来一起解析
            paths_text = self.create_path_edit.text().strip()
            if not paths_text:
                self._parsed_create_tables = []
                self.create_table_list.clear()
                self.create_error_view.setVisible(False)
                self._update_create_count()
                return
            sep = re.split(r"[;\n]+", paths_text)
            paths = [p.strip() for p in sep if p.strip()]
            all_tables: list[ParsedTable] = []
            all_errs: list[str] = []
            for p in paths:
                if not Path(p).is_file():
                    all_errs.append(f"文件不存在: {p}")
                    continue
                try:
                    tables, errs = parse_ddl_file(p, dialect)
                    all_tables.extend(tables)
                    all_errs.extend(errs)
                except Exception as e:
                    all_errs.append(f"{p}: {e}")
            self._parsed_create_tables = all_tables
            self.create_table_list.clear()
            for t in all_tables:
                self.create_table_list.addItem(_TableItem(t))
            if all_errs:
                self.create_error_view.setPlainText("\n".join(all_errs))
                self.create_error_view.setVisible(True)
            elif not all_tables:
                self.create_error_view.setPlainText(tr("dlg.import_sql.no_table_found"))
                self.create_error_view.setVisible(True)
            else:
                self.create_error_view.setVisible(False)
        else:
            # 粘贴模式
            text = self.create_paste_edit.toPlainText()
            if not text.strip():
                self._parsed_create_tables = []
                self.create_table_list.clear()
                self.create_error_view.setVisible(False)
                self._update_create_count()
                return
            try:
                tables, errs = parse_ddl_text(text, dialect)
            except Exception as e:
                QMessageBox.warning(self, tr("common.error"), f"解析失败: {e}")
                return
            self._parsed_create_tables = tables
            self.create_table_list.clear()
            for t in tables:
                self.create_table_list.addItem(_TableItem(t))
            if errs:
                self.create_error_view.setPlainText("\n".join(errs))
                self.create_error_view.setVisible(True)
            elif not tables:
                self.create_error_view.setPlainText(tr("dlg.import_sql.no_table_found"))
                self.create_error_view.setVisible(True)
            else:
                self.create_error_view.setVisible(False)
        self._update_create_count()

    def _update_create_count(self):
        total = self.create_table_list.count()
        sel = sum(
            1 for i in range(total)
            if self.create_table_list.item(i).checkState() == Qt.CheckState.Checked
        )
        self.create_count_label.setText(f"{sel} / {total}")

    # ===== FOREIGN KEY / INDEX 模式  共享 build 模板 =====
    def _build_ddl_kind_tab(self, kind: str, w: QWidget):
        """kind = 'fk' | 'index'"""
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 8, 0, 8)
        v.setSpacing(8)

        # 子 tab:文件 / 粘贴
        sub_tabs = QTabWidget()
        # 文件
        file_tab = QWidget()
        ft = QVBoxLayout(file_tab)
        ft.setContentsMargins(0, 8, 0, 8)
        ft.setSpacing(6)
        file_row = QHBoxLayout()
        file_row.setSpacing(8)
        ft.addWidget(QLabel(tr("dlg.import_sql.file")))
        path_edit = QLineEdit()
        path_edit.setPlaceholderText(tr("dlg.import_sql.file.placeholder.multi"))
        file_row.addWidget(path_edit, 1)
        browse_btn = QPushButton(tr("action.browse"))
        browse_btn.clicked.connect(lambda: self._on_ddl_browse(kind, path_edit))
        file_row.addWidget(browse_btn)
        ft.addLayout(file_row)
        ft.addWidget(QLabel(tr("dlg.import_sql.file.tip")))
        sub_tabs.addTab(file_tab, tr("dlg.import_sql.tab.file"))
        # 粘贴
        paste_tab = QWidget()
        pt = QVBoxLayout(paste_tab)
        pt.setContentsMargins(0, 8, 0, 8)
        pt.setSpacing(6)
        paste_edit = QPlainTextEdit()
        paste_edit.setPlaceholderText(tr("dlg.import_sql.ddl_paste.placeholder").format(kind=kind))
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        paste_edit.setFont(mono)
        paste_edit.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 12px; "
            "background: #0b1220; color: #e2e8f0; border: 1px solid #334155; border-radius: 6px;"
        )
        # 粘贴时实时解析(防抖)
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(250)
        def _parse_now():
            self._parse_ddl_paste(kind, paste_edit.toPlainText())
        timer.timeout.connect(_parse_now)
        paste_edit.textChanged.connect(lambda: timer.start())
        pt.addWidget(paste_edit, 1)
        sub_tabs.addTab(paste_tab, tr("dlg.import_sql.tab.paste"))
        sub_tabs.currentChanged.connect(lambda _: _parse_now())
        v.addWidget(sub_tabs)

        # 行容器
        rows_scroll = QWidget()
        rows_layout = QVBoxLayout(rows_scroll)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.setSpacing(4)
        rows_layout.addStretch()
        # 滚動容器 防止行多了溢出
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(rows_scroll)
        scroll.setMinimumHeight(220)
        v.addWidget(scroll, 1)

        # 存引用
        if kind == "fk":
            self._fk_sub_tabs = sub_tabs
            self._fk_path_edit = path_edit
            self._fk_paste_edit = paste_edit
            self._fk_rows_container = rows_layout
            self._fk_rows_scroll = scroll
            self._fk_rows_scroll_widget = rows_scroll
        else:
            self._index_sub_tabs = sub_tabs
            self._index_path_edit = path_edit
            self._index_paste_edit = paste_edit
            self._index_rows_container = rows_layout
            self._index_rows_scroll = scroll
            self._index_rows_scroll_widget = rows_scroll

        # 一键全选已匹配
        match_row = QHBoxLayout()
        match_row.addStretch()
        # 占位,以后可扩展
        v.addLayout(match_row)

    def _build_fk_tab(self):
        w = QWidget()
        self._build_ddl_kind_tab("fk", w)
        self._fk_tab_widget = w

    def _build_index_tab(self):
        w = QWidget()
        self._build_ddl_kind_tab("index", w)
        self._index_tab_widget = w

    def _on_ddl_browse(self, kind: str, path_edit: QLineEdit):
        start = str(Path(path_edit.text()).parent) if path_edit.text() else str(Path.home())
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("dlg.import_sql.browse_title"), start,
            "SQL files (*.sql);;All files (*.*)",
        )
        if paths:
            path_edit.setText(";\n".join(paths))
            self._parse_ddl_files(kind, paths)

    def _parse_ddl_files(self, kind: str, paths: list[str]):
        """从多文件读出 DDL,按语句切,加入行列表"""
        split_fn = _split_fk_stmts if kind == "fk" else _split_index_stmts
        detect_fn = _detect_table_for_fk if kind == "fk" else _detect_table_for_index
        for p in paths:
            if not Path(p).is_file():
                continue
            try:
                text = Path(p).read_text(encoding="utf-8")
            except Exception as e:
                QMessageBox.warning(self, tr("common.error"), f"读取失败: {p}\n{e}")
                continue
            self._add_ddl_stmts(kind, split_fn(text), detect_fn, Path(p).name)

    def _parse_ddl_paste(self, kind: str, text: str):
        """粘贴内容变化时,从粘贴中解析"""
        split_fn = _split_fk_stmts if kind == "fk" else _split_index_stmts
        detect_fn = _detect_table_for_fk if kind == "fk" else _detect_table_for_index
        stmts = split_fn(text)
        if not stmts:
            # 清空行
            self._clear_rows(kind)
            return
        self._clear_rows(kind)
        self._add_ddl_stmts(kind, stmts, detect_fn, tr("dlg.import_sql.paste_label"))

    def _clear_rows(self, kind: str):
        rows_attr = f"_{kind}_rows"
        container_attr = f"_{kind}_rows_container"
        rows = getattr(self, rows_attr)
        for w in rows:
            w.setParent(None)
            w.deleteLater()
        setattr(self, rows_attr, [])
        container = getattr(self, container_attr)
        # 把 stretch 留下
        while container.count() > 1:
            container.takeAt(0)

    def _add_ddl_stmts(self, kind: str, stmts: list[str], detect_fn, label_prefix: str):
        """往列表里加 N 行 DDL"""
        rows_attr = f"_{kind}_rows"
        container_attr = f"_{kind}_rows_container"
        rows: list[_DDLRowWidget] = getattr(self, rows_attr)
        container: QVBoxLayout = getattr(self, container_attr)
        # 在 stretch 前插入
        stretch_idx = container.count() - 1
        for i, s in enumerate(stmts):
            detected = detect_fn(s)
            row = _DDLRowWidget(
                source_label=f"{label_prefix}  #{i + 1}",
                sql_text=s,
                detected=detected,
                available_tables=self._existing_table_names,
                on_delete=lambda r: self._remove_ddl_row(kind, r),
                on_change=lambda: None,
                on_preview=self._preview_ddl,
                parent=self._fk_rows_scroll_widget if kind == "fk" else self._index_rows_scroll_widget,
            )
            rows.append(row)
            container.insertWidget(stretch_idx + len(rows) - 1, row)

    def _remove_ddl_row(self, kind: str, row):
        rows_attr = f"_{kind}_rows"
        rows: list[_DDLRowWidget] = getattr(self, rows_attr)
        if row in rows:
            rows.remove(row)
        row.setParent(None)
        row.deleteLater()

    def _preview_ddl(self, row: _DDLRowWidget):
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("dlg.import_sql.preview_title"))
        dlg.resize(680, 360)
        lay = QVBoxLayout(dlg)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText(row.sql())
        view.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 12px; "
            "background: #0b1220; color: #e2e8f0; border: 1px solid #334155; border-radius: 6px;"
        )
        lay.addWidget(view, 1)
        btn = QPushButton(tr("action.close"))
        btn.setObjectName("Primary")
        btn.clicked.connect(dlg.accept)
        lay.addWidget(btn)
        dlg.exec()

    def _on_kind_changed(self, _idx: int):
        """切顶层 tab 时,不重置数据"""
        pass

    # ============ 接受 ============
    def _on_accept(self):
        kind_idx = self.kind_tabs.currentIndex()
        if kind_idx == 0:
            # CREATE 模式
            selected = []
            for i in range(self.create_table_list.count()):
                it = self.create_table_list.item(i)
                if it.checkState() == Qt.CheckState.Checked:
                    selected.append(it.parsed)
            if not selected:
                QMessageBox.information(
                    self, tr("common.info"),
                    tr("dlg.import_sql.empty_selection"),
                )
                return
            self._selected_tables = selected
            self._fk_ddls = {}
            self._index_ddls = {}
            self.accept()
        elif kind_idx == 1:
            # FK 模式
            out: dict[str, list[str]] = {}
            for row in self._fk_rows:
                t = row.target()
                if not t:
                    continue
                out.setdefault(t, []).append(row.sql().strip().rstrip(";") + ";")
            if not out:
                QMessageBox.information(
                    self, tr("common.info"),
                    tr("dlg.import_sql.no_target_selected"),
                )
                return
            self._fk_ddls = {k: "\n\n".join(v) for k, v in out.items()}
            self._selected_tables = []
            self._index_ddls = {}
            self.accept()
        else:
            # INDEX 模式
            out: dict[str, list[str]] = {}
            for row in self._index_rows:
                t = row.target()
                if not t:
                    continue
                out.setdefault(t, []).append(row.sql().strip().rstrip(";") + ";")
            if not out:
                QMessageBox.information(
                    self, tr("common.info"),
                    tr("dlg.import_sql.no_target_selected"),
                )
                return
            self._index_ddls = {k: "\n\n".join(v) for k, v in out.items()}
            self._selected_tables = []
            self._fk_ddls = {}
            self.accept()

    # ============ 公开 getter ============
    def get_selected_tables(self) -> list[ParsedTable]:
        return list(self._selected_tables)

    def get_fk_ddls(self) -> dict[str, str]:
        return dict(self._fk_ddls)

    def get_index_ddls(self) -> dict[str, str]:
        return dict(self._index_ddls)

    def get_import_kind(self) -> str:
        """当前接受时对应的类别:create / fk / index"""
        return ("create", "fk", "index")[self.kind_tabs.currentIndex()]

    def set_paste_text(self, text: str) -> None:
        """公开:预填 CREATE 粘贴内容 + 切到 CREATE / 粘贴 tab + 立即解析(兼容老调用)"""
        self.kind_tabs.setCurrentIndex(0)
        self.create_input_tabs.setCurrentIndex(1)
        self.create_paste_edit.setPlainText(text)
        self._do_create_parse()


# 兼容老 import 的别名
_QDDLRowWidget = _DDLRowWidget
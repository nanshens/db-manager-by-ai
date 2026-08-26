"""常用 SQL 库页 — 列表 + 搜索 + 项目/标签过滤 + 新建/编辑/删除/复制"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QPushButton, QLineEdit, QFrame, QComboBox,
    QListWidget, QListWidgetItem, QMessageBox, QSplitter, QPlainTextEdit, QWidget,
    QApplication, QLabel,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.ui.widgets import EmptyState, show_toast
from app.ui.widgets.syntax_highlight import SqlHighlighter
from app.ui.dialogs import SqlSnippetDialog
from app.services.registry import reg
from app.repos.sql_snippet_repo import SqlSnippet, DIALECTS


def _split_tags(tags: str) -> list[str]:
    """把 'a, b, c' 这种 tag 字符串拆成 ['a', 'b', 'c']。"""
    if not tags:
        return []
    out = []
    for t in tags.split(","):
        t = t.strip()
        if t:
            out.append(t)
    return out


class SqlLibPage(QWidget):
    new_snippet_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._new_btn = None
        self._new_btn_empty = None
        self._current: Optional[SqlSnippet] = None
        self._all_tags_cache: list[str] = []
        self._build()
        self.refresh()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # Toolbar
        toolbar = QFrame()
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(0, 0, 0, 0)
        tb.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("sqllib.search_placeholder"))
        self.search.setMaximumWidth(280)
        self.search.textChanged.connect(self._on_filter_change)
        tb.addWidget(self.search)

        self.project_filter = QComboBox()
        self.project_filter.setMinimumWidth(150)
        self.project_filter.currentIndexChanged.connect(self._on_filter_change)
        tb.addWidget(self.project_filter)

        self.tag_filter = QComboBox()
        self.tag_filter.setMinimumWidth(130)
        self.tag_filter.currentIndexChanged.connect(self._on_filter_change)
        tb.addWidget(self.tag_filter)

        # 方言过滤
        self.dialect_filter = QComboBox()
        self.dialect_filter.setMinimumWidth(110)
        self.dialect_filter.currentIndexChanged.connect(self._on_filter_change)
        tb.addWidget(self.dialect_filter)

        tb.addStretch()

        self._new_btn = QPushButton(tr("sqllib.new"))
        self._new_btn.setObjectName("Primary")
        self._new_btn.setIcon(qta.icon("mdi6.plus", color="white"))
        self._new_btn.clicked.connect(self._on_new)
        tb.addWidget(self._new_btn)
        layout.addWidget(toolbar)

        # Splitter: 左 list / 右 detail
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)
        layout.addWidget(self.splitter, 1)

        # Left: snippet list
        left = QFrame()
        left.setMinimumWidth(280)
        left.setMaximumWidth(420)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.snippet_list = QListWidget()
        self.snippet_list.itemSelectionChanged.connect(self._on_selection)
        self.snippet_list.itemDoubleClicked.connect(self._on_edit_current)
        ll.addWidget(self.snippet_list)

        # Right: detail
        right = QFrame()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        # header
        hdr = QHBoxLayout()
        self.title_label = QLabel("—")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: 700;")
        hdr.addWidget(self.title_label)
        hdr.addStretch()

        self.copy_btn = QPushButton(tr("action.copy"))
        self.copy_btn.setObjectName("Primary")
        self.copy_btn.setIcon(qta.icon("mdi6.content-copy", color="white"))
        self.copy_btn.clicked.connect(self._on_copy)
        hdr.addWidget(self.copy_btn)
        self.edit_btn = QPushButton()
        self.edit_btn.setIcon(qta.icon("mdi6.pencil", color="#94a3b8"))
        self.edit_btn.setFixedSize(32, 32)
        self.edit_btn.clicked.connect(self._on_edit_current)
        hdr.addWidget(self.edit_btn)
        self.del_btn = QPushButton()
        self.del_btn.setIcon(qta.icon("mdi6.trash-can-outline", color="#ef4444"))
        self.del_btn.setFixedSize(32, 32)
        self.del_btn.clicked.connect(self._on_delete)
        hdr.addWidget(self.del_btn)
        rl.addLayout(hdr)

        self.meta_label = QLabel("")
        self.meta_label.setObjectName("Muted")
        self.meta_label.setWordWrap(True)
        rl.addWidget(self.meta_label)

        self.sql_view = QPlainTextEdit()
        self.sql_view.setReadOnly(True)
        self.sql_view.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 12px; "
            "background: #0b1220; color: #e2e8f0; border: 1px solid #334155; border-radius: 6px;"
        )
        self._sql_highlighter = SqlHighlighter(self.sql_view.document())
        rl.addWidget(self.sql_view, 1)

        self._detail_widgets = [self.title_label, self.meta_label, self.sql_view,
                                self.copy_btn, self.edit_btn, self.del_btn]
        self._init_state()

        # Empty state for right — 纯展示,无按钮(新建走工具栏)
        self.empty = EmptyState(
            icon_name="mdi6.database-outline",
            title=tr("sqllib.empty.title"),
            description=tr("sqllib.empty.desc"),
            primary_text="",  # 不显示按钮
            parent=self,
        )
        # 留信号连接是为了兼容旧的"双击空态=新建"行为(虽然现在没按钮)
        self.empty.primary_clicked.connect(self._on_new)
        self._new_btn_empty = None  # 不再需要

        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self.empty)
        right_layout.addStretch()

        self.splitter.addWidget(left)
        self.splitter.addWidget(right)
        self.splitter.setSizes([320, 700])

    def retranslate(self) -> None:
        self.search.setPlaceholderText(tr("sqllib.search_placeholder"))
        if self._new_btn:
            self._new_btn.setText(tr("sqllib.new"))
        if self._new_btn_empty:
            self._new_btn_empty.setText(tr("sqllib.new"))
        # 保留当前选中的项目/标签,只刷新显示文字
        self._refresh_project_filter()
        self._refresh_tag_filter()
        self._refresh_dialect_filter()

    def _init_state(self) -> None:
        for w in self._detail_widgets:
            w.hide()

    def _refresh_project_filter(self) -> None:
        cur = self.project_filter.currentData()
        self.project_filter.blockSignals(True)
        self.project_filter.clear()
        self.project_filter.addItem(tr("sqllib.scope.all"), None)            # 全部(含全局)
        self.project_filter.addItem(tr("sqllib.scope.global_only"), "global")  # 仅全局
        projects = reg().project_service.list_all()
        for p in projects:
            self.project_filter.addItem(p.name, p.id)
        # 恢复选中
        if cur is not None:
            idx = self.project_filter.findData(cur)
            if idx >= 0:
                self.project_filter.setCurrentIndex(idx)
        self.project_filter.blockSignals(False)

    def _refresh_tag_filter(self) -> None:
        """从所有 snippet 收集唯一 tag,放进下拉。"""
        cur = self.tag_filter.currentData()
        # 收集
        tags: set[str] = set()
        try:
            for s in reg().sql_lib_service.list(include_global=True):
                tags.update(_split_tags(s.tags))
        except Exception:
            tags = set()
        self._all_tags_cache = sorted(tags)
        self.tag_filter.blockSignals(True)
        self.tag_filter.clear()
        self.tag_filter.addItem(tr("sqllib.tags_filter"), "")  # 所有标签
        for t in self._all_tags_cache:
            self.tag_filter.addItem(f"#{t}", t)
        if cur is not None:
            idx = self.tag_filter.findData(cur)
            if idx >= 0:
                self.tag_filter.setCurrentIndex(idx)
        self.tag_filter.blockSignals(False)

    def _refresh_dialect_filter(self) -> None:
        """方言过滤下拉:全部 + 3 个方言。"""
        cur = self.dialect_filter.currentData()
        self.dialect_filter.blockSignals(True)
        self.dialect_filter.clear()
        self.dialect_filter.addItem(tr("sqllib.dialect.all"), "")
        for d in DIALECTS:
            self.dialect_filter.addItem(d.upper(), d)
        if cur is not None:
            idx = self.dialect_filter.findData(cur)
            if idx >= 0:
                self.dialect_filter.setCurrentIndex(idx)
        self.dialect_filter.blockSignals(False)

    def refresh(self) -> None:
        """从 DB 重读过滤条件 + 重新计算可用 tag 列表。"""
        self._refresh_project_filter()
        self._refresh_tag_filter()
        self._refresh_dialect_filter()
        self._on_filter_change()

    def _on_filter_change(self) -> None:
        """search + project + tag + dialect 四合一过滤。"""
        q = self.search.text().strip()
        cur_project = self.project_filter.currentData()
        cur_tag = self.tag_filter.currentData() or ""
        cur_dialect = self.dialect_filter.currentData() or ""

        # 1) 项目范围
        if cur_project is None:
            base = reg().sql_lib_service.list(include_global=True)
        elif cur_project == "global":
            base = reg().sql_lib_service.list(project_id=None, include_global=True)
        else:
            base = reg().sql_lib_service.list(project_id=cur_project, include_global=True)

        # 2) tag 过滤
        if cur_tag:
            base = [s for s in base if cur_tag in _split_tags(s.tags)]

        # 3) dialect 过滤
        if cur_dialect:
            base = [s for s in base if s.dialect == cur_dialect]

        # 4) 搜索关键词
        if q:
            ql = q.lower()
            base = [s for s in base
                    if ql in s.title.lower()
                    or ql in s.sql_text.lower()
                    or ql in (s.tags or "").lower()]

        # 渲染
        self.snippet_list.clear()
        self._init_state()
        self._current = None
        if not base:
            # 有搜索/过滤时显示"没找到"文案;否则显示"还没建过"文案
            if q or cur_tag:
                self.empty.set_text(
                    title=tr("sqllib.empty.search.title"),
                    description=tr("sqllib.empty.search.desc"),
                )
            else:
                self.empty.set_text(
                    title=tr("sqllib.empty.title"),
                    description=tr("sqllib.empty.desc"),
                )
            self.empty.show()
            return
        self.empty.hide()
        for s in base:
            scope = "🌐" if s.project_id is None else "📁"
            item = QListWidgetItem(f"{scope} {s.title}")
            item.setData(Qt.ItemDataRole.UserRole, s.id)
            self.snippet_list.addItem(item)
        if self.snippet_list.count() > 0:
            self.snippet_list.setCurrentRow(0)

    def _on_selection(self) -> None:
        items = self.snippet_list.selectedItems()
        if not items:
            self._current = None
            self._init_state()
            return
        sid = items[0].data(Qt.ItemDataRole.UserRole)
        s = reg().sql_lib_service.get(sid)
        self._current = s
        if not s:
            return
        for w in self._detail_widgets:
            w.show()
        self.title_label.setText(s.title)
        meta = []
        if s.project_id:
            p = reg().project_service.get(s.project_id)
            if p:
                meta.append(f"📁 {p.name}")
        else:
            meta.append("🌐 全局")
        meta.append(f"使用 {s.use_count} 次")
        meta.append(f"🛢  {s.dialect.upper()}")
        if s.tags:
            meta.append(f"🏷  {s.tags}")
        if s.description:
            meta.append(f"📝 {s.description}")
        self.meta_label.setText("  ·  ".join(meta))
        self.sql_view.setPlainText(s.sql_text)

    def _on_new(self) -> None:
        # 预填方言:沿用当前过滤项
        cur_dialect = self.dialect_filter.currentData() or "postgres"
        dlg = SqlSnippetDialog(
            projects=reg().project_service.list_all(),
            default_dialect=cur_dialect if cur_dialect else "postgres",
            parent=self,
        )
        if dlg.exec() == dlg.DialogCode.Accepted:
            v = dlg.get_values()
            try:
                reg().sql_lib_service.create(
                    title=v["title"], sql_text=v["sql_text"],
                    description=v["description"], tags=v["tags"],
                    project_id=v["project_id"],
                    dialect=v["dialect"],
                )
                show_toast(tr("toast.saved"), "success")
                self.refresh()
            except ValueError as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

    def _on_edit_current(self) -> None:
        if not self._current:
            return
        cur_dialect = self.dialect_filter.currentData() or "postgres"
        dlg = SqlSnippetDialog(
            snippet=self._current,
            projects=reg().project_service.list_all(),
            default_dialect=cur_dialect if cur_dialect else "postgres",
            parent=self,
        )
        if dlg.exec() == dlg.DialogCode.Accepted:
            v = dlg.get_values()
            try:
                reg().sql_lib_service.update(
                    self._current.id,
                    title=v["title"], description=v["description"],
                    sql_text=v["sql_text"], tags=v["tags"],
                    project_id=v["project_id"],
                    dialect=v["dialect"],
                )
                show_toast(tr("toast.saved"), "success")
                self.refresh()
            except ValueError as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

    def _on_delete(self) -> None:
        if not self._current:
            return
        if QMessageBox.question(
            self, tr("action.confirm_delete"),
            f"Delete \"{self._current.title}\"?"
        ) == QMessageBox.StandardButton.Yes:
            try:
                reg().sql_lib_service.delete(self._current.id)
                show_toast(tr("toast.deleted"), "success")
                self._current = None
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

    def _on_copy(self) -> None:
        if not self._current:
            return
        QApplication.clipboard().setText(self._current.sql_text)
        reg().sql_lib_service.increment_use(self._current.id)
        show_toast(tr("toast.copied"), "success", 1500)

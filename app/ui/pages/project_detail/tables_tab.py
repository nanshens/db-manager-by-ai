"""Tables Tab — 表结构管理"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QFrame, QListWidget,
    QListWidgetItem, QSplitter, QTextEdit, QMessageBox, QSizePolicy,
    QWidget, QLineEdit, QComboBox,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.ui.widgets import EmptyState, show_toast, SqlHighlighter
from app.ui.dialogs import TableDialog, ImportSqlDialog, TagDialog
from app.services.registry import reg
from app.repos.table_repo import Table, Column


class TablesTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_id: Optional[int] = None
        self._current_table: Optional[Table] = None
        # 过滤状态
        self._search_kw: str = ""           # 表名模糊搜索
        self._tag_filter_id: Optional[int] = None  # 选中的标签 id;None = 全部
        # 缓存
        self._all_tables: list[Table] = []
        self._table_tags_map: dict[int, list] = {}  # {table_id: [Tag, ...]}
        # 跨 tab 通知 bus 只订阅一次(避免 showEvent 重复 disconnect 触发 PySide RuntimeWarning)
        self._bus_connected: bool = False
        self._build()
        # 触发空态显示
        self.refresh()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 工具栏
        toolbar = QFrame()
        toolbar.setStyleSheet("background: transparent;")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(16, 12, 16, 12)
        tb.setSpacing(8)

        self.add_btn = QPushButton(tr("tables_tab.add_table"))
        self.add_btn.setObjectName("Primary")
        self.add_btn.setIcon(qta.icon("mdi6.plus", color="white"))
        self.add_btn.clicked.connect(self._on_add)
        tb.addWidget(self.add_btn)

        self.import_btn = QPushButton(tr("action.import"))
        self.import_btn.setObjectName("Ghost")
        self.import_btn.setIcon(qta.icon("mdi6.database-import-outline", color="#94a3b8"))
        self.import_btn.setToolTip(tr("dlg.import_sql.title"))
        self.import_btn.clicked.connect(self._on_import_sql)
        tb.addWidget(self.import_btn)

        # 计数(共 N 张)— 显示在工具栏右侧
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        self.count_label.setStyleSheet("font-size: 12px;")
        tb.addWidget(self.count_label)

        tb.addStretch()

        # 删除全部(危险操作,放最后,字体略小,带确认弹窗)
        self.del_all_btn = QPushButton(tr("tables_tab.delete_all"))
        self.del_all_btn.setObjectName("Ghost")
        self.del_all_btn.setIcon(qta.icon("mdi6.trash-can-outline", color="#ef4444"))
        self.del_all_btn.clicked.connect(self._on_delete_all)
        tb.addWidget(self.del_all_btn)

        layout.addWidget(toolbar)

        # Splitter: 左表列表 / 右表详情
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)
        layout.addWidget(self.splitter, 1)

        # Left: table list
        left = QFrame()
        left.setMinimumWidth(200)
        left.setMaximumWidth(320)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8, 8, 8, 8)
        ll.setSpacing(4)

        # 搜索框(按表名模糊)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(tr("tables_tab.search.placeholder"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._on_search_changed)
        ll.addWidget(self.search_edit)

        # 标签 filter combo + 标签管理按钮
        tag_row = QHBoxLayout()
        tag_row.setSpacing(4)
        self.tag_combo = QComboBox()
        self.tag_combo.setMinimumWidth(0)
        self.tag_combo.currentIndexChanged.connect(self._on_tag_filter_changed)
        tag_row.addWidget(self.tag_combo, 1)
        new_tag_btn = QPushButton()
        new_tag_btn.setIcon(qta.icon("mdi6.tag-plus-outline", color="#94a3b8"))
        new_tag_btn.setFixedSize(28, 28)
        new_tag_btn.setToolTip(tr("tables_tab.tag.new"))
        new_tag_btn.clicked.connect(self._on_new_tag)
        tag_row.addWidget(new_tag_btn)
        manage_tag_btn = QPushButton()
        manage_tag_btn.setIcon(qta.icon("mdi6.tag-outline", color="#94a3b8"))
        manage_tag_btn.setFixedSize(28, 28)
        manage_tag_btn.setToolTip(tr("tables_tab.tag.manage"))
        manage_tag_btn.clicked.connect(self._on_manage_tags)
        tag_row.addWidget(manage_tag_btn)
        ll.addLayout(tag_row)

        self.table_list = QListWidget()
        self.table_list.itemSelectionChanged.connect(self._on_selection)
        self.table_list.itemDoubleClicked.connect(lambda _: self._on_edit_current())
        ll.addWidget(self.table_list)

        # Right: detail
        right = QFrame()
        self._right_layout = QVBoxLayout(right)
        self._right_layout.setContentsMargins(16, 8, 16, 8)
        self._right_layout.setSpacing(8)

        # Detail header
        self.detail_header = QFrame()
        dh = QHBoxLayout(self.detail_header)
        dh.setContentsMargins(0, 4, 0, 4)
        self.detail_name = QLabel("—")
        self.detail_name.setStyleSheet("font-size: 16px; font-weight: 700;")
        dh.addWidget(self.detail_name)
        dh.addStretch()

        self.edit_btn = QPushButton()
        self.edit_btn.setIcon(qta.icon("mdi6.pencil", color="#94a3b8"))
        self.edit_btn.setFixedSize(32, 32)
        self.edit_btn.clicked.connect(self._on_edit_current)
        dh.addWidget(self.edit_btn)

        self.del_btn = QPushButton()
        self.del_btn.setIcon(qta.icon("mdi6.trash-can-outline", color="#ef4444"))
        self.del_btn.setFixedSize(32, 32)
        self.del_btn.clicked.connect(self._on_delete_current)
        dh.addWidget(self.del_btn)
        self._right_layout.addWidget(self.detail_header)

        # Comment
        self.detail_comment = QLabel("")
        self.detail_comment.setObjectName("Secondary")
        self.detail_comment.setWordWrap(True)
        self._right_layout.addWidget(self.detail_comment)

        # DDL preview
        ddl_label = QLabel(tr("tables_tab.ddl"))
        ddl_label.setObjectName("Muted")
        ddl_label.setStyleSheet("font-size: 11px;")
        self._right_layout.addWidget(ddl_label)

        self.ddl_view = QTextEdit()
        self.ddl_view.setReadOnly(True)
        self.ddl_view.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 12px; "
            "background: #0b1220; color: #e2e8f0; border: 1px solid #334155; border-radius: 6px;"
        )
        self._sql_highlighter = SqlHighlighter(self.ddl_view.document())
        self._right_layout.addWidget(self.ddl_view, 1)

        # Empty state for right — 纯展示,无按钮(新建走工具栏)
        self.empty = EmptyState(
            icon_name="mdi6.table",
            title=tr("tables_tab.empty.title"),
            description=tr("tables_tab.empty.desc"),
            primary_text="",  # 不显示按钮
        )
        # 即便没按钮,连一下信号也兼容
        self.empty.primary_clicked.connect(self._on_add)
        self._right_layout.addWidget(self.empty)
        self.empty.hide()

        # Initial state
        self.detail_header.hide()
        self.detail_comment.hide()
        self.ddl_view.hide()
        self.ddl_label = ddl_label
        self.ddl_label.hide()

        self.splitter.addWidget(left)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([240, 600])

    def retranslate(self) -> None:
        self.add_btn.setText(tr("tables_tab.add_table"))
        self.import_btn.setText(tr("action.import"))
        self.import_btn.setToolTip(tr("dlg.import_sql.title"))
        self.del_all_btn.setText(tr("tables_tab.delete_all"))
        if self._search_kw:
            pass  # search edit 的 placeholder 已固定
        self.search_edit.setPlaceholderText(tr("tables_tab.search.placeholder"))
        if self._current_table:
            self._show_detail(self._current_table)
        else:
            self.empty.title_label.setText(tr("tables_tab.empty.title"))
            self.empty.desc_label.setText(tr("tables_tab.empty.desc"))
        self.ddl_label.setText(tr("tables_tab.ddl"))

    def showEvent(self, event):
        # 跨 tab 同步:从其他 tab(SQL 生成器等)创建/修改 tag 后,切到本 tab 时自动 refresh
        super().showEvent(event)
        # 只 connect 一次 — PySide 重复 disconnect 没连过的 slot 会 emit RuntimeWarning
        # (C 端 warning,Python try/except 抓不到),所以用 flag 控制只连一次
        if not self._bus_connected:
            try:
                reg().bus.tag_changed.connect(self._on_tag_changed_external)
                self._bus_connected = True
            except Exception:
                pass
        if self._project_id is not None:
            self.refresh()

    def _on_tag_changed_external(self) -> None:
        """SQL 生成器(或别处)改了 tag,刷新本 tab 列表 / tag combo"""
        if self._project_id is None:
            return
        self.refresh()

    def set_project(self, project_id: int) -> None:
        self._project_id = project_id
        self.refresh()

    def refresh(self) -> None:
        if self._project_id is None:
            return
        # 缓存全量数据
        self._all_tables = reg().table_service.list_by_project(self._project_id)
        self._table_tags_map = reg().tag_repo.get_table_tags_map(self._project_id)
        # 刷新标签 combo
        self._refresh_tag_combo()
        # 渲染(走过滤逻辑)
        self._render_table_list()

    def _refresh_tag_combo(self) -> None:
        """重新加载 tag combo(保留当前选中的 tag)"""
        self.tag_combo.blockSignals(True)
        cur = self._tag_filter_id
        self.tag_combo.clear()
        self.tag_combo.addItem(tr("tables_tab.tag.all"), None)
        for t in reg().tag_repo.list_by_project(self._project_id):
            n = len(reg().tag_repo.get_table_ids_for_tag(t.id))
            self.tag_combo.addItem(f"{t.name}  ({n})", t.id)
        # 恢复选中
        if cur is not None:
            for i in range(self.tag_combo.count()):
                if self.tag_combo.itemData(i) == cur:
                    self.tag_combo.setCurrentIndex(i)
                    break
        self.tag_combo.blockSignals(False)

    def _render_table_list(self) -> None:
        """按当前 _search_kw + _tag_filter_id 过滤,渲染 table_list"""
        self.table_list.clear()
        tables = self._all_tables
        kw = self._search_kw.strip().lower()
        tag_id = self._tag_filter_id

        # 过滤
        filtered = []
        for t in tables:
            if kw and kw not in t.name.lower():
                continue
            if tag_id is not None:
                # 只保留带这个 tag 的表
                tags = self._table_tags_map.get(t.id, [])
                if not any(tag.id == tag_id for tag in tags):
                    continue
            filtered.append(t)

        # 更新计数
        n_total = len(tables)
        n_show = len(filtered)
        if kw or tag_id is not None:
            self.count_label.setText(
                tr("tables_tab.total_count_filtered").format(n=n_show, total=n_total)
            )
        else:
            self.count_label.setText(tr("tables_tab.total_count").format(n=n_total))

        if n_total == 0:
            self.empty.show()
            self.detail_header.hide()
            self.detail_comment.hide()
            self.ddl_view.hide()
            self.ddl_label.hide()
            return
        self.empty.hide()
        if n_show == 0:
            # 有表但被过滤完了 — 给个"无匹配"提示
            self.detail_header.hide()
            self.detail_comment.hide()
            self.ddl_view.hide()
            self.ddl_label.hide()
            self.empty.show()
            self.empty.title_label.setText(tr("tables_tab.empty.filtered.title"))
            self.empty.desc_label.setText(tr("tables_tab.empty.filtered.desc"))
            return

        for t in filtered:
            tags = self._table_tags_map.get(t.id, [])
            tag_str = ""
            if tags:
                tag_str = "  ".join(f"🏷{tg.name}" for tg in tags[:3])
                if len(tags) > 3:
                    tag_str += f"  +{len(tags) - 3}"
            label = f"📄 {t.name}  ({len(t.columns)})"
            if tag_str:
                label += f"\n    {tag_str}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, t.id)
            # tooltip 显示完整 tag 列表
            if tags:
                item.setToolTip("标签: " + ", ".join(tg.name for tg in tags))
            self.table_list.addItem(item)
        # 默认选第一个
        if self.table_list.count() > 0:
            self.table_list.setCurrentRow(0)

    # ============== 搜索 / 标签过滤 ==============
    def _on_search_changed(self, text: str) -> None:
        self._search_kw = text
        self._render_table_list()

    def _on_tag_filter_changed(self, _idx: int) -> None:
        self._tag_filter_id = self.tag_combo.currentData()
        self._render_table_list()

    # ============== 标签管理 ==============
    def _on_new_tag(self) -> None:
        if self._project_id is None:
            return
        dlg = TagDialog(self._project_id, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            tag = dlg.get_tag()
            try:
                tid = reg().tag_repo.create(tag)
                # 关联选中的表
                for table_id in dlg.get_selected_table_ids():
                    reg().tag_repo.add_table_to_tag(tid, table_id)
                show_toast(
                    tr("toast.saved").format(name=tag.name), "success"
                )
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

    def _on_manage_tags(self) -> None:
        if self._project_id is None:
            return
        # 简单版:弹个菜单选 edit / delete
        from PySide6.QtWidgets import QMenu
        tags = reg().tag_repo.list_by_project(self._project_id)
        if not tags:
            show_toast(tr("tables_tab.tag.no_tags"), "info")
            return
        menu = QMenu(self)
        for t in tags:
            n = len(reg().tag_repo.get_table_ids_for_tag(t.id))
            act = menu.addAction(f"🏷 {t.name}  ({n})")
            # 用 lambda 捕获 t 的 id
            act.triggered.connect(lambda _checked=False, tag=t: self._open_tag_for_edit(tag))
        menu.exec(self.cursor().pos())

    def _open_tag_for_edit(self, tag) -> None:
        dlg = TagDialog(self._project_id, tag=tag, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            try:
                new_tag = dlg.get_tag()
                reg().tag_repo.update(new_tag)
                reg().tag_repo.set_tag_tables(new_tag.id, dlg.get_selected_table_ids())
                show_toast(
                    tr("toast.saved").format(name=new_tag.name), "success"
                )
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

    def _on_selection(self) -> None:
        items = self.table_list.selectedItems()
        if not items:
            self._current_table = None
            self.empty.show()
            self.detail_header.hide()
            self.detail_comment.hide()
            self.ddl_view.hide()
            self.ddl_label.hide()
            return
        tid = items[0].data(Qt.ItemDataRole.UserRole)
        t = reg().table_service.get(tid)
        if t:
            self._current_table = t
            self._show_detail(t)
            self.empty.hide()

    def _show_detail(self, t: Table) -> None:
        self.detail_header.show()
        self.detail_comment.show()
        self.ddl_view.show()
        self.ddl_label.show()
        self.detail_name.setText(t.name)
        self.detail_comment.setText(t.comment or "")
        self.ddl_view.setPlainText(t.ddl_text or "")

    def _on_add(self) -> None:
        if self._project_id is None:
            return
        dlg = TableDialog(project_id=self._project_id, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            t = dlg.get_table()
            try:
                reg().table_service.create(
                    self._project_id, t.name, t.comment, t.columns,
                )
                show_toast(tr("toast.saved"), "success")
                self.refresh()
            except ValueError as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

    def _on_edit_current(self) -> None:
        if not self._current_table:
            return
        dlg = TableDialog(table=self._current_table, project_id=self._project_id, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            t = dlg.get_table()
            try:
                reg().table_service.update(
                    self._current_table.id, t.name, t.comment, t.columns,
                )
                show_toast(tr("toast.saved"), "success")
                self.refresh()
            except ValueError as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

    def _on_delete_current(self) -> None:
        if not self._current_table:
            return
        if QMessageBox.question(
            self, tr("dlg.confirm.delete_table.title"),
            tr("dlg.confirm.delete_table.msg").format(name=self._current_table.name)
        ) == QMessageBox.StandardButton.Yes:
            try:
                reg().table_service.delete(self._current_table.id)
                show_toast(tr("toast.deleted"), "success")
                self._current_table = None
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

    def _on_delete_all(self) -> None:
        if self._project_id is None:
            return
        tables = reg().table_service.list_by_project(self._project_id)
        if not tables:
            show_toast(tr("tables_tab.delete_all.empty"), "info")
            return
        n = len(tables)
        if QMessageBox.question(
            self,
            tr("tables_tab.delete_all.title"),
            tr("tables_tab.delete_all.msg").format(n=n),
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            reg().table_service.delete_by_project(self._project_id)
            show_toast(tr("tables_tab.delete_all.done").format(n=n), "success")
            self._current_table = None
            self.refresh()
        except Exception as e:
            QMessageBox.warning(self, tr("common.error"), str(e))

    def _on_import_sql(self) -> None:
        """从 SQL 文件批量导入表结构。"""
        if self._project_id is None:
            return
        dlg = ImportSqlDialog(parent=self, default_dialect="postgres")
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        selected = dlg.get_selected_tables()
        if not selected:
            return

        ok, fail, first_err = 0, 0, ""
        for pt in selected:
            try:
                cols = [
                    Column(
                        name=c.name, type=c.type,
                        nullable=c.nullable, default=c.default,
                        pk=c.pk, comment=c.comment,
                    )
                    for c in pt.columns
                ]
                reg().table_service.create(
                    self._project_id, pt.name, "", cols,
                )
                ok += 1
            except Exception as e:
                fail += 1
                if not first_err:
                    first_err = f"{pt.name}: {e}"
        if fail == 0:
            show_toast(tr("dlg.import_sql.done").format(n=ok), "success")
        else:
            show_toast(
                tr("dlg.import_sql.partial").format(ok=ok, fail=fail),
                "warning", 4000,
            )
            if first_err:
                QMessageBox.warning(
                    self, tr("dlg.import_sql.fail"), first_err
                )
        self.refresh()

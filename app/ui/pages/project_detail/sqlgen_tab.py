"""SQL Generator Tab — 批量为多张表生成 INSERT/DELETE/Import-CSV/Export-CSV

特性:
- 整行点击 = 切换选中(无 checkbox,MultiSelection 模式)
- 选中行整行深蓝(走 QSS :selected)
- 顶部显示 已选 N / 总 M
- Import/Export 选项固定一行显示(不弹不收)
- 输出无注释、无空行,直接多行替换
"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QFrame, QCheckBox,
    QRadioButton, QButtonGroup, QPlainTextEdit, QListWidget,
    QListWidgetItem, QMessageBox, QWidget, QSplitter,
    QAbstractItemView, QLineEdit, QComboBox,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.ui.widgets import EmptyState, show_toast, SqlHighlighter
from app.ui.dialogs import SqlSnippetDialog
from app.services.registry import reg
from app.core.sqlgen import (
    generate_insert, generate_delete, generate_copy, generate_csv_export,
    generate_export_insert, generate_create,
)


class _TableListItem(QListWidgetItem):
    """纯点击切换选中的表项 — 不要 checkbox。"""
    def __init__(self, table, parent=None):
        super().__init__(parent)
        self.table = table
        self.setText(f"📄 {table.name}    ({len(table.columns)} cols)")
        self.setData(Qt.ItemDataRole.UserRole, table.id)
        # 默认不选中
        self.setSelected(False)


class SqlGenTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_id: Optional[int] = None
        self._tables: list = []
        # 过滤状态
        self._search_kw: str = ""
        self._tag_filter_id: Optional[int] = None
        self._all_tables: list = []  # 缓存
        # 跨过滤/搜索的持久化选集(用 table id 集合,跨搜索/标签保留)
        self._selected_ids: set[int] = set()
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)
        layout.addWidget(self.splitter, 1)

        # ====== 左:表列表 + 操作 + 生成 ======
        left = QFrame()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(12, 12, 12, 12)
        ll.setSpacing(8)

        # 表列表头(已选 N / 总 M + 全选/反选)
        tbl_hdr = QHBoxLayout()
        tbl_hdr.addWidget(QLabel(tr("sqlgen_tab.tables")))
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        self.count_label.setStyleSheet("font-size: 11px; margin-left: 8px;")
        tbl_hdr.addWidget(self.count_label)
        tbl_hdr.addStretch()
        self.sel_all_btn = QPushButton(tr("action.select_all"))
        self.sel_all_btn.setObjectName("Ghost")
        self.sel_all_btn.clicked.connect(self._on_select_all)
        tbl_hdr.addWidget(self.sel_all_btn)
        self.desel_all_btn = QPushButton(tr("action.deselect_all"))
        self.desel_all_btn.setObjectName("Ghost")
        self.desel_all_btn.clicked.connect(self._on_deselect_all)
        tbl_hdr.addWidget(self.desel_all_btn)
        ll.addLayout(tbl_hdr)

        # 搜索框 + 标签过滤
        filter_row = QHBoxLayout()
        filter_row.setSpacing(4)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(tr("sqlgen_tab.search.placeholder"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._on_search_changed)
        filter_row.addWidget(self.search_edit, 1)
        self.tag_combo = QComboBox()
        self.tag_combo.setMinimumWidth(140)
        self.tag_combo.currentIndexChanged.connect(self._on_tag_filter_changed)
        filter_row.addWidget(self.tag_combo)
        ll.addLayout(filter_row)

        # 表列表:MultiSelection 模式 → 点击切换(无 checkbox)
        self.table_list = QListWidget()
        self.table_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.table_list.itemSelectionChanged.connect(self._on_list_selection_changed)
        ll.addWidget(self.table_list, 1)

        # 操作复选框
        op_label = QLabel(tr("sqlgen_tab.ops"))
        op_label.setStyleSheet("font-weight: 600;")
        ll.addWidget(op_label)
        self.op_create = QCheckBox("CREATE TABLE DDL")
        self.op_create.setToolTip(tr("sqlgen_tab.op_create.tip"))
        self.op_insert = QCheckBox("INSERT")
        self.op_delete = QCheckBox("DELETE")
        self.op_import = QCheckBox("Import CSV/TSV")
        self.op_export = QCheckBox("Export CSV/TSV")
        # Export Insert SQL 跟 DB 链接选同一行(checkbox + combo 紧邻)
        self.op_export_insert = QCheckBox("Export Insert SQL (dump)")
        self.ei_link_combo = QComboBox()
        self.ei_link_combo.setMinimumWidth(220)
        self.ei_link_combo.currentIndexChanged.connect(self._on_ei_link_changed)
        ei_row = QHBoxLayout()
        ei_row.setSpacing(8)
        ei_row.addWidget(self.op_export_insert)
        ei_row.addWidget(QLabel(tr("sqlgen_tab.ei.db_link")))
        ei_row.addWidget(self.ei_link_combo)
        ei_row.addStretch()

        ll.addWidget(self.op_create)
        ll.addWidget(self.op_insert)
        ll.addWidget(self.op_delete)
        ll.addLayout(ei_row)
        ll.addWidget(self.op_import)
        ll.addWidget(self.op_export)

        # === Import/Export 配置:固定一行(始终可见,不弹不收) ===
        io_row = QHBoxLayout()
        io_row.setSpacing(12)
        # 格式
        io_row.addWidget(QLabel(tr("sqlgen_tab.io.format")))
        self.fmt_csv = QRadioButton("CSV")
        self.fmt_tsv = QRadioButton("TSV")
        self.fmt_csv.setChecked(True)
        self.fmt_group = QButtonGroup(self)
        self.fmt_group.addButton(self.fmt_csv, 0)
        self.fmt_group.addButton(self.fmt_tsv, 1)
        io_row.addWidget(self.fmt_csv)
        io_row.addWidget(self.fmt_tsv)
        # 目录(默认空,生成 SQL 时只拼文件名;填了就用这个目录)
        io_row.addWidget(QLabel(tr("sqlgen_tab.io.dir")))
        self.io_dir = QLineEdit()
        self.io_dir.setPlaceholderText(tr("sqlgen_tab.io.dir.placeholder"))
        self.io_dir.setMaximumWidth(180)
        self.io_dir.setToolTip(tr("sqlgen_tab.io.dir.tip"))
        io_row.addWidget(self.io_dir)
        # 列名 / 表头 复选
        self.with_columns = QCheckBox(tr("sqlgen_tab.io.with_columns"))
        self.with_columns.setChecked(True)
        self.with_columns.setToolTip(tr("sqlgen_tab.io.with_columns.tip"))
        io_row.addWidget(self.with_columns)
        self.with_header = QCheckBox(tr("sqlgen_tab.io.with_header"))
        self.with_header.setChecked(True)
        io_row.addWidget(self.with_header)
        ll.addLayout(io_row)

        # 生成按钮
        gen_btn = QPushButton(tr("sqlgen_tab.generate"))
        gen_btn.setObjectName("Primary")
        gen_btn.setIcon(qta.icon("mdi6.play", color="white"))
        gen_btn.clicked.connect(self._on_generate)
        ll.addWidget(gen_btn)

        # ====== 右:SQL 输出 ======
        right = QFrame()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(12, 12, 12, 12)
        rl.setSpacing(8)

        h = QHBoxLayout()
        self.output_label = QLabel(tr("sqlgen_tab.output"))
        h.addWidget(self.output_label)
        h.addStretch()
        # 创建标签:用当前选中的表
        create_tag_btn = QPushButton(tr("sqlgen_tab.create_tag"))
        create_tag_btn.setObjectName("Ghost")
        create_tag_btn.setIcon(qta.icon("mdi6.tag-plus-outline", color="#94a3b8"))
        create_tag_btn.setToolTip(tr("sqlgen_tab.create_tag.tip"))
        create_tag_btn.clicked.connect(self._on_create_tag_from_selection)
        h.addWidget(create_tag_btn)
        copy_btn = QPushButton(tr("action.copy"))
        copy_btn.setObjectName("Ghost")
        copy_btn.setIcon(qta.icon("mdi6.content-copy", color="#94a3b8"))
        copy_btn.clicked.connect(self._on_copy)
        h.addWidget(copy_btn)
        save_btn = QPushButton(tr("action.save"))
        save_btn.setObjectName("Ghost")
        save_btn.setIcon(qta.icon("mdi6.content-save", color="#94a3b8"))
        save_btn.clicked.connect(self._on_save)
        h.addWidget(save_btn)
        rl.addLayout(h)

        self.sql_view = QPlainTextEdit()
        self.sql_view.setReadOnly(True)
        self.sql_view.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 12px; "
            "background: #0b1220; color: #e2e8f0; border: 1px solid #334155; border-radius: 6px;"
        )
        self._sql_highlighter = SqlHighlighter(self.sql_view.document())
        rl.addWidget(self.sql_view, 1)

        self.splitter.addWidget(left)
        self.splitter.addWidget(right)
        self.splitter.setSizes([360, 800])

    # ============== 数据装载 ==============
    def set_project(self, project_id: int) -> None:
        self._project_id = project_id
        self._refresh_tables()
        self._refresh_db_links()

    def _refresh_db_links(self) -> None:
        """加载 db_links 列表到 combo(供 Export Insert SQL 选 link)"""
        try:
            links = reg().db_link_repo.list_all()
        except Exception:
            links = []
        self.ei_link_combo.blockSignals(True)
        self.ei_link_combo.clear()
        self.ei_link_combo.addItem(tr("sqlgen_tab.ei.no_link"), None)
        for link in links:
            label = f"{link.name}  [{tr(f'db_link.type.{link.db_type}')}]"
            self.ei_link_combo.addItem(label, link.id)
        self.ei_link_combo.blockSignals(False)
        self._on_ei_link_changed()

    def _on_ei_link_changed(self) -> None:
        """选 link 的回调用(预留:以后这里可以做一些上下文相关 UI 更新)"""
        pass

    def _refresh_tables(self) -> None:
        if self._project_id is None:
            return
        # 缓存全量表
        self._all_tables = reg().table_service.list_by_project(self._project_id)
        # 切 project 时重置过滤 + 选集(避免跨 project 残留)
        self._search_kw = ""
        if hasattr(self, "search_edit"):
            self.search_edit.blockSignals(True)
            self.search_edit.setText("")
            self.search_edit.blockSignals(False)
        self._tag_filter_id = None
        self._selected_ids.clear()
        # 刷新标签 combo
        self._refresh_tag_combo()
        # 渲染
        self._render_table_list()

    def _refresh_tag_combo(self) -> None:
        """重新加载 tag combo(保留当前选中的 tag)"""
        if not hasattr(self, "tag_combo"):
            return
        cur = self._tag_filter_id
        self.tag_combo.blockSignals(True)
        self.tag_combo.clear()
        self.tag_combo.addItem(tr("sqlgen_tab.tag.all"), None)
        if self._project_id is not None:
            try:
                tags = reg().tag_repo.list_by_project(self._project_id)
            except Exception:
                tags = []
            for t in tags:
                n = len(reg().tag_repo.get_table_ids_for_tag(t.id))
                self.tag_combo.addItem(f"{t.name}  ({n})", t.id)
        if cur is not None:
            for i in range(self.tag_combo.count()):
                if self.tag_combo.itemData(i) == cur:
                    self.tag_combo.setCurrentIndex(i)
                    break
        self.tag_combo.blockSignals(False)

    def _render_table_list(self) -> None:
        """按 _search_kw + _tag_filter_id 过滤并渲染

        选集跨过滤/搜索持久化:_selected_ids(set<int>)是唯一真理源,
        即使某次过滤让表从视图消失,它的 id 还在 _selected_ids 里。
        重新出现时(比如改回搜索关键字)自动 setSelected。
        """
        tables = self._all_tables
        kw = self._search_kw.strip().lower()
        tag_id = self._tag_filter_id

        # 过滤
        if tag_id is not None:
            tags_map = reg().tag_repo.get_table_tags_map(self._project_id)
        else:
            tags_map = {}

        filtered = []
        for t in tables:
            if kw and kw not in t.name.lower():
                continue
            if tag_id is not None:
                tags = tags_map.get(t.id, [])
                if not any(tag.id == tag_id for tag in tags):
                    continue
            filtered.append(t)
        self._tables = filtered

        self.table_list.blockSignals(True)
        self.table_list.clear()
        for t in filtered:
            item = _TableListItem(t)
            self.table_list.addItem(item)
        # 跨过滤/搜索持久化:_selected_ids 是真理源,视图重渲后按它恢复 setSelected
        for i in range(self.table_list.count()):
            it = self.table_list.item(i)
            if it.table.id in self._selected_ids:
                it.setSelected(True)
        # 只清理"表被删"(在 _all_tables 里都没了)的 id — 不能清当前不可见的(搜索过滤)!
        # 否则搜 "a" 选 a1, 搜 "b" 选 b1, 清空搜索 → a1 会被 &=visible_ids 误踢
        all_ids = {t.id for t in self._all_tables}
        self._selected_ids &= all_ids
        self.table_list.blockSignals(False)
        self._update_count()

    def retranslate(self) -> None:
        self.output_label.setText(tr("sqlgen_tab.output"))
        if hasattr(self, "search_edit"):
            self.search_edit.setPlaceholderText(tr("sqlgen_tab.search.placeholder"))
        self._update_count()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_tables()

    # ============== 槽 ==============
    def _on_select_all(self) -> None:
        """全选:把当前可见的表都加进 _selected_ids(跨过滤不丢)"""
        for i in range(self.table_list.count()):
            self._selected_ids.add(self.table_list.item(i).table.id)
        # 刷新选中状态
        self.table_list.blockSignals(True)
        for i in range(self.table_list.count()):
            self.table_list.item(i).setSelected(True)
        self.table_list.blockSignals(False)
        self._update_count()

    def _on_deselect_all(self) -> None:
        """全不选:从 _selected_ids 移除当前可见表(不丢跨过滤的其它选中)"""
        for i in range(self.table_list.count()):
            self._selected_ids.discard(self.table_list.item(i).table.id)
        self.table_list.blockSignals(True)
        for i in range(self.table_list.count()):
            self.table_list.item(i).setSelected(False)
        self.table_list.blockSignals(False)
        self._update_count()

    def _on_list_selection_changed(self) -> None:
        """用户在 list 里点选/取消勾:同步 _selected_ids(以 setSelected 反推 — 跨过滤持久化)"""
        for i in range(self.table_list.count()):
            item = self.table_list.item(i)
            if item.isSelected():
                self._selected_ids.add(item.table.id)
            else:
                self._selected_ids.discard(item.table.id)
        self._update_count()

    def _update_count(self) -> None:
        total = self.table_list.count()
        # 选集总数用 _selected_ids(跨过滤 — 即使当前视图里看不到某张选中的表,也算)
        n_sel_all = len(self._selected_ids)
        if self._search_kw or self._tag_filter_id is not None:
            self.count_label.setText(
                tr("sqlgen_tab.count_filtered").format(
                    sel=n_sel_all, shown=total, total=len(self._all_tables)
                )
            )
        else:
            self.count_label.setText(f"({n_sel_all} / {total})")

    def _selected_tables(self) -> list:
        """返回当前选中的表(走持久化 _selected_ids,不只看当前视图)"""
        id_to_table = {t.id: t for t in self._all_tables}
        out = []
        for tid in self._selected_ids:
            if tid in id_to_table:
                out.append(id_to_table[tid])
        return out

    # ============== 搜索 / 标签过滤 ==============
    def _on_search_changed(self, text: str) -> None:
        self._search_kw = text
        self._render_table_list()

    def _on_tag_filter_changed(self, _idx: int) -> None:
        self._tag_filter_id = self.tag_combo.currentData()
        self._render_table_list()

    # ============== 创建标签(用当前选中的表)==============
    def _on_create_tag_from_selection(self) -> None:
        if self._project_id is None:
            return
        selected = self._selected_tables()
        if not selected:
            show_toast(tr("sqlgen_tab.create_tag.empty"), "warning")
            return
        from app.ui.dialogs import TagDialog
        dlg = TagDialog(
            self._project_id,
            preselected_table_ids=[t.id for t in selected],
            parent=self,
        )
        if dlg.exec() == dlg.DialogCode.Accepted:
            tag = dlg.get_tag()
            try:
                tid = reg().tag_repo.create(tag)
                for table_id in dlg.get_selected_table_ids():
                    reg().tag_repo.add_table_to_tag(tid, table_id)
                show_toast(
                    tr("sqlgen_tab.create_tag.done").format(name=tag.name, n=len(selected)),
                    "success",
                )
                # 刷新标签 combo(用户可能想立即用新 tag 过滤)
                self._refresh_tag_combo()
                # 通知其它 tab(表结构页)刷新 tag combo / 列表
                try:
                    reg().bus.tag_changed.emit()
                except Exception:
                    pass
            except Exception as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

    def _io_config_kwargs(self) -> dict:
        return dict(
            fmt="tsv" if self.fmt_tsv.isChecked() else "csv",
            with_columns=self.with_columns.isChecked(),
            with_header=self.with_header.isChecked(),
            directory=self.io_dir.text().strip().rstrip("\\/"),  # 去掉末尾分隔符
        )

    def _resolve_io_path(self, t_name: str, direction: str) -> str:
        """根据配置的目录 + 表名 + 格式,生成完整路径。

        - 目录空:只返回 "{t_name}.{fmt}"
        - 目录非空:返回 "{directory}/{t_name}.{fmt}"(用 / 通用,PG 也吃)
        """
        cfg = self._io_config_kwargs()
        base = cfg["directory"]
        if base:
            return f"{base}/{t_name}.{cfg['fmt']}"
        return f"{t_name}.{cfg['fmt']}"

    def _on_generate(self) -> None:
        tables = self._selected_tables()
        if not tables:
            QMessageBox.information(
                self, tr("common.info"),
                tr("sqlgen_tab.no_table_selected"),
            )
            return
        if not any([
            self.op_create.isChecked(),
            self.op_insert.isChecked(),
            self.op_delete.isChecked(),
            self.op_import.isChecked(),
            self.op_export.isChecked(),
            self.op_export_insert.isChecked(),
        ]):
            QMessageBox.information(
                self, tr("common.info"),
                tr("sqlgen_tab.no_op_selected"),
            )
            return

        cfg = self._io_config_kwargs()
        # 每张表 × 每种操作 = 1 行,行内不含换行;块间用单个 \n 分隔 → 无空行
        # 完全去掉任何注释/标题行,只保留可执行 SQL
        lines: list[str] = []
        for t in tables:
            cols = [c.name for c in t.columns]
            pk_col = t.columns[0].name if t.columns else "id"
            if self.op_create.isChecked():
                # CREATE TABLE DDL + (可选) FK DDL + (可选) INDEX DDL
                lines.append(generate_create(
                    table=t.name,
                    raw_ddl=t.ddl_text,
                    fk_ddl=t.fk_ddl_text,
                    index_ddl=t.index_ddl_text,
                ))
            if self.op_insert.isChecked():
                lines.append(generate_insert(t.name, cols))
            if self.op_delete.isChecked():
                lines.append(generate_delete(t.name, pk_col))
            if self.op_import.isChecked():
                lines.append(generate_copy(
                    t.name, cols if cfg["with_columns"] else [],
                    self._resolve_io_path(t.name, "import"),
                    fmt=cfg["fmt"],
                    with_columns=cfg["with_columns"],
                    with_header=cfg["with_header"],
                ))
            if self.op_export.isChecked():
                lines.append(generate_csv_export(
                    t.name, cols if cfg["with_columns"] else [],
                    self._resolve_io_path(t.name, "export"),
                    fmt=cfg["fmt"],
                    with_columns=cfg["with_columns"],
                    with_header=cfg["with_header"],
                ))
            if self.op_export_insert.isChecked():
                # Export Insert SQL(pg_dump / mysqldump / expdp 命令)
                link_id = self.ei_link_combo.currentData()
                if not link_id:
                    lines.append(f"-- [{t.name}] ⚠ 跳过 Export Insert SQL:未选 db_link")
                else:
                    link = reg().db_link_repo.get(link_id)
                    if link is None:
                        lines.append(f"-- [{t.name}] ⚠ 跳过 Export Insert SQL:db_link(id={link_id}) 不存在")
                    else:
                        try:
                            lines.append(generate_export_insert(
                                table=t.name,
                                db_type=link.db_type,
                                host=link.host,
                                port=link.port,
                                username=link.username,
                                password=link.password,
                                database=link.database,
                                schema=link.schema or "public",
                                service_name=link.service_name,
                                out_dir=cfg["directory"] or ".",
                            ))
                        except Exception as e:
                            lines.append(f"-- [{t.name}] ⚠ Export Insert SQL 生成失败: {e}")
        # 直接 join,无任何注释、无空行
        self.sql_view.setPlainText("\n".join(lines))
        show_toast(
            tr("sqlgen_tab.generated").format(n=len(tables)),
            "success", 1500,
        )

    def _on_copy(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.sql_view.toPlainText())
        show_toast(tr("toast.copied"), "success", 1500)

    def _on_save(self) -> None:
        tables = self._selected_tables()
        dlg = SqlSnippetDialog(
            projects=reg().project_service.list_all(),
            default_project_id=self._project_id,
            default_dialect="postgres",
            parent=self,
        )
        if tables:
            dlg.title_edit.setText(
                tr("sqlgen_tab.save_title").format(n=len(tables))
            )
        dlg.sql_edit.setPlainText(self.sql_view.toPlainText())
        if dlg.exec() == dlg.DialogCode.Accepted:
            v = dlg.get_values()
            try:
                reg().sql_lib_service.create(
                    title=v["title"], sql_text=v["sql_text"],
                    description=v["description"], tags=v["tags"],
                    project_id=v["project_id"],
                )
                show_toast(tr("toast.saved"), "success")
            except ValueError as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

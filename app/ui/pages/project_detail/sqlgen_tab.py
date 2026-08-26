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
    QAbstractItemView, QLineEdit,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.ui.widgets import EmptyState, show_toast, SqlHighlighter
from app.ui.dialogs import SqlSnippetDialog
from app.services.registry import reg
from app.core.sqlgen import (
    generate_insert, generate_delete, generate_copy, generate_csv_export,
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

        # 表列表:MultiSelection 模式 → 点击切换(无 checkbox)
        self.table_list = QListWidget()
        self.table_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.table_list.itemSelectionChanged.connect(self._update_count)
        ll.addWidget(self.table_list, 1)

        # 操作复选框
        op_label = QLabel(tr("sqlgen_tab.ops"))
        op_label.setStyleSheet("font-weight: 600;")
        ll.addWidget(op_label)
        self.op_insert = QCheckBox("INSERT")
        self.op_insert.setChecked(True)
        self.op_delete = QCheckBox("DELETE")
        self.op_import = QCheckBox("Import CSV/TSV")
        self.op_export = QCheckBox("Export CSV/TSV")
        ll.addWidget(self.op_insert)
        ll.addWidget(self.op_delete)
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

    def _refresh_tables(self) -> None:
        if self._project_id is None:
            return
        self._tables = reg().table_service.list_by_project(self._project_id)
        self.table_list.blockSignals(True)
        self.table_list.clear()
        for t in self._tables:
            self.table_list.addItem(_TableListItem(t))
        self.table_list.blockSignals(False)
        self._update_count()

    def retranslate(self) -> None:
        self.output_label.setText(tr("sqlgen_tab.output"))
        self._update_count()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_tables()

    # ============== 槽 ==============
    def _on_select_all(self) -> None:
        self.table_list.selectAll()

    def _on_deselect_all(self) -> None:
        self.table_list.clearSelection()

    def _update_count(self) -> None:
        total = self.table_list.count()
        sel = len(self.table_list.selectedItems())
        self.count_label.setText(f"({sel} / {total})")

    def _selected_tables(self) -> list:
        return [it.table for it in self.table_list.selectedItems()]

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
            self.op_insert.isChecked(),
            self.op_delete.isChecked(),
            self.op_import.isChecked(),
            self.op_export.isChecked(),
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

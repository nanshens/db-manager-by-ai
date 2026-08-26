"""Tables Tab — 表结构管理"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QFrame, QListWidget,
    QListWidgetItem, QSplitter, QTextEdit, QMessageBox, QSizePolicy,
    QWidget,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.ui.widgets import EmptyState, show_toast, SqlHighlighter
from app.ui.dialogs import TableDialog, ImportSqlDialog
from app.services.registry import reg
from app.repos.table_repo import Table, Column


class TablesTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_id: Optional[int] = None
        self._current_table: Optional[Table] = None
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
        if self._current_table:
            self._show_detail(self._current_table)
        else:
            self.empty.title_label.setText(tr("tables_tab.empty.title"))
            self.empty.desc_label.setText(tr("tables_tab.empty.desc"))
        self.ddl_label.setText(tr("tables_tab.ddl"))

    def set_project(self, project_id: int) -> None:
        self._project_id = project_id
        self.refresh()

    def refresh(self) -> None:
        if self._project_id is None:
            return
        self.table_list.clear()
        tables = reg().table_service.list_by_project(self._project_id)
        # 更新计数
        n = len(tables)
        self.count_label.setText(tr("tables_tab.total_count").format(n=n))
        if not tables:
            self.empty.show()
            self.detail_header.hide()
            self.detail_comment.hide()
            self.ddl_view.hide()
            self.ddl_label.hide()
            return
        self.empty.hide()
        for t in tables:
            item = QListWidgetItem(f"📄 {t.name}  ({len(t.columns)})")
            item.setData(Qt.ItemDataRole.UserRole, t.id)
            self.table_list.addItem(item)
        # 默认选第一个
        if self.table_list.count() > 0:
            self.table_list.setCurrentRow(0)

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

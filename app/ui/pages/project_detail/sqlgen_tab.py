"""SQL Generator Tab — 批量为多张表生成 INSERT/DELETE/Import-CSV/Export-CSV

特性:
- 整行可点击切换勾选
- 选中行(checked)整行染色,不是 :selected(用自定义 QStyledItemDelegate 实现)
- 顶部显示 已选 N / 总 M
- Import/Export 带配置面板(列名/格式/header)
- 输出无注释无空行,方便复制后多行替换
"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import QBrush, QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QFrame, QCheckBox,
    QRadioButton, QButtonGroup, QPlainTextEdit, QListWidget,
    QListWidgetItem, QMessageBox, QWidget, QSplitter,
    QStyledItemDelegate, QStyle, QApplication,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.ui.widgets import EmptyState, show_toast, SqlHighlighter
from app.ui.dialogs import SqlSnippetDialog
from app.services.registry import reg
from app.core.sqlgen import (
    generate_insert, generate_delete, generate_copy, generate_csv_export,
)


# 选中行(checked)配色
_COLOR_CHECKED_DARK = QColor("#1e3a8a")
_COLOR_CHECKED_LIGHT = QColor("#dbeafe")
_COLOR_CHECKED_FG_DARK = QColor("#ffffff")
_COLOR_CHECKED_FG_LIGHT = QColor("#1e3a8a")


def _is_dark_theme() -> bool:
    return True


class _CheckedRowDelegate(QStyledItemDelegate):
    """自定义 delegate: 根据 checkState 整行染色,覆盖 QSS 的默认 :selected。"""

    def paint(self, painter, option, index):
        # 拿 item 的 check state
        is_checked = (index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked.value)
        # 只在 checked 时画背景;否则让 QSS 默认样式生效
        if is_checked:
            dark = _is_dark_theme()
            bg = _COLOR_CHECKED_DARK if dark else _COLOR_CHECKED_LIGHT
            fg = _COLOR_CHECKED_FG_DARK if dark else _COLOR_CHECKED_FG_LIGHT
            painter.save()
            painter.fillRect(option.rect, bg)
            painter.setPen(fg)
        # 让默认 delegate 画文字 + checkbox
        super().paint(painter, option, index)
        if is_checked:
            painter.restore()

    def sizeHint(self, option, index) -> QSize:
        s = super().sizeHint(option, index)
        s.setHeight(max(s.height(), 28))
        return s


class _TableListItem(QListWidgetItem):
    """可勾选的表项 — 颜色由 _CheckedRowDelegate 渲染。"""
    def __init__(self, table, parent=None):
        super().__init__(parent)
        self.table = table
        self.setFlags(self.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        self.setText(f"📄 {table.name}    ({len(table.columns)} cols)")
        self.setCheckState(Qt.CheckState.Unchecked)
        self.setData(Qt.ItemDataRole.UserRole, table.id)


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

        # 表列表头(带"已选 N / 总 M" + 全选/反选)
        tbl_hdr = QHBoxLayout()
        tbl_hdr.addWidget(QLabel(tr("sqlgen_tab.tables")))
        self.count_label = QLabel("")  # "已选 0 / 总 0"
        self.count_label.setObjectName("Muted")
        self.count_label.setStyleSheet("font-size: 11px; margin-left: 8px;")
        tbl_hdr.addWidget(self.count_label)
        tbl_hdr.addStretch()
        self.sel_all_btn = QPushButton(tr("action.select_all"))
        self.sel_all_btn.setObjectName("Ghost")
        self.sel_all_btn.clicked.connect(self._on_select_all_tables)
        tbl_hdr.addWidget(self.sel_all_btn)
        self.desel_all_btn = QPushButton(tr("action.deselect_all"))
        self.desel_all_btn.setObjectName("Ghost")
        self.desel_all_btn.clicked.connect(self._on_deselect_all_tables)
        tbl_hdr.addWidget(self.desel_all_btn)
        ll.addLayout(tbl_hdr)

        self.table_list = QListWidget()
        # 自定义 delegate: 勾选 = 整行深蓝
        self.table_list.setItemDelegate(_CheckedRowDelegate(self.table_list))
        self.table_list.itemClicked.connect(self._on_item_clicked)
        # itemChanged 在 check state 变化时触发(程序和点击都走)— 强制重绘
        self.table_list.itemChanged.connect(self._on_item_changed)
        ll.addWidget(self.table_list, 1)

        # 操作复选框
        op_label = QLabel(tr("sqlgen_tab.ops"))
        op_label.setStyleSheet("font-weight: 600;")
        ll.addWidget(op_label)
        self.op_insert = QCheckBox("INSERT")
        self.op_insert.setChecked(True)
        self.op_delete = QCheckBox("DELETE")
        self.op_copy = QCheckBox("Import CSV/TSV")
        self.op_export = QCheckBox("Export CSV/TSV")
        # IMPORT/EXPORT 任一勾选时,显示配置面板
        self.op_copy.toggled.connect(self._on_op_toggled)
        self.op_export.toggled.connect(self._on_op_toggled)
        ll.addWidget(self.op_insert)
        ll.addWidget(self.op_delete)
        ll.addWidget(self.op_copy)
        ll.addWidget(self.op_export)

        # === Import/Export 配置面板(默认隐藏) ===
        self.io_config = QFrame()
        self.io_config.setFrameShape(QFrame.Shape.StyledPanel)
        self.io_config.setStyleSheet("background-color: rgba(59, 130, 246, 0.05); border-radius: 4px;")
        iol = QVBoxLayout(self.io_config)
        iol.setContentsMargins(8, 6, 8, 6)
        iol.setSpacing(4)
        iol.addWidget(self._kv_label(tr("sqlgen_tab.io.format")))
        fmt_row = QHBoxLayout()
        self.fmt_csv = QRadioButton("CSV")
        self.fmt_tsv = QRadioButton("TSV")
        self.fmt_csv.setChecked(True)
        self.fmt_group = QButtonGroup(self)
        self.fmt_group.addButton(self.fmt_csv, 0)
        self.fmt_group.addButton(self.fmt_tsv, 1)
        fmt_row.addWidget(self.fmt_csv)
        fmt_row.addWidget(self.fmt_tsv)
        fmt_row.addStretch()
        iol.addLayout(fmt_row)
        self.with_columns = QCheckBox(tr("sqlgen_tab.io.with_columns"))
        self.with_columns.setChecked(True)
        self.with_columns.setToolTip(tr("sqlgen_tab.io.with_columns.tip"))
        iol.addWidget(self.with_columns)
        self.with_header = QCheckBox(tr("sqlgen_tab.io.with_header"))
        self.with_header.setChecked(True)
        iol.addWidget(self.with_header)
        self.io_config.setVisible(False)
        ll.addWidget(self.io_config)

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

    # ----- 工具 -----
    @staticmethod
    def _kv_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("Muted")
        lbl.setStyleSheet("font-size: 11px; font-weight: 600;")
        return lbl

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
    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """整行点击 → 切换勾选(色块由 _CheckedRowDelegate 渲染)。"""
        new_state = (
            Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked
            else Qt.CheckState.Checked
        )
        item.setCheckState(new_state)
        self._update_count()

    def _on_item_changed(self, _item: QListWidgetItem) -> None:
        """check state 变了 → 强制刷新 list(让 delegate 重新画) + 同步计数。"""
        self.table_list.viewport().update()
        self._update_count()

    def _on_select_all_tables(self) -> None:
        self.table_list.blockSignals(True)
        for i in range(self.table_list.count()):
            self.table_list.item(i).setCheckState(Qt.CheckState.Checked)
        self.table_list.blockSignals(False)
        self.table_list.viewport().update()
        self._update_count()

    def _on_deselect_all_tables(self) -> None:
        self.table_list.blockSignals(True)
        for i in range(self.table_list.count()):
            self.table_list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self.table_list.blockSignals(False)
        self.table_list.viewport().update()
        self._update_count()

    def _update_count(self) -> None:
        total = self.table_list.count()
        sel = sum(
            1 for i in range(total)
            if self.table_list.item(i).checkState() == Qt.CheckState.Checked
        )
        self.count_label.setText(f"({sel} / {total})")

    def _on_op_toggled(self) -> None:
        """Import/Export 任一勾选 → 显示配置面板。"""
        self.io_config.setVisible(
            self.op_copy.isChecked() or self.op_export.isChecked()
        )

    def _selected_tables(self) -> list:
        return [
            it.table for i in range(self.table_list.count())
            for it in [self.table_list.item(i)]
            if it.checkState() == Qt.CheckState.Checked
        ]

    def _io_config_kwargs(self) -> dict:
        """Import/Export 共享的格式化参数。"""
        return dict(
            fmt="tsv" if self.fmt_tsv.isChecked() else "csv",
            with_columns=self.with_columns.isChecked(),
            with_header=self.with_header.isChecked(),
        )

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
            self.op_copy.isChecked(),
            self.op_export.isChecked(),
        ]):
            QMessageBox.information(
                self, tr("common.info"),
                tr("sqlgen_tab.no_op_selected"),
            )
            return

        cfg = self._io_config_kwargs()
        lines: list[str] = []
        for t in tables:
            cols = [c.name for c in t.columns]
            pk_col = t.columns[0].name if t.columns else "id"
            if self.op_insert.isChecked():
                lines.append(generate_insert(t.name, cols))
            if self.op_delete.isChecked():
                lines.append(generate_delete(t.name, pk_col))
            if self.op_copy.isChecked():
                # Import: COPY ... FROM (列名可选/格式/header 可选)
                lines.append(
                    f"-- IMPORT {t.name}\n"
                    + generate_copy(
                        t.name, cols if cfg["with_columns"] else [],
                        f"D:\\import\\{t.name}.{cfg['fmt']}",
                        fmt=cfg["fmt"],
                        with_columns=cfg["with_columns"],
                        with_header=cfg["with_header"],
                    )
                )
            if self.op_export.isChecked():
                lines.append(
                    f"-- EXPORT {t.name}\n"
                    + generate_csv_export(
                        t.name, cols if cfg["with_columns"] else [],
                        f"D:\\export\\{t.name}.{cfg['fmt']}",
                        fmt=cfg["fmt"],
                        with_columns=cfg["with_columns"],
                        with_header=cfg["with_header"],
                    )
                )
        # 紧凑:去掉空行 + 合并连续多行
        compact = "\n".join(
            "\n".join(line for line in block.splitlines() if line.strip())
            for block in lines
        )
        self.sql_view.setPlainText(compact)
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

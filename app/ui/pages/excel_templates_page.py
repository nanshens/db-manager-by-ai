"""Excel 解析模板页 — 列表 + 新建/编辑/删除/复制"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QPushButton, QLineEdit, QFrame, QComboBox,
    QListWidget, QListWidgetItem, QMessageBox, QSplitter, QPlainTextEdit, QWidget,
    QApplication, QLabel,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.ui.widgets import EmptyState, show_toast
from app.ui.dialogs import ExcelTemplateDialog, ExcelParseDialog
from app.services.registry import reg
from app.repos.excel_template_repo import ExcelTemplate


class ExcelTemplatesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._new_btn = None
        self._new_btn_empty = None
        self._current: Optional[ExcelTemplate] = None
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
        self.search.setPlaceholderText(tr("excel_tpl.search_placeholder"))
        self.search.setMaximumWidth(320)
        self.search.textChanged.connect(self._on_search)
        tb.addWidget(self.search)

        self.project_filter = QComboBox()
        self.project_filter.setMinimumWidth(160)
        self.project_filter.currentIndexChanged.connect(self.refresh)
        tb.addWidget(self.project_filter)
        tb.addStretch()

        self._new_btn = QPushButton(tr("excel_tpl.new"))
        self._new_btn.setObjectName("Primary")
        self._new_btn.setIcon(qta.icon("mdi6.plus", color="white"))
        self._new_btn.clicked.connect(self._on_new)
        tb.addWidget(self._new_btn)
        layout.addWidget(toolbar)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)
        layout.addWidget(self.splitter, 1)

        left = QFrame()
        left.setMinimumWidth(280)
        left.setMaximumWidth(420)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.tpl_list = QListWidget()
        self.tpl_list.itemSelectionChanged.connect(self._on_selection)
        self.tpl_list.itemDoubleClicked.connect(self._on_edit_current)
        ll.addWidget(self.tpl_list)

        # Right: detail
        right = QFrame()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

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
        self.apply_btn = QPushButton(tr("excel_tpl.action.apply"))
        self.apply_btn.setObjectName("Primary")
        self.apply_btn.setIcon(qta.icon("mdi6.play", color="white"))
        self.apply_btn.clicked.connect(self._on_apply)
        hdr.addWidget(self.apply_btn)
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

        self.body_view = QPlainTextEdit()
        self.body_view.setReadOnly(True)
        self.body_view.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 11px; "
            "background: #0b1220; color: #e2e8f0; border: 1px solid #334155; border-radius: 6px;"
        )
        rl.addWidget(self.body_view, 1)

        self._detail_widgets = [self.title_label, self.meta_label, self.body_view,
                                self.copy_btn, self.apply_btn, self.edit_btn, self.del_btn]
        self._init_state()

        self.empty = EmptyState(
            icon_name="mdi6.file-table-box-outline",
            title=tr("excel_tpl.empty.title"),
            description=tr("excel_tpl.empty.desc"),
            primary_text=tr("excel_tpl.new"),
        )
        self._new_btn_empty = self.empty.primary_btn
        self.empty.primary_clicked.connect(self._on_new)

        # empty 直接放 right 容器,避免生命周期问题
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self.empty)
        right_layout.addStretch()
        right.setLayout(right_layout)

        self.splitter.addWidget(left)
        self.splitter.addWidget(right)
        self.splitter.setSizes([320, 700])

    def retranslate(self) -> None:
        self.search.setPlaceholderText(tr("excel_tpl.search_placeholder"))
        if self._new_btn:
            self._new_btn.setText(tr("excel_tpl.new"))
        if self._new_btn_empty:
            self._new_btn_empty.setText(tr("excel_tpl.new"))

    def _init_state(self) -> None:
        for w in self._detail_widgets:
            w.hide()

    def _refresh_project_filter(self) -> None:
        self.project_filter.blockSignals(True)
        self.project_filter.clear()
        self.project_filter.addItem(tr("sqllib.project_filter"), None)
        self.project_filter.addItem(tr("sqllib.project_filter_global"), "global")
        for p in reg().project_service.list_all():
            self.project_filter.addItem(p.name, p.id)
        self.project_filter.blockSignals(False)

    def refresh(self) -> None:
        self._refresh_project_filter()
        self._on_search()

    def _on_search(self) -> None:
        q = self.search.text().strip()
        cur = self.project_filter.currentData()
        if cur is None:
            tpls = reg().excel_template_service.list(include_global=True)
        elif cur == "global":
            tpls = reg().excel_template_service.list(project_id=None, include_global=True)
        else:
            tpls = reg().excel_template_service.list(project_id=cur, include_global=True)
        if q:
            ql = q.lower()
            tpls = [t for t in tpls
                    if ql in t.template_name.lower()
                    or ql in t.config_sheet_name.lower()
                    or ql in (t.description or "").lower()]
        self.tpl_list.clear()
        self._init_state()
        if not tpls:
            self.empty.show()
            return
        self.empty.hide()
        for t in tpls:
            scope = "🌐" if t.project_id is None else "📁"
            item = QListWidgetItem(f"{scope} {t.template_name}")
            item.setData(Qt.ItemDataRole.UserRole, t.id)
            self.tpl_list.addItem(item)
        if self.tpl_list.count() > 0:
            self.tpl_list.setCurrentRow(0)

    def _on_selection(self) -> None:
        items = self.tpl_list.selectedItems()
        if not items:
            self._current = None
            self._init_state()
            return
        tid = items[0].data(Qt.ItemDataRole.UserRole)
        t = reg().excel_template_service.get(tid)
        self._current = t
        if not t:
            return
        for w in self._detail_widgets:
            w.show()
        self.title_label.setText(t.template_name)
        meta = []
        if t.project_id:
            p = reg().project_service.get(t.project_id)
            if p:
                meta.append(f"📁 {p.name}")
        else:
            meta.append("🌐 全局")
        meta.append(f"使用 {t.use_count} 次")
        if t.description:
            meta.append(f"📝 {t.description}")
        self.meta_label.setText("  ·  ".join(meta))
        # Body:显示配置
        body = (
            f"配置 sheet:    {t.config_sheet_name}\n"
            f"表名列:        {t.table_name_col}\n"
            f"Sheet 名列:    {t.sheet_name_col}\n"
            f"header 行:     {t.header_row}\n"
            f"data 起始行:   {t.data_start_row}\n"
        )
        self.body_view.setPlainText(body)

    def _on_new(self) -> None:
        dlg = ExcelTemplateDialog(
            projects=reg().project_service.list_all(),
            parent=self,
        )
        if dlg.exec() == dlg.DialogCode.Accepted:
            v = dlg.get_template()
            try:
                reg().excel_template_service.create(**v)
                show_toast(tr("toast.saved"), "success")
                self.refresh()
            except ValueError as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

    def _on_edit_current(self) -> None:
        if not self._current:
            return
        dlg = ExcelTemplateDialog(
            template=self._current,
            projects=reg().project_service.list_all(),
            parent=self,
        )
        if dlg.exec() == dlg.DialogCode.Accepted:
            v = dlg.get_template()
            try:
                reg().excel_template_service.update(self._current.id, **v)
                show_toast(tr("toast.saved"), "success")
                self.refresh()
            except ValueError as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

    def _on_delete(self) -> None:
        if not self._current:
            return
        if QMessageBox.question(
            self, tr("action.confirm_delete"),
            f"Delete template \"{self._current.template_name}\"?"
        ) == QMessageBox.StandardButton.Yes:
            try:
                reg().excel_template_service.delete(self._current.id)
                show_toast(tr("toast.deleted"), "success")
                self._current = None
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

    def _on_apply(self) -> None:
        """应用模板解析 Excel 文件"""
        if not self._current:
            return
        dlg = ExcelParseDialog(self._current, parent=self)
        dlg.exec()
        # 使用次数 +1
        reg().excel_template_service.increment_use(self._current.id)
        # 刷新列表
        self.refresh()

    def _on_copy(self) -> None:
        if not self._current:
            return
        # 复制 = 新建同名的"副本"
        dlg = ExcelTemplateDialog(
            projects=reg().project_service.list_all(),
            parent=self,
        )
        dlg.name_edit.setText(f"{self._current.template_name} (副本)")
        dlg.sheet_edit.setText(self._current.config_sheet_name)
        dlg.tn_col_edit.setText(self._current.table_name_col)
        dlg.sn_col_edit.setText(self._current.sheet_name_col)
        dlg.header_spin.setValue(self._current.header_row)
        dlg.data_spin.setValue(self._current.data_start_row)
        if self._current.project_id:
            idx = dlg.project_combo.findData(self._current.project_id)
            if idx >= 0:
                dlg.project_combo.setCurrentIndex(idx)
        dlg.desc_edit.setPlainText(self._current.description or "")
        dlg.setWindowTitle(tr("excel_tpl.action.duplicate"))
        if dlg.exec() == dlg.DialogCode.Accepted:
            v = dlg.get_template()
            try:
                reg().excel_template_service.create(**v)
                show_toast(tr("toast.saved"), "success")
                self.refresh()
            except ValueError as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

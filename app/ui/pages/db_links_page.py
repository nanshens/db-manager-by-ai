"""DB 链接管理页 — 保存 db 连接信息,供 SQL 生成器选 db_link 生成 pg_dump / mysqldump / expdp 命令"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QPushButton, QLineEdit, QFrame, QComboBox,
    QListWidget, QListWidgetItem, QMessageBox, QSplitter, QPlainTextEdit, QWidget,
    QFormLayout, QDialog, QDialogButtonBox, QLabel, QSpinBox, QCheckBox, QApplication,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.ui.widgets import show_toast
from app.services.registry import reg
from app.repos.db_link_repo import DbLink, DEFAULT_PORTS


DB_TYPES = [
    ("postgres", "db_link.type.postgres"),
    ("mysql", "db_link.type.mysql"),
    ("oracle", "db_link.type.oracle"),
]


# ============================================================
# 添加 / 编辑 dialog
# ============================================================
class _DbLinkDialog(QDialog):
    """新增 / 编辑 db 链接"""

    def __init__(self, link: Optional[DbLink] = None, parent=None):
        super().__init__(parent)
        self._link = link
        self.setWindowTitle(
            tr("db_link.edit_title") if link else tr("db_link.new_title")
        )
        self.setMinimumWidth(420)
        self._build()
        if link:
            self._fill_from_link(link)

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)
        form = QFormLayout()
        form.setSpacing(8)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("db_link.name.placeholder"))
        form.addRow(tr("db_link.name"), self.name_edit)

        self.type_combo = QComboBox()
        for code, label_key in DB_TYPES:
            self.type_combo.addItem(tr(label_key), code)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        form.addRow(tr("db_link.db_type"), self.type_combo)

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("127.0.0.1")
        form.addRow(tr("db_link.host"), self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(0, 65535)
        self.port_spin.setValue(5432)
        form.addRow(tr("db_link.port"), self.port_spin)

        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("postgres")
        form.addRow(tr("db_link.username"), self.user_edit)

        self.pwd_edit = QLineEdit()
        self.pwd_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_edit.setPlaceholderText(tr("db_link.password.placeholder"))
        form.addRow(tr("db_link.password"), self.pwd_edit)
        # 显示密码复选
        self.show_pwd_chk = QCheckBox(tr("db_link.password.show"))
        self.show_pwd_chk.toggled.connect(
            lambda on: self.pwd_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        form.addRow("", self.show_pwd_chk)

        self.db_edit = QLineEdit()
        self.db_edit.setPlaceholderText("mydb")
        form.addRow(tr("db_link.database"), self.db_edit)

        self.schema_edit = QLineEdit()
        self.schema_edit.setText("public")
        form.addRow(tr("db_link.schema"), self.schema_edit)

        self.svc_edit = QLineEdit()
        self.svc_edit.setPlaceholderText("ORCLPDB1")
        form.addRow(tr("db_link.service_name"), self.svc_edit)

        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText(tr("db_link.description.placeholder"))
        form.addRow(tr("db_link.description"), self.desc_edit)

        v.addLayout(form)

        # 提示
        tip = QLabel(tr("db_link.password.tip"))
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        v.addWidget(tip)

        # 按钮
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

        self._on_type_changed()

    def _on_type_changed(self):
        db_type = self.type_combo.currentData()
        default_port = DEFAULT_PORTS.get(db_type, 0)
        if default_port and self.port_spin.value() in (0, 5432, 3306, 1521):
            self.port_spin.setValue(default_port)
        # oracle 提示填 service_name
        self.svc_edit.setEnabled(db_type == "oracle")
        # postgres 默认 schema=public, mysql 默认 schema 空(不强制)
        if db_type == "mysql":
            self.schema_edit.setPlaceholderText("（可空,默认当前 db）")
        else:
            self.schema_edit.setPlaceholderText("")

    def _fill_from_link(self, link: DbLink):
        self.name_edit.setText(link.name)
        for i in range(self.type_combo.count()):
            if self.type_combo.itemData(i) == link.db_type:
                self.type_combo.setCurrentIndex(i)
                break
        self.host_edit.setText(link.host)
        self.port_spin.setValue(link.port)
        self.user_edit.setText(link.username)
        self.pwd_edit.setText(link.password)
        self.db_edit.setText(link.database)
        self.schema_edit.setText(link.schema)
        self.svc_edit.setText(link.service_name)
        self.desc_edit.setText(link.description)

    def _on_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, tr("common.error"), tr("db_link.error.no_name"))
            return
        # 名称唯一性
        existing = reg().db_link_repo.get_by_name(name)
        if existing and (not self._link or existing.id != self._link.id):
            QMessageBox.warning(self, tr("common.error"),
                                tr("db_link.error.name_exists").format(name=name))
            return
        self.accept()

    def get_link(self) -> DbLink:
        if self._link:
            link = self._link
        else:
            link = DbLink(
                id=None, name="", db_type="postgres",
                created_at="", updated_at="",
            )
        link.name = self.name_edit.text().strip()
        link.db_type = self.type_combo.currentData()
        link.host = self.host_edit.text().strip()
        link.port = self.port_spin.value()
        link.username = self.user_edit.text().strip()
        link.password = self.pwd_edit.text()
        link.database = self.db_edit.text().strip()
        link.schema = self.schema_edit.text().strip() or "public"
        link.service_name = self.svc_edit.text().strip()
        link.description = self.desc_edit.text().strip()
        return link


# ============================================================
# Page
# ============================================================
class DbLinksPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current: Optional[DbLink] = None
        self._build()
        self.refresh()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # 标题 + 描述
        head = QVBoxLayout()
        head.setSpacing(4)
        title = QLabel(tr("db_link.title"))
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        head.addWidget(title)
        desc = QLabel(tr("db_link.description.hint"))
        desc.setObjectName("Muted")
        desc.setWordWrap(True)
        head.addWidget(desc)
        layout.addLayout(head)

        # Toolbar
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("db_link.search_placeholder"))
        self.search.setMaximumWidth(320)
        self.search.textChanged.connect(self._on_search)
        toolbar.addWidget(self.search)
        toolbar.addStretch()
        new_btn = QPushButton(tr("db_link.new"))
        new_btn.setObjectName("Primary")
        new_btn.setIcon(qta.icon("mdi6.plus", color="white"))
        new_btn.clicked.connect(self._on_new)
        toolbar.addWidget(new_btn)
        layout.addLayout(toolbar)

        # 主体 splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        # 左:列表
        left = QFrame()
        left.setMinimumWidth(280)
        left.setMaximumWidth(420)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.itemSelectionChanged.connect(self._on_selection)
        self.list.itemDoubleClicked.connect(self._on_edit_current)
        ll.addWidget(self.list)
        splitter.addWidget(left)

        # 右:详情
        right = QFrame()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        hdr = QHBoxLayout()
        self.title_label = QLabel("—")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: 700;")
        hdr.addWidget(self.title_label)
        hdr.addStretch()

        edit_btn = QPushButton()
        edit_btn.setIcon(qta.icon("mdi6.pencil", color="#94a3b8"))
        edit_btn.setFixedSize(32, 32)
        edit_btn.clicked.connect(self._on_edit_current)
        hdr.addWidget(edit_btn)

        del_btn = QPushButton()
        del_btn.setIcon(qta.icon("mdi6.trash-can-outline", color="#ef4444"))
        del_btn.setFixedSize(32, 32)
        del_btn.clicked.connect(self._on_delete)
        hdr.addWidget(del_btn)
        rl.addLayout(hdr)

        # 详情字段(用 QFormLayout,只读)
        self.meta_view = QWidget()
        self.meta_layout = QFormLayout(self.meta_view)
        self.meta_layout.setSpacing(6)
        self._meta_labels: dict[str, QLabel] = {}
        for key in ("db_type", "host", "port", "username", "password",
                    "database", "schema", "service_name", "description", "updated_at"):
            lbl = QLabel("—")
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.meta_layout.addRow(tr(f"db_link.{key}") + ":", lbl)
            self._meta_labels[key] = lbl
        rl.addWidget(self.meta_view)

        rl.addStretch()

        # 命令预览(展示基于此 link 的 pg_dump/mysqldump 模板,方便用户验证)
        preview_lbl = QLabel(tr("db_link.preview_label"))
        preview_lbl.setObjectName("Muted")
        rl.addWidget(preview_lbl)
        self.preview_view = QPlainTextEdit()
        self.preview_view.setReadOnly(True)
        self.preview_view.setMaximumHeight(120)
        self.preview_view.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 11px; "
            "background: #0b1220; color: #e2e8f0; border: 1px solid #334155; border-radius: 6px;"
        )
        rl.addWidget(self.preview_view)

        copy_preview_btn = QPushButton(tr("action.copy"))
        copy_preview_btn.setObjectName("Ghost")
        copy_preview_btn.setIcon(qta.icon("mdi6.content-copy", color="#94a3b8"))
        copy_preview_btn.clicked.connect(self._on_copy_preview)
        rl.addWidget(copy_preview_btn)

        self._detail_widgets = [self.title_label, self.meta_view, self.preview_view,
                                edit_btn, del_btn, copy_preview_btn]
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        self._init_state()

    def _init_state(self):
        self._set_detail_enabled(False)

    def _set_detail_enabled(self, on: bool):
        for w in self._detail_widgets:
            w.setEnabled(on)

    # ============== data ==============
    def refresh(self):
        self.list.clear()
        items = reg().db_link_repo.list_all()
        kw = self.search.text().strip().lower()
        for link in items:
            if kw and kw not in link.name.lower() and kw not in link.db_type.lower():
                continue
            type_label = tr(f"db_link.type.{link.db_type}")
            item = QListWidgetItem(f"📦 {link.name}    [{type_label}]")
            item.setData(Qt.ItemDataRole.UserRole, link.id)
            item.setToolTip(
                f"{link.name}\n{type_label}  {link.host}:{link.port or '—'}\n"
                f"{link.username or '—'} @ {link.database or link.schema or '—'}"
            )
            self.list.addItem(item)
        if not items:
            self.title_label.setText("—")
            self._set_detail_enabled(False)
        elif self.list.currentRow() < 0 and self.list.count() > 0:
            self.list.setCurrentRow(0)

    def _on_search(self, _t: str):
        self.refresh()

    def _on_selection(self):
        item = self.list.currentItem()
        if not item:
            self._current = None
            self._set_detail_enabled(False)
            return
        link_id = item.data(Qt.ItemDataRole.UserRole)
        link = reg().db_link_repo.get(link_id)
        if not link:
            return
        self._current = link
        self._set_detail_enabled(True)
        self._render_detail(link)

    def _render_detail(self, link: DbLink):
        self.title_label.setText(link.name)
        for key, lbl in self._meta_labels.items():
            val = getattr(link, key, "") or "—"
            if key == "password":
                lbl.setText("•" * len(val) if val else "—")
            elif key == "db_type":
                lbl.setText(tr(f"db_link.type.{val}"))
            else:
                lbl.setText(str(val))
        # 命令预览
        from app.core.sqlgen import generate_export_insert
        sample_table = f"{link.schema or 'public'}.sample_table"
        try:
            preview = generate_export_insert(
                table="sample_table",
                db_type=link.db_type,
                host=link.host,
                port=link.port,
                username=link.username,
                password="••••" if link.password else "",
                database=link.database,
                schema=link.schema,
                service_name=link.service_name,
            )
        except Exception as e:
            preview = f"（{e}）"
        self.preview_view.setPlainText(preview)

    # ============== actions ==============
    def _on_new(self):
        dlg = _DbLinkDialog(parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            link = dlg.get_link()
            try:
                reg().db_link_repo.create(link)
                show_toast(tr("db_link.toast.created").format(name=link.name), "success")
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

    def _on_edit_current(self):
        if not self._current:
            return
        dlg = _DbLinkDialog(self._current, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            link = dlg.get_link()
            try:
                reg().db_link_repo.update(link)
                show_toast(tr("db_link.toast.updated").format(name=link.name), "success")
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

    def _on_delete(self):
        if not self._current:
            return
        if QMessageBox.question(
            self, tr("common.confirm"),
            tr("db_link.confirm_delete").format(name=self._current.name),
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            reg().db_link_repo.delete(self._current.id)
            show_toast(tr("db_link.toast.deleted").format(name=self._current.name), "success")
            self._current = None
            self.refresh()
        except Exception as e:
            QMessageBox.warning(self, tr("common.error"), str(e))

    def _on_copy_preview(self):
        text = self.preview_view.toPlainText()
        if not text.strip():
            return
        QApplication.clipboard().setText(text)
        show_toast(tr("toast.copied"), "success", 1500)

    # ============== API for other pages (sqlgen) ==============
    def get_all_links(self) -> list[DbLink]:
        return reg().db_link_repo.list_all()

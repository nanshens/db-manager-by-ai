"""Tag 对话框 — 新建 / 编辑表标签

UI:
- 标签名(必填,project 内唯一)
- 描述(可选,多行)
- 表名列表(多行文本框,每行一个表名;输入后自动跟 project 下的表名匹配)
- 右下角显示"匹配 N/M 张"提示
"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QPushButton, QLineEdit, QFrame, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QWidget, QFormLayout,
    QDialog, QDialogButtonBox, QLabel,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.services.registry import reg
from app.repos.tag_repo import Tag, TAG_COLORS


class TagDialog(QDialog):
    """创建 / 编辑标签"""

    def __init__(self, project_id: int, tag: Optional[Tag] = None,
                 preselected_table_ids: Optional[list[int]] = None,
                 parent=None):
        super().__init__(parent)
        self._project_id = project_id
        self._tag = tag
        # 当前已选表 id 集合(从多行文本框解析)
        self._selected_table_ids: set[int] = set()
        # project 下所有表 {name_lower: id} 和 {id: name}
        self._table_map: dict[str, int] = {}
        self._id_to_name: dict[int, str] = {}
        self._load_tables()

        self.setWindowTitle(
            tr("tag.edit_title") if tag else tr("tag.new_title")
        )
        self.setMinimumWidth(520)
        self._build()
        if tag:
            self._fill_from_tag(tag)
        elif preselected_table_ids:
            # 预填(从 SQL 生成器 / 其他地方传入的表 id 列表)
            self._fill_from_table_ids(preselected_table_ids)
        self._refresh_match_hint()

    def _load_tables(self) -> None:
        for t in reg().table_service.list_by_project(self._project_id):
            self._table_map[t.name.lower()] = t.id
            self._id_to_name[t.id] = t.name

    def _fill_from_table_ids(self, table_ids: list[int]) -> None:
        """预填:把给定 table id 列表的表名填到多行文本框"""
        names = [self._id_to_name[i] for i in table_ids if i in self._id_to_name]
        if not names:
            return
        self.tables_edit.setPlainText("\n".join(names))
        # 手动触发一次 match(因为 setPlainText 会触发 textChanged → _on_tables_changed,
        # 但放在 _build 阶段时 _selected_table_ids 还是空,这里显式更新一下)
        self._selected_table_ids = set(table_ids)
        self._refresh_match_hint()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        # 标签名
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("tag.name.placeholder"))
        self.name_edit.textChanged.connect(self._on_changed)
        form.addRow(tr("tag.name"), self.name_edit)

        # 描述
        self.desc_edit = QPlainTextEdit()
        self.desc_edit.setPlaceholderText(tr("tag.description.placeholder"))
        self.desc_edit.setMaximumHeight(60)
        form.addRow(tr("tag.description"), self.desc_edit)

        v.addLayout(form)

        # 表名多行输入
        ll = QVBoxLayout()
        ll.setSpacing(4)
        hint = QLabel(tr("tag.tables.hint"))
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        ll.addWidget(hint)

        self.tables_edit = QPlainTextEdit()
        self.tables_edit.setPlaceholderText(tr("tag.tables.placeholder"))
        self.tables_edit.setMinimumHeight(160)
        self.tables_edit.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 12px;"
        )
        self.tables_edit.textChanged.connect(self._on_tables_changed)
        ll.addWidget(self.tables_edit)

        # 匹配提示
        self.match_label = QLabel("")
        self.match_label.setObjectName("Muted")
        ll.addWidget(self.match_label)

        v.addLayout(ll)

        # 按钮
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

    def _fill_from_tag(self, tag: Tag) -> None:
        self.name_edit.setText(tag.name)
        self.desc_edit.setPlainText(tag.description)
        # 填表名
        table_ids = reg().tag_repo.get_table_ids_for_tag(tag.id)
        tables = reg().table_service.list_by_project(self._project_id)
        id_to_name = {t.id: t.name for t in tables}
        names = [id_to_name[i] for i in table_ids if i in id_to_name]
        self.tables_edit.setPlainText("\n".join(names))
        self._selected_table_ids = set(table_ids)

    def _on_changed(self, _text: str) -> None:
        pass  # 暂时不需要

    def _on_tables_changed(self) -> None:
        """解析多行文本框,匹配表名,更新提示 + 选集"""
        lines = [ln.strip() for ln in self.tables_edit.toPlainText().splitlines()]
        lines = [ln for ln in lines if ln]  # 去空行
        self._selected_table_ids.clear()
        matched, unmatched = [], []
        for ln in lines:
            tid = self._table_map.get(ln.lower())
            if tid is not None:
                self._selected_table_ids.add(tid)
                matched.append(ln)
            else:
                unmatched.append(ln)
        self._refresh_match_hint(matched=matched, unmatched=unmatched)

    def _refresh_match_hint(self, matched: Optional[list] = None,
                            unmatched: Optional[list] = None) -> None:
        if matched is None:
            # 初始化:用已选 set 数量
            self.match_label.setText(
                tr("tag.match.count").format(n=len(self._selected_table_ids), total=len(self._table_map))
            )
        else:
            n_unmatch = len(unmatched)
            if n_unmatch == 0:
                self.match_label.setText(
                    tr("tag.match.count").format(n=len(matched), total=len(self._table_map))
                )
            else:
                self.match_label.setText(
                    tr("tag.match.count_with_unmatched").format(
                        n=len(matched), total=len(self._table_map),
                        unmatch=", ".join(unmatched[:5]) + ("…" if n_unmatch > 5 else ""),
                    )
                )

    def _on_accept(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, tr("common.error"), tr("tag.error.no_name"))
            return
        # 名称唯一(同一 project)
        existing = reg().tag_repo.get_by_name(self._project_id, name)
        if existing and (not self._tag or existing.id != self._tag.id):
            QMessageBox.warning(self, tr("common.error"),
                                tr("tag.error.name_exists").format(name=name))
            return
        self.accept()

    def get_tag(self) -> Tag:
        """给外部用:拿到填好的 Tag + 选中的表 id 列表"""
        if self._tag:
            t = self._tag
        else:
            t = Tag(id=None, project_id=self._project_id, name="", created_at="", updated_at="")
        t.name = self.name_edit.text().strip()
        t.color = TAG_COLORS[0]  # 固定默认色(用户不可改)
        t.description = self.desc_edit.toPlainText().strip()
        return t

    def get_selected_table_ids(self) -> list[int]:
        return list(self._selected_table_ids)

"""SQL 编辑器自动联想 — 自定义 QListWidget 弹窗

触发方式:
- 输入时自动联想(光标前的 token 长度 >= 2 时)
- Tab 键强制弹出/接受
- Esc 关闭弹窗
- 上下箭头切换候选项
- Enter 接受候选项

数据源:
- SQL 关键字(基础,各方言通用)
- 方言函数(PG / MySQL / Oracle)
- 当前项目下的表名 + 列名(动态注入)
"""
from __future__ import annotations
import re
from typing import Optional
from PySide6.QtCore import Qt, QPoint, QRect, QTimer, QObject, QEvent
from PySide6.QtGui import (
    QFont, QKeyEvent, QTextCursor, QColor, QPainter, QFontMetrics,
)
from PySide6.QtWidgets import (
    QTextEdit, QListWidget, QListWidgetItem, QFrame, QVBoxLayout, QLabel,
    QWidget, QApplication,
)


# Token 提取:从光标位置往前找"非空白非标点"连续字符
_WORD_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
                  "0123456789_")


def _current_token(text_edit: QTextEdit) -> tuple[str, int]:
    """取光标前的当前 token (字母数字下划线)。

    返回 (token, token 起始位置)
    """
    cursor = text_edit.textCursor()
    pos = cursor.position()
    full = text_edit.toPlainText()
    # 找 token 起点
    end = pos
    start = pos
    while start > 0 and full[start - 1] in _WORD_CHARS:
        start -= 1
    token = full[start:end]
    return token, start


class _PopupList(QListWidget):
    """联想弹窗列表 — 作为 editor 的子 widget,这样:
    - 不会脱离父级(不会变成独立窗口被裁剪)
    - 不会抢焦点(子 widget 默认不抢)
    - 用 raise_() 让它绘制在 editor 之上
    """

    def __init__(self, parent=None):
        # 作为 editor 的子 widget — 不传 None
        super().__init__(parent)
        # 不设 WindowFlags,保留默认(子 widget)
        # 不接受 focus
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setUniformItemSizes(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(10)
        self.setFont(font)
        self.setStyleSheet(
            "QListWidget {"
            "  background-color: #0b1220;"
            "  color: #e2e8f0;"
            "  border: 1px solid #3b82f6;"
            "  border-radius: 6px;"
            "  padding: 4px;"
            "}"
            "QListWidget::item { padding: 4px 12px; border-radius: 3px; }"
            "QListWidget::item:selected {"
            "  background-color: #1d4ed8;"
            "  color: white;"
            "}"
        )
        self.setMaximumHeight(220)
        self.setMinimumWidth(280)
        self.hide()


class SqlAutocomplete(QObject):
    """管理联想弹窗:跟踪光标、计算候选、显示/接受建议。"""

    def __init__(self, editor: QTextEdit, dialect_getter, parent=None):
        """
        editor: QTextEdit 实例
        dialect_getter: callable() -> "postgres" / "mysql" / "oracle"
        """
        super().__init__(parent)
        self.editor = editor
        self.dialect_getter = dialect_getter
        self.popup = _PopupList(editor)
        self.popup.itemClicked.connect(self._on_item_clicked)

        # 缓存:关键字/函数一次性载入;表/列按需加载
        self._static_vocab: list[str] = []  # 全部静态候选
        self._static_help: dict[str, str] = {}  # 函数说明
        self._project_vocab: set[str] = set()
        self._project_types: dict[str, str] = {}
        # 上次显示的 token — 用来在 _show_for_token 重建候选时保留 currentRow
        # (否则 50ms 防抖 timer 触发后会把选中行重置成 0,用户按 ↓ 永远只能选 0/1)
        self._last_shown_token: str = ""

        # 防抖 timer — 50ms 内合并连续 KeyRelease,只在停手时触发一次
        self._autoshow_timer = QTimer(self)
        self._autoshow_timer.setSingleShot(True)
        self._autoshow_timer.setInterval(50)
        self._autoshow_timer.timeout.connect(self._try_autoshow)

        self._current_project_id: Optional[int] = None
        self._refresh_static()
        self._refresh_project(None)

        # 事件
        editor.installEventFilter(self)
        self.popup.installEventFilter(self)

    # ----- 公开 API -----
    def set_project(self, project_id: Optional[int]) -> None:
        self._current_project_id = project_id
        self._refresh_project(project_id)

    def retranslate_static(self) -> None:
        self._refresh_static()

    # ----- 内部 -----
    def _refresh_static(self) -> None:
        from app.core.sql_vocab import get_vocab, get_function_help
        dialect = self.dialect_getter() or "postgres"
        self._static_vocab = get_vocab(dialect)
        self._static_help = get_function_help()

    def _refresh_project(self, project_id: Optional[int]) -> None:
        from app.core.sql_vocab import collect_project_vocab
        ids, types = collect_project_vocab(project_id)
        self._project_vocab = ids
        self._project_types = types

    def _all_candidates(self) -> list[tuple[str, str, str]]:
        """返回 [(name, kind, detail), ...] — name/类别/说明。"""
        cands: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        # 表/列
        for name in self._project_vocab:
            if name in seen:
                continue
            seen.add(name)
            kind = self._project_types.get(name, "?")
            if kind == "table":
                cands.append((name, "TBL", "表"))
            else:
                tbl = kind.split(":", 1)[1] if ":" in kind else ""
                cands.append((name, "COL", f"列 ({tbl})" if tbl else "列"))
        # 关键字 / 函数
        for name in self._static_vocab:
            key = name.upper()
            if key in seen:
                continue
            seen.add(key)
            if "(" in name:
                # 函数
                detail = self._static_help.get(name.split("(")[0].strip(), "")
                cands.append((name, "FN", detail))
            else:
                cands.append((name, "KW", "关键字"))
        return cands

    # ----- 事件过滤器 -----
    def eventFilter(self, obj, event):
        if obj is self.editor:
            et = event.type()
            if et == QEvent.Type.KeyPress:
                key = event.key()
                if self.popup.isVisible():
                    if key == Qt.Key.Key_Escape:
                        self._hide()
                        return True
                    if key == Qt.Key.Key_Down:
                        self._move_selection(1)
                        return True
                    if key == Qt.Key.Key_Up:
                        self._move_selection(-1)
                        return True
                    if key in (Qt.Key.Key_Return, Qt.Key.Key_Tab):
                        self._accept_current()
                        return True
                # Tab 主动触发(弹窗未开时)
                if key == Qt.Key.Key_Tab and not self.popup.isVisible():
                    if self._show_for_token(force=True):
                        return True
                # 不 return False,让 KeyRelease 也能命中(在下面统一处理)
            elif et == QEvent.Type.KeyRelease:
                # 输入变化时尝试自动联想(防抖,避免每个键都查)
                # 50ms 内合并连续按键(用户连打)
                self._autoshow_timer.start()
        if obj is self.popup:
            if event.type() == QEvent.Type.MouseButtonPress:
                # 点击列表外区域时,延迟关闭(让 click 先处理)
                QTimer.singleShot(100, self._hide_if_outside)
        return False

    def _try_autoshow(self) -> None:
        # 关键:即使 popup 已经在显示,也要刷新(用户继续输入 / 退格都要更新候选项)
        self._show_for_token(force=False)
        # 如果 token 太短导致 _show_for_token 返回 False(没显示),
        # 但 popup 还残留显示 — 主动关掉
        token, _ = _current_token(self.editor)
        if len(token) < 2 and self.popup.isVisible():
            self._hide()

    def _show_for_token(self, force: bool = False) -> bool:
        token, start = _current_token(self.editor)
        if not token:
            # token 为空(在空格后 / 行首)— 不显示
            if self.popup.isVisible():
                self.popup.hide()
            self._last_shown_token = ""
            return False
        if not force and len(token) < 2:
            return False
        candidates = self._all_candidates()
        # 过滤:前缀匹配优先,再子串匹配
        prefix = token.lower()
        prefix_matches = [c for c in candidates if c[0].lower().startswith(prefix)]
        substring_matches = [c for c in candidates
                             if prefix in c[0].lower() and c not in prefix_matches]
        matches = prefix_matches[:8] + substring_matches[:8]
        if not matches:
            self._last_shown_token = ""
            return False
        if len(matches) == 1 and matches[0][0].lower() == prefix:
            self._last_shown_token = ""
            return False  # 完全等于输入,无意义

        # 关键:token 没变(用户只是按方向键切换选择)— 保留 currentRow
        # 否则 50ms 防抖 timer 触发 _show_for_token 会重置成 0,用户按 ↓ 永远只能 0/1 循环
        same_token = (self._last_shown_token == token) and self.popup.isVisible()
        prev_row = self.popup.currentRow() if same_token else 0
        self._last_shown_token = token

        self.popup.clear()
        for name, kind, detail in matches:
            item = QListWidgetItem(f"{name}    [{kind}]  {detail}")
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.popup.addItem(item)
        if self.popup.count() == 0:
            return False
        # 定位:光标下方
        cursor = self.editor.textCursor()
        rect = self.editor.cursorRect(cursor)
        # 用 editor 的 viewport 坐标系,popup 跟随光标定位
        viewport_pos = rect.bottomLeft()
        self.popup.move(viewport_pos + QPoint(0, 4))
        # token 没变就保留之前的选中(token 变了就重置成 0)
        target_row = min(prev_row, self.popup.count() - 1) if same_token else 0
        self.popup.setCurrentRow(target_row)
        self.popup.show()
        self.popup.raise_()  # 绘制在 editor 内容之上
        # 子 widget 不抢焦点,editor 自然保留 focus
        return True

    def _move_selection(self, delta: int) -> None:
        n = self.popup.count()
        if n == 0:
            return
        cur = self.popup.currentRow()
        nxt = (cur + delta) % n
        self.popup.setCurrentRow(nxt)

    def _accept_current(self) -> None:
        item = self.popup.currentItem()
        if not item:
            self._hide()
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        kind = item.text()  # "name    [KIND]  detail"
        # 推断 kind 标签(从 "name [KIND] detail" 里抽)
        m = re.search(r"\[(\w+)\]", kind)
        kind_tag = m.group(1) if m else "KW"
        self._insert(name, kind_tag)
        # 隐藏旧 popup,然后立即基于新光标位置触发一次新联想
        self._hide()
        # 紧接着触发(不靠 timer 50ms,用户立刻看到下一波候选)
        QTimer.singleShot(0, self._show_for_token)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        text = item.text()
        m = re.search(r"\[(\w+)\]", text)
        kind_tag = m.group(1) if m else "KW"
        name = item.data(Qt.ItemDataRole.UserRole)
        self._insert(name, kind_tag)
        self._hide()
        QTimer.singleShot(0, self._show_for_token)

    def _insert(self, name: str, kind_tag: str = "KW") -> None:
        """用 name 替换当前 token;然后根据 kind 自动补一个分隔符:
        - 关键字 (KW) / 表 (TBL): 加空格(让用户接着写)
        - 列 (COL): 不加(列后接逗号/点号/算符,加空格反而尴尬)
        - 函数 (FN) / 其它: 不加(函数后接 ( 自动补)
        """
        token, start = _current_token(self.editor)
        cursor = self.editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(self.editor.textCursor().position(),
                           QTextCursor.MoveMode.KeepAnchor)
        # 决定要不要在 name 后加空格
        suffix = ""
        if kind_tag in ("KW", "TBL") and not name.endswith("("):
            suffix = " "
        cursor.insertText(name + suffix)
        self.editor.setTextCursor(cursor)

    def _hide(self) -> None:
        self.popup.hide()
        self.editor.setFocus()

    def _hide_if_outside(self) -> None:
        if not self.popup.underMouse() and not self.editor.underMouse():
            self._hide()
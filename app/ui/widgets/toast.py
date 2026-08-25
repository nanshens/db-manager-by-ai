"""Toast 通知 — 右下角浮层,3s 自动消失"""
from __future__ import annotations
import time
from typing import Optional
from PySide6.QtCore import Qt, QTimer, QPoint, QPropertyAnimation, QEasingCurve, Signal, QObject
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QLabel, QHBoxLayout, QApplication, QWidget
import qtawesome as qta


class _ToastItem(QFrame):
    """单个 Toast — 左侧色条 + 图标 + 文本"""
    closed = Signal(object)

    def __init__(self, message: str, kind: str = "info", duration_ms: int = 3000):
        super().__init__()
        self.setObjectName(f"Toast{ 'Success' if kind=='success' else 'Error' if kind=='error' else 'Info'}")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedWidth(320)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 16, 10)
        layout.setSpacing(10)

        # Icon
        icon_name = "mdi6.check-circle" if kind == "success" else "mdi6.close-circle" if kind == "error" else "mdi6.information"
        icon_color = "#10b981" if kind == "success" else "#ef4444" if kind == "error" else "#3b82f6"
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(20, 20))
        icon_label.setStyleSheet("background: transparent;")
        layout.addWidget(icon_label)

        # Text
        text_label = QLabel(message)
        text_label.setWordWrap(True)
        text_label.setStyleSheet("background: transparent; color: #e2e8f0;")
        layout.addWidget(text_label, 1)

        # Auto-close
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_and_close)
        self._timer.start(duration_ms)

    def _fade_and_close(self):
        # 简化:直接关闭
        self.closed.emit(self)
        self.close()
        self.deleteLater()


class ToastManager(QObject):
    """Toast 管理器 — 维护栈,自动堆叠"""
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._items: list[_ToastItem] = []
        self._margin = 16
        self._spacing = 8
        self._item_height = 56

    def show(self, message: str, kind: str = "info", duration_ms: int = 3000) -> None:
        item = _ToastItem(message, kind, duration_ms)
        item.closed.connect(self._on_closed)
        self._items.append(item)
        item.show()
        self._reposition()

    def _on_closed(self, item) -> None:
        if item in self._items:
            self._items.remove(item)
        self._reposition()

    def _reposition(self) -> None:
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        x = geo.right() - self._margin - 320
        for i, item in enumerate(self._items):
            y = geo.bottom() - self._margin - self._item_height * (i + 1) - self._spacing * i
            item.move(x, y)


# 全局单例
_manager: Optional[ToastManager] = None


def get_manager() -> ToastManager:
    global _manager
    if _manager is None:
        _manager = ToastManager()
    return _manager


def show_toast(message: str, kind: str = "info", duration_ms: int = 3000) -> None:
    """显示 Toast(success / error / info)"""
    get_manager().show(message, kind, duration_ms)

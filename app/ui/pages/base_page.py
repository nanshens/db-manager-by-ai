"""页面基类 — 提供统一样式的页头 + 主体容器"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea,
)
from app.ui.i18n import tr


class PageHeader(QFrame):
    """页头:标题 + 副标题(支持 retranslate)"""
    def __init__(self, title: str, subtitle: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("PageHeader")
        self._title_text = title
        self._subtitle_text = subtitle

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 16)
        layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("PageTitle")
        layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("PageSubtitle")
        if not subtitle:
            self.subtitle_label.hide()
        layout.addWidget(self.subtitle_label)

    def retranslate(self, title: str, subtitle: str) -> None:
        self._title_text = title
        self._subtitle_text = subtitle
        self.title_label.setText(title)
        if subtitle:
            self.subtitle_label.setText(subtitle)
            self.subtitle_label.show()
        else:
            self.subtitle_label.clear()
            self.subtitle_label.hide()


class BasePage(QWidget):
    """所有页面的基类 — 顶部 PageHeader + 滚动主体"""
    def __init__(self, title_key: str, subtitle_key: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("PageRoot")
        self._title_key = title_key
        self._subtitle_key = subtitle_key

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 24, 32, 24)
        outer.setSpacing(0)

        # Header
        self.header = PageHeader(tr(title_key), tr(subtitle_key) if subtitle_key else "")
        outer.addWidget(self.header)

        # Scrollable content
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setObjectName("PageScroll")
        outer.addWidget(self.scroll, 1)

        # Body container
        self.body = QWidget()
        self.body.setObjectName("PageBody")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 8, 0, 8)
        self.body_layout.setSpacing(16)
        self.scroll.setWidget(self.body)

    def retranslate(self) -> None:
        """刷新页头(子类可重写以更新其他文本)"""
        self.header.retranslate(
            tr(self._title_key),
            tr(self._subtitle_key) if self._subtitle_key else ""
        )

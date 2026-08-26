"""统一空状态组件 — 插画 + 标题 + 描述 + 主按钮"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
)
import qtawesome as qta


class EmptyState(QFrame):
    """统一的空状态;接受可选主按钮文本 + 回调"""
    primary_clicked = Signal()

    def __init__(
        self,
        icon_name: str = "mdi6.package-variant",
        title: str = "",
        description: str = "",
        primary_text: str = "",
        secondary_text: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setObjectName("EmptyState")
        self.setMinimumHeight(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 48, 32, 48)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Icon
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent; color: #475569;")
        layout.addWidget(self.icon_label)
        self.set_icon(icon_name)

        # Title
        self.title_label = QLabel(title)
        self.title_label.setObjectName("EmptyTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        layout.addWidget(self.title_label)

        # Description
        self.desc_label = QLabel(description)
        self.desc_label.setObjectName("EmptyDesc")
        self.desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.desc_label.setWordWrap(True)
        layout.addWidget(self.desc_label)

        # Buttons
        if primary_text:
            self.primary_btn = QPushButton(primary_text)
            self.primary_btn.setObjectName("Primary")
            self.primary_btn.setIcon(qta.icon("mdi6.plus", color="white"))
            self.primary_btn.clicked.connect(self.primary_clicked)
            btn_layout = QHBoxLayout()
            btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn_layout.addWidget(self.primary_btn)
            if secondary_text:
                self.secondary_btn = QPushButton(secondary_text)
                self.secondary_btn.setObjectName("Ghost")
                btn_layout.addWidget(self.secondary_btn)
            layout.addLayout(btn_layout)

        layout.addStretch()

    def set_icon(self, icon_name: str) -> None:
        """设置图标(qtawesome 名称)"""
        try:
            self.icon_label.setPixmap(
                qta.icon(icon_name, color="#64748b").pixmap(72, 72)
            )
        except Exception:
            self.icon_label.setText("📦")

    def set_text(self, title: str = "", description: str = "") -> None:
        """动态更新标题/描述(空字符串保留原值)"""
        if title:
            self.title_label.setText(title)
        if description:
            self.desc_label.setText(description)

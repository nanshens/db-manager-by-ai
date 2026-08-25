"""设置页"""
from __future__ import annotations
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame, QComboBox, QGridLayout,
)
import qtawesome as qta

from app import __version__
from app.ui.i18n import tr, available_languages
from app.ui.pages.base_page import BasePage


class SettingsPage(BasePage):
    theme_changed = Signal(str)
    language_changed = Signal(str)

    def __init__(self, current_theme: str = "dark", current_lang: str = "zh", parent=None):
        super().__init__("settings.title", "", parent)
        self._current_theme = current_theme
        self._current_lang = current_lang
        self._build()

    def _build(self) -> None:
        # 外观
        appearance_card = QFrame()
        appearance_card.setObjectName("Card")
        ap_layout = QVBoxLayout(appearance_card)
        ap_layout.setContentsMargins(20, 16, 20, 16)
        ap_layout.setSpacing(12)

        self._ap_title = QLabel(tr("settings.appearance"))
        self._ap_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        ap_layout.addWidget(self._ap_title)

        # Theme row
        theme_row = QHBoxLayout()
        self._theme_label = QLabel(tr("settings.theme"))
        self._theme_label.setMinimumWidth(100)
        theme_row.addWidget(self._theme_label)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem(tr("settings.theme.dark"), "dark")
        self.theme_combo.addItem(tr("settings.theme.light"), "light")
        for i in range(self.theme_combo.count()):
            if self.theme_combo.itemData(i) == self._current_theme:
                self.theme_combo.setCurrentIndex(i)
                break
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch()
        ap_layout.addLayout(theme_row)

        # Language row
        lang_row = QHBoxLayout()
        self._lang_label = QLabel(tr("settings.language"))
        self._lang_label.setMinimumWidth(100)
        lang_row.addWidget(self._lang_label)

        self.lang_combo = QComboBox()
        for lang in available_languages():
            self.lang_combo.addItem(lang["name"], lang["code"])
        for i in range(self.lang_combo.count()):
            if self.lang_combo.itemData(i) == self._current_lang:
                self.lang_combo.setCurrentIndex(i)
                break
        self.lang_combo.currentIndexChanged.connect(self._on_lang_changed)
        lang_row.addWidget(self.lang_combo)
        lang_row.addStretch()
        ap_layout.addLayout(lang_row)

        self.body_layout.addWidget(appearance_card)

        # 关于
        about_card = QFrame()
        about_card.setObjectName("Card")
        ab_layout = QVBoxLayout(about_card)
        ab_layout.setContentsMargins(20, 16, 20, 16)
        ab_layout.setSpacing(8)

        self._ab_title = QLabel(tr("settings.about"))
        self._ab_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        ab_layout.addWidget(self._ab_title)

        ver_row = QHBoxLayout()
        self._ver_label = QLabel(tr("settings.about.version"))
        self._ver_label.setMinimumWidth(100)
        ver_row.addWidget(self._ver_label)
        self._ver_value = QLabel(f"DBManager v{__version__}")
        self._ver_value.setObjectName("Secondary")
        ver_row.addWidget(self._ver_value)
        ver_row.addStretch()
        ab_layout.addLayout(ver_row)

        self._desc_label = QLabel(tr("settings.about.desc"))
        self._desc_label.setObjectName("Muted")
        self._desc_label.setWordWrap(True)
        ab_layout.addWidget(self._desc_label)

        self.body_layout.addWidget(about_card)
        self.body_layout.addStretch()

    def retranslate(self) -> None:
        super().retranslate()
        self._ap_title.setText(tr("settings.appearance"))
        self._theme_label.setText(tr("settings.theme"))
        self._lang_label.setText(tr("settings.language"))
        # Combo boxes: 记住当前选中的 data,重新填充文字
        cur_theme = self.theme_combo.currentData()
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        self.theme_combo.addItem(tr("settings.theme.dark"), "dark")
        self.theme_combo.addItem(tr("settings.theme.light"), "light")
        for i in range(self.theme_combo.count()):
            if self.theme_combo.itemData(i) == cur_theme:
                self.theme_combo.setCurrentIndex(i)
                break
        self.theme_combo.blockSignals(False)

        cur_lang = self.lang_combo.currentData()
        self.lang_combo.blockSignals(True)
        self.lang_combo.clear()
        for lang in available_languages():
            self.lang_combo.addItem(lang["name"], lang["code"])
        for i in range(self.lang_combo.count()):
            if self.lang_combo.itemData(i) == cur_lang:
                self.lang_combo.setCurrentIndex(i)
                break
        self.lang_combo.blockSignals(False)

        self._ab_title.setText(tr("settings.about"))
        self._ver_label.setText(tr("settings.about.version"))
        self._desc_label.setText(tr("settings.about.desc"))

    def _on_theme_changed(self, idx: int) -> None:
        theme = self.theme_combo.itemData(idx)
        if theme:
            self.theme_changed.emit(theme)

    def _on_lang_changed(self, idx: int) -> None:
        lang = self.lang_combo.itemData(idx)
        if lang:
            self.language_changed.emit(lang)

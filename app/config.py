"""应用配置(基于 QSettings,跨平台)"""
from __future__ import annotations
from PySide6.QtCore import QSettings

ORG = "DBManager"
APP = "DBManager"

# 主题: dark(默认) / light
DEFAULT_THEME = "dark"
# 语言: zh(默认) / en / ja
DEFAULT_LANG = "zh"
# 侧边栏: expanded(默认) / collapsed
DEFAULT_SIDEBAR = "expanded"


def settings() -> QSettings:
    return QSettings(ORG, APP)


def get_theme() -> str:
    return settings().value("ui/theme", DEFAULT_THEME, type=str)


def set_theme(theme: str) -> None:
    settings().setValue("ui/theme", theme)


def get_lang() -> str:
    return settings().value("ui/lang", DEFAULT_LANG, type=str)


def set_lang(lang: str) -> None:
    settings().setValue("ui/lang", lang)


def get_sidebar() -> str:
    return settings().value("ui/sidebar", DEFAULT_SIDEBAR, type=str)


def set_sidebar(state: str) -> None:
    settings().setValue("ui/sidebar", state)

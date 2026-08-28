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


# ===== 数据对比判别条件(用户偏好) =====

def get_diff_match_mode() -> str:
    """all / selected"""
    return settings().value("diff/match_mode", "all", type=str)


def set_diff_match_mode(mode: str) -> None:
    settings().setValue("diff/match_mode", mode)


def get_diff_compare_cols() -> list[str]:
    """上次选的对比列(每行一个,存为字符串)"""
    raw = settings().value("diff/compare_cols", "", type=str)
    if not raw:
        return []
    return [c.strip() for c in raw.split("\n") if c.strip()]


def set_diff_compare_cols(cols: list[str]) -> None:
    settings().setValue("diff/compare_cols", "\n".join(cols))

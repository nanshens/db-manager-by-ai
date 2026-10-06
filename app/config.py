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


# ===== Lite 模式(打包定制:只显示部分 tab)=====
# 打包精简版时:把下面的 _LITE_MODE 改成 True,然后只编译 LITE_NAV_ITEMS 列出的 page_id
# 开发/全功能版:保持 _LITE_MODE = False
_LITE_MODE = False

# Lite 模式下 sidebar 显示哪些 tab(只保留 page_id 在这个列表里的)
LITE_NAV_ITEMS = [
    "excel_tpl",       # PageId.EXCEL_TPL
    "excel_parse",     # PageId.EXCEL_PARSE
]

# Lite 模式下启动时默认进入哪个页面(只在此模式生效)
# 值必须是 LITE_NAV_ITEMS 里的一项,否则启动 fallback 到列表第一项
# 改成 "_LITE_MODE = False" 后此常量会被忽略(默认走 PageId.PROJECTS)
_LITE_INITIAL_PAGE = "excel_tpl"   # ← 改成你想要的 page_id (excel_tpl / excel_parse)


def get_lite_initial_page() -> str:
    """Lite 模式启动页配置(供 main_window 使用)。"""
    return _LITE_INITIAL_PAGE if _LITE_INITIAL_PAGE in LITE_NAV_ITEMS else (
        LITE_NAV_ITEMS[0] if LITE_NAV_ITEMS else "projects"
    )


def is_lite_mode() -> bool:
    return _LITE_MODE


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

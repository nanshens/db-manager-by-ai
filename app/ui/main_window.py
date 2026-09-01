"""主窗口 — 可折叠侧边栏 + 顶部栏 + 多个页面 + 详情页"""
from __future__ import annotations
from enum import Enum
from typing import Optional
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Signal, QSize
from PySide6.QtGui import QAction, QKeySequence, QShortcut, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QPushButton, QFrame, QLabel, QSizePolicy, QApplication,
    QButtonGroup, QToolButton,
)
import qtawesome as qta

from app import __app_name__, __version__
from app.ui import i18n
from app.ui.pages import (
    ProjectsPage, SqlLibPage, ExcelTemplatesPage, SettingsPage, FileConvertPage,
    DbLinksPage,
)
from app.ui.pages.project_detail_page import ProjectDetailPage
from app.ui.widgets import show_toast
from app.services.registry import reg
from app import config as app_config


class PageId(str, Enum):
    PROJECTS = "projects"
    SQLLIB = "sqllib"
    EXCEL_TPL = "excel_tpl"
    FILE_CONVERT = "file_convert"
    DB_LINKS = "db_links"
    PROJECT_DETAIL = "project_detail"
    SETTINGS = "settings"


# 侧边栏导航项配置
NAV_ITEMS = [
    (PageId.PROJECTS, "mdi6.folder-multiple", "nav.projects"),
    (PageId.SQLLIB, "mdi6.database", "nav.sqllib"),
    (PageId.EXCEL_TPL, "mdi6.microsoft-excel", "nav.excel_templates"),
    (PageId.FILE_CONVERT, "mdi6.file-replace-outline", "nav.file_convert"),
    (PageId.DB_LINKS, "mdi6.database-cog-outline", "nav.db_links"),
]

EXPANDED_WIDTH = 220
COLLAPSED_WIDTH = 56


class NavButton(QToolButton):
    def __init__(self, page_id: PageId, icon_name: str, text_key: str):
        super().__init__()
        self.setObjectName("NavItem")
        self.setCheckable(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setIconSize(QSize(20, 20))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setIcon(qta.icon(icon_name, color="#94a3b8"))
        self.setText(i18n.tr(text_key))
        self._page_id = page_id
        self._icon_name = icon_name
        self._text_key = text_key

    def page_id(self) -> PageId:
        return self._page_id

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed:
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            self.setText("")
        else:
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self.setText(i18n.tr(self._text_key))

    def retranslate_text(self) -> None:
        if self.toolButtonStyle() != Qt.ToolButtonStyle.ToolButtonIconOnly:
            self.setText(i18n.tr(self._text_key))

    def set_active_style(self, active: bool) -> None:
        if active:
            self.setIcon(qta.icon(self._icon_name, color="#3b82f6"))
        else:
            self.setIcon(qta.icon(self._icon_name, color="#94a3b8"))


class MainWindow(QMainWindow):
    theme_change_requested = Signal(str)
    language_change_requested = Signal(str)

    def __init__(self, initial_theme: str = "dark", initial_lang: str = "zh"):
        super().__init__()
        self.setWindowTitle(f"{__app_name__} v{__version__}")
        self.resize(1280, 800)
        self.setMinimumSize(960, 600)

        self._current_theme = initial_theme
        self._current_lang = initial_lang
        self._is_collapsed = app_config.get_sidebar() == "collapsed"

        self._build_root()
        self._build_sidebar()
        self._build_content()
        self._build_shortcuts()
        self._apply_sidebar_state(animate=False)
        self._switch_page(PageId.PROJECTS)

    # ============== 构建 ==============
    def _build_root(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        self.root = QHBoxLayout(central)
        self.root.setContentsMargins(0, 0, 0, 0)
        self.root.setSpacing(0)

    def _build_sidebar(self) -> None:
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(EXPANDED_WIDTH)
        self.sidebar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toggle
        self.toggle_btn = QPushButton()
        self.toggle_btn.setObjectName("SidebarToggle")
        self.toggle_btn.setIcon(qta.icon("mdi6.chevron-double-left", color="#94a3b8"))
        self.toggle_btn.setIconSize(QSize(20, 20))
        self.toggle_btn.setFixedHeight(44)
        self.toggle_btn.clicked.connect(self._toggle_sidebar)
        layout.addWidget(self.toggle_btn)

        # Nav
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[PageId, NavButton] = {}

        for page_id, icon_name, text_key in NAV_ITEMS:
            btn = NavButton(page_id, icon_name, text_key)
            btn.clicked.connect(lambda _checked, pid=page_id: self._switch_page(pid))
            self.nav_group.addButton(btn)
            self.nav_buttons[page_id] = btn
            layout.addWidget(btn)

        layout.addStretch()

        # Settings at bottom
        self.settings_btn = NavButton(PageId.SETTINGS, "mdi6.cog", "nav.settings")
        self.settings_btn.clicked.connect(lambda: self._switch_page(PageId.SETTINGS))
        self.nav_group.addButton(self.settings_btn)
        self.nav_buttons[PageId.SETTINGS] = self.settings_btn
        layout.addWidget(self.settings_btn)

        self.root.addWidget(self.sidebar)

    def _build_content(self) -> None:
        right = QWidget()
        right.setObjectName("ContentArea")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        # 顶部栏已删除 — 主题/语言走设置页(Ctrl+/ / Ctrl+L 快捷键仍可用)

        # Stacked pages
        self.stack = QStackedWidget()
        self.stack.setObjectName("ContentStack")

        self.home_page = None  # 仪表盘已移除
        self.projects_page = ProjectsPage()
        self.projects_page.open_project_clicked.connect(self._open_project)
        self.sqllib_page = SqlLibPage()
        self.excel_tpl_page = ExcelTemplatesPage()
        self.file_convert_page = FileConvertPage()
        self.db_links_page = DbLinksPage()
        self.project_detail_page = ProjectDetailPage()
        self.project_detail_page.back_clicked.connect(lambda: self._switch_page(PageId.PROJECTS))
        self.project_detail_page.project_updated.connect(lambda: self.projects_page.refresh())
        self.settings_page = SettingsPage(
            current_theme=self._current_theme,
            current_lang=self._current_lang,
        )
        self.settings_page.theme_changed.connect(self._on_theme_change_requested)
        self.settings_page.language_changed.connect(self._on_language_change_requested)

        # 顺序:projects, sqllib, excel_tpl, file_convert, db_links, project_detail, settings
        self.stack.addWidget(self.projects_page)           # 0
        self.stack.addWidget(self.sqllib_page)             # 1
        self.stack.addWidget(self.excel_tpl_page)          # 2
        self.stack.addWidget(self.file_convert_page)       # 3
        self.stack.addWidget(self.db_links_page)           # 4
        self.stack.addWidget(self.project_detail_page)     # 5
        self.stack.addWidget(self.settings_page)           # 6

        # 保存 page_id → index 映射
        self._page_index = {
            PageId.PROJECTS: 0,
            PageId.SQLLIB: 1,
            PageId.EXCEL_TPL: 2,
            PageId.FILE_CONVERT: 3,
            PageId.DB_LINKS: 4,
            PageId.PROJECT_DETAIL: 5,
            PageId.SETTINGS: 6,
        }

        rl.addWidget(self.stack, 1)
        self.root.addWidget(right, 1)

    def _build_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+B"), self, activated=self._toggle_sidebar)
        QShortcut(QKeySequence("Ctrl+/"), self, activated=self._toggle_theme)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self._cycle_language)
        # Ctrl+K 已删除(顶部无搜索框)
        page_map = [
            ("Ctrl+1", PageId.PROJECTS),
            ("Ctrl+2", PageId.SQLLIB),
            ("Ctrl+3", PageId.EXCEL_TPL),
            ("Ctrl+4", PageId.FILE_CONVERT),
            ("Ctrl+5", PageId.DB_LINKS),
            ("Ctrl+6", PageId.SETTINGS),
        ]
        for seq, pid in page_map:
            QShortcut(QKeySequence(seq), self, activated=lambda p=pid: self._switch_page(p))

    # ============== 页面切换 ==============
    def _switch_page(self, page_id: PageId) -> None:
        if page_id == PageId.PROJECT_DETAIL:
            # 详情页只能在 _open_project 里设置 project 后再切
            return
        if page_id not in self._page_index:
            return
        self.stack.setCurrentIndex(self._page_index[page_id])
        for pid, btn in self.nav_buttons.items():
            is_active = (pid == page_id)
            btn.setChecked(is_active)
            btn.set_active_style(is_active)
        # 离开详情页时清空 project 状态(防止误显示旧数据)
        # 实际:不再显示,无需清

    def _open_project(self, project_id: int) -> None:
        if not project_id:
            return
        self.project_detail_page.set_project(project_id)
        self.stack.setCurrentIndex(self._page_index[PageId.PROJECT_DETAIL])
        # 详情页不进 nav 选中(没有 nav 按钮对应),无需更新 nav 状态

    # ============== 侧边栏折叠 ==============
    def _toggle_sidebar(self) -> None:
        self._is_collapsed = not self._is_collapsed
        self._apply_sidebar_state(animate=True)

    def _apply_sidebar_state(self, animate: bool) -> None:
        target_w = COLLAPSED_WIDTH if self._is_collapsed else EXPANDED_WIDTH
        icon_name = "mdi6.chevron-double-right" if self._is_collapsed else "mdi6.chevron-double-left"
        self.toggle_btn.setIcon(qta.icon(icon_name, color="#94a3b8"))

        if animate:
            anim = QPropertyAnimation(self.sidebar, b"minimumWidth")
            anim.setDuration(200)
            anim.setStartValue(self.sidebar.width())
            anim.setEndValue(target_w)
            anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
            anim.start()
            self._sidebar_anim = anim
        self.sidebar.setFixedWidth(target_w)

        for btn in self.nav_buttons.values():
            btn.set_collapsed(self._is_collapsed)

        app_config.set_sidebar("collapsed" if self._is_collapsed else "expanded")

    # ============== 主题 ==============
    def _toggle_theme(self) -> None:
        new_theme = "light" if self._current_theme == "dark" else "dark"
        self._on_theme_change_requested(new_theme)

    def _on_theme_change_requested(self, theme: str) -> None:
        if theme == self._current_theme:
            return
        self._current_theme = theme
        app_config.set_theme(theme)
        self.theme_change_requested.emit(theme)

    # ============== 语言 ==============
    def _cycle_language(self) -> None:
        order = ["zh", "en", "ja"]
        idx = order.index(self._current_lang) if self._current_lang in order else 0
        next_idx = (idx + 1) % len(order)
        self._on_language_change_requested(order[next_idx])

    def _on_language_change_requested(self, lang: str) -> None:
        if lang == self._current_lang:
            return
        self._current_lang = lang
        app_config.set_lang(lang)
        self.language_change_requested.emit(lang)
        show_toast(f"Language → {lang.upper()}", "info", 1500)

    # ============== 外部同步 ==============
    def set_theme_external(self, theme: str) -> None:
        self._current_theme = theme
        if hasattr(self, "settings_page"):
            for i in range(self.settings_page.theme_combo.count()):
                if self.settings_page.theme_combo.itemData(i) == theme:
                    self.settings_page.theme_combo.blockSignals(True)
                    self.settings_page.theme_combo.setCurrentIndex(i)
                    self.settings_page.theme_combo.blockSignals(False)
                    break

    def set_lang_external(self, lang: str) -> None:
        self._current_lang = lang
        for btn in self.nav_buttons.values():
            btn.retranslate_text()
        if self._is_collapsed:
            for btn in self.nav_buttons.values():
                btn.set_collapsed(True)
        for page in [self.projects_page, self.sqllib_page,
                     self.excel_tpl_page, self.file_convert_page,
                     self.project_detail_page, self.settings_page]:
            if hasattr(page, "retranslate"):
                page.retranslate()

    def current_theme(self) -> str:
        return self._current_theme

    def current_lang(self) -> str:
        return self._current_lang

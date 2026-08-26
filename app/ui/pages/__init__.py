"""页面模块"""
from .base_page import BasePage
from .projects_page import ProjectsPage
from .sqllib_page import SqlLibPage
from .excel_templates_page import ExcelTemplatesPage
from .settings_page import SettingsPage
from .project_detail_page import ProjectDetailPage
from .file_convert_page import FileConvertPage

__all__ = [
    "BasePage",
    "ProjectsPage",
    "SqlLibPage",
    "ExcelTemplatesPage",
    "SettingsPage",
    "ProjectDetailPage",
    "FileConvertPage",
]

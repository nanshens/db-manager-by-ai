# DBManager

桌面端数据库(DDL/DML/数据对比)管理工具 · Python 3.13 + PySide6 + SQLite + polars

> **自用工具** — 解决项目表结构散落、初期数据版本混乱、常用 SQL 重复造轮子、表数据变更无审计。
> 支持百万行流式 diff / 中英日三语 / polars 高性能 / 可折叠侧边栏 / 对比配置可复用 / Excel 多 sheet 模板解析。

## v1.0 — 全部 M0–M6 完成

✅ 已实现功能:

| 模块 | 功能 |
| --- | --- |
| **M0 基建** | 主题(深/浅,可手动)/ i18n(中英日)/ 可折叠侧边栏/ 线性图标(qtawesome)/ 公共组件(Toast/EmptyState) |
| **M1 项目/表结构** | 项目 CRUD(名称/描述/标签色)/ 表 CRUD / 列编辑器(类型/可空/默认值/主键/注释)/ 自动生成 DDL / 数据统计 |
| **M2 常用 SQL 库** | 完整 CRUD / 全局+项目绑定 / 关键字搜索(LIKE)/ 标签 / 复制(use_count 自动 +1)/ 跨项目筛选 |
| **M3 数据版本** | 上传 CSV/TSV/XLSX / 自动算 sha256 + 行数(不读全文件)/ 多文件版本(每表一个)/ 版本列表 + 文件元数据展示 |
| **M4 大文件 diff** ⭐ | 版本 vs 版本 / polars 流式 / 可配置主键 + 忽略列 + 大小写/trim / Worker 线程(后台不卡)/ 4 类差异统计(新增/删除/修改/未变) |
| **M5 SQL 生成器** | INSERT(?, %(name)s, 'literal' 三风格)/ DELETE / COPY(PostgreSQL)/ CSV 导出 / 复制到 SQL 库 |
| **M6 Excel 模板解析** ⭐ | 模板 CRUD(项目/全局)/ 配置 sheet + 表名列 + sheet 名列 + header 行 / 应用模板解析(实读多 sheet)/ 解析预览(列 + 前 10 行) |
| **附加** | 5 个 Tab 的项目详情页(表结构 / 数据版本 / SQL 生成器 / 数据对比 / 概览)/ 全局搜索框 / 快捷键(Ctrl+B/+//+L/+K/+1~5) |

## 启动

```bash
# 开发运行
python main.py

# Windows 一键启动
run.bat

# 自检(不依赖 GUI)
python _self_check.py
```

## 打包

```bash
build.bat
# 产物: dist\DBManager\DBManager.exe
```

## 数据存储

- Windows: `%APPDATA%\DBManager\dbmanager.db`
- macOS/Linux: `~/.local/share/DBManager/dbmanager.db`

## 项目结构

```
dbmanager/
├── main.py                     # 入口
├── build.spec                  # PyInstaller 打包配置
├── run.bat / build.bat          # 一键脚本
├── _self_check.py              # 自检脚本(不依赖 GUI)
├── _screenshot.py              # 截图脚本(用于 UI 验证)
├── app/
│   ├── bootstrap.py            # 启动初始化
│   ├── config.py               # QSettings 配置
│   ├── paths.py                # 跨平台路径
│   ├── core/                   # 纯函数核心
│   │   ├── file_reader.py      # polars/fastexcel 流式读取
│   │   ├── diff_engine.py      # 表数据 diff 核心算法
│   │   ├── excel_parser.py     # Excel 多 sheet 模板解析
│   │   └── sqlgen.py           # SQL 批量生成
│   ├── repos/                  # 数据访问层 (8 个 repo)
│   ├── services/               # 业务逻辑层 (7 个 service + registry)
│   ├── ui/
│   │   ├── main_window.py      # 主窗口 + 侧边栏 + 顶部栏
│   │   ├── theme.py            # QSS 加载
│   │   ├── i18n.py             # tr() 翻译
│   │   ├── dialogs/            # 9 个弹窗
│   │   ├── pages/              # 5 个页面 + 项目详情 5 个 Tab
│   │   └── widgets/            # Toast / EmptyState
│   └── resources/
│       ├── i18n/{zh,en,ja}.json  # 3 语翻译 (~120 keys each)
│       └── qss/{dark,light}.qss  # 主题样式
├── docs/                       # 设计文档
│   ├── DEV_DOC.md
│   └── DEV_DOC.html
└── screenshots/                # _screenshot.py 输出
```

## 重置 QSettings(清空配置)

```python
python -c "from PySide6.QtCore import QSettings; from PySide6.QtWidgets import QApplication; import sys; app = QApplication(sys.argv); QApplication.setOrganizationName('DBManager'); QApplication.setApplicationName('DBManager'); QSettings('DBManager', 'DBManager').clear()"
```

## 重置数据库

```bash
del %APPDATA%\DBManager\dbmanager.db
```

## 版本

**v1.0.0** — 完整功能版本(M0–M6 全部实现)

# DBManager

桌面端数据库(DDL/DML/数据对比)管理工具 · Python 3.13 + PySide6 + SQLite + polars

> **自用工具** — 解决项目表结构散落、初期数据版本混乱、常用 SQL 重复造轮子、表数据变更无审计。
> 支持百万行流式 diff / 中英日三语 / polars 高性能 / 可折叠侧边栏 / 对比配置可复用 / Excel 多 sheet 模板解析。

## v1.1 — 增量更新

- **DB 链接管理**(侧边栏新 tab `Ctrl+5`):保存 postgres / mysql / oracle 连接信息,name + host + port + user + password + database + schema + service_name,命令预览用 `sample_table` 演示,密码显示成 `••••`,明文存本地 SQLite(自用)。
- **SQL 生成器新增 Export Insert SQL (dump)**:勾上 + 选 DB 链接,每张表生成 `pg_dump` / `mysqldump` / `expdp` 命令,直接复制到本地执行;输出目录复用 `io_dir` 字段,Schema 用 db_link 自己的。
- **数据对比修复**:展示和导出保留原始大小写(不 lower),case-insensitive / trim 只在对比时生效;`case_sensitive` 默认 True(区分大小写,跟 checkbox label 语义对齐)。
- **数据对比:Excel 解析表"选列"显示对应表的列**(之前固定显示第一个 A 表的列,Excel 解析的临时表不在 `db_table` 里也能正确显示)。

## 安装

```bash
# 推荐:用 venv
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 安装依赖
pip install -r requirements.txt
# 或锁版本(可复现)
pip install -r requirements2.txt
```

## 启动

```bash
# 开发运行
python main.py

# Windows 一键启动
run.bat
```

## 打包(Windows)

```bash
# 一键
build.bat
# 产物: dist\DBManager\DBManager.exe

# 或手动
pip install pyinstaller
pyinstaller --clean build.spec
```

`build.spec` 已配好:`windowed` 模式、含 `app/` + `app/resources/` 数据、排除无用包。

## 数据存储

- Windows: `%APPDATA%\DBManager\dbmanager.db`
- macOS/Linux: `~/.local/share/DBManager/dbmanager.db`

## 功能一览(v1.0 + v1.1)

| 模块 | 功能 |
| --- | --- |
| **M0 基建** | 主题(深/浅)/ i18n(中英日)/ 可折叠侧边栏/ 线性图标(qtawesome)/ Toast + EmptyState |
| **M1 项目/表结构** | 项目 CRUD / 表 CRUD / 列编辑器(类型/可空/默认值/主键/注释)/ 自动生成 DDL / 数据统计 |
| **M2 常用 SQL 库** | 完整 CRUD / 全局+项目绑定 / 关键字搜索 / 标签 / 复制(use_count +1) |
| **M3 数据版本** | 上传 CSV/TSV/XLSX / 自动 sha256 + 行数(不读全文件)/ 多文件版本 |
| **M4 大文件 diff** ⭐ | 版本 vs 版本 / polars 流式 / 可配置 PK + 忽略列 + 大小写/trim / Worker 线程 / 4 类差异统计 |
| **M5 SQL 生成器** | INSERT(?, %(name)s, 'literal' 三风格)/ DELETE / COPY(PG)/ CSV 导出 / 复制到 SQL 库 / **Export Insert SQL dump (v1.1)** |
| **M6 Excel 模板解析** ⭐ | 模板 CRUD / 配置 sheet + 表名列 + sheet 名列 + header 行 / 多模式(mapping / sheet_name / chinese_name)/ 3 模式预览 |
| **附加 v1.1** | **DB 链接管理(sidebar tab, Ctrl+5)** / **数据对比保留原始大小写** / **选列显示对应表的列** |
| **5 Tab 详情页** | 表结构 / 数据版本 / SQL 生成器 / 数据对比 / 概览 / 快捷键(Ctrl+B/+//+L/+1~6) |

## 项目结构

```
dbmanager/
├── main.py                     # 入口
├── build.spec                  # PyInstaller 打包配置
├── run.bat / build.bat         # 一键启动 / 打包
├── requirements.txt            # 最小依赖(>= 版本)
├── requirements2.txt           # 锁版本(==,可复现)
├── app/
│   ├── bootstrap.py            # 启动初始化
│   ├── config.py               # QSettings
│   ├── paths.py                # 跨平台路径
│   ├── core/                   # 纯函数核心
│   │   ├── file_reader.py      # polars / fastexcel 流式读取
│   │   ├── diff_engine.py      # 表数据 diff(set-based + 原始行展示)
│   │   ├── excel_parser.py     # Excel 多 sheet 模板解析(3 模式)
│   │   └── sqlgen.py           # SQL 批量生成(insert / delete / copy / export / dump)
│   ├── repos/                  # 数据访问层(8 个 repo + db_link_repo)
│   ├── services/               # 业务逻辑层(7 个 service + registry)
│   ├── ui/
│   │   ├── main_window.py      # 主窗口 + 侧边栏 + 顶部栏
│   │   ├── theme.py            # QSS 加载
│   │   ├── i18n.py             # tr() 翻译
│   │   ├── dialogs/            # 弹窗
│   │   ├── pages/              # 5 个主页面(含 db_links_page) + 项目详情 5 Tab
│   │   └── widgets/            # Toast / EmptyState
│   └── resources/
│       ├── i18n/{zh,en,ja}.json  # 3 语翻译
│       └── qss/{dark,light}.qss  # 主题样式
├── docs/                       # 设计文档
└── screenshots/                # 截图
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

- **v1.1.0** — DB 链接管理 + Export Insert SQL dump + 数据对比保留原始大小写 + 选列按对应表
- **v1.0.0** — 完整功能版本(M0–M6 全部实现)

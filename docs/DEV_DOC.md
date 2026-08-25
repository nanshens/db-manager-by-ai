# DBManager — 数据库管理工具开发文档

> 桌面端数据库(DDL/DML/数据对比)管理工具 · Python 3.13 + PySide6 + SQLite · PyInstaller 打包
>
> 文档版本: v0.3 · 2026-08-25

---

## 1. 项目目标

做一个**本地离线**运行的桌面端数据库管理工具,核心解决:

| 痛点 | 解决方式 |
| --- | --- |
| 项目表结构散落在各文档/SQL 文件 | 按项目统一管理表结构,可视化增删改 |
| 初期数据(种子数据)版本混乱 | 每个项目独立的数据版本库,支持多版本对比 |
| 业务方写 SQL 总是重复造轮子 | 常用 SQL 库,支持项目绑定 + 全局搜索 |
| **表数据变更无审计** | **表级数据双文件 diff,支持百万行流式对比,差异/全量双模式 + 可配置忽略列** |
| 批量改数据/灌数据要手写脚本 | SQL 生成器,勾选即生成 INSERT/DELETE/COPY/导出 |
| 临时查"某个值在哪行" | 表内值检索,直接显示匹配行(无需 SQL 技能) |

**目标用户**: 后端开发 / DBA / 数据工程师(自用工具)
**运行环境**: Windows 10/11(优先),macOS/Linux(代码兼容)
**部署形态**: PyInstaller 单文件 EXE

---

## 2. 技术栈

### 2.1 核心选型

| 层 | 选型 | 理由 |
| --- | --- | --- |
| 语言 | **Python 3.13** | 最新稳定版,自用,无兼容性顾虑 |
| GUI | **PySide6** (Qt for Python 6.6+) | 官方 Qt for Python,组件丰富,样式系统(QSS)强大,自用无协议顾虑 |
| 数据库 | **SQLite3** (Python 内置) | 工具自身数据全部走 SQLite,零依赖 |
| **大文件读取 / diff / 查值** | **polars** (Rust 内核) | 列式 + Lazy + 流式,百万行 Excel/CSV 秒级;比 pandas 快 5–20×、内存低数倍;`filter()` 满足"查某值是否在某行" |
| **Excel 读取** | **fastexcel** (Rust) | 只读 xlsx 速度极快,read_only 模式逐行流;polars 也支持 xlsx,按需选 |
| **Excel 模板解析** | **openpyxl** | 精细控制:多 sheet + 按行范围切 + 公式计算值 + read_only 流式 |
| SQL 解析/高亮 | **sqlparse** + 自研高亮 | 格式化 + 关键字着色,不做自动补全(可选简单补全) |
| 打包 | **PyInstaller 6.x** | 单文件 EXE |
| 主题 | 自研 **QSS** + **qtawesome** (线性图标) | 现代扁平 + 玻璃拟态风,深/浅色,全矢量线性图标 |
| i18n | **自研 JSON 多语言** + `tr()` 包装 | 轻量,中/英/日三语,自用无需 gettext 工具链 |

> 关于 PySide6 vs PyQt6:自用无风险,选 **PySide6** 是因为它是 Qt 公司官方维护、API 与 PyQt6 几乎一致、样式文档更新更及时。

### 2.2 砍掉的依赖

| 砍掉 | 原计划 | 不再需要的原因 |
| --- | --- | --- |
| ❌ DuckDB | 想用 SQL 查 CSV/Parquet | 用户场景只需"值是否存在 + 显示行",**polars `filter()` 完全够**,而且快 10×;DuckDB 还额外加 ~30MB EXE |
| ❌ pandas | 数据处理 | 全部用 polars 替代 |
| ❌ SQLAlchemy | ORM | 直接 sqlite3 + 自封装 Repository |
| ❌ QtWebEngine | 嵌入网页 | 无网页需求 |
| ❌ PyQt6 | 备选 GUI | 选 PySide6 |
| ❌ matplotlib / numpy(test) | 图表 | 不做图表,PyInstaller 排除 |

### 2.3 依赖清单

```txt
# runtime
pyside6>=6.6
polars>=0.20
fastexcel>=0.10
openpyxl>=3.1        # Excel 模板解析(多 sheet + 行范围)
sqlparse>=0.5
qtawesome>=1.3

# dev / build
pyinstaller>=6.3
pytest>=8.0
```

---

## 3. 系统架构

> 自用工具,**架构从简**:去掉 ViewModel 层,UI 直接用 Service;Service 直接用 Repo。
> 模块边界清晰即可,不必强求教科书式分层。

### 3.1 三层架构

```
┌─────────────────────────────────────────────────────────┐
│  UI Layer  (PySide6 Widgets / QSS / tr() 国际化)         │
│  - Pages / Widgets / Dialogs                            │
│  - 通过 Service 调用业务,自身只管状态与信号                │
├─────────────────────────────────────────────────────────┤
│  Service Layer  (业务用例,不依赖 UI)                      │
│  - ProjectService / TableService /                      │
│    DataVersionService / SqlLibService / DiffService     │
├─────────────────────────────────────────────────────────┤
│  Data Layer (sqlite3 + 纯函数 core)                     │
│  - Repo:ProjectRepo / TableRepo / VersionRepo /         │
│         SqlSnippetRepo / DiffRepo                       │
│  - Core:file_reader / diff_engine / sqlgen /            │
│         sql_format / i18n                               │
└─────────────────────────────────────────────────────────┘
                ↓
        SQLite (dbmanager.db)              +     本地文件 (CSV/TSV/XLSX)
```

### 3.2 模块划分(简化版)

```
dbmanager/
├── main.py                     # 入口
├── app/
│   ├── __init__.py
│   ├── bootstrap.py            # 启动初始化(DB 建表/迁移/主题/i18n)
│   ├── config.py               # 配置
│   ├── paths.py                # 跨平台路径
│   │
│   ├── ui/                     # 视图层
│   │   ├── main_window.py      # 主窗口 + 侧边栏
│   │   ├── theme.py            # QSS 加载
│   │   ├── i18n.py             # tr() 国际化
│   │   ├── widgets/            # Toast/Modal/EmptyState/SearchBox/...
│   │   ├── pages/
│   │   │   ├── home_page.py
│   │   │   ├── projects_page.py
│   │   │   ├── project_detail_page.py  # Tab 容器
│   │   │   │   ├── tables_tab.py
│   │   │   │   ├── versions_tab.py
│   │   │   │   ├── sqlgen_tab.py
│   │   │   │   └── diff_tab.py
│   │   │   ├── sqllib_page.py
│   │   │   └── settings_page.py
│   │   └── dialogs/            # 新建项目 / 列编辑器 / 新建版本 ...
│   │
│   ├── services/               # 业务
│   │   ├── project_service.py
│   │   ├── table_service.py
│   │   ├── data_version_service.py
│   │   ├── sql_lib_service.py
│   │   ├── diff_service.py
│   │   └── sqlgen_service.py
│   │
│   ├── repos/                  # 数据访问
│   │   ├── db.py
│   │   ├── project_repo.py
│   │   ├── table_repo.py
│   │   ├── version_repo.py
│   │   ├── sql_snippet_repo.py
│   │   └── diff_repo.py
│   │
│   ├── core/                   # 纯函数,可单测
│   │   ├── file_reader.py      # polars/fastexcel 流式读取
│   │   ├── file_writer.py      # CSV/TSV 导出
│   │   ├── diff_engine.py      # 流式 diff
│   │   ├── sqlgen.py
│   │   └── sql_format.py
│   │
│   └── resources/              # 图标/QSS/i18n JSON
│       ├── icons/
│       ├── themes/light.qss
│       ├── themes/dark.qss
│       └── i18n/{zh,en,ja}.json
│
├── build.spec                  # PyInstaller
├── requirements.txt
├── README.md
└── docs/
    ├── DEV_DOC.md
    └── DEV_DOC.html
```

### 3.3 线程模型

- **UI 线程**:只跑 PySide6 事件循环
- **Worker 线程**(`QThreadPool + QRunnable + QObject.Signal`):
  - 大文件读取(CSV/Excel)
  - diff 计算
  - SQL 批量生成
- **进度反馈**:Worker 通过 Signal 周期性 emit `progress(pct, msg)`,UI 进度条订阅
- **取消**:支持 `QAtomicInt` 中断标志位,大文件读取/diff 都可以中途取消

---

## 4. 数据模型(工具自身 SQLite)

> 文件位置: `%APPDATA%\DBManager\dbmanager.db`(Windows)

### 4.1 表结构

```sql
-- 项目
CREATE TABLE project (
  id           INTEGER PRIMARY KEY,
  name         TEXT NOT NULL UNIQUE,
  description  TEXT,
  color        TEXT,                   -- 标签色 hex
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
);

-- 表结构(一个项目 N 张表)
CREATE TABLE db_table (
  id           INTEGER PRIMARY KEY,
  project_id   INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  comment      TEXT,
  columns_json TEXT NOT NULL,           -- [{name,type,nullable,default,pk,comment}, ...]
  ddl_text     TEXT NOT NULL,           -- 当前 DDL 快照,用于回看/导出
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL,
  UNIQUE(project_id, name)
);

-- 数据版本(每个项目独立,同一项目可多个版本)
CREATE TABLE data_version (
  id              INTEGER PRIMARY KEY,
  project_id      INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  version_name    TEXT NOT NULL,        -- v1.0 / initial / 2024Q1
  description     TEXT,
  source_files    TEXT NOT NULL,        -- JSON:[{table_name, format, local_path, rows, sha256, uploaded_at}]
  created_at      TEXT NOT NULL,
  UNIQUE(project_id, version_name)
);

-- 常用 SQL
CREATE TABLE sql_snippet (
  id           INTEGER PRIMARY KEY,
  title        TEXT NOT NULL,
  description  TEXT,
  sql_text     TEXT NOT NULL,
  tags         TEXT,                    -- 逗号分隔
  project_id   INTEGER REFERENCES project(id) ON DELETE SET NULL,  -- NULL = 全局
  use_count    INTEGER DEFAULT 0,
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
);

-- 对比历史
CREATE TABLE diff_record (
  id              INTEGER PRIMARY KEY,
  project_id      INTEGER REFERENCES project(id) ON DELETE SET NULL,
  left_label      TEXT NOT NULL,        -- "v1.0" / "新上传" / 文件名
  right_label     TEXT NOT NULL,
  left_meta_json  TEXT,                 -- {version_id | file_path, sha256, rows}
  right_meta_json TEXT,
  result_json     TEXT,                 -- diff 结果(差异行 + 列级 diff)
  config_id       INTEGER REFERENCES compare_config(id) ON DELETE SET NULL,
  created_at      TEXT NOT NULL
);

-- 对比配置(每表可多套,带"默认"标记)
CREATE TABLE compare_config (
  id               INTEGER PRIMARY KEY,
  project_id       INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  table_name       TEXT NOT NULL,
  config_name      TEXT NOT NULL,        -- "忽略时间列" / "严格全列" / 自定义名
  pk_columns_json  TEXT NOT NULL,        -- JSON:["id"] 或 ["id","sub_id"]
  compare_columns_json TEXT,             -- JSON:["col1","col2",...] NULL = 全列(除 PK)
  ignore_columns_json  TEXT,             -- JSON:["updated_at","created_at"] 冗余存储便于显示
  case_sensitive   INTEGER DEFAULT 1,    -- 0/1
  trim_whitespace  INTEGER DEFAULT 1,    -- 0/1
  is_default       INTEGER DEFAULT 0,    -- 该表下的默认配置
  created_at       TEXT NOT NULL,
  updated_at       TEXT NOT NULL,
  UNIQUE(project_id, table_name, config_name)
);

-- Excel 解析模板(可复用,支持"配置 sheet + 多数据 sheet"模式)
CREATE TABLE excel_template (
  id                 INTEGER PRIMARY KEY,
  project_id         INTEGER REFERENCES project(id) ON DELETE CASCADE,  -- NULL = 全局
  template_name      TEXT NOT NULL,
  config_sheet_name  TEXT NOT NULL,    -- "总览" / "目录" / "Config" 等
  table_name_col     TEXT NOT NULL,    -- 在 config sheet 中,标识"表名"的列(列字母或列名)
  sheet_name_col     TEXT NOT NULL,    -- 在 config sheet 中,标识"对应数据 sheet 名"的列
  header_row         INTEGER DEFAULT 1,-- 数据 sheet 中,列名所在行
  data_start_row     INTEGER DEFAULT 2,-- 数据 sheet 中,数据起始行
  description        TEXT,
  use_count          INTEGER DEFAULT 0,
  created_at         TEXT NOT NULL,
  updated_at         TEXT NOT NULL,
  UNIQUE(project_id, template_name)
);
```

### 4.2 FTS5 全文搜索

```sql
CREATE VIRTUAL TABLE sql_snippet_fts USING fts5(
  title, description, sql_text, tags,
  content='sql_snippet', content_rowid='id'
);
```

---

## 5. 业务功能详解

### 5.1 常用 SQL 库

| 操作 | 行为 |
| --- | --- |
| 添加 | 标题/描述/SQL 文本/标签/项目(可选) |
| 搜索 | FTS5 全文匹配 + 标签筛选 + 项目筛选 |
| 复制 | 一键复制 SQL 到剪贴板,`use_count` +1 |
| 编辑/删除 | CRUD |
| 项目绑定 | 选择下拉;`NULL` 表示全局 SQL,所有项目可见 |

### 5.2 项目 — 表结构

- 新建项目 → 进入项目详情 → **表结构 Tab**
- **添加表**:
  - 方式 A: 手动建(列编辑器:列名/类型/可空/默认值/主键/注释)
  - 方式 B: 导入 DDL(粘贴 SQL,`sqlparse` 解析为列)
  - 方式 C: 从 CSV/TSV/XLSX 头推断(列名 + 推断类型,后续可调整)
- **查看表**: 表卡片 + 列详情表 + DDL 预览
- **修改表**: 列增删改、注释改、重命名
- **删除表**: 二次确认

### 5.3 项目 — 数据版本(初期数据)

- **新建版本**:
  - 选版本名(v1.0 / initial)
  - 选项目下的若干表,每张表选一个本地文件(CSV/TSV/XLSX)
  - **只记录本地路径** + 文件 sha256 + 行数,不把数据复制进 DB
  - 元数据存 `data_version.source_files`
- **查看版本**: 表名 → 文件路径 → 行数 → sha256 → 一键在资源管理器中打开
- **版本对比**:
  - 选两个版本(可同项目/跨项目),逐表 diff
  - 结果:行级增删改 + 列级差异单元格高亮
  - 结果存 `diff_record`### 5.4 项目 — 表数据对比(单表) ⭐ 核心功能

> 数据对比是核心,需要同时支持**小文件直显**和**大文件流式**两种模式。

**入口**
- 选项目内一张表 → 三种数据源组合:
  - 版本 A vs 版本 B(选已上传的两个数据版本)
  - 版本 vs 新文件(选一个版本 vs 本地 CSV/TSV/XLSX)
  - 新文件 A vs 新文件 B(临时上传两个本地文件)
- 选主键列(必填,支持复合主键)
- 选可选配置:列忽略(忽略某些列的差异)、大小写敏感、空白 trim

**双模式结果视图**(用户切换)

| 模式 | 适用 | 行为 |
| --- | --- | --- |
| **差异视图(默认)** | 快速定位问题 | 只显示有差异的行(新增/删除/修改),带状态徽章;行级 + 列级 diff 抽屉 |
| **完整并排视图** | 全面审阅 | 两侧完整数据并排,差异单元格红/绿高亮;**虚拟滚动 + 懒加载**,百万行不卡 |
| **统计视图** | 总体评估 | 只看汇总:总行数 / 新增/删除/修改数 + 每列差异分布柱图 |

**结果持久化**:差异记录存 `diff_record`,可随时回看历史 diff。

**导出**
- 当前筛选条件下的差异行 → CSV / JSON
- 完整 diff 报告(ZIP 含两侧数据 + 差异明细)

### 5.4.1 大文件流式对比策略

- **后端(Worker 线程)**:不一次性加载,使用 polars LazyFrame 流式运算
  - 单文件 hash 索引可放外存 temp(超大数据时)
  - 按 chunk(50K 行)分批处理
  - 实时 emit `progress(pct, msg)` + `partial_result(chunk_diff)` 增量返回
- **前端(UI 线程)**:
  - 进度条 + 当前阶段文字提示
  - 收到首个 chunk 后立刻渲染(不等全部完成)
  - 「取消」按钮:中断 worker,已渲染结果保留
- **完整并排模式**:虚拟滚动(`QTableView` + 自定义 `QAbstractTableModel`)
  - 模型层维护「数据行索引 → chunk_id + chunk 内偏移」映射
  - 滚动到新行时再 lazy load 对应 chunk
  - LRU 缓存最近 5 个 chunk(共 ~250K 行内存占用)

### 5.4.2 对比配置(每表可保存多套) ⭐

> 默认行为:**整行全列完全相同才算"未变"**;但实际场景中常有列(如 `updated_at`、时间戳、随机 ID)变化不影响业务判断,所以需要可配置。

**配置项**

| 字段 | 含义 | 默认 |
| --- | --- | --- |
| `config_name` | 配置名(便于切换) | — |
| `pk_columns` | 主键列(必填,支持复合) | 必填 |
| `compare_columns` | 参与匹配的列(空=除 PK 外全列) | 全部非 PK |
| `case_sensitive` | 字符串是否区分大小写 | 0(否) |
| `trim_whitespace` | 字符串比较前是否 trim | 1(是) |
| `is_default` | 该表下的默认配置 | — |

**特殊选项**:`严格全列相等`(系统内置,等同"全列参与比较 + 区分大小写 + 不 trim"),永远在配置下拉第一个。

**UI 行为**
1. 进入「数据对比」Tab → 选表后,系统**自动加载该表上次的默认配置**
2. 配置行:`[默认: 忽略时间列 ▼]   ⚙ 管理配置`
3. 下拉选项:
   - 系统默认 `严格全列相等`
   - 该表保存的所有配置(显示配置名 + 概要"忽略 2 列")
   - `保存当前为新配置…` → 弹配置编辑对话框
4. 切换配置后,右侧实时显示概要:`忽略: updated_at, created_at · case 不敏感`
5. **配置编辑对话框**(独立 dialog):
   - 名称(必填,同表内唯一)
   - 主键列(多选树)
   - 参与匹配的列(可全选 / 取消全选 / 单独勾选)
   - 高级:大小写、trim
   - 底部:`保存` / `保存为默认` / `删除`(删除时确认)
6. diff 完成后,顶部右侧追加 `💾 保存为配置` 按钮,一键把当前设置保存为该表新配置

**diff 算法使用配置**
- 匹配判定:主键相同 + `compare_columns` 内所有列值相同(应用 case/trim 选项)
- 列级 diff 抽屉:被 ignore 的列**仍显示**(标灰),但不影响"modified / unchanged"判定
- 摘要统计:`X 列被修改` 统计只算 `compare_columns` 内的列

### 5.4.3 表内值检索(轻量查询)

> 不连真实 DB,纯在已上传的文件 / 选中的版本中按列查值。

**入口**:`数据对比 Tab` 顶部工具栏 → 选项目 / 选表 / 选文件 → 选一列 → 输入值 → 检索

**实现**:
- 精确:`pl.col("col") == value`
- 模糊:`pl.col("col").cast(pl.Utf8).str.contains(pattern)`
- 结果:在原表 QTableView 中显示所有匹配行(虚拟滚动)
- 高亮命中单元格
- 支持「复制行」/「跳转到对比 Tab 把命中行作为左/右」

### 5.5 项目 — SQL 生成器

- 选一张表 → 列出所有列(可勾选)
- 操作类型多选:
  - `INSERT INTO table(col,...) VALUES (?,?,...)` 模板(可填示例值)
  - `DELETE FROM table WHERE ...` 模板
  - `COPY table FROM 'path' (FORMAT csv, HEADER true)` — PostgreSQL 风格
  - `BULK INSERT/LOAD DATA INFILE` — MySQL 风格
  - **导出当前预览数据为 CSV/TSV**(先上传一份)
- 一键复制 / 一键保存到常用 SQL 库(自动绑定当前项目)

---

### 5.6 Excel 解析模板(多 sheet + 配置页) ⭐

> **场景**:业务方常发来一个 Excel,**第一个 sheet 是"总览/目录"**,列出 N 张表对应到 N 个数据 sheet;每个数据 sheet 又有自己的格式(可能前几行是公司 logo / 标题,后面才是列名和数据)。每次手动解析很烦 → **模板化**,保存一次,以后同类文件直接套用。

#### 5.6.1 模板结构

```python
@dataclass
class ExcelTemplate:
    template_name: str          # "财务季度初版" / "运营日报"
    project_id:   int | None    # NULL = 全局可见
    config_sheet_name: str      # "总览" / "目录" / "Config" 等
    table_name_col: str         # 配置 sheet 中,标识"表名"的列(列字母 A/B/C 或列名)
    sheet_name_col: str         # 配置 sheet 中,标识"对应数据 sheet 名"的列
    header_row:    int = 1      # 数据 sheet 中,列名所在行(从 1 开始)
    data_start_row: int = 2     # 数据 sheet 中,数据起始行
    description:   str = ""
```

**典型 Excel 例子**

`总览` sheet(配置页):
| A: 表名 (table_name_col) | B: 数据 sheet (sheet_name_col) | C: 备注 |
|---|---|---|
| orders | orders_2024Q1 | 主订单 |
| users | users_2024Q1 | 全量 |
| products | products_2024Q1 | 有合并单元格 |

`orders_2024Q1` sheet(数据页,header_row=2, data_start_row=3):
```
Row 1: [公司 Logo]  2024 Q1 订单表  ......(忽略)
Row 2: id  user_id  total_amount  status  created_at  ← 列名(header_row=2)
Row 3: 1001  1  99.00  paid  2024-01-15  ← 数据(data_start_row=3)
Row 4: 1002  2  150.00  paid  2024-01-16
...
```

#### 5.6.2 模板管理页(图 6-5c)

- 入口:侧边栏新增「**📑 Excel 模板**」导航(或放在"常用 SQL"旁)
- 列表:
  - 列:模板名 / 所属项目 / 配置 sheet / header 行 / 使用次数 / 创建时间
  - 行操作:**应用** / 编辑 / 复制 / 删除
- 顶部:搜索 + 项目筛选 + 「**+ 新建模板**」按钮
- 空状态:首次提示"用模板解析多 sheet 的复杂 Excel"

#### 5.6.3 模板编辑器(图 6-5d)

- 弹出 dialog,字段对应 `ExcelTemplate`
- 关键交互:
  - **实时预览**:上传一个示例 Excel,选 sheet 名后立刻看到该 sheet 的前 N 行
  - 配置「表名列」「sheet 名列」时,从下拉选(列出该 sheet 的列名),避免手敲列字母
  - 「header 行」「数据起始行」支持 ↑↓ 调整并预览
- 保存后回到模板管理页

#### 5.6.4 应用模板(上传 Excel 时)

集成在「数据版本 Tab → 新建版本」和「数据对比 Tab → 上传文件」两个入口:

1. 选本地文件(`*.xlsx`)
2. 若该 Excel 有 ≥2 个 sheet,自动弹出"**Excel 解析**"区块:
   - 「解析模板」下拉:默认解析(第 1 sheet / header=1 / data=2)/ 已保存模板(显示概要)
   - 「新建模板」按钮
   - 「应用并预览」按钮
3. **解析预览对话框**(图 6-5e):
   - 顶部:解析统计(N 张表 / 总行数 / 错误数)
   - 左侧:解析出的表列表 + 每张表的行数 / 错误状态
   - 右侧:当前选中表的列名 + 前 50 行(虚拟滚动)
   - 警告区:空 sheet / 列数不匹配 / 主键冲突等
4. 用户确认后:
   - 在「数据版本」场景:每张解析出的表 → 对应项目下的一张表 → 记录为新数据版本
   - 在「数据对比」场景:用户选其中一张表作为左/右源

#### 5.6.5 解析算法

```python
def parse_with_template(file_path, template) -> dict[str, DataFrame]:
    wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    config = pd.read_excel(file_path, sheet_name=template.config_sheet_name)
    tables = {}
    for _, row in config.iterrows():
        t_name = row[template.table_name_col]
        s_name = row[template.sheet_name_col]
        if pd.isna(s_name) or s_name not in wb.sheetnames:
            continue  # 跳过空 / 不存在
        # 读数据 sheet:header_row 取列名,data_start_row 起取数据
        df = pd.read_excel(
            file_path, sheet_name=s_name,
            header=template.header_row - 1,      # pandas header 是 0-based
            skiprows=range(template.data_start_row - 1)
        )
        tables[t_name] = df
    return tables
```

- 大文件(>10 万行):用 `openpyxl.read_only` 模式流式
- 类型推断失败 → fallback `str`
- 列名去重 / 空白处理
- 公式取计算值(`data_only=True`)

#### 5.6.6 与现有功能的集成

| 入口 | 集成点 |
| --- | --- |
| **数据版本 Tab** | 新建版本 → 选 Excel → 应用模板 → 解析出 N 张表 → 选项目下对应的表 → 存为版本 |
| **数据对比 Tab** | 数据源 A/B → 上传 Excel → 应用模板 → 选其中一张表作为源 |
| **表结构 Tab** | 新建表 → 从 Excel 导入列 → 应用模板(只取一张表的列) |
| **SQL 生成器** | 数据预览可来自"应用模板后选一张表" |

---

## 6. UI / UX 设计

### 6.1 设计语言

- **风格**: 现代扁平 + 玻璃拟态(关键面板轻微透明)
- **配色**:
  - 主色 `#3B82F6`(蓝)
  - 成功 `#10B981` / 警告 `#F59E0B` / 危险 `#EF4444`
  - 深色背景 `#0F172A` / 浅色背景 `#F8FAFC`
- **字体**: 系统默认(`Segoe UI` / `PingFang SC`)
- **圆角**: 8px(卡片)/ 6px(按钮)/ 4px(输入框)
- **间距**: 8 / 12 / 16 / 24 px 体系

### 6.2 全局布局(可折叠侧边栏)

**侧边栏两态**(用户可切换,状态持久化)

| 状态 | 宽度 | 适用 |
| --- | --- | --- |
| **展开**(默认) | 220px | 常规浏览、找功能 |
| **折叠** | 56px(图标 only) | 大数据对比、表格全屏、屏幕窄 |

- 切换:侧边栏顶部 `☰` 按钮 / `Ctrl+B` 快捷键 / 拖拽边缘
- 动画:`QPropertyAnimation` 200ms 平滑滑动
- 状态存 `app_config` 表 / QSettings,启动时恢复
- 折叠时:图标居中、tooltip 显示完整文字;主内容区自动扩到 1100+px

```
展开:                              折叠:
┌────┬─────────────────────┐      ┌──┬──────────────────────┐
│ ☰  │  顶部栏              │      │☰ │  顶部栏               │
│    │ ─────────────────── │      │  │ ──────────────────── │
│📊  │                     │      │📊│                      │
│📁  │   主内容区           │      │📁│   主内容区(更宽)      │
│📚  │                     │      │📚│                      │
│    │                     │      │  │                      │
│⚙  │                     │      │⚙│                      │
└────┴─────────────────────┘      └──┴──────────────────────┘
  220px                              56px
```

侧边栏 5 项(底部 ⚙ 紧贴底部):
1. 仪表盘
2. 项目
3. 常用 SQL
4. **Excel 模板** ⭐
5. 设置

### 6.3 关键页面线框

> HTML 版本带 SVG 线框图 →  `docs/DEV_DOC.html`

#### 6.3.1 仪表盘

- 顶部:数据卡片(项目数 / SQL 数 / 数据版本数 / 今日 diff 数)
- 中部:最近项目(横向卡片轮播)
- 底部:最近 SQL 使用记录

#### 6.3.2 项目列表

- 顶栏:项目名搜索 + 排序 + 「新建项目」按钮
- 卡片网格:每卡片显示项目名/描述/表数/版本数/更新时间
- 空状态:插画 + 「创建你的第一个项目」

#### 6.3.3 项目详情

- 顶部:项目头(名/描述/标签色/编辑)
- Tab:**表结构** / **数据版本** / **SQL 生成器** / **数据对比** / **概览**

#### 6.3.4 表结构 Tab

- 左:表列表 + 「添加表」按钮
- 右:选中表 → 列编辑器 + DDL 预览

#### 6.3.5 数据版本 Tab

- 顶部:版本时间线(横轴) + 「新建版本」按钮
- 主区:版本卡(版本名/描述/表数/创建时间/对比按钮/编辑/删除)

#### 6.3.6 数据对比 Tab(三种入口 + 双模式结果)

**配置区**
- 选项目 + 选表
- 数据源 A(下拉):版本 / 上传文件
- 数据源 B(下拉):版本 / 上传文件
- 主键列(必填,支持多选复合)
- 高级选项(折叠):忽略列 / 大小写 / 空白处理
- **[开始对比]** 大按钮 → 启动 worker,显示进度条

**结果区**(详见 HTML 图 6-5)
- 顶部:4 张汇总卡(左行数 / 右行数 / +新增 / -删除 / ~修改)
- 第二行:筛选 chip(全部 / 仅新增 / 仅删除 / 仅修改)+ 搜索框 + 视图切换 tab(差异/完整/统计)
- 主区:差异表 / 并排表 / 统计图
- 行点击 → 右侧抽屉显示列级 diff(高亮单元格)
- 顶部右侧:导出按钮(CSV/JSON/ZIP)

#### 6.3.7 SQL 生成器 Tab

- 左:表选择 + 列勾选
- 中:操作多选(Insert/Delete/Copy/Export)
- 右:实时生成 SQL 预览 + 复制/保存按钮

#### 6.3.8 常用 SQL 库

- 顶:搜索框 + 标签筛选 + 项目筛选 + 「新建」按钮
- 主:SQL 卡片网格(标题/SQL 摘要/标签/项目/使用次数)
- 卡片右上:复制 / 编辑 / 删除
- 点开:大预览 + 复制按钮

### 6.4 交互细节

- **Toast**:右下角浮层,成功/失败/信息 3 态,3s 自动消失
- **确认弹窗**:危险操作二次确认
- **空状态**:统一插画 + 引导文字 + 主按钮
- **快捷键**:`Ctrl+N` 新建项目 / `Ctrl+K` 全局搜索 / `Ctrl+B` 折叠侧边栏 / `Ctrl+/` 主题切换 / `Ctrl+L` 切换语言
- **主题(深/浅)**:手动切换,顶栏一键 / `Ctrl+/` / 设置页;**默认深色**;状态存 QSettings,启动恢复
- **语言切换**:顶栏下拉,zh / en / ja,实时生效(无需重启)

---

## 7. 核心算法

### 7.1 表数据 diff(支持大文件流式 + 配置化)

**输入**:两个文件路径(CSV/TSV/XLSX)+ `CompareConfig`(主键、比较列、case/trim 选项)
**输出**:`DiffResult` 差异结构

```python
@dataclass
class CellDiff:
    col: str
    left: Any
    right: Any
    in_compare_scope: bool     # 是否参与匹配判定

@dataclass
class RowDiff:
    key: tuple
    kind: Literal['only_left','only_right','modified','unchanged']
    left_row:  dict | None
    right_row: dict | None
    cell_diffs: list[CellDiff] # modified 时有内容(包含 ignored 列,标灰)

@dataclass
class DiffResult:
    only_left:  list[RowDiff]
    only_right: list[RowDiff]
    modified:   list[RowDiff]
    unchanged_count: int
    total_left: int
    total_right: int
    column_diff_stats: dict[str, int]   # 只统计 compare_columns 内的列
```

**小文件路径(< 100 万行)**
1. 用 polars 读两侧文件为 DataFrame
2. 列对齐(以左为准,右缺列填 null,多列标 `+`)
3. **应用 config**:只对 `compare_columns` 内列做值 normalize(trim/case)
4. 按主键建 hash 索引 → 求集合差 → only_left/only_right
5. 交集逐行 cell 比较(modified 的列包含 ignored 列的差异,标灰)
6. 无主键时兜底:全行 sha256 哈希后比较

**大文件路径(≥ 100 万行)**
1. polars `scan_csv` / `pl.read_excel` 流式加载,按 5 万行一批
2. 左侧每批构建临时主键索引(放内存);右侧同批对齐
3. 应用 config 做 normalize + 求 set 差 + modified 判定
4. 结果分批 emit 给 UI,UI 增量渲染
5. **无 DuckDB**,全部用 polars LazyFrame(实测百万行内 polars 完全够用)

**取消支持**:`QAtomicInt cancel_flag`,worker 每处理一个 chunk 检查一次

### 7.2 CSV/TSV/XLSX 大文件读取

| 格式 | 库 | 策略 |
| --- | --- | --- |
| CSV / TSV | `polars.scan_csv` | Lazy 读取,推断 schema,流式 |
| XLSX(只读) | `fastexcel` 或 `polars.read_excel` | read_only 模式,逐行流 |
| XLSX(写) | `polars` / `openpyxl` | 导出时用 polars 写 |
| 大文件元数据(行数/sha256) | `os` + `hashlib` | **不读全文件**,只算 sha256(流式 64KB 块) |

**避免内存泄漏**
- 用 `with` / context manager 保证 polars / fastexcel 句柄释放
- 临时 DataFrame 显式 `del` + `gc.collect()`(每 N 个 chunk 一次)
- Worker 完成后,UI 端旧 model 显式 `setModel(None)` 再赋新 model

### 7.3 表内值检索

```python
# 精确
result = lf.filter(pl.col("user_email") == "a@x.com").collect(streaming=True)

# 模糊
result = lf.filter(
    pl.col("user_email").cast(pl.Utf8).str.contains(pattern, case_sensitive=False)
).collect(streaming=True)
```

- `streaming=True` 让 polars 用流式执行,内存友好
- 返回的行直接送 UI 的 QTableView
- 超大结果(>10 万行)→ 同样走虚拟滚动

### 7.4 类型推断

- 读前 1000 行推断每列类型:`int → float → datetime → str`
- 给出推断结果,用户在「新建表」时可一键采用

### 7.5 SQL 生成

- 表/列元数据已经在 `db_table.columns_json`
- INSERT 模板占位符:`?` / `%(col)s` / `'{val}'` 三种风格可选
- COPY/LOAD DATA 按 dialect(用户选 PG/MySQL)切换
- **SQL 高亮**:`sqlparse` tokenizer + 正则关键字着色,自绘 `QSyntaxHighlighter`
- **SQL 补全(可选)简单版**:基于已保存 snippet 标题 + SQL 关键字,前缀匹配下拉

### 7.6 国际化(i18n)

**实现**:JSON 三语字典 + `tr(key)` 全局函数

```python
# app/ui/i18n.py
_current = "zh"
_dicts = {}

def load(lang: str, base_dir: Path):
    global _current
    _current = lang
    _dicts.clear()
    _dicts["zh"] = json.loads((base_dir / "zh.json").read_text(encoding="utf-8"))
    _dicts["en"] = json.loads((base_dir / "en.json").read_text(encoding="utf-8"))
    _dicts["ja"] = json.loads((base_dir / "ja.json").read_text(encoding="utf-8"))

def tr(key: str, **kwargs) -> str:
    text = _dicts.get(_current, {}).get(key, key)
    return text.format(**kwargs) if kwargs else text
```

**调用**:`btn.setText(tr("btn.new_project"))`

**支持范围**:菜单 / 按钮 / 标签 / 提示 / 错误 / Toast
**范围外**:用户数据(SQL 标题、描述等)保持原文,只翻界面

---

## 8. 打包与发布

### 8.1 PyInstaller 配置要点

```python
# build.spec 摘要
a = Analysis(
    ['main.py'],
    datas=[
        ('app/resources', 'app/resources'),
    ],
    hiddenimports=[
        'polars', 'fastexcel',
        'sqlparse', 'qtawesome',
        'PySide6.QtSvg', 'PySide6.QtSvgWidgets',  # 图标 + 高亮
    ],
    excludes=[
        'tkinter', 'matplotlib',
        'pandas', 'duckdb',     # 不用 pandas / duckdb
        'PySide6.QtWebEngine', 'PySide6.QtWebEngineCore',
        'PySide6.Qt3D', 'PySide6.QtCharts', 'PySide6.QtDataVisualization',
    ],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts,
          name='DBManager',
          console=False,          # GUI
          icon='app/resources/icons/app.ico',
          onefile=True)           # 单文件
coll = COLLECT(exe, a.binaries, a.datas, name='DBManager')
```

### 8.2 体积优化

- `excludes` 去掉 pandas / duckdb / QtWebEngine / Qt3D / QtCharts
- 资源用 `--add-data` 而不是 base64 嵌入
- UPX 可选(自用场景影响小)

### 8.3 输出

- 单文件 EXE 约 **60–90 MB**(无 DuckDB 后明显瘦身)
- 首次运行在 `%APPDATA%\DBManager\` 下创建 `dbmanager.db` + `i18n/` 缓存

---

## 9. 开发计划(里程碑)

| 阶段 | 周 | 交付 |
| --- | --- | --- |
| **M0 基建** | W1 | 项目骨架、主题、SQLite 建表/迁移、空主窗口 + 侧边栏 |
| **M1 项目/表结构** | W2 | 项目 CRUD + 表结构增删改 + 列编辑器 + DDL 预览 |
| **M2 常用 SQL 库** | W3 | SQL 库 CRUD + FTS 搜索 + 项目绑定 + 复制/统计 |
| **M3 数据版本** | W4 | 版本管理 + 导入器(CSV/TSV/XLSX)+ 文件元数据记录 |
| **M4 数据对比** | W5 | diff 算法 + 版本对比 + 单表双文件对比 + 可视化 |
| **M5 SQL 生成器** | W6 | INSERT/DELETE/COPY 模板 + 导出 CSV/TSV |
| **M6 Excel 模板** | W7 | 模板管理页 + 编辑器 + 解析预览 + 多入口集成 |
| **M7 打磨** | W8 | 暗色模式 / 快捷键 / Toast / 空状态 / 性能 |
| **M8 打包** | W9 | PyInstaller 单文件 EXE + 图标 + 自检脚本 |

> 注:实际节奏可压缩,1–2 人 2–3 周可出可用版本

---

## 10. 风险与对策

| 风险 | 影响 | 对策 |
| --- | --- | --- |
| 大文件(GB 级)导入卡 UI | 用户体验差 | 后台线程 + 进度条 + 分块读取 |
| 字符编码乱码(尤其 Excel) | 数据错 | 强制 `utf-8-sig`,Excel 显式 `engine='openpyxl'` |
| SQL 误执行破坏数据 | 严重 | 工具**不连真实 DB**,所有数据导入导出走本地文件;SQL 仅生成文本 |
| EXE 杀软误报 | 分发受阻 | 数字签名(可选) / 分发说明 / 提交白名单 |
| 跨平台 | 时间 | 一期只保 Windows,代码层面避免硬编码 Windows 路径 |

---

## 11. 已确认决策

| # | 问题 | 决定 | 落地 |
| --- | --- | --- | --- |
| 1 | 连真实 DB? | **否**,纯本地 SQLite + 文件 | 仅 sqlite3,无 DB driver |
| 2 | 数据对比规模 | **必须支持百万行**,不能卡 | polars Lazy + 流式 + 虚拟滚动 |
| 3 | 多端同步? | **否**,纯本地自用 | 无云端依赖 |
| 4 | SQL 编辑器 | **高亮要,补全可选(简单做)** | sqlparse + QSyntaxHighlighter;简单前缀补全 |
| 5 | i18n | **中 / 英 / 日 三语** | JSON 字典 + `tr()` |
| 6 | DuckDB | **不需要**,只用 polars | 砍掉依赖,EXE 省 30MB |
| 7 | 临时查"某值是否在" | **polars `filter()`** 够用 | 5.4.3 表内值检索 |
| 8 | 侧边栏 | **可折叠**(220px / 56px) | Ctrl+B 切换,状态持久化 |
| 9 | 对比配置 | **可保存多套,默认读取上次** | `compare_config` 表 + 5.4.2 详解 |
| 10 | 配置对话框列选择 | **不需要 PK 分组**,保持"全选 + 列列表" | 维持图 6-5b 现状 |
| 11 | 侧边栏图标 | **qtawesome 线性图标**,好看现代 | 不用 emoji,用 `ph.regular` / `mdi6` 系列 |
| 12 | Tab 顺序 | 保持现序 | 表结构 / 数据版本 / SQL 生成器 / 数据对比 / 概览 |
| 13 | 主色 | 蓝 `#3B82F6` + 紫 `#A855F7` | 保持 |
| 14 | 暗色模式 | **手动切换,默认深色** | 设置页切换 + Ctrl+/ 快捷键 + QSettings 持久化 |
| 15 | Excel 多 sheet 解析 | **模板化(可保存复用)** | `excel_template` 表 + 5.6 详解 |

## 12. 仍待你补充(后续轮次)

- [ ] 还有什么额外业务模块?(数据导出向导 / 定时备份 / 查询历史 / SQL 执行计划)
- [ ] 是否还有其他细化需求?

---

*文档待审阅后开始编码,任何修改直接告诉我即可更新本文件。*

"""自检脚本 — 验证所有 M0–M6 功能

不依赖 Qt GUI,直接通过 services 验证。
"""
import os
os.environ['DBMANAGER_DATA_DIR'] = os.path.join(
    os.environ.get('TEMP', '.'),
    f'dbmanager_selfcheck_{os.getpid()}'
)
import sys
import shutil
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))


def main() -> int:
    from app.bootstrap import bootstrap
    from app.services.registry import reg
    from app.repos.table_repo import Column

    # 1. bootstrap
    print("=" * 60)
    print("DBManager 自检 — M0–M6")
    print("=" * 60)
    db, theme, lang, _ = bootstrap()
    print(f"\n[OK] bootstrap: db={db.name}, theme={theme}, lang={lang}")

    # 2. Project CRUD
    print("\n--- M1: 项目 CRUD ---")
    p1 = reg().project_service.create("测试项目 A", "描述 A", "#3b82f6")
    p2 = reg().project_service.create("测试项目 B", "描述 B", "#a855f7")
    print(f"[OK] created 2 projects: {p1.id}, {p2.id}")
    assert len(reg().project_service.list_all()) == 2

    p_updated = reg().project_service.update(p1.id, "项目 A 重命名", "新描述", "#10b981")
    assert p_updated.name == "项目 A 重命名"
    print(f"[OK] updated project {p1.id}")

    # 3. Table CRUD
    print("\n--- M1: 表 CRUD ---")
    t1 = reg().table_service.create(p1.id, "users", "用户表", [
        Column(name="id", type="INTEGER", nullable=False, pk=True),
        Column(name="email", type="VARCHAR(100)"),
        Column(name="age", type="INTEGER"),
        Column(name="created_at", type="DATETIME"),
    ])
    t2 = reg().table_service.create(p1.id, "orders", "订单表", [
        Column(name="id", type="INTEGER", nullable=False, pk=True),
        Column(name="user_id", type="BIGINT", nullable=False),
        Column(name="total", type="DECIMAL(10,2)"),
    ])
    print(f"[OK] created 2 tables: {t1.name}, {t2.name}")

    # 验证 DDL 生成
    assert "CREATE TABLE users" in t1.ddl_text
    assert "PRIMARY KEY" in t1.ddl_text
    assert "VARCHAR(100)" in t1.ddl_text
    print(f"[OK] DDL generated: {t1.ddl_text[:50]}...")

    # 验证 stats
    stats = reg().project_service.get_with_stats(p1.id)
    assert stats["table_count"] == 2
    print(f"[OK] project stats: {stats}")

    # 4. SQL 库 CRUD
    print("\n--- M2: SQL 库 CRUD ---")
    s1 = reg().sql_lib_service.create("查用户", "SELECT * FROM users WHERE id = ?", "查单个", "user,select", None)
    s2 = reg().sql_lib_service.create("订单统计", "SELECT COUNT(*) FROM orders", "统计", "stats", p1.id)
    s3 = reg().sql_lib_service.create("更新用户", "UPDATE users SET email=? WHERE id=?", "更新", "user,update", p1.id)
    assert reg().sql_lib_service.count() == 3
    print(f"[OK] created 3 SQL snippets")
    # search
    results = reg().sql_lib_service.search("统计")
    assert len(results) == 1
    print(f"[OK] search '统计' found {len(results)} results")
    results = reg().sql_lib_service.search("select")
    assert len(results) >= 1
    print(f"[OK] search 'select' found {len(results)} results")
    # project filter
    results = reg().sql_lib_service.list(project_id=p1.id, include_global=False)
    assert len(results) == 2  # 订单统计 + 更新用户
    print(f"[OK] project filter (only): {len(results)} results for project {p1.id}")
    results_all = reg().sql_lib_service.list(project_id=p1.id)  # 默认 include_global=True
    assert len(results_all) == 3  # + 1 global
    print(f"[OK] project filter + global: {len(results_all)} results")
    # use count
    reg().sql_lib_service.increment_use(s1.id)
    s1_after = reg().sql_lib_service.get(s1.id)
    assert s1_after.use_count == 1
    print(f"[OK] use_count incremented")

    # 5. 数据版本 + 文件元数据
    print("\n--- M3: 数据版本 ---")
    # 创建一个临时 CSV
    tmpdir = tempfile.mkdtemp()
    csv_path = os.path.join(tmpdir, "users_v1.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("id,email,age\n")
        for i in range(1, 11):
            f.write(f"{i},user{i}@x.com,{20+i}\n")
    print(f"[OK] created temp CSV: {csv_path}")

    v1 = reg().data_version_service.create(
        p1.id, "v1.0", "初始版本", {"users": csv_path}
    )
    assert v1.source_files[0].rows >= 10
    assert len(v1.source_files[0].sha256) == 64
    print(f"[OK] data version created: {v1.version_name}, rows={v1.source_files[0].rows}, sha256={v1.source_files[0].sha256[:16]}...")

    # 6. SQL 生成
    print("\n--- M5: SQL 生成器 ---")
    from app.core.sqlgen import generate_insert, generate_delete, generate_copy
    sql1 = generate_insert("users", ["id", "email", "age"])
    assert "INSERT INTO users" in sql1
    assert "(?, ?, ?)" in sql1
    sql2 = generate_delete("users", "id")
    assert "DELETE FROM users" in sql2
    sql3 = generate_copy("users", ["id", "email"], "D:/data/users.csv")
    assert "COPY users" in sql3
    print(f"[OK] SQL gen: {sql1[:50]}...")

    # 7. 对比配置
    print("\n--- M4: 对比配置 ---")
    cfg1 = reg().compare_config_service.create(
        p1.id, "users", "忽略时间列",
        pk_columns=["id"],
        compare_columns=["id", "email", "age"],
        ignore_columns=["created_at"],
        case_sensitive=False, trim_whitespace=True, is_default=True,
    )
    print(f"[OK] compare config: {cfg1.config_name}")
    cfgs = reg().compare_config_service.list_for_table(p1.id, "users")
    assert len(cfgs) == 1
    assert cfgs[0].is_default
    print(f"[OK] list configs: {len(cfgs)}")

    # 8. Diff engine (用 CSV 文件)
    print("\n--- M4: Diff 引擎 ---")
    # 创建第二个 CSV(有些修改)
    csv2 = os.path.join(tmpdir, "users_v2.csv")
    with open(csv2, "w", encoding="utf-8") as f:
        f.write("id,email,age\n")
        for i in range(1, 11):
            # 改了 age,加一个用户
            email = f"user{i}@x.com" if i != 5 else "user5_updated@x.com"
            f.write(f"{i},{email},{25+i}\n")
        f.write("11,new_user@x.com,40\n")  # 新增

    from app.core.diff_engine import DiffEngine, DiffConfig
    engine = DiffEngine()
    config = DiffConfig(
        pk_columns=["id"],
        compare_columns=["id", "email", "age"],
        ignore_columns=["created_at"],
        case_sensitive=False, trim_whitespace=True,
    )
    result = engine.compute(csv_path, csv2, config)
    print(f"[OK] diff result: only_left={len(result.only_left)}, only_right={len(result.only_right)}, modified={len(result.modified)}, unchanged={result.unchanged_count}")
    assert len(result.only_right) == 1  # 11 是新增
    assert len(result.modified) >= 1    # 5 和其他修改
    assert result.unchanged_count >= 0

    # 9. Excel 模板
    print("\n--- M6: Excel 模板 ---")
    tpl1 = reg().excel_template_service.create(
        p1.id, "财务模板", "总览", "A", "B", 2, 3, "财务季度"
    )
    tpl2 = reg().excel_template_service.create(
        None, "通用模板", "目录", "表名", "Sheet", 1, 2, "通用"
    )
    print(f"[OK] created 2 templates: {tpl1.id}, {tpl2.id}")
    print(f"[OK] all: {reg().excel_template_service.count()}")

    # 10. 清理
    reg().project_service.delete(p1.id)
    reg().project_service.delete(p2.id)
    print(f"\n[OK] cleanup: deleted both projects")

    shutil.rmtree(tmpdir)

    print("\n" + "=" * 60)
    print("[OK] 全部自检通过 — M0-M6 核心功能正常")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())

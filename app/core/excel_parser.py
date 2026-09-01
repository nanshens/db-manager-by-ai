"""Excel 解析 — 支持 3 种模式

模式:
1. mapping (默认): 配置 sheet(TOTAL/索引页)有 table_name_col + sheet_name_col,
                   按配置读映射,再解析对应 sheet
2. sheet_name: 跳过配置,把所有 sheet 名直接当英文表名
3. chinese_name: sheet 名是中文,通过 template.name_mapping JSON 转换(中文→英文表名)

数据页配置(全局,所有 sheet 共用):
- header_row: 列名所在行(1-based)
- data_start_row: 数据起始行(1-based)
- column_start: 数据起始列(1-based)
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import openpyxl
from openpyxl.utils.exceptions import InvalidFileException
import polars as pl
import json

from app.repos.excel_template_repo import ExcelTemplate


@dataclass
class ParseResult:
    """单张表的解析结果"""
    table_name: str       # 英文表名(给数据对比用的 key)
    sheet_name: str       # 原始 sheet 名
    columns: list[str]
    rows: int
    error: str = ""        # 空 = 成功
    sample_rows: list[list] = None  # 前 10 行


def parse_excel(file_path: str, template: ExcelTemplate,
                sample_size: int = 10) -> tuple[list[ParseResult], list[str]]:
    """解析 Excel,根据 template.parse_mode 分发到不同实现"""
    if template.parse_mode == "sheet_name":
        return _parse_sheet_name_mode(file_path, template, sample_size)
    elif template.parse_mode == "chinese_name":
        return _parse_chinese_name_mode(file_path, template, sample_size)
    else:  # mapping (默认)
        return _parse_mapping_mode(file_path, template, sample_size)


def _col_to_index(col_str: str, headers: list[str]) -> int:
    """列标识 → 0-based 索引。
    支持:Excel 字母 (A, B, ..., Z, AA, AB, ...) / 数字 (1, 2, 3) / 列名
    失败返回 -1
    """
    s = (col_str or "").strip()
    if not s:
        return -1
    # 字母 (A=1, B=2, ..., Z=26, AA=27, ...)
    if s.replace(" ", "").isalpha():
        n = 0
        for ch in s.upper():
            n = n * 26 + (ord(ch) - ord('A') + 1)
        return n - 1
    # 数字 (1-based)
    if s.isdigit():
        return int(s) - 1
    # 列名
    if s in headers:
        return headers.index(s)
    return -1


# ============================================================
# 模式 1: mapping (TOTAL 页 + table_name_col + sheet_name_col)
# ============================================================
def _parse_mapping_mode(file_path: str, template: ExcelTemplate,
                        sample_size: int) -> tuple[list[ParseResult], list[str]]:
    results: list[ParseResult] = []
    errors: list[str] = []

    try:
        wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    except (InvalidFileException, FileNotFoundError) as e:
        return [], [f"无法打开文件: {e}"]

    if not template.config_sheet_name:
        wb.close()
        return [], ["模式 1 需要配置 config_sheet_name(TOTAL/索引页)"]
    if template.config_sheet_name not in wb.sheetnames:
        wb.close()
        return [], [f"配置 sheet 不存在: {template.config_sheet_name!r}"]

    try:
        config_ws = wb[template.config_sheet_name]
        config_rows = list(config_ws.iter_rows(values_only=True))
        if not config_rows:
            wb.close()
            return [], [f"配置 sheet {template.config_sheet_name!r} 是空的"]
        headers = [str(c).strip() if c is not None else "" for c in config_rows[0]]
        # 支持字母 (A/B/C) / 数字 (1/2/3) / 列名 三种写法
        tn_idx = _col_to_index(template.table_name_col, headers)
        sn_idx = _col_to_index(template.sheet_name_col, headers)
        if tn_idx < 0 or tn_idx >= len(headers):
            wb.close()
            return [], [f"英文表名列 {template.table_name_col!r} 解析失败(支持: 字母 A/B/C、数字 1/2/3、列名)"]
        if sn_idx < 0 or sn_idx >= len(headers):
            wb.close()
            return [], [f"Sheet 名称列 {template.sheet_name_col!r} 解析失败(支持: 字母 A/B/C、数字 1/2/3、列名)"]

        for row in config_rows[1:]:
            if not row or all(c is None for c in row):
                continue
            tn = row[tn_idx] if tn_idx < len(row) else None
            sn = row[sn_idx] if sn_idx < len(row) else None
            if tn is None or sn is None:
                continue
            table_name = str(tn).strip()
            sheet_name = str(sn).strip()
            if not table_name or not sheet_name:
                continue
            result = _parse_sheet(wb, file_path, sheet_name, table_name, template, sample_size)
            results.append(result)
            if result.error:
                errors.append(f"[{table_name}] {result.error}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        errors.append(f"解析过程异常: {e}")
    finally:
        wb.close()

    return results, errors


# ============================================================
# 模式 2: sheet_name (所有 sheet 名直接当英文表名)
# ============================================================
def _parse_sheet_name_mode(file_path: str, template: ExcelTemplate,
                           sample_size: int) -> tuple[list[ParseResult], list[str]]:
    results: list[ParseResult] = []
    errors: list[str] = []

    try:
        wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    except (InvalidFileException, FileNotFoundError) as e:
        return [], [f"无法打开文件: {e}"]

    try:
        for sheet_name in wb.sheetnames:
            # sheet 名直接当英文表名
            result = _parse_sheet(wb, file_path, sheet_name, sheet_name, template, sample_size)
            results.append(result)
            if result.error:
                errors.append(f"[{sheet_name}] {result.error}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        errors.append(f"解析过程异常: {e}")
    finally:
        wb.close()

    return results, errors


# ============================================================
# 模式 3: chinese_name (sheet 名是中文,用 name_mapping JSON 转换)
# ============================================================
def _parse_chinese_name_mode(file_path: str, template: ExcelTemplate,
                             sample_size: int) -> tuple[list[ParseResult], list[str]]:
    results: list[ParseResult] = []
    errors: list[str] = []

    try:
        wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    except (InvalidFileException, FileNotFoundError) as e:
        return [], [f"无法打开文件: {e}"]

    name_map = template.get_name_mapping()
    if not name_map:
        wb.close()
        return [], ["模式 3 需要配置 name_mapping(中文→英文表名)映射"]

    try:
        for sheet_name in wb.sheetnames:
            # 在 name_map 里查英文表名
            table_name = name_map.get(sheet_name) or name_map.get(sheet_name.strip())
            if not table_name:
                errors.append(f"sheet {sheet_name!r} 没有对应的英文表名映射(在 name_mapping 里查不到)")
                results.append(ParseResult(
                    table_name="", sheet_name=sheet_name,
                    columns=[], rows=0,
                    error="无映射",
                ))
                continue
            result = _parse_sheet(wb, file_path, sheet_name, table_name, template, sample_size)
            results.append(result)
            if result.error:
                errors.append(f"[{table_name}] {result.error}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        errors.append(f"解析过程异常: {e}")
    finally:
        wb.close()

    return results, errors


# ============================================================
# 通用: 解析单张 sheet
# ============================================================
def _read_sheet_fast(file_path: str, sheet_name: str,
                     header_row: int = 0, skip_rows: int = 0) -> pl.DataFrame:
    """用 fastexcel(calamine, Rust 实现)直接读 + to_polars。

    为什么不用 pl.read_excel:
    - calamine engine (默认) 内部调 from_arrow(ArrowStreamExportable) 会打 FutureWarning
    - openpyxl engine 不会打 warning,但比 calamine 慢 ~8x (polars 1.x 的实现问题)
    - fastexcel.to_polars() 走 polars 官方的 extension,无 warning 且最快(实测 3ms vs 25ms vs 4ms+warning)

    header_row: 0=第一行当 header,None=无 header(列名是 col_0, col_1...)
    skip_rows: 跳过前 N 行(在 header 之前的)
    """
    import fastexcel
    reader = fastexcel.read_excel(file_path)
    sheet = reader.load_sheet_by_name(
        sheet_name,
        header_row=header_row,
        skip_rows=skip_rows,
        schema_sample_rows=10000,
    )
    return sheet.to_polars()


def _parse_sheet(wb, file_path: str, sheet_name: str, table_name: str,
                 template: ExcelTemplate, sample_size: int) -> ParseResult:
    if sheet_name not in wb.sheetnames:
        return ParseResult(
            table_name=table_name, sheet_name=sheet_name,
            columns=[], rows=0,
            error=f"Sheet 不存在: {sheet_name!r}",
        )
    try:
        # 用 fastexcel(calamine)读 — 比 pl.read_excel(openpyxl) 快 8x,且无 FutureWarning
        if template.header_row > 1 or template.data_start_row > template.header_row + 1:
            # 重新读 raw(无 header,fastexcel 拿所有行)
            raw = _read_sheet_fast(file_path, sheet_name, header_row=None)
            if raw.height < template.data_start_row:
                return ParseResult(
                    table_name=table_name, sheet_name=sheet_name,
                    columns=[], rows=0,
                    error="数据起始行超出 sheet 范围",
                )
            header_row_data = raw.row(template.header_row - 1)
            df = raw.slice(template.data_start_row - 1)
            new_cols = [str(c) if c is not None else f"col_{i}" for i, c in enumerate(header_row_data)]
            df = df.rename(dict(zip(df.columns, new_cols)))
        else:
            # header_row=1, data_start_row=2: fastexcel 默认第 1 行当 header
            df = _read_sheet_fast(file_path, sheet_name, header_row=0)
    except Exception as e:
        return ParseResult(
            table_name=table_name, sheet_name=sheet_name,
            columns=[], rows=0,
            error=f"读取失败: {e}",
        )

    # 起始列(1-based)— 切掉前面 column_start-1 列
    if template.column_start > 1:
        try:
            df = df.select(df.columns[template.column_start - 1:])
        except Exception as e:
            return ParseResult(
                table_name=table_name, sheet_name=sheet_name,
                columns=[], rows=0,
                error=f"起始列处理失败: {e}",
            )

    cols = list(df.columns)
    n_rows = df.height
    sample = []
    for row in df.head(sample_size).iter_rows(named=False):
        sample.append([str(c) if c is not None else "" for c in row])
    return ParseResult(
        table_name=table_name, sheet_name=sheet_name,
        columns=cols, rows=n_rows, sample_rows=sample,
    )

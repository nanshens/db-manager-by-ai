"""Excel 模板解析 — 按配置解析多 sheet Excel

输入:Excel 路径 + ExcelTemplate
输出:{table_name: DataFrame} 字典
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import openpyxl
from openpyxl.utils.exceptions import InvalidFileException
import polars as pl

from app.repos.excel_template_repo import ExcelTemplate


@dataclass
class ParseResult:
    """单张表的解析结果"""
    table_name: str
    sheet_name: str
    columns: list[str]
    rows: int
    error: str = ""        # 空 = 成功
    sample_rows: list[list] = None  # 前 10 行


def parse_excel(file_path: str, template: ExcelTemplate,
                sample_size: int = 10) -> tuple[list[ParseResult], list[str]]:
    """解析 Excel,返回 (结果列表, 全局错误列表)"""
    results: list[ParseResult] = []
    errors: list[str] = []

    try:
        wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    except (InvalidFileException, FileNotFoundError) as e:
        return [], [f"无法打开文件: {e}"]

    # 读 config sheet
    if template.config_sheet_name not in wb.sheetnames:
        return [], [f"配置 sheet 不存在: {template.config_sheet_name!r}"]

    try:
        config_ws = wb[template.config_sheet_name]
        # 读成 list of dict(用第一行作为列名)
        config_rows = list(config_ws.iter_rows(values_only=True))
        if not config_rows:
            return [], [f"配置 sheet {template.config_sheet_name!r} 是空的"]
        # 第一行:表头(可能也是数据,看用户怎么填)
        # 我们的约定:第一行就是列名
        headers = [str(c).strip() if c is not None else "" for c in config_rows[0]]
        if template.table_name_col not in headers:
            return [], [f"配置 sheet 缺少列: {template.table_name_col!r}"]
        if template.sheet_name_col not in headers:
            return [], [f"配置 sheet 缺少列: {template.sheet_name_col!r}"]
        tn_idx = headers.index(template.table_name_col)
        sn_idx = headers.index(template.sheet_name_col)

        # 遍历数据行(从第二行开始)
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
            # 解析对应的 sheet
            result = _parse_sheet(wb, sheet_name, table_name, template, sample_size)
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


def _parse_sheet(wb, sheet_name: str, table_name: str,
                 template: ExcelTemplate, sample_size: int) -> ParseResult:
    if sheet_name not in wb.sheetnames:
        return ParseResult(
            table_name=table_name, sheet_name=sheet_name,
            columns=[], rows=0,
            error=f"Sheet 不存在: {sheet_name!r}",
        )
    ws = wb[sheet_name]
    # 用 polars 读
    try:
        # polars read_excel 支持多 sheet,但需要单独调
        df = pl.read_excel(
            ws.parent.path,
            sheet_name=sheet_name,
            infer_schema_length=10000,
        )
    except Exception as e:
        return ParseResult(
            table_name=table_name, sheet_name=sheet_name,
            columns=[], rows=0,
            error=f"读取失败: {e}",
        )

    # header_row/data_start_row 处理
    # polars 默认 header=0 (第一行), data 从第 1 行开始
    # 我们要做的是:跳过前 (header_row-1) 行,然后下一行作为 header,再跳过 (data_start_row - header_row - 1) 行
    # 实际上:第 header_row 行作为列名,第 data_start_row 行起为数据
    # polars 内部:header=N 表示 N+1 行作为 header
    # 我们需要:先读全部,然后切片
    all_cols = list(df.columns)
    n_total = df.height

    # 简化:polars 已经把第一行作为 header 了
    # 我们的 header_row 表示"列名所在行"(1-based)
    # data_start_row 表示"数据起始行"(1-based)
    # 那么 polars 读到的 df:
    #   - 列名:第 1 行(原 header_row=1)
    #   - 数据:第 2 行起(原 data_start_row=2)
    # 当 header_row=1, data_start_row=2: 正常
    # 当 header_row=2, data_start_row=3: 意味着原文件第 1 行是垃圾,polars 已经把它当成数据了
    #   需要把第一行数据丢掉 + 第 2 行作为列名
    # 当 header_row=2, data_start_row=3 → 用户希望:第 1 行忽略,第 2 行列名,第 3 行起数据
    #   我们的 polars 已经读了所有行作为数据(列名是默认 col_0, col_1...)
    #   所以我们需要重新读
    if template.header_row > 1 or template.data_start_row > template.header_row + 1:
        # 重新读
        try:
            raw = pl.read_excel(ws.parent.path, sheet_name=sheet_name, has_header=False)
        except Exception as e:
            return ParseResult(
                table_name=table_name, sheet_name=sheet_name,
                columns=[], rows=0,
                error=f"原始读取失败: {e}",
            )
        # raw: 所有行
        # 切片:header_row-1 取列名,data_start_row-1 起取数据
        if raw.height < template.data_start_row:
            return ParseResult(
                table_name=table_name, sheet_name=sheet_name,
                columns=[], rows=0,
                error="数据起始行超出 sheet 范围",
            )
        header_row_data = raw.row(template.header_row - 1)
        data_df = raw.slice(template.data_start_row - 1)
        # 重新设置列名
        new_cols = [str(c) if c is not None else f"col_{i}" for i, c in enumerate(header_row_data)]
        data_df = data_df.rename(dict(zip(data_df.columns, new_cols)))
        df = data_df

    cols = list(df.columns)
    n_rows = df.height
    sample = []
    for row in df.head(sample_size).iter_rows(named=False):
        sample.append([str(c) if c is not None else "" for c in row])
    return ParseResult(
        table_name=table_name, sheet_name=sheet_name,
        columns=cols, rows=n_rows, sample_rows=sample,
    )

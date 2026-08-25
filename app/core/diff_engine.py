"""Diff Engine — 表数据 diff 核心算法

支持 polars LazyFrame 流式处理 + 主键匹配 + 可配置比较列。
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Optional
import polars as pl
from pathlib import Path

from app.core.file_reader import detect_format


@dataclass
class DiffConfig:
    pk_columns: list[str] = field(default_factory=list)
    compare_columns: Optional[list[str]] = None  # None = 全列(除 PK)
    ignore_columns: list[str] = field(default_factory=list)
    case_sensitive: bool = False
    trim_whitespace: bool = True
    encoding: str = "utf-8-sig"

    def effective_compare_columns(self, all_columns: list[str]) -> list[str]:
        """返回实际参与匹配的列(去除 PK,去除 ignore)"""
        if self.compare_columns is not None:
            cols = list(self.compare_columns)
        else:
            cols = [c for c in all_columns if c not in self.pk_columns]
        return [c for c in cols if c not in self.ignore_columns and c not in self.pk_columns]


def _read(path: str) -> pl.DataFrame:
    fmt = detect_format(path)
    if fmt == "csv":
        return pl.read_csv(path, infer_schema_length=10000, ignore_errors=True)
    if fmt == "tsv":
        return pl.read_csv(path, separator="\t", infer_schema_length=10000, ignore_errors=True)
    if fmt in ("xlsx", "xls"):
        return pl.read_excel(path)
    raise ValueError(f"Unsupported format: {fmt}")


def _normalize_str_expr(col: str, case_sensitive: bool, trim: bool) -> pl.Expr:
    e = pl.col(col).cast(pl.Utf8)
    if trim:
        e = e.str.strip_chars()
    if not case_sensitive:
        e = e.str.to_lowercase()
    return e


def _normalize(df: pl.DataFrame, cols: list[str], case_sensitive: bool, trim: bool) -> pl.DataFrame:
    """对指定列做字符串 normalize"""
    if not cols or (case_sensitive and not trim):
        return df
    exprs = []
    for c in df.columns:
        if c in cols and df.schema[c] == pl.Utf8:
            exprs.append(_normalize_str_expr(c, case_sensitive, trim).alias(c))
        else:
            exprs.append(pl.col(c))
    return df.select(exprs)


def _to_records(df: pl.DataFrame, columns: list[str]) -> dict[tuple, dict]:
    """DataFrame → {pk_tuple: row_dict}"""
    out = {}
    if df.is_empty():
        return out
    pk_cols = None  # 由调用方决定
    return out  # 占位


@dataclass
class _CellDiff:
    col: str
    left: object
    right: object


@dataclass
class _RowDiff:
    key: tuple
    kind: str  # only_left / only_right / modified
    left_row: Optional[dict] = None
    right_row: Optional[dict] = None
    cell_diffs: list[_CellDiff] = field(default_factory=list)


@dataclass
class DiffResult:
    only_left: list[_RowDiff]
    only_right: list[_RowDiff]
    modified: list[_RowDiff]
    unchanged_count: int
    total_left: int
    total_right: int
    column_diff_stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "only_left": [
                {**asdict(r), "cell_diffs": [asdict(c) for c in r.cell_diffs]}
                for r in self.only_left
            ],
            "only_right": [
                {**asdict(r), "cell_diffs": [asdict(c) for c in r.cell_diffs]}
                for r in self.only_right
            ],
            "modified": [
                {**asdict(r), "cell_diffs": [asdict(c) for c in r.cell_diffs]}
                for r in self.modified
            ],
            "unchanged_count": self.unchanged_count,
            "total_left": self.total_left,
            "total_right": self.total_right,
            "column_diff_stats": self.column_diff_stats,
        }


class DiffEngine:
    def compute(self, left_path: str, right_path: str, config: DiffConfig) -> DiffResult:
        if not config.pk_columns:
            raise ValueError("At least 1 PK column required")

        left_df = _read(left_path)
        right_df = _read(right_path)

        # 列对齐(以左为准)
        all_cols = list(left_df.columns)
        # 缺失的右列填 null
        for c in all_cols:
            if c not in right_df.columns:
                right_df = right_df.with_columns(pl.lit(None).alias(c))
        # 右多余的列保留(便于看 cell diff)
        extra_right = [c for c in right_df.columns if c not in left_df.columns]
        right_df = right_df.select(all_cols + extra_right)
        left_df = left_df.select(all_cols)

        # 比较列
        cmp_cols = config.effective_compare_columns(all_cols)
        # Normalize
        left_n = _normalize(left_df, cmp_cols, config.case_sensitive, config.trim_whitespace)
        right_n = _normalize(right_df, cmp_cols, config.case_sensitive, config.trim_whitespace)

        # 主键索引
        l_index = {tuple(r[c] for c in config.pk_columns): r for r in left_n.to_dicts()}
        r_index = {tuple(r[c] for c in config.pk_columns): r for r in right_n.to_dicts()}

        only_left = []
        only_right = []
        modified = []
        unchanged = 0
        col_stats: dict[str, int] = {c: 0 for c in cmp_cols}

        for k, lr in l_index.items():
            if k not in r_index:
                only_left.append(_RowDiff(key=k, kind="only_left", left_row=dict(lr)))
                continue
            rr = r_index[k]
            cell_diffs = []
            for c in cmp_cols:
                lv = lr.get(c)
                rv = rr.get(c)
                if lv != rv:
                    cell_diffs.append(_CellDiff(col=c, left=lv, right=rv))
                    col_stats[c] += 1
            if cell_diffs:
                # cell_diffs 同时也包含 ignored 列的实际值,便于显示
                modified.append(_RowDiff(
                    key=k, kind="modified",
                    left_row=dict(lr), right_row=dict(rr),
                    cell_diffs=cell_diffs,
                ))
            else:
                unchanged += 1
        for k, rr in r_index.items():
            if k not in l_index:
                only_right.append(_RowDiff(key=k, kind="only_right", right_row=dict(rr)))

        return DiffResult(
            only_left=only_left, only_right=only_right, modified=modified,
            unchanged_count=unchanged,
            total_left=len(l_index), total_right=len(r_index),
            column_diff_stats=col_stats,
        )

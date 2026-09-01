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
        return pl.read_csv(path, infer_schema_length=10000, ignore_errors=True,
                          encoding="utf8-lossy")
    if fmt == "tsv":
        return pl.read_csv(path, separator="\t", infer_schema_length=10000, ignore_errors=True,
                          encoding="utf8-lossy")
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
    """对指定列做字符串 normalize
    - trim: 去首尾空白 + 内部多空白合成单空格 + 空字符串→None
    - case_sensitive=False: 统一转小写
    """
    if not cols:
        return df
    exprs = []
    for c in df.columns:
        if c in cols and df.schema[c] == pl.Utf8:
            e = pl.col(c).cast(pl.Utf8)
            if trim:
                e = e.str.strip_chars()
                # 多空白合一
                e = e.str.replace_all(r"\s+", " ")
            # 空字符串→null
            e = e.map_elements(lambda s: None if (s is None or str(s).strip() == "") else s,
                                return_dtype=pl.Utf8)
            if not case_sensitive:
                e = e.str.to_lowercase()
            exprs.append(e.alias(c))
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
    # 实际参与 key 的列(供 UI 端用同样规则算行 key)
    cmp_cols: list[str] = field(default_factory=list)
    # 归一化规则(供 UI 端算 key 时用,跟 _normalize 行为保持一致)
    case_sensitive: bool = False
    trim_whitespace: bool = True

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
            "cmp_cols": list(self.cmp_cols),
            "case_sensitive": self.case_sensitive,
            "trim_whitespace": self.trim_whitespace,
        }


class DiffEngine:
    def compute(self, left_path: str, right_path: str, config: DiffConfig) -> tuple[DiffResult, list[dict], list[dict], list[str]]:
        """set-based 内容比较:行号不重要,只看 A 的某行内容是否在 B 集合里存在。

        Returns: (DiffResult, left_rows, right_rows, common_cols)
        - left_rows / right_rows: **原始**完整行数据(供 UI 展示/导出,不被归一化污染)
        - common_cols: A/B 共同列(用于 UI 展示)
        - DiffResult.cmp_cols / case_sensitive / trim_whitespace: 供 UI 端按同样规则算行 key
        """
        left_df = _read(left_path)
        right_df = _read(right_path)

        # 列对齐(以左为准)
        all_cols = list(left_df.columns)
        for c in all_cols:
            if c not in right_df.columns:
                right_df = right_df.with_columns(pl.lit(None).alias(c))
        extra_right = [c for c in right_df.columns if c not in left_df.columns]
        right_df = right_df.select(all_cols + extra_right)
        left_df = left_df.select(all_cols)

        # 关键:用 compare_columns 做内容 key(set-based)
        if config.compare_columns:
            cmp_cols = list(config.compare_columns)
        else:
            cmp_cols = list(all_cols)
        if not cmp_cols:
            raise ValueError("No compare columns")

        # 共同列(用于 UI)
        common_cols = [c for c in all_cols if c in (right_df.columns)]

        # 原始行 — 供 UI 展示 / 导出,保持原值(不 lower / 不 trim)
        left_raw = left_df.to_dicts()
        right_raw = right_df.to_dicts()

        # Normalize(仅用于算 key,set-based 比较)
        left_n = _normalize(left_df, cmp_cols, config.case_sensitive, config.trim_whitespace)
        right_n = _normalize(right_df, cmp_cols, config.case_sensitive, config.trim_whitespace)

        # key 算子:按 normalize 后的 row 取 cmp_cols tuple
        def _key(r):
            return tuple(r[c] for c in cmp_cols)
        # 关键:key 来自 normalize 后的 row,但 left_row / right_row 用原始 row(展示用)
        left_list = [(_key(rn), rr) for rr, rn in zip(left_raw, left_n.to_dicts())]
        right_list = [(_key(rn), rr) for rr, rn in zip(right_raw, right_n.to_dicts())]

        # set-based:每行的 key 是否在另一边的 keys 集合里
        right_keys = set(k for k, _ in right_list)
        left_keys = set(k for k, _ in left_list)

        only_left = []
        only_right = []
        unchanged = 0
        for k, r in left_list:
            if k in right_keys:
                unchanged += 1
            else:
                only_left.append(_RowDiff(key=k, kind="only_left", left_row=dict(r)))
        for k, r in right_list:
            if k not in left_keys:
                only_right.append(_RowDiff(key=k, kind="only_right", right_row=dict(r)))

        col_stats: dict[str, int] = {c: 0 for c in cmp_cols}

        result = DiffResult(
            only_left=only_left, only_right=only_right, modified=[],
            unchanged_count=unchanged,
            total_left=len(left_list), total_right=len(right_list),
            column_diff_stats=col_stats,
            cmp_cols=cmp_cols,
            case_sensitive=config.case_sensitive,
            trim_whitespace=config.trim_whitespace,
        )
        # 关键:传**原始** rows 给 UI,展示/导出不被归一化污染
        # UI 端用 _cell_key_value 跟 cmp_cols/case_sensitive/trim_whitespace 算行 key
        return result, left_raw, right_raw, common_cols

"""文件格式检测 + 列名推断(轻量)"""
from __future__ import annotations
from pathlib import Path


def detect_format(path: str) -> str:
    p = path.lower()
    if p.endswith(".csv"):
        return "csv"
    if p.endswith(".tsv"):
        return "tsv"
    if p.endswith(".xlsx"):
        return "xlsx"
    if p.endswith(".xls"):
        return "xls"
    return "unknown"


def infer_columns_from_csv(path: str, sep: str = ",", encoding: str = "utf-8-sig") -> list[str]:
    """轻量:读前一行作为列名"""
    try:
        with open(path, "r", encoding=encoding, errors="replace") as f:
            line = f.readline()
        if not line:
            return []
        return [c.strip().strip('"').strip("'") for c in line.split(sep)]
    except (OSError, UnicodeError):
        return []


def infer_columns(path: str) -> list[str]:
    """根据文件格式推断列名"""
    fmt = detect_format(path)
    if fmt == "csv":
        return infer_columns_from_csv(path, sep=",")
    if fmt == "tsv":
        return infer_columns_from_csv(path, sep="\t")
    if fmt in ("xlsx", "xls"):
        # 简化:用 polars 读 header(不读数据)
        try:
            import polars as pl
            df = pl.read_excel(path, n_rows=0)
            return list(df.columns)
        except Exception:
            return []
    return []


def quick_row_count(path: str) -> int:
    """快速估算行数(不全读)"""
    fmt = detect_format(path)
    if fmt not in ("csv", "tsv"):
        return -1
    try:
        size = Path(path).stat().st_size
        # 取首行估算
        with open(path, "rb") as f:
            first = f.readline()
        avg = max(len(first), 1)
        return size // avg
    except OSError:
        return -1

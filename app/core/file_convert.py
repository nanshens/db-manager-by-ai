"""TSV ↔ CSV 转换 — 处理换行符(关键)

使用场景:Postgres on Linux 输出 TSV(默认 LF)→ 复制到 Windows → 转换或编辑
- "保持原样"模式:不碰换行符,只替换分隔符
- "强制 LF" / "强制 CRLF":统一成指定换行

字段内分隔符处理:
- 简单 TSV/CSV:tab/comma 直接换
- 含特殊字符(分隔符本身 / 引号 / 换行)的字段:加双引号包裹,内部双引号转义
"""
from __future__ import annotations
import csv
import io
from pathlib import Path
from typing import Optional, Literal


LineEnding = Literal["preserve", "lf", "crlf"]


def detect_line_ending(content: bytes) -> str:
    """从原始字节里看换行符是 LF / CRLF / CR / 混合,返回主类型。"""
    crlf = content.count(b"\r\n")
    lone_lf = sum(1 for i, b in enumerate(content) if b == 0x0A and (i == 0 or content[i - 1] != 0x0D))
    if crlf > lone_lf:
        return "crlf"
    if lone_lf > 0:
        return "lf"
    if content.count(b"\r") > 0:
        return "cr"
    return "lf"  # 默认按 LF


def _normalize_endings(text: str, mode: LineEnding) -> str:
    """根据 mode 统一换行。

    - preserve: 不动
    - lf: 所有 \\r\\n / \\r → \\n
    - crlf: 所有 \\n → \\r\\n(已经 \\r\\n 的保持)
    """
    if mode == "preserve":
        return text
    if mode == "lf":
        # \r\n → \n, 单独 \r → \n
        return text.replace("\r\n", "\n").replace("\r", "\n")
    if mode == "crlf":
        # 先把 \r\n 规范化避免双重转换
        normalized = text.replace("\r\n", "\n")
        return normalized.replace("\n", "\r\n")
    return text


def convert_text(
    text: str,
    direction: Literal["tsv_to_csv", "csv_to_tsv"],
    line_ending: LineEnding = "preserve",
    quote_char: str = '"',
) -> str:
    """内存中转换字符串。direction: 转换方向。line_ending: 换行符处理。"""
    delim_src = "\t" if direction == "tsv_to_csv" else ","
    delim_dst = "," if direction == "tsv_to_csv" else "\t"
    # 用 csv 模块读,再写出 — 它会正确处理带引号的字段
    reader = csv.reader(io.StringIO(text), delimiter=delim_src, quotechar=quote_char)
    out_buf = io.StringIO()
    writer = csv.writer(out_buf, delimiter=delim_dst, quotechar=quote_char, lineterminator="\n")
    for row in reader:
        writer.writerow(row)
    result = out_buf.getvalue()
    # 应用换行符策略(preserve 时已保留原文 line ending;这里再统一覆盖)
    return _normalize_endings(result, line_ending)


def convert_file(
    src: str | Path,
    dst: Optional[str | Path] = None,
    direction: Literal["tsv_to_csv", "csv_to_tsv"] = "tsv_to_csv",
    line_ending: LineEnding = "preserve",
    encoding: str = "utf-8",
    encoding_fallback: str = "gbk",
) -> tuple[Path, str]:
    """读 src → 转换 → 写 dst(若 None 则在 src 同目录加 .csv / .tsv 后缀)。

    返回 (输出文件路径, 实际使用的 encoding)。
    编码检测策略:先 utf-8 试解,失败用 fallback(GBK 适合中文 Windows 文件)。
    """
    src = Path(src)
    raw = src.read_bytes()
    # 试编码
    enc_used = encoding
    try:
        text = raw.decode(encoding)
    except UnicodeDecodeError:
        try:
            text = raw.decode(encoding_fallback)
            enc_used = encoding_fallback
        except UnicodeDecodeError:
            # 都没解出来,用 errors=replace 兜底
            text = raw.decode(encoding, errors="replace")
            enc_used = f"{encoding}(replaced)"

    converted = convert_text(text, direction, line_ending)

    if dst is None:
        # 推断目标扩展名
        new_ext = ".csv" if direction == "tsv_to_csv" else ".tsv"
        dst = src.with_suffix(new_ext)
    dst = Path(dst)
    # 关键:用 newline='' 写,避免 Windows 文本模式自动把 \n → \r\n 导致双重转换
    # (我们已经用 _normalize_endings 控制了换行符)
    with open(dst, "w", encoding=encoding, newline="") as f:
        f.write(converted)
    return dst, enc_used


def preview(text: str, n_lines: int = 10) -> str:
    """返回前 n 行预览。"""
    lines = text.splitlines()
    if len(lines) <= n_lines:
        return text
    return "\n".join(lines[:n_lines]) + f"\n... ({len(lines) - n_lines} more lines)"

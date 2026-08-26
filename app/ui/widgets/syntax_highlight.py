"""SQL 语法高亮 — 给 QPlainTextEdit / QTextEdit 染色

支持的语法元素:
- 关键字 (SELECT/FROM/...)
- 字符串字面量 '...'
- 数字字面量
- 注释 -- ... 和 # ...
- 标识符
- 操作符 = < > 等

颜色跟随 dark / light 主题;默认走中性配色,在编辑器内仍然清晰。
"""
from __future__ import annotations
import re
from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont,
)


# SQL 关键字(大写匹配,大小写不敏感)
SQL_KEYWORDS = {
    "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "IN", "IS", "NULL",
    "INSERT", "INTO", "VALUES", "UPDATE", "SET", "DELETE",
    "CREATE", "TABLE", "INDEX", "VIEW", "DROP", "ALTER", "ADD", "COLUMN",
    "PRIMARY", "KEY", "FOREIGN", "REFERENCES", "UNIQUE", "DEFAULT",
    "AS", "ON", "JOIN", "INNER", "LEFT", "RIGHT", "OUTER", "FULL", "CROSS",
    "GROUP", "BY", "ORDER", "HAVING", "LIMIT", "OFFSET", "DISTINCT",
    "UNION", "ALL", "INTERSECT", "EXCEPT", "EXISTS", "BETWEEN", "LIKE",
    "CASE", "WHEN", "THEN", "ELSE", "END", "WITH", "RECURSIVE",
    "BEGIN", "COMMIT", "ROLLBACK", "TRANSACTION",
    "IF", "ELSEIF", "WHILE", "LOOP", "RETURN",
    "USE", "DATABASE", "SCHEMA", "TRUNCATE", "RENAME", "TO",
    "TRUE", "FALSE", "BOOLEAN", "INT", "INTEGER", "BIGINT", "VARCHAR",
    "CHAR", "TEXT", "DATE", "DATETIME", "TIMESTAMP", "DECIMAL", "FLOAT",
    "DOUBLE", "BLOB", "CLOB", "JSON",
}


class SqlHighlighter(QSyntaxHighlighter):
    """标准 SQL 语法高亮。"""

    def __init__(self, document, dark: bool = True):
        super().__init__(document)
        self._dark = dark
        self._build_rules()

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self._build_rules()
        self.rehighlight()

    def _kw_fmt(self) -> QTextCharFormat:
        f = QTextCharFormat()
        # 深色:蓝紫,浅色:深紫
        f.setForeground(QColor("#c084fc") if self._dark else "#7c3aed")
        f.setFontWeight(QFont.Weight.Bold)
        return f

    def _str_fmt(self) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor("#86efac") if self._dark else "#16a34a")
        return f

    def _num_fmt(self) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor("#fbbf24") if self._dark else "#d97706")
        return f

    def _comment_fmt(self) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor("#64748b") if self._dark else "#94a3b8")
        f.setFontItalic(True)
        return f

    def _op_fmt(self) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor("#94a3b8") if self._dark else "#475569")
        return f

    def _fn_fmt(self) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor("#60a5fa") if self._dark else "#2563eb")
        return f

    def _build_rules(self) -> None:
        kw_pat = r"\b(" + "|".join(sorted(SQL_KEYWORDS, key=len, reverse=True)) + r")\b"
        # 常见 SQL 函数,粗略匹配 identifier(
        fn_pat = r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\("

        self._rules = [
            (QRegularExpression(kw_pat), self._kw_fmt(), QRegularExpression.NoMatchOption),
            (QRegularExpression(fn_pat), self._fn_fmt(), QRegularExpression.NoMatchOption),
            (QRegularExpression(r"'[^']*'"), self._str_fmt(), QRegularExpression.NoMatchOption),
            (QRegularExpression(r"\b\d+(\.\d+)?\b"), self._num_fmt(), QRegularExpression.NoMatchOption),
            (QRegularExpression(r"--[^\n]*"), self._comment_fmt(), QRegularExpression.NoMatchOption),
            (QRegularExpression(r"#[^\n]*"), self._comment_fmt(), QRegularExpression.NoMatchOption),
            (QRegularExpression(r"[=<>!+\-*/%]+"), self._op_fmt(), QRegularExpression.NoMatchOption),
        ]

    def highlightBlock(self, text: str) -> None:
        # 命中范围(避免重复染色)
        occupied: list[tuple[int, int]] = []

        for pattern, fmt, _opt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                start, end = m.capturedStart(), m.capturedEnd()
                if any(s < end and start < e for s, e in occupied):
                    continue
                occupied.append((start, end))
                self.setFormat(start, end - start, fmt)

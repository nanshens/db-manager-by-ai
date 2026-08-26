"""文件转换页 — TSV ↔ CSV 互转,重点处理换行符

关键点:Linux Postgres 输出的 TSV 默认 LF,跨平台传输时换行符会变,
提供"保持原样 / 强制 LF / 强制 CRLF"三档可选。
"""
from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QFrame, QRadioButton,
    QButtonGroup, QPlainTextEdit, QFileDialog, QMessageBox, QWidget,
    QLineEdit, QComboBox, QSplitter,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.ui.widgets import show_toast
from app.core.file_convert import convert_file, detect_line_ending, preview


class FileConvertPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # 标题
        title = QLabel(tr("file_convert.title"))
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(title)
        sub = QLabel(tr("file_convert.subtitle"))
        sub.setObjectName("Muted")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        # ============ 输入区 ============
        in_box = QFrame()
        in_box.setObjectName("Card")
        il = QVBoxLayout(in_box)
        il.setContentsMargins(16, 14, 16, 14)
        il.setSpacing(10)

        # 源文件
        src_row = QHBoxLayout()
        src_row.addWidget(QLabel(tr("file_convert.source")))
        self.src_edit = QLineEdit()
        self.src_edit.setPlaceholderText(tr("file_convert.source.placeholder"))
        src_row.addWidget(self.src_edit, 1)
        src_browse = QPushButton(tr("action.browse"))
        src_browse.setObjectName("Ghost")
        src_browse.clicked.connect(self._on_browse_src)
        src_row.addWidget(src_browse)
        il.addLayout(src_row)

        # 目标文件(可选)
        dst_row = QHBoxLayout()
        dst_row.addWidget(QLabel(tr("file_convert.target")))
        self.dst_edit = QLineEdit()
        self.dst_edit.setPlaceholderText(tr("file_convert.target.placeholder"))
        dst_row.addWidget(self.dst_edit, 1)
        dst_browse = QPushButton(tr("action.browse"))
        dst_browse.setObjectName("Ghost")
        dst_browse.clicked.connect(self._on_browse_dst)
        dst_row.addWidget(dst_browse)
        il.addLayout(dst_row)

        # 转换方向
        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel(tr("file_convert.direction")))
        self.dir_tsv_to_csv = QRadioButton("TSV → CSV")
        self.dir_csv_to_tsv = QRadioButton("CSV → TSV")
        self.dir_tsv_to_csv.setChecked(True)
        self.dir_group = QButtonGroup(self)
        self.dir_group.addButton(self.dir_tsv_to_csv, 0)
        self.dir_group.addButton(self.dir_csv_to_tsv, 1)
        dir_row.addWidget(self.dir_tsv_to_csv)
        dir_row.addWidget(self.dir_csv_to_tsv)
        dir_row.addStretch()
        il.addLayout(dir_row)

        # 换行符策略(关键!)
        le_row = QHBoxLayout()
        le_row.addWidget(QLabel(tr("file_convert.line_ending")))
        self.le_preserve = QRadioButton(tr("file_convert.line_ending.preserve"))
        self.le_lf = QRadioButton(tr("file_convert.line_ending.lf"))
        self.le_crlf = QRadioButton(tr("file_convert.line_ending.crlf"))
        self.le_preserve.setChecked(True)
        self.le_group = QButtonGroup(self)
        self.le_group.addButton(self.le_preserve, 0)
        self.le_group.addButton(self.le_lf, 1)
        self.le_group.addButton(self.le_crlf, 2)
        le_row.addWidget(self.le_preserve)
        le_row.addWidget(self.le_lf)
        le_row.addWidget(self.le_crlf)
        le_row.addStretch()
        # 当前检测到的换行符
        self.le_status = QLabel("")
        self.le_status.setObjectName("Muted")
        self.le_status.setStyleSheet("font-size: 11px; margin-left: 12px;")
        le_row.addWidget(self.le_status)
        il.addLayout(le_row)

        # 编码
        enc_row = QHBoxLayout()
        enc_row.addWidget(QLabel(tr("file_convert.encoding")))
        self.enc_combo = QComboBox()
        self.enc_combo.addItems(["utf-8", "utf-8-sig", "gbk", "gb18030", "shift_jis", "latin-1"])
        self.enc_combo.setCurrentText("utf-8")
        enc_row.addWidget(self.enc_combo)
        enc_row.addStretch()
        il.addLayout(enc_row)

        # 操作按钮
        act_row = QHBoxLayout()
        self.preview_btn = QPushButton(tr("file_convert.preview"))
        self.preview_btn.setObjectName("Ghost")
        self.preview_btn.setIcon(qta.icon("mdi6.eye-outline", color="#94a3b8"))
        self.preview_btn.clicked.connect(self._on_preview)
        act_row.addWidget(self.preview_btn)
        self.convert_btn = QPushButton(tr("file_convert.convert"))
        self.convert_btn.setObjectName("Primary")
        self.convert_btn.setIcon(qta.icon("mdi6.swap-horizontal", color="white"))
        self.convert_btn.clicked.connect(self._on_convert)
        act_row.addWidget(self.convert_btn)
        act_row.addStretch()
        il.addLayout(act_row)

        layout.addWidget(in_box)

        # ============ 预览区 ============
        prev_label = QLabel(tr("file_convert.preview.label"))
        prev_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(prev_label)

        prev_box = QFrame()
        prev_box.setObjectName("Card")
        pl = QVBoxLayout(prev_box)
        pl.setContentsMargins(12, 8, 12, 8)
        pl.setSpacing(4)
        self.preview_view = QPlainTextEdit()
        self.preview_view.setReadOnly(True)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.preview_view.setFont(mono)
        self.preview_view.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 11px; "
            "background: #0b1220; color: #e2e8f0; border: 1px solid #334155; border-radius: 4px;"
        )
        pl.addWidget(self.preview_view, 1)
        layout.addWidget(prev_box, 1)

        # 状态栏
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        self.status.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.status)

    # ============== 槽 ==============
    def _on_browse_src(self):
        start = str(Path(self.src_edit.text()).parent) if self.src_edit.text() else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, tr("file_convert.browse_src"), start,
            "Data files (*.tsv *.csv *.txt);;All files (*.*)"
        )
        if path:
            self.src_edit.setText(path)
            self._update_line_status(path)
            # 自动推断方向
            if path.lower().endswith(".tsv"):
                self.dir_tsv_to_csv.setChecked(True)
            elif path.lower().endswith(".csv"):
                self.dir_csv_to_tsv.setChecked(True)

    def _on_browse_dst(self):
        start = str(Path(self.dst_edit.text()).parent) if self.dst_edit.text() else str(Path.home())
        default = str(Path(self.src_edit.text()).with_suffix(".csv" if self.dir_tsv_to_csv.isChecked() else ".tsv")) \
            if self.src_edit.text() else "output"
        path, _ = QFileDialog.getSaveFileName(
            self, tr("file_convert.browse_dst"), start,
            "Data files (*.tsv *.csv);;All files (*.*)"
        )
        if path:
            self.dst_edit.setText(path)

    def _update_line_status(self, path: str):
        """读文件前 N 字节,提示换行符类型。"""
        try:
            with open(path, "rb") as f:
                head = f.read(65536)
            le = detect_line_ending(head)
            le_text = {
                "lf":   "LF (\\n) — 常见于 Linux/macOS",
                "crlf": "CRLF (\\r\\n) — 常见于 Windows",
                "cr":   "CR (\\r) — 旧 Mac",
            }.get(le, "未知")
            self.le_status.setText(f"{tr('file_convert.line_ending.detected')}: {le_text}")
        except Exception as e:
            self.le_status.setText("")

    def _selected_direction(self) -> str:
        return "tsv_to_csv" if self.dir_tsv_to_csv.isChecked() else "csv_to_tsv"

    def _selected_line_ending(self) -> str:
        if self.le_lf.isChecked():
            return "lf"
        if self.le_crlf.isChecked():
            return "crlf"
        return "preserve"

    def _on_preview(self):
        src = self.src_edit.text().strip()
        if not src:
            QMessageBox.information(self, tr("common.info"), tr("file_convert.no_src"))
            return
        if not Path(src).is_file():
            QMessageBox.warning(self, tr("common.error"), tr("file_convert.src_not_exist"))
            return
        try:
            raw = Path(src).read_bytes()
            enc_used = self.enc_combo.currentText()
            try:
                text = raw.decode(enc_used)
            except UnicodeDecodeError:
                text = raw.decode(enc_used, errors="replace")
                enc_used += "(replaced)"
            direction = self._selected_direction()
            from app.core.file_convert import convert_text
            converted = convert_text(text, direction, self._selected_line_ending())
            self.preview_view.setPlainText(preview(converted, 20))
            self.status.setText(
                f"{tr('file_convert.preview.ok')}: "
                f"{len(text):,} bytes → {len(converted):,} bytes, "
                f"encoding={enc_used}, direction={direction}, "
                f"line_ending={self._selected_line_ending()}"
            )
        except Exception as e:
            QMessageBox.warning(self, tr("common.error"), str(e))

    def _on_convert(self):
        src = self.src_edit.text().strip()
        if not src:
            QMessageBox.information(self, tr("common.info"), tr("file_convert.no_src"))
            return
        if not Path(src).is_file():
            QMessageBox.warning(self, tr("common.error"), tr("file_convert.src_not_exist"))
            return
        dst = self.dst_edit.text().strip() or None
        try:
            direction = self._selected_direction()
            line_ending = self._selected_line_ending()
            enc = self.enc_combo.currentText()
            out_path, enc_used = convert_file(
                src, dst, direction, line_ending, encoding=enc,
            )
            show_toast(
                tr("file_convert.done").format(path=str(out_path)),
                "success", 2500,
            )
            self.status.setText(
                f"{tr('file_convert.done')}: {out_path}  (encoding={enc_used})"
            )
            # 自动填回 dst
            self.dst_edit.setText(str(out_path))
        except Exception as e:
            QMessageBox.warning(self, tr("common.error"), str(e))

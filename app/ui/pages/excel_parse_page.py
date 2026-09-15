"""Excel 解析页 — 选 excel + 模板,解析出每个 sheet,支持预览 / 导出 csv/tsv / 全部导出

UI:
- 顶部 toolbar: 选文件 + 模板 combo + 创建模板按钮 + 解析按钮
- 主体 QTableWidget: 每个 sheet 一行
  列: sheet 名 / 英文表名 / 行数 / 列数 / 状态 / 预览 / 导出 csv / 导出 tsv
- 底部 toolbar: 全部导出 csv / 全部导出 tsv
- 预览: QDialog + QTableWidget(显示 sample_rows 或全量)
"""
from __future__ import annotations
from typing import Optional
from pathlib import Path
import polars as pl
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QFrame, QLineEdit, QFileDialog,
    QMessageBox, QWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QDialog, QVBoxLayout as QVBox, QPlainTextEdit, QSizePolicy, QAbstractItemView,
    QComboBox,
)
import qtawesome as qta

from app.ui.i18n import tr
from app.ui.widgets import show_toast
from app.ui.dialogs import ExcelTemplateDialog
from app.core.excel_parser import parse_excel, ParseResult
from app.repos.excel_template_repo import ExcelTemplate
from app.services.registry import reg

# 预览最多显示多少行(防止 100w+ 行 QTableWidget setItem 卡 UI / 内存爆)
MAX_PREVIEW_ROWS = 5000
# 导出时 polars 内部批量写文件的行数(默认 1024 太小,大文件应分批写)
WRITE_BATCH_SIZE = 100_000


# ============================================================
# 预览 dialog(单 sheet 数据)
# ============================================================
class _SheetPreviewDialog(QDialog):
    """显示某 sheet 的解析结果(标题 + 行数 + 列数 + 完整数据 + 关闭)"""
    def __init__(self, result: ParseResult, parent=None):
        super().__init__(parent)
        self.setWindowTitle(
            f"{tr('excel_parse.preview.title')} — {result.table_name}  ({result.sheet_name})"
        )
        self.resize(900, 600)
        self._build(result)

    def _build(self, r: ParseResult):
        v = QVBox(self)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(8)

        # 标题
        title = QLabel(f"📄 {r.table_name}  ·  {r.sheet_name}")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        v.addWidget(title)

        # 元信息
        if r.error:
            meta = QLabel(f"❌ {r.error}")
            meta.setStyleSheet("color: #ef4444;")
        else:
            meta = QLabel(
                f"{tr('excel_parse.preview.rows')}: {r.rows}  ·  "
                f"{tr('excel_parse.preview.cols')}: {len(r.columns)}  ·  "
                f"{tr('excel_parse.preview.col_list')}: {', '.join(r.columns) or '—'}"
            )
        meta.setObjectName("Muted")
        meta.setWordWrap(True)
        v.addWidget(meta)

        # 表格(显示前 N 行,不全量加载 — 大 sheet(100w+ 行)不卡 UI)
        table = QTableWidget()
        if r.df is None or r.df.height == 0:
            table.setRowCount(0)
            table.setColumnCount(len(r.columns))
            table.setHorizontalHeaderLabels(r.columns or [])
        else:
            df = r.df
            MAX_SHOW = MAX_PREVIEW_ROWS
            show_n = min(df.height, MAX_PREVIEW_ROWS)
            table.setColumnCount(len(df.columns))
            # 关键:只 setRowCount(show_n) — 不预留 df.height 行(避免 100w 行 QTableWidget 内存爆)
            table.setRowCount(show_n)
            table.setHorizontalHeaderLabels(list(df.columns))
            for i in range(show_n):
                row = df.row(i)
                for j, v_ in enumerate(row):
                    txt = "" if v_ is None else str(v_)
                    table.setItem(i, j, QTableWidgetItem(txt))
            # 提示用户还有更多行 — 引导到导出
            if df.height > show_n:
                notice = QLabel(
                    f"… 还有 {df.height - show_n:,} 行未在预览中显示 "
                    f"(导出 csv/tsv 可拿全量)"
                )
                notice.setObjectName("Muted")
                notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
                v.addWidget(notice)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        v.addWidget(table, 1)

        # 关闭按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton(tr("action.close"))
        close_btn.setObjectName("Ghost")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        v.addLayout(btn_row)


# ============================================================
# Page
# ============================================================
class ExcelParsePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._file_path: str = ""
        self._results: list[ParseResult] = []
        self._build()
        # 初始刷新模板 combo
        self._refresh_template_combo()

    # ---------- UI ----------
    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # 标题
        head = QVBoxLayout()
        head.setSpacing(4)
        title = QLabel(tr("excel_parse.title"))
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        head.addWidget(title)
        desc = QLabel(tr("excel_parse.description"))
        desc.setObjectName("Muted")
        desc.setWordWrap(True)
        head.addWidget(desc)
        layout.addLayout(head)

        # Toolbar: 文件 + 模板 + 解析
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        toolbar.addWidget(QLabel(tr("excel_parse.file") + ":"))
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(tr("excel_parse.file.placeholder"))
        self.path_edit.setReadOnly(True)
        toolbar.addWidget(self.path_edit, 1)
        browse_btn = QPushButton(tr("action.browse"))
        browse_btn.setObjectName("Ghost")
        browse_btn.setIcon(qta.icon("mdi6.folder-open-outline", color="#94a3b8"))
        browse_btn.clicked.connect(self._on_browse)
        toolbar.addWidget(browse_btn)

        toolbar.addSpacing(12)
        toolbar.addWidget(QLabel(tr("excel_parse.template") + ":"))
        self.template_combo = QComboBox()
        self.template_combo.setMinimumWidth(220)
        toolbar.addWidget(self.template_combo)
        new_tpl_btn = QPushButton()
        new_tpl_btn.setIcon(qta.icon("mdi6.plus", color="#94a3b8"))
        new_tpl_btn.setFixedSize(28, 28)
        new_tpl_btn.setToolTip(tr("excel_parse.template.new"))
        new_tpl_btn.clicked.connect(self._on_new_template)
        toolbar.addWidget(new_tpl_btn)
        refresh_btn = QPushButton()
        refresh_btn.setIcon(qta.icon("mdi6.refresh", color="#94a3b8"))
        refresh_btn.setFixedSize(28, 28)
        refresh_btn.setToolTip(tr("action.refresh"))
        refresh_btn.clicked.connect(self._refresh_template_combo)
        toolbar.addWidget(refresh_btn)

        parse_btn = QPushButton(tr("excel_parse.parse"))
        parse_btn.setObjectName("Primary")
        parse_btn.setIcon(qta.icon("mdi6.play", color="white"))
        parse_btn.clicked.connect(self._on_parse)
        toolbar.addWidget(parse_btn)

        # 清空(清路径 + 解析结果,保留模板选择)
        clear_btn = QPushButton(tr("excel_parse.clear"))
        clear_btn.setObjectName("Ghost")
        clear_btn.setIcon(qta.icon("mdi6.broom", color="#94a3b8"))
        clear_btn.setToolTip(tr("excel_parse.clear.tip"))
        clear_btn.clicked.connect(self._on_clear)
        toolbar.addWidget(clear_btn)

        layout.addLayout(toolbar)

        # Sheet 列表
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            tr("excel_parse.col.sheet"),
            tr("excel_parse.col.table"),
            tr("excel_parse.col.rows"),
            tr("excel_parse.col.cols"),
            tr("excel_parse.col.status"),
            tr("excel_parse.col.preview"),
            tr("excel_parse.col.export_csv"),
            tr("excel_parse.col.export_tsv"),
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in (2, 3, 4):
            self.table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        for c in (5, 6, 7):
            self.table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)

        # 底部:全部导出
        bottom = QHBoxLayout()
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        bottom.addWidget(self.count_label)
        bottom.addStretch()
        export_all_csv = QPushButton(tr("excel_parse.export_all_csv"))
        export_all_csv.setObjectName("Ghost")
        export_all_csv.setIcon(qta.icon("mdi6.export", color="#94a3b8"))
        export_all_csv.clicked.connect(lambda: self._on_export_all("csv"))
        bottom.addWidget(export_all_csv)
        export_all_tsv = QPushButton(tr("excel_parse.export_all_tsv"))
        export_all_tsv.setObjectName("Ghost")
        export_all_tsv.setIcon(qta.icon("mdi6.export", color="#94a3b8"))
        export_all_tsv.clicked.connect(lambda: self._on_export_all("tsv"))
        bottom.addWidget(export_all_tsv)
        layout.addLayout(bottom)

    def retranslate(self) -> None:
        self.table.setHorizontalHeaderLabels([
            tr("excel_parse.col.sheet"),
            tr("excel_parse.col.table"),
            tr("excel_parse.col.rows"),
            tr("excel_parse.col.cols"),
            tr("excel_parse.col.status"),
            tr("excel_parse.col.preview"),
            tr("excel_parse.col.export_csv"),
            tr("excel_parse.col.export_tsv"),
        ])
        self._render()

    # ---------- actions ----------
    def _refresh_template_combo(self) -> None:
        self.template_combo.clear()
        tpls = reg().excel_template_repo.list_all()
        if not tpls:
            self.template_combo.addItem(tr("excel_parse.template.none"), None)
        for t in tpls:
            self.template_combo.addItem(t.template_name, t.id)

    def _on_new_template(self) -> None:
        # 复用 ExcelTemplateDialog 新建模式
        # 已选文件 → 自动带入 + 锁定(不让改,只让配模板)
        dlg = ExcelTemplateDialog(
            template=None,
            file_path=self._file_path,
            lock_file=bool(self._file_path),
            parent=self,
        )
        if dlg.exec() == dlg.DialogCode.Accepted:
            try:
                # get_template() 返回 dict → 用 service.create(**v) 让 service 内部建 dataclass + 校验
                v = dlg.get_template()
                tpl = reg().excel_template_service.create(**v)
                if not tpl or not tpl.id:
                    raise ValueError(tr("toast.save_failed"))
                show_toast(tr("toast.saved").format(name=tpl.template_name), "success")
                self._refresh_template_combo()
                # 选中新模板
                for i in range(self.template_combo.count()):
                    if self.template_combo.itemData(i) == tpl.id:
                        self.template_combo.setCurrentIndex(i)
                        break
            except Exception as e:
                QMessageBox.warning(self, tr("common.error"), str(e))

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("excel_parse.browse_title"),
            "", "Excel files (*.xlsx *.xls);;All files (*)",
        )
        if path:
            self.path_edit.setText(path)
            self._file_path = path

    def _on_clear(self) -> None:
        """清空已选文件 + 解析结果(保留模板选择,方便换文件)"""
        self._file_path = ""
        self.path_edit.clear()
        self._results = []
        self._render()
        show_toast(tr("excel_parse.clear.done"), "info", 1200)

    def _on_parse(self) -> None:
        path = self.path_edit.text().strip()
        if not path:
            QMessageBox.information(self, tr("common.info"), tr("excel_parse.no_file"))
            return
        tpl_id = self.template_combo.currentData()
        if not tpl_id:
            QMessageBox.information(self, tr("common.info"), tr("excel_parse.no_template"))
            return
        tpl = reg().excel_template_repo.get(tpl_id)
        if tpl is None:
            QMessageBox.warning(self, tr("common.error"), tr("excel_parse.template_deleted"))
            return
        try:
            self._results, errors = parse_excel(path, tpl)
            self._render()
            ok_count = sum(1 for r in self._results if not r.error)
            show_toast(
                tr("excel_parse.parsed").format(
                    total=len(self._results), ok=ok_count, err=len(self._results) - ok_count
                ),
                "success" if not errors else "warning",
            )
            if errors:
                QMessageBox.warning(
                    self, tr("common.warning"),
                    tr("excel_parse.parse.errors") + "\n" + "\n".join(errors[:5])
                )
        except Exception as e:
            QMessageBox.warning(self, tr("common.error"), str(e))

    def _render(self) -> None:
        self.table.setRowCount(len(self._results))
        ok_count = 0
        for i, r in enumerate(self._results):
            # col 0: sheet
            sheet_item = QTableWidgetItem(r.sheet_name)
            self.table.setItem(i, 0, sheet_item)
            # col 1: table
            self.table.setItem(i, 1, QTableWidgetItem(r.table_name or "—"))
            # col 2: rows(>10w 加提示符,提醒用户大文件)
            if r.error:
                rows_text = "—"
            else:
                n = r.rows
                if n >= 100_000:
                    rows_text = f"{n:,}  ⚠ 大文件"
                else:
                    rows_text = f"{n:,}" if n else "0"
            self.table.setItem(i, 2, QTableWidgetItem(rows_text))
            # col 3: cols
            self.table.setItem(i, 3, QTableWidgetItem(str(len(r.columns)) if not r.error else "—"))
            # col 4: status
            if r.error:
                status_item = QTableWidgetItem("✗")
                status_item.setForeground(Qt.GlobalColor.red)
                self.table.setItem(i, 4, status_item)
            else:
                status_item = QTableWidgetItem("✓")
                status_item.setForeground(Qt.GlobalColor.green)
                self.table.setItem(i, 4, status_item)
                ok_count += 1
            # col 5: 预览按钮
            preview_btn = QPushButton(tr("excel_parse.preview"))
            preview_btn.setObjectName("Ghost")
            preview_btn.clicked.connect(lambda _=False, ix=i: self._on_preview(ix))
            self.table.setCellWidget(i, 5, preview_btn)
            # col 6: 导出 csv
            csv_btn = QPushButton("CSV")
            csv_btn.setObjectName("Ghost")
            csv_btn.setEnabled(not r.error and r.df is not None and r.df.height > 0)
            csv_btn.clicked.connect(lambda _=False, ix=i: self._on_export_single(ix, "csv"))
            self.table.setCellWidget(i, 6, csv_btn)
            # col 7: 导出 tsv
            tsv_btn = QPushButton("TSV")
            tsv_btn.setObjectName("Ghost")
            tsv_btn.setEnabled(not r.error and r.df is not None and r.df.height > 0)
            tsv_btn.clicked.connect(lambda _=False, ix=i: self._on_export_single(ix, "tsv"))
            self.table.setCellWidget(i, 7, tsv_btn)

        # 计数
        if self._results:
            self.count_label.setText(
                tr("excel_parse.count").format(
                    total=len(self._results), ok=ok_count, err=len(self._results) - ok_count
                )
            )
        else:
            self.count_label.setText("")

    # ---------- 预览 ----------
    def _on_preview(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._results):
            return
        r = self._results[idx]
        dlg = _SheetPreviewDialog(r, parent=self)
        dlg.exec()

    # ---------- 单条导出 ----------
    def _on_export_single(self, idx: int, fmt: str) -> None:
        if idx < 0 or idx >= len(self._results):
            return
        r = self._results[idx]
        if r.df is None or r.df.height == 0:
            return
        sep = "," if fmt == "csv" else "\t"
        default_name = f"{Path(self._file_path).stem}_{r.table_name or r.sheet_name}.{fmt}"
        path, _ = QFileDialog.getSaveFileName(
            self, tr("excel_parse.export.title"),
            default_name, f"{fmt.upper()} files (*.{fmt})",
        )
        if not path:
            return
        try:
            # 大文件分批写(10w/批,polars 内部 streaming,避免一次性序列化全量到 string)
            r.df.write_csv(path, separator=sep, include_header=True,
                           batch_size=WRITE_BATCH_SIZE)
            QMessageBox.information(
                self, tr("excel_parse.export.title"),
                tr("excel_parse.export.ok").format(
                    name=r.table_name or r.sheet_name, path=path
                )
            )
        except Exception as e:
            QMessageBox.warning(self, tr("common.error"), str(e))

    # ---------- 全部导出 ----------
    def _on_export_all(self, fmt: str) -> None:
        if not self._results:
            return
        valid = [r for r in self._results if not r.error and r.df is not None and r.df.height > 0]
        if not valid:
            QMessageBox.information(self, tr("common.info"), tr("excel_parse.export.none"))
            return
        directory = QFileDialog.getExistingDirectory(
            self, tr("excel_parse.export.dir_title"),
        )
        if not directory:
            return
        sep = "," if fmt == "csv" else "\t"
        base = Path(self._file_path).stem if self._file_path else "export"
        ok_count, fail, first_err = 0, 0, ""
        for r in valid:
            out = Path(directory) / f"{r.table_name or r.sheet_name}.{fmt}"
            try:
                r.df.write_csv(str(out), separator=sep, include_header=True,
                               batch_size=WRITE_BATCH_SIZE)
                ok_count += 1
            except Exception as e:
                fail += 1
                if not first_err:
                    first_err = f"{r.table_name}: {e}"
        if fail == 0:
            QMessageBox.information(
                self, tr("excel_parse.export.title"),
                tr("excel_parse.export.all_ok").format(n=ok_count, dir=directory)
            )
        else:
            if first_err:
                QMessageBox.warning(
                    self, tr("excel_parse.export.title"),
                    tr("excel_parse.export.partial").format(ok=ok_count, fail=fail)
                    + "\n\n" + first_err
                )
            else:
                QMessageBox.warning(
                    self, tr("excel_parse.export.title"),
                    tr("excel_parse.export.partial").format(ok=ok_count, fail=fail)
                )

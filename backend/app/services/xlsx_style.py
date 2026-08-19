"""Shared XLSX table styling for catalog and sync exports.

Standard:
- font Calibri 11
- header row: bold + centered + thin border
- body: thin border; optional row fill
- single-line row height
- column widths from max(header, min_chars, content)
- autofilter on the used range
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

import xlsxwriter
from xlsxwriter.worksheet import Worksheet

FONT_NAME = "Calibri"
FONT_SIZE = 11
ROW_HEIGHT = 15  # single visual line for Calibri 11
MIN_COL_WIDTH = 8
MAX_COL_WIDTH = 60
WIDTH_PADDING = 2
_THIN_BORDER = 1


def excel_col_width(max_chars: int) -> float:
    """Map character count to a reasonable Excel column width."""
    return float(min(MAX_COL_WIDTH, max(MIN_COL_WIDTH, max_chars + WIDTH_PADDING)))


def display_len(value: Any) -> int:
    if value is None:
        return 0
    return len(str(value))


def apply_workbook_defaults(workbook: xlsxwriter.Workbook) -> None:
    """Set Calibri 11 as the workbook default (no fill)."""
    default = workbook.formats[0]
    default.set_font_name(FONT_NAME)
    default.set_font_size(FONT_SIZE)


def open_styled_workbook(path: str, *, constant_memory: bool = True) -> xlsxwriter.Workbook:
    workbook = xlsxwriter.Workbook(
        path,
        {"constant_memory": constant_memory, "strings_to_urls": False},
    )
    apply_workbook_defaults(workbook)
    return workbook


class StyledSheetWriter:
    """Stream rows into an xlsxwriter worksheet with shared DID export style."""

    def __init__(
        self,
        workbook: xlsxwriter.Workbook,
        worksheet: Worksheet,
        headers: Sequence[str],
        *,
        track_content_width: bool = True,
        min_chars: Sequence[int] | None = None,
    ):
        self.workbook = workbook
        self.ws = worksheet
        self.headers = list(headers)
        self.ncols = len(self.headers)
        self._track_content_width = track_content_width
        self._max_lens = [
            max(
                display_len(h),
                int(min_chars[i]) if min_chars is not None and i < len(min_chars) else 0,
            )
            for i, h in enumerate(self.headers)
        ]
        self._row = 0

        base = {
            "font_name": FONT_NAME,
            "font_size": FONT_SIZE,
            "border": _THIN_BORDER,
        }
        self.header_fmt = workbook.add_format(
            {**base, "bold": True, "align": "center", "valign": "vcenter"}
        )
        self.body_fmt = workbook.add_format(base)
        self._fill_fmts: dict[str, Any] = {}
        worksheet.set_default_row(ROW_HEIGHT)
        for col_idx, header in enumerate(self.headers):
            worksheet.write(0, col_idx, header, self.header_fmt)
        self._row = 1

    def write_row(self, values: Sequence[Any], *, fill_color: str | None = None) -> None:
        excel_row = self._row
        if fill_color:
            if fill_color not in self._fill_fmts:
                self._fill_fmts[fill_color] = self.workbook.add_format(
                    {
                        "font_name": FONT_NAME,
                        "font_size": FONT_SIZE,
                        "border": _THIN_BORDER,
                        "bg_color": fill_color,
                    }
                )
            cell_fmt = self._fill_fmts[fill_color]
        else:
            cell_fmt = self.body_fmt
        row_vals: list[Any] = []
        for col_idx in range(self.ncols):
            value = values[col_idx] if col_idx < len(values) else ""
            if value is None:
                value = ""
            row_vals.append(value)
            if self._track_content_width:
                self._max_lens[col_idx] = max(self._max_lens[col_idx], display_len(value))
        self.ws.write_row(excel_row, 0, row_vals, cell_fmt)
        self._row += 1

    def write_rows(self, rows: Iterable[Sequence[Any]]) -> int:
        n = 0
        for row in rows:
            self.write_row(row)
            n += 1
        return n

    @property
    def data_rows(self) -> int:
        return max(0, self._row - 1)

    def finalize(self) -> None:
        """Apply column widths and autofilter. Call before workbook.close()."""
        for col_idx, max_len in enumerate(self._max_lens):
            self.ws.set_column(col_idx, col_idx, excel_col_width(max_len))
        last_row = max(0, self._row - 1)
        last_col = max(0, self.ncols - 1)
        self.ws.autofilter(0, 0, last_row, last_col)

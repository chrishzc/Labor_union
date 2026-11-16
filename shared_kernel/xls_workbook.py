"""File: xls_workbook.py
職責：以 xlrd 讀取舊版 .xls，並提供與 openpyxl 相容的唯讀值活頁簿及 pandas engine 選擇。
"""

from __future__ import annotations

from datetime import time
from pathlib import Path

from openpyxl import Workbook, load_workbook

_OLE2_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")


def is_xls_file(path: str | Path) -> bool:
    """以 OLE2 檔頭（而非副檔名）判斷是否為 BIFF .xls。"""
    with Path(path).open("rb") as stream:
        return stream.read(8) == _OLE2_SIGNATURE


def excel_engine(path: str | Path) -> str:
    """回傳 pandas.ExcelFile 應使用的 engine。"""
    return "xlrd" if is_xls_file(path) else "openpyxl"


def _cell_value(cell, datemode: int):
    import xlrd

    kind = cell.ctype
    if kind in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
        return None
    if kind == xlrd.XL_CELL_NUMBER:
        value = cell.value
        return int(value) if float(value).is_integer() else value
    if kind == xlrd.XL_CELL_DATE:
        converted = xlrd.xldate_as_datetime(cell.value, datemode)
        return time(converted.hour, converted.minute, converted.second) if cell.value < 1 else converted
    if kind == xlrd.XL_CELL_BOOLEAN:
        return bool(cell.value)
    if kind == xlrd.XL_CELL_ERROR:
        return xlrd.error_text_from_code.get(cell.value, "#VALUE!")
    return cell.value


def load_values_workbook(path: str | Path) -> Workbook:
    """載入活頁簿的儲存格值：.xls 轉為 openpyxl 活頁簿，其餘走 openpyxl 唯讀載入。"""
    if not is_xls_file(path):
        return load_workbook(path, read_only=True, data_only=True)
    import xlrd

    book = xlrd.open_workbook(str(path), on_demand=True)
    result = Workbook()
    result.remove(result.active)
    try:
        for index in range(book.nsheets):
            source = book.sheet_by_index(index)
            target = result.create_sheet(source.name)
            for row_index in range(source.nrows):
                target.append([_cell_value(cell, book.datemode) for cell in source.row(row_index)])
            book.unload_sheet(index)
    finally:
        book.release_resources()
    return result

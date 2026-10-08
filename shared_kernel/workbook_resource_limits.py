"""Bound XLSX expansion and worksheet size before in-process spreadsheet parsers."""

from __future__ import annotations

from pathlib import Path
import re
from xml.etree import ElementTree
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile


_MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
_MAX_ENTRIES = 256
_MAX_EXPANDED_BYTES = 64 * 1024 * 1024
_MAX_MEMBER_BYTES = 32 * 1024 * 1024
_MAX_COMPRESSION_RATIO = 200
_MAX_SHEETS = 16
_MAX_ROWS = 50_000
_MAX_COLUMNS = 256
_MAX_CELLS = 500_000
_MAX_SHARED_STRINGS = 200_000
_MAX_STYLES = 10_000
_CELL_REFERENCE = re.compile(r"\$?([A-Z]+)\$?([1-9][0-9]*)\Z", re.IGNORECASE)


def validate_xlsx_workbook(path: str | Path) -> None:
    """Reject archives that can amplify into excessive parser work or memory."""
    path = Path(path)
    if path.stat().st_size > _MAX_ARCHIVE_BYTES:
        raise ValueError("xlsx_archive_too_large")
    try:
        with ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) > _MAX_ENTRIES:
                raise ValueError("xlsx_too_many_members")
            seen: set[str] = set()
            expanded = 0
            sheets = []
            for member in members:
                name = member.filename
                if (
                    name in seen
                    or name.startswith("/")
                    or "\\" in name
                    or any(part in {"", ".", ".."} for part in name.rstrip("/").split("/"))
                    or member.flag_bits & 1
                    or member.compress_type not in {ZIP_STORED, ZIP_DEFLATED}
                ):
                    raise ValueError("xlsx_unsafe_member")
                seen.add(name)
                if member.is_dir():
                    continue
                expanded += member.file_size
                if (
                    member.file_size > _MAX_MEMBER_BYTES
                    or expanded > _MAX_EXPANDED_BYTES
                    or member.file_size > _MAX_COMPRESSION_RATIO * max(member.compress_size, 1)
                ):
                    raise ValueError("xlsx_expansion_limit_exceeded")
                if name.startswith("xl/worksheets/") and name.endswith(".xml") and "/_rels/" not in name:
                    sheets.append(member)
            if not {"[Content_Types].xml", "xl/workbook.xml"} <= seen or not sheets:
                raise ValueError("xlsx_missing_workbook_parts")
            if len(sheets) > _MAX_SHEETS:
                raise ValueError("xlsx_too_many_sheets")
            for part, element, maximum in (
                ("xl/sharedStrings.xml", "si", _MAX_SHARED_STRINGS),
                ("xl/styles.xml", "xf", _MAX_STYLES),
            ):
                if part in seen:
                    with archive.open(part) as stream:
                        _limit_elements(stream, element, maximum)
            total_cells = 0
            total_rectangle = 0
            for sheet in sheets:
                with archive.open(sheet) as stream:
                    cells, rectangle = _sheet_size(stream)
                total_cells += cells
                total_rectangle += rectangle
                if total_cells > _MAX_CELLS or total_rectangle > _MAX_CELLS:
                    raise ValueError("xlsx_cell_limit_exceeded")
    except (BadZipFile, ElementTree.ParseError, EOFError, OSError, RuntimeError) as error:
        raise ValueError("xlsx_invalid_archive") from error


def _sheet_size(stream) -> tuple[int, int]:
    rows = cells = row_cells = max_row = max_column = 0
    for event, node in ElementTree.iterparse(stream, events=("start", "end")):
        tag = node.tag.rsplit("}", 1)[-1]
        if event == "start":
            if tag == "dimension":
                endpoint = node.get("ref", "").split(":")[-1]
                max_column, max_row = _reference(endpoint)
            elif tag == "row":
                rows += 1
                row_cells = 0
                position = node.get("r")
                if position is not None:
                    max_row = max(max_row, _row_index(position))
                else:
                    max_row = max(max_row, rows)
            elif tag == "c":
                cells += 1
                row_cells += 1
                position = node.get("r")
                if position is not None:
                    column, row = _reference(position)
                    max_column = max(max_column, column)
                    max_row = max(max_row, row)
                else:
                    max_column = max(max_column, row_cells)
            if (
                rows > _MAX_ROWS
                or cells > _MAX_CELLS
                or max_row > _MAX_ROWS
                or max_column > _MAX_COLUMNS
                or max_row * max_column > _MAX_CELLS
            ):
                raise ValueError("xlsx_sheet_limit_exceeded")
        elif tag in {"c", "row"}:
            node.clear()
    return cells, max_row * max_column


def _row_index(value: str) -> int:
    if not value.isascii() or not value.isdecimal() or int(value) < 1:
        raise ValueError("xlsx_invalid_cell_reference")
    return int(value)


def _reference(value: str) -> tuple[int, int]:
    match = _CELL_REFERENCE.fullmatch(value)
    if match is None:
        raise ValueError("xlsx_invalid_cell_reference")
    column = 0
    for char in match.group(1).upper():
        column = column * 26 + ord(char) - ord("A") + 1
    return column, int(match.group(2))


def _limit_elements(stream, name: str, maximum: int) -> None:
    count = 0
    for event, node in ElementTree.iterparse(stream, events=("start", "end")):
        if event == "start" and node.tag.rsplit("}", 1)[-1] == name:
            count += 1
            if count > maximum:
                raise ValueError("xlsx_xml_element_limit_exceeded")
        elif event == "end":
            node.clear()

"""Admission checks for untrusted XLSX workbook imports."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest
from openpyxl import Workbook

from shared_kernel.workbook_resource_limits import validate_xlsx_workbook


def _xlsx(tmp_path: Path, sheet: str, *, other_sheets: int = 0) -> Path:
    path = tmp_path / "test.xlsx"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("xl/workbook.xml", "<workbook />")
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
        for index in range(2, other_sheets + 2):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", "<worksheet />")
    return path


def test_openpyxl_workbook_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "ordinary.xlsx"
    book = Workbook()
    book.active.append(["name", "amount"])
    book.active.append(["Alice", 10])
    book.save(path)
    validate_xlsx_workbook(path)


def test_compression_bomb_is_rejected(tmp_path: Path) -> None:
    path = _xlsx(tmp_path, "<worksheet>" + " " * 1_000_000 + "</worksheet>")
    with pytest.raises(ValueError, match="xlsx_expansion_limit_exceeded"):
        validate_xlsx_workbook(path)


@pytest.mark.parametrize("xml", [
    '<worksheet><dimension ref="A1:ZZZ10" /></worksheet>',
    '<worksheet><dimension ref="A1:A1000000" /></worksheet>',
    '<worksheet><row r="50001"><c r="A50001"/></row></worksheet>',
    '<worksheet><row r="1"><c r="ZZ1"/></row></worksheet>',
    '<worksheet><dimension ref="A1:IV50000"/></worksheet>',
])
def test_overwide_or_overlong_sheets_are_rejected(tmp_path: Path, xml: str) -> None:
    path = _xlsx(tmp_path, xml)
    with pytest.raises(ValueError, match="xlsx_sheet_limit_exceeded"):
        validate_xlsx_workbook(path)


def test_many_sheets_are_rejected(tmp_path: Path) -> None:
    path = _xlsx(tmp_path, "<worksheet />", other_sheets=16)
    with pytest.raises(ValueError, match="xlsx_too_many_sheets"):
        validate_xlsx_workbook(path)


def test_path_traversal_member_is_rejected(tmp_path: Path) -> None:
    path = _xlsx(tmp_path, "<worksheet />")
    with ZipFile(path, "a", ZIP_DEFLATED) as archive:
        archive.writestr("../outside.xml", "<bad />")
    with pytest.raises(ValueError, match="xlsx_unsafe_member"):
        validate_xlsx_workbook(path)


def test_invalid_archive_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.xlsx"
    path.write_bytes(b"not a zip")
    with pytest.raises(ValueError, match="xlsx_invalid_archive"):
        validate_xlsx_workbook(path)


def test_excessive_cell_elements_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "many.xlsx"
    with ZipFile(path, "w", ZIP_STORED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("xl/workbook.xml", "<workbook />")
        archive.writestr("xl/worksheets/sheet1.xml", "<worksheet><row r=\"1\">" + "<c r=\"A1\"/>" * 500_001 + "</row></worksheet>")
    with pytest.raises(ValueError, match="xlsx_sheet_limit_exceeded"):
        validate_xlsx_workbook(path)


def test_excessive_shared_strings_are_rejected(tmp_path: Path) -> None:
    path = _xlsx(tmp_path, "<worksheet />")
    with ZipFile(path, "a", ZIP_STORED) as archive:
        archive.writestr("xl/sharedStrings.xml", "<sst>" + "<si/>" * 200_001 + "</sst>")
    with pytest.raises(ValueError, match="xlsx_xml_element_limit_exceeded"):
        validate_xlsx_workbook(path)

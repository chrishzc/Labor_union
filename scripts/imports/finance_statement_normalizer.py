"""Detect and normalize a supported bank workbook without business classification."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from scripts.imports.finance_formats.detector import detect_statement_format
from scripts.imports.finance_formats.legacy import normalize_legacy_rows
from scripts.imports.finance_formats.sinopac import normalize_sinopac_rows
from scripts.imports.finance_formats.taishin import normalize_taishin_rows
from scripts.imports.finance_normalized_row import validate_normalized_row


Adapter = Callable[[str | Path, str, int], list[dict[str, Any]]]

FORMAT_ADAPTERS: dict[str, Adapter] = {
    "legacy": normalize_legacy_rows,
    "taishin": normalize_taishin_rows,
    "sinopac": normalize_sinopac_rows,
}


def normalize_workbook(excel_path: str | Path) -> dict[str, Any]:
    """Return detector metadata and validator-approved normalized rows."""
    assert set(FORMAT_ADAPTERS) == {"legacy", "taishin", "sinopac"}
    detected = detect_statement_format(excel_path)
    format_id = detected["format_id"]
    try:
        adapter = FORMAT_ADAPTERS[format_id]
    except KeyError as exc:
        raise ValueError(f"unsupported detected finance format: {format_id}") from exc

    sheet_name = detected["sheet_name"]
    header_row = detected["header_row"]
    rows = adapter(excel_path, sheet_name, header_row)
    validated_rows = [validate_normalized_row(row) for row in rows]
    return {
        "format_id": format_id,
        "sheet_name": sheet_name,
        "header_row": header_row,
        "normalized_rows": validated_rows,
    }

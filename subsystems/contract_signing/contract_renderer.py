"""Render approved Excel templates from an immutable case-fact snapshot."""

from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
from typing import Mapping

from openpyxl import load_workbook


def render_contract_template(
    *, template_path: Path, mapping_path: Path, facts: Mapping[str, object]
) -> bytes:
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    workbook = load_workbook(template_path)
    worksheet = workbook.active
    for cell, descriptor in mapping["param_mappings"].items():
        key = descriptor.get("db_key")
        if not isinstance(key, str) or not key or key not in facts:
            continue
        worksheet[cell] = facts[key]
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()

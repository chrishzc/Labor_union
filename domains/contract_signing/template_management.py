"""Closed field rules and immutable template identities; no transport or storage."""
from __future__ import annotations

from dataclasses import dataclass
import re
from collections.abc import Mapping

TEMPLATE_KEYS = frozenset({'contract_client_copy', 'contract_staff_service'})


class TemplateManagementError(RuntimeError):
    def __init__(self, category: str, code: str, message: str) -> None:
        self.category, self.code = category, code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class TemplateField:
    key: str
    label: str
    requiredness: str
    applicability: str | None = None


@dataclass(frozen=True, slots=True)
class TemplateVersion:
    version_id: str
    template_key: str
    number: int
    filename: str
    worksheet_name: str
    template_sha256: str
    mapping_sha256: str
    created_by: str
    created_at: str | None


def require_template_key(key: str) -> str:
    if key not in TEMPLATE_KEYS:
        raise TemplateManagementError('validation', 'contract_template_key_invalid', '契約模板類型無效。')
    return key


def validate_assignments(
    assignments: Mapping[str, str], fields: tuple[TemplateField, ...],
    *, valid_cells: frozenset[str], covered_cells: frozenset[str], require_complete: bool,
) -> tuple[str, ...]:
    catalog = {field.key: field for field in fields}
    for cell, key in assignments.items():
        if not isinstance(cell, str) or not re.fullmatch(r'[A-Z]{1,3}[1-9][0-9]*', cell) or cell not in valid_cells:
            raise TemplateManagementError('validation', 'contract_template_cell_invalid', '映射位置不在選定工作表範圍內。')
        if cell in covered_cells:
            raise TemplateManagementError('validation', 'contract_template_merge_anchor_required', '合併儲存格只能映射到左上角位置。')
        if key not in catalog:
            raise TemplateManagementError('validation', 'contract_template_field_unknown', '映射包含此契約類型不支援的資料欄位。')
    assigned = set(assignments.values())
    missing = tuple(field.label for field in fields if field.requiredness == 'required' and field.key not in assigned)
    if require_complete and missing:
        raise TemplateManagementError('validation', 'contract_template_required_fields_missing', '必要資料尚未設定映射：' + '、'.join(missing))
    return missing

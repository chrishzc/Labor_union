"""Template management Query/Preview/Apply and bounded workbook/catalog ports."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, TypedDict
import json
from pathlib import PurePath

from domains.contract_signing.template_management import (
    TemplateField, TemplateManagementError, TemplateVersion, require_template_key, validate_assignments,
)
from subsystems.contract_signing.template_catalog import (
    TemplateCatalogPort, approved_template_mapping_path, load_approved_template,
)


class WorkbookCellView(TypedDict):
    ref: str
    row: int
    col: int
    value: str
    style: dict[str, object]


@dataclass(frozen=True, slots=True)
class WorkbookSheetView:
    name: str
    rows: int
    columns: int
    column_widths: dict[str, float]
    row_heights: dict[str, float]
    merges: tuple[dict[str, int], ...]
    cells: tuple[WorkbookCellView, ...]
    formula_cells: tuple[str, ...]
    images: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class WorkbookPreview:
    filename: str
    worksheet_name: str
    worksheet_names: tuple[str, ...]
    sheet: WorkbookSheetView
    missing_fields: tuple[str, ...]
    assignments: Mapping[str, str]
    sample_values: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class TemplateCatalogView:
    template_key: str
    catalog_version: int
    active_version_id: str
    versions: tuple[TemplateVersion, ...]
    fields: tuple[TemplateField, ...]


@dataclass(frozen=True, slots=True)
class TemplateMutationReceipt:
    version_id: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class TemplateMutationResult:
    catalog: TemplateCatalogView
    version_id: str
    replayed: bool


class TemplateWorkbookPort(Protocol):
    def inspect(self, content: bytes, worksheet_name: str | None = None) -> tuple[tuple[str, ...], WorkbookSheetView]: ...


class TemplateVersionStore(TemplateCatalogPort, Protocol):
    def query(self, template_key: str) -> tuple[int, str, tuple[TemplateVersion, ...]]: ...
    def content(self, template_key: str, version_id: str) -> tuple[bytes, dict[str, object], TemplateVersion]: ...
    def receipt(self, template_key: str, idempotency_key: str) -> TemplateMutationReceipt | None: ...
    def save(self, *, template_key: str, content: bytes, mapping: dict[str, object], filename: str,
             worksheet_name: str, expected_version: int, actor: str, idempotency_key: str) -> TemplateMutationReceipt: ...
    def activate(self, *, template_key: str, version_id: str, expected_version: int,
                 actor: str, idempotency_key: str) -> TemplateMutationReceipt: ...


def template_fields(template_key: str) -> tuple[TemplateField, ...]:
    require_template_key(template_key)
    mapping = json.loads(approved_template_mapping_path(template_key).read_text(encoding='utf-8'))
    result: dict[str, TemplateField] = {}
    rank = {'optional': 0, 'conditional': 1, 'required': 2}
    for descriptor in mapping['param_mappings'].values():
        key = descriptor.get('db_key')
        if not key or descriptor.get('status') in {'not_applicable', 'pending', 'unresolved'}:
            continue
        candidate = TemplateField(key, descriptor['label'], descriptor['requiredness'], descriptor.get('applicability'))
        previous = result.get(key)
        if previous is None or rank[candidate.requiredness] > rank[previous.requiredness]:
            result[key] = candidate
    return tuple(result.values())


def sample_value(field: TemplateField) -> str:
    known = {'case_no': 'DEMO-001', 'client_name': '範例客戶', 'staff_name': '範例月嫂',
             'service_time': '09:00–17:00', 'service_type': '每週日休假', 'service_days': '26',
             'assignment_service_days': '26', 'identity_status': '一般市民', 'city': '臺北市',
             'address': '示範服務地址', 'multi_birth_count': '1', 'delivery_type': '自然產', 'residence_type': '電梯住宅'}
    if field.key in known:
        return known[field.key]
    if 'date' in field.key:
        return '2026/11/01'
    if any(part in field.key for part in ('amount', 'total', 'fee', 'price', 'payable')):
        return '1,000'
    if 'account' in field.key or 'phone' in field.key:
        return '示範資料'
    return '〔' + field.label + '範例〕'


class ContractTemplateManagement:
    def __init__(self, store: TemplateVersionStore, workbook: TemplateWorkbookPort) -> None:
        self.store, self.workbook = store, workbook

    def query(self, template_key: str) -> TemplateCatalogView:
        require_template_key(template_key)
        version, active, versions = self.store.query(template_key)
        return TemplateCatalogView(template_key, version, active, versions, template_fields(template_key))

    def inspect(self, template_key: str, content: bytes, filename: str, worksheet_name: str | None,
                assignments: Mapping[str, str], *, sample: bool = False, complete: bool = False) -> WorkbookPreview:
        require_template_key(template_key)
        if not filename or len(filename) > 200 or any(ord(ch) < 32 for ch in filename) or PurePath(filename).name != filename or '/' in filename or '\\' in filename or not filename.lower().endswith('.xlsx'):
            raise TemplateManagementError('validation', 'contract_template_filename_invalid', '請選擇 .xlsx 格式的 Excel 模板。')
        names, sheet = self.workbook.inspect(content, worksheet_name)
        fields = template_fields(template_key)
        anchors = {(merge['start_row'], merge['start_col']) for merge in sheet.merges}
        covered = frozenset(cell['ref'] for cell in sheet.cells if any(
            merge['start_row'] <= cell['row'] <= merge['end_row'] and merge['start_col'] <= cell['col'] <= merge['end_col']
            and (cell['row'], cell['col']) not in anchors for merge in sheet.merges))
        missing = validate_assignments(assignments, fields, valid_cells=frozenset(cell['ref'] for cell in sheet.cells),
                                       covered_cells=covered, require_complete=complete)
        unmapped_formulas = set(sheet.formula_cells) - assignments.keys()
        if complete and unmapped_formulas:
            raise TemplateManagementError('validation', 'contract_template_formula_unmapped', '公式須先轉為固定內容或設為系統映射：' + '、'.join(sorted(unmapped_formulas)))
        catalog = {field.key: field for field in fields}
        values = {cell: sample_value(catalog[key]) for cell, key in assignments.items()} if sample else {}
        return WorkbookPreview(filename, sheet.name, names, sheet, missing, dict(assignments), values)

    def read_version(self, template_key: str, version_id: str, *, sample: bool = False) -> WorkbookPreview:
        content, mapping, metadata = self.store.content(require_template_key(template_key), version_id)
        assignments = {cell: descriptor['db_key'] for cell, descriptor in mapping['param_mappings'].items()
                       if descriptor.get('db_key') and descriptor.get('status') not in {'not_applicable', 'pending', 'unresolved'}}
        return self.inspect(template_key, content, metadata.filename, metadata.worksheet_name or None, assignments, sample=sample)

    def save(self, template_key: str, content: bytes, filename: str, worksheet_name: str | None,
             assignments: Mapping[str, str], expected_version: int, actor: str, idempotency_key: str) -> TemplateMutationResult:
        preview = self.inspect(template_key, content, filename, worksheet_name, assignments, complete=True)
        catalog = {field.key: field for field in template_fields(template_key)}
        mapping: dict[str, object] = {'id': template_key, 'name': '客戶服務契約' if template_key == 'contract_client_copy' else '服務人員委任契約',
            'template_filename': 'source.xlsx', 'worksheet_name': preview.worksheet_name,
            'param_mappings': {cell: {'db_key': key, 'label': catalog[key].label, 'requiredness': catalog[key].requiredness,
                **({'applicability': catalog[key].applicability} if catalog[key].applicability else {})}
                for cell, key in sorted(assignments.items())}}
        receipt = self.store.save(template_key=template_key, content=content, mapping=mapping, filename=filename,
                        worksheet_name=preview.worksheet_name, expected_version=expected_version, actor=actor, idempotency_key=idempotency_key)
        return TemplateMutationResult(self.query(template_key), receipt.version_id, receipt.replayed)

    def activate(self, template_key: str, version_id: str, expected_version: int, actor: str, idempotency_key: str) -> TemplateMutationResult:
        receipt = self.store.activate(template_key=require_template_key(template_key), version_id=version_id,
                            expected_version=expected_version, actor=actor, idempotency_key=idempotency_key)
        return TemplateMutationResult(self.query(template_key), receipt.version_id, receipt.replayed)

    def receipt(self, template_key: str, idempotency_key: str) -> TemplateMutationResult | None:
        receipt = self.store.receipt(require_template_key(template_key), idempotency_key)
        return None if receipt is None else TemplateMutationResult(self.query(template_key), receipt.version_id, True)

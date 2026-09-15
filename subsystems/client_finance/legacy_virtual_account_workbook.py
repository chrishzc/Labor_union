"""Preview and apply legacy virtual-account mappings from an XLSX workbook."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Callable, Protocol

import pandas as pd

from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.ports import UnitOfWork


_REQUIRED_HEADERS = frozenset({"虛擬帳號", "市府訂單號碼"})
_ACCOUNT_PATTERN = re.compile(r"^99781699[0-9]{6}$")
_CASE_PATTERN = re.compile(r"^[0-9]{9}$")


@dataclass(frozen=True, slots=True)
class _Row:
    source_row: int
    virtual_account: str
    case_no: str


@dataclass(frozen=True, slots=True)
class _Workbook:
    digest: str
    sheet_identity: str
    source_row_count: int
    rows: tuple[_Row, ...]
    initially_skipped_count: int


@dataclass(frozen=True, slots=True)
class LegacyVirtualAccountPreview:
    source_content_digest: str
    sheet_identity: str
    source_row_count: int
    candidate_count: int
    import_count: int
    existing_count: int
    skipped_count: int
    preview_fingerprint: str

    def as_dict(self) -> dict[str, object]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class LegacyVirtualAccountReceipt:
    source_content_digest: str
    source_row_count: int
    inserted_count: int
    existing_count: int
    skipped_count: int
    replayed_workbook: bool

    def as_dict(self) -> dict[str, object]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


class LegacyVirtualAccountWorkbookConflict(RuntimeError):
    pass


class LegacyVirtualAccountWorkbookUnavailable(RuntimeError):
    pass


class LegacyVirtualAccountRepositoryPort(Protocol):
    def acquire_lock(self, key: str) -> bool: ...
    def release_lock(self, key: str) -> None: ...
    def row_state(self, case_no: str, virtual_account: str, *, lock: bool) -> str: ...
    def insert_mapping(self, case_no: str, virtual_account: str, source_digest: str, source_row: int, actor: str) -> bool: ...
    def load_receipt(self, key: str): ...
    def save_receipt(self, key: str, request_fingerprint: str, preview_fingerprint: str, actor: str, result: dict[str, object]) -> None: ...


class LegacyVirtualAccountWorkbookService:
    def __init__(self, repository: LegacyVirtualAccountRepositoryPort, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def preview(self, source_path: str) -> LegacyVirtualAccountPreview:
        return self._preview(_load_workbook(source_path), lock=False)

    def apply(self, source_path: str, key: str, supplied_preview: str, actor: str) -> LegacyVirtualAccountReceipt:
        if not self._repository.acquire_lock(key):
            raise LegacyVirtualAccountWorkbookUnavailable("legacy_virtual_account_workbook_lock_timeout")
        try:
            workbook = _load_workbook(source_path)
            with self._unit_of_work_factory() as unit_of_work:
                stored = self._repository.load_receipt(key)
                if stored is not None:
                    if (
                        stored["request_fingerprint"] != workbook.digest
                        or stored["preview_fingerprint"] != supplied_preview
                    ):
                        raise LegacyVirtualAccountWorkbookConflict("legacy_virtual_account_workbook_idempotency_conflict")
                    payload = json.loads(stored["result_snapshot"])
                    unit_of_work.commit()
                    return LegacyVirtualAccountReceipt(**{**payload, "replayed_workbook": True})

                preview = self._preview(workbook, lock=True)
                if preview.preview_fingerprint != supplied_preview:
                    raise LegacyVirtualAccountWorkbookConflict("legacy_virtual_account_preview_stale")

                outcomes: Counter[str] = Counter()
                for row in workbook.rows:
                    state = self._repository.row_state(row.case_no, row.virtual_account, lock=True)
                    if state == "missing_order":
                        outcomes["skipped"] += 1
                    elif state == "existing":
                        outcomes["existing"] += 1
                    elif self._repository.insert_mapping(row.case_no, row.virtual_account, workbook.digest, row.source_row, actor):
                        outcomes["inserted"] += 1
                    else:
                        outcomes["existing"] += 1
                receipt = LegacyVirtualAccountReceipt(
                    workbook.digest,
                    workbook.source_row_count,
                    outcomes["inserted"],
                    outcomes["existing"],
                    workbook.initially_skipped_count + outcomes["skipped"],
                    False,
                )
                self._repository.save_receipt(key, workbook.digest, supplied_preview, actor, receipt.as_dict())
                unit_of_work.commit()
                return receipt
        finally:
            self._repository.release_lock(key)

    def _preview(self, workbook: _Workbook, *, lock: bool) -> LegacyVirtualAccountPreview:
        row_states = tuple(
            (row, self._repository.row_state(row.case_no, row.virtual_account, lock=lock))
            for row in workbook.rows
        )
        outcomes = Counter(state for _, state in row_states)
        candidate_count = outcomes["create"] + outcomes["existing"]
        skipped_count = workbook.initially_skipped_count + outcomes["missing_order"]
        contract = {
            "digest": workbook.digest,
            "sheet": workbook.sheet_identity,
            "rows": [(row.source_row, row.case_no, row.virtual_account, state) for row, state in row_states],
            "skipped": workbook.initially_skipped_count,
        }
        return LegacyVirtualAccountPreview(
            workbook.digest,
            workbook.sheet_identity,
            workbook.source_row_count,
            candidate_count,
            outcomes["create"],
            outcomes["existing"],
            skipped_count,
            fingerprint_payload(contract).value,
        )


def _load_workbook(source_path: str) -> _Workbook:
    path = Path(source_path)
    digest = sha256(path.read_bytes()).hexdigest()
    with pd.ExcelFile(path, engine="openpyxl") as excel:
        candidates = []
        for index, name in enumerate(excel.sheet_names):
            frame = excel.parse(sheet_name=name, dtype=object)
            headers = {str(column).strip() for column in frame.columns}
            if not frame.dropna(how="all").empty and _REQUIRED_HEADERS <= headers:
                candidates.append((index, frame))
    if len(candidates) != 1:
        raise ValueError("legacy_virtual_account_workbook_sheet_contract_not_unique")
    sheet_index, frame = candidates[0]
    rows: list[_Row] = []
    skipped = 0
    seen: set[tuple[str, str]] = set()
    source_rows = 0
    for source_row, (_, source) in enumerate(frame.iterrows(), start=2):
        account = _text(source.get("虛擬帳號"))
        case_no = _text(source.get("市府訂單號碼"))
        if not account and not case_no:
            continue
        source_rows += 1
        pair = (case_no, account)
        if not case_no or not _CASE_PATTERN.fullmatch(case_no) or not _ACCOUNT_PATTERN.fullmatch(account) or pair in seen:
            skipped += 1
            continue
        seen.add(pair)
        rows.append(_Row(source_row, account, case_no))
    return _Workbook(digest, sha256(f"sheet:{sheet_index}".encode()).hexdigest(), source_rows, tuple(rows), skipped)


def _text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


__all__ = [
    "LegacyVirtualAccountPreview",
    "LegacyVirtualAccountReceipt",
    "LegacyVirtualAccountWorkbookConflict",
    "LegacyVirtualAccountWorkbookService",
    "LegacyVirtualAccountWorkbookUnavailable",
]

"""Preview and apply legacy virtual-account mappings from an XLSX workbook."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Callable, Protocol

import pandas as pd

from domains.client_finance.virtual_account import allows_historical_non_citizen_account
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.ports import UnitOfWork
from shared_kernel.workbook_resource_limits import validate_xlsx_workbook
from subsystems.client_finance.case_virtual_account import AccountMapping, AccountOccupant


_REQUIRED_HEADERS = frozenset({"虛擬帳號", "市府訂單號碼"})
_ACCOUNT_PATTERN = re.compile(r"^99781699[0-9]{6}$")
_CASE_PATTERN = re.compile(r"(?:[0-9]{9}|A[0-9]{6})")


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
class WorkbookRowOutcome:
    source_row: int
    case_no: str
    status: str
    related_case_nos: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _WorkbookRowState:
    row: _Row
    status: str
    related_case_nos: tuple[str, ...] = ()
    mappings: tuple[AccountMapping, ...] = ()
    occupants: tuple[AccountOccupant, ...] = ()

    def outcome(self) -> WorkbookRowOutcome:
        return WorkbookRowOutcome(self.row.source_row, self.row.case_no, self.status, self.related_case_nos)


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
    non_citizen_rows: tuple[WorkbookRowOutcome, ...] = ()

    def as_dict(self) -> dict[str, object]:
        values = asdict(self)
        if not self.non_citizen_rows:
            del values["non_citizen_rows"]
        return values


@dataclass(frozen=True, slots=True)
class LegacyVirtualAccountReceipt:
    source_content_digest: str
    source_row_count: int
    inserted_count: int
    existing_count: int
    skipped_count: int
    replayed_workbook: bool
    non_citizen_rows: tuple[WorkbookRowOutcome, ...] = ()

    def as_dict(self) -> dict[str, object]:
        values = asdict(self)
        if not self.non_citizen_rows:
            del values["non_citizen_rows"]
        return values


class LegacyVirtualAccountWorkbookConflict(RuntimeError):
    pass


class LegacyVirtualAccountWorkbookUnavailable(RuntimeError):
    pass


class LegacyVirtualAccountRepositoryPort(Protocol):
    def acquire_lock(self, key: str) -> bool: ...
    def release_lock(self, key: str) -> None: ...
    def row_state(self, case_no: str, virtual_account: str, *, lock: bool) -> str: ...
    def insert_mapping(self, case_no: str, virtual_account: str, source_digest: str, source_row: int, actor: str) -> bool: ...
    def effective_non_citizen_account_owner(self, account: str) -> str | None: ...
    def load_case_mappings(self, case_no: str, *, lock: bool) -> tuple[AccountMapping, ...] | None: ...
    def account_occupants(self, case_no: str, account: str, *, lock: bool) -> tuple[AccountOccupant, ...]: ...
    def replace_historical_non_citizen_account(
        self, case_no: str, account: str, digest: str, actor: str, source_row: int,
        mapping_ids: tuple[int, ...], occupants: tuple[AccountOccupant, ...],
    ) -> None: ...
    def load_receipt(self, key: str): ...
    def save_receipt(self, key: str, request_fingerprint: str, preview_fingerprint: str, actor: str, result: dict[str, object]) -> None: ...


class LegacyVirtualAccountWorkbookService:
    def __init__(self, repository: LegacyVirtualAccountRepositoryPort, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def preview(self, source_path: str) -> LegacyVirtualAccountPreview:
        workbook = _load_workbook(source_path)
        return self._preview(workbook, self._row_states(workbook, lock=False))

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
                    details = tuple(
                        WorkbookRowOutcome(
                            row["source_row"], row["case_no"], row["status"], tuple(row["related_case_nos"]),
                        )
                        for row in payload.pop("non_citizen_rows", ())
                    )
                    unit_of_work.commit()
                    return LegacyVirtualAccountReceipt(**{**payload, "replayed_workbook": True}, non_citizen_rows=details)

                row_states = self._row_states(workbook, lock=True)
                preview = self._preview(workbook, row_states)
                if preview.preview_fingerprint != supplied_preview:
                    raise LegacyVirtualAccountWorkbookConflict("legacy_virtual_account_preview_stale")

                outcomes: Counter[str] = Counter()
                for planned in row_states:
                    row = planned.row
                    if row.case_no.startswith("A") or planned.status == "conflict":
                        if planned.status in {"create", "transfer"}:
                            self._repository.replace_historical_non_citizen_account(
                                row.case_no, row.virtual_account, workbook.digest, actor, row.source_row,
                                tuple(item.id for item in planned.mappings), planned.occupants,
                            )
                            outcomes["inserted"] += 1
                        elif planned.status == "existing":
                            outcomes["existing"] += 1
                        else:
                            outcomes["skipped"] += 1
                        continue
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
                    preview.non_citizen_rows,
                )
                self._repository.save_receipt(key, workbook.digest, supplied_preview, actor, receipt.as_dict())
                unit_of_work.commit()
                return receipt
        finally:
            self._repository.release_lock(key)

    def _row_states(self, workbook: _Workbook, *, lock: bool) -> tuple[_WorkbookRowState, ...]:
        initial_states = tuple(self._row_state(row, lock=lock) for row in workbook.rows)
        by_account: dict[str, set[str]] = defaultdict(set)
        by_non_citizen_case: dict[str, set[str]] = defaultdict(set)
        for state in initial_states:
            row = state.row
            if state.status in {"ineligible_year", "missing_order"}:
                continue
            if row.case_no.startswith("A"):
                by_non_citizen_case[row.case_no].add(row.virtual_account)
            by_account[row.virtual_account].add(row.case_no)
        contested_accounts = {
            account for account, cases in by_account.items()
            if len(cases) > 1 and any(case_no in by_non_citizen_case for case_no in cases)
        }
        states = []
        for state in initial_states:
            row = state.row
            if state.status not in {"ineligible_year", "missing_order"}:
                if row.virtual_account in contested_accounts:
                    state = _WorkbookRowState(
                        row, "conflict", tuple(sorted(by_account[row.virtual_account] - {row.case_no})),
                    )
                elif len(by_non_citizen_case.get(row.case_no, ())) > 1:
                    state = _WorkbookRowState(row, "conflict", (row.case_no,))
            states.append(state)
        return tuple(states)

    def _row_state(self, row: _Row, *, lock: bool) -> _WorkbookRowState:
        non_citizen = row.case_no.startswith("A")
        if non_citizen and not allows_historical_non_citizen_account(row.case_no):
            return _WorkbookRowState(row, "ineligible_year")
        if not non_citizen:
            status = self._repository.row_state(row.case_no, row.virtual_account, lock=lock)
            if status == "create":
                owner = self._repository.effective_non_citizen_account_owner(row.virtual_account)
                if owner is not None:
                    return _WorkbookRowState(row, "conflict", (owner,))
            return _WorkbookRowState(row, status)
        mappings = self._repository.load_case_mappings(row.case_no, lock=lock)
        if mappings is None:
            return _WorkbookRowState(row, "missing_order")
        occupants = self._repository.account_occupants(row.case_no, row.virtual_account, lock=lock)
        active_cases = tuple(item.case_no for item in occupants if not item.cancelled)
        if active_cases:
            return _WorkbookRowState(row, "conflict", active_cases, mappings, occupants)
        if any(item.virtual_account != row.virtual_account for item in mappings):
            return _WorkbookRowState(row, "replace_required", (), mappings, occupants)
        status = "transfer" if occupants else "existing" if mappings else "create"
        return _WorkbookRowState(row, status, tuple(item.case_no for item in occupants), mappings, occupants)

    def _preview(self, workbook: _Workbook, row_states: tuple[_WorkbookRowState, ...]) -> LegacyVirtualAccountPreview:
        outcomes = Counter(state.status for state in row_states)
        import_count = outcomes["create"] + outcomes["transfer"]
        candidate_count = import_count + outcomes["existing"]
        skipped_count = workbook.initially_skipped_count + len(row_states) - candidate_count
        detailed_states = tuple(state for state in row_states if state.row.case_no.startswith("A") or state.status == "conflict")
        contract = {
            "digest": workbook.digest,
            "sheet": workbook.sheet_identity,
            "rows": [(state.row.source_row, state.row.case_no, state.row.virtual_account, state.status) for state in row_states],
            "skipped": workbook.initially_skipped_count,
        }
        if detailed_states:
            contract["non_citizen_rows"] = [
                (state.row.source_row, state.related_case_nos, tuple(item.id for item in state.mappings),
                 tuple((item.id, item.case_no, item.cancelled, item.cancellation_event_id) for item in state.occupants))
                for state in detailed_states
            ]
        return LegacyVirtualAccountPreview(
            workbook.digest,
            workbook.sheet_identity,
            workbook.source_row_count,
            candidate_count,
            import_count,
            outcomes["existing"],
            skipped_count,
            fingerprint_payload(contract).value,
            tuple(state.outcome() for state in detailed_states),
        )


def _load_workbook(source_path: str) -> _Workbook:
    path = Path(source_path)
    validate_xlsx_workbook(path)
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

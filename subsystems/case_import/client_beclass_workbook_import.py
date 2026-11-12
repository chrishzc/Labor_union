"""
File: client_beclass_workbook_import.py
Description: 協調 Client BeClass 暫時活頁簿的 typed Preview、逐列 Apply 與 replay 收據。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable, Protocol

import pandas as pd

from shared_kernel.workbook_resource_limits import validate_xlsx_workbook

from domains.case_import.client_beclass_validation import CLIENT_BECLASS_REQUIRED_HEADERS, validate_client_beclass_row
from domains.case_import.client_beclass_binding import ClientCaseBindingStatus
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.ports import UnitOfWork
from subsystems.case_import.beclass_review_intake import canonical_review_identifier, record_invalid_beclass_row
from domains.case_import.beclass_import_review import BeClassImportSourceKind


@dataclass(frozen=True, slots=True)
class ClientBeClassWorkbookRowIssue:
    source_row: int
    query_no: str | None
    fields: tuple[str, ...]
    issue_codes: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "source_row": self.source_row,
            "query_no": self.query_no,
            "fields": list(self.fields),
            "issue_codes": list(self.issue_codes),
        }


@dataclass(frozen=True, slots=True)
class ClientBeClassCaseCandidate:
    case_no: str
    client_id: int
    name: str
    masked_phone: str
    city: str | None
    created_at: str | None
    start_date: str | None

    def as_view(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ClientBeClassManualRow:
    source_row: int
    query_no: str
    name: str
    masked_phone: str
    city: str | None
    submitted_at: str | None
    case_nos: tuple[str, ...]

    def as_view(self) -> dict[str, object]:
        return {**asdict(self), "case_nos": list(self.case_nos)}


@dataclass(frozen=True, slots=True)
class ClientBeClassManualBinding:
    source_row: int
    query_no: str
    case_no: str


def mask_client_beclass_phone(phone: str) -> str:
    return f"{phone[:2]}•••••{phone[-3:]}" if len(phone) == 10 else "••••"


@dataclass(frozen=True, slots=True)
class ClientBeClassWorkbookPreview:
    source_content_digest: str
    sheet_identity: str
    source_row_count: int
    create_count: int
    review_required_count: int
    existing_conflict_count: int
    existing_source_count: int
    preview_fingerprint: str
    row_issues: tuple[ClientBeClassWorkbookRowIssue, ...] = ()
    manual_rows: tuple[ClientBeClassManualRow, ...] = ()
    candidates: tuple[ClientBeClassCaseCandidate, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "source_content_digest": self.source_content_digest,
            "sheet_identity": self.sheet_identity,
            "source_row_count": self.source_row_count,
            "create_count": self.create_count,
            "review_required_count": self.review_required_count,
            "existing_conflict_count": self.existing_conflict_count,
            "existing_source_count": self.existing_source_count,
            "preview_fingerprint": self.preview_fingerprint,
            "row_issues": [item.as_dict() for item in self.row_issues],
            "manual_rows": [item.as_view() for item in self.manual_rows],
            "candidates": [item.as_view() for item in self.candidates],
        }


def _client_validation_issue_codes(errors: dict[str, str]) -> tuple[str, ...]:
    """Preserve field identity and missing/invalid semantics without raw values."""
    return tuple(
        sorted(
            f"client_field_{'missing' if '不可空' in message else 'invalid'}:{field}"
            for field, message in errors.items()
        )
    )


@dataclass(frozen=True, slots=True)
class ClientBeClassWorkbookReceipt:
    source_content_digest: str
    source_row_count: int
    created_count: int
    exact_replay_count: int
    review_required_count: int
    existing_conflict_count: int
    existing_source_count: int
    replayed_workbook: bool
    row_issues: tuple[ClientBeClassWorkbookRowIssue, ...] | None = None
    manual_bindings: tuple[ClientBeClassManualBinding, ...] = ()

    def __post_init__(self) -> None:
        if self.row_issues is not None and len(self.row_issues) != self.review_required_count + self.existing_conflict_count:
            raise ValueError("client_beclass_not_imported_rows_not_conserved")

    def as_dict(self) -> dict[str, object]:
        return {
            "source_content_digest": self.source_content_digest,
            "source_row_count": self.source_row_count,
            "created_count": self.created_count,
            "exact_replay_count": self.exact_replay_count,
            "review_required_count": self.review_required_count,
            "existing_conflict_count": self.existing_conflict_count,
            "existing_source_count": self.existing_source_count,
            "replayed_workbook": self.replayed_workbook,
            "row_issues": None if self.row_issues is None else [item.as_dict() for item in self.row_issues],
            "manual_bindings": [asdict(item) for item in self.manual_bindings],
        }


@dataclass(frozen=True, slots=True)
class _Workbook:
    digest: str
    sheet_identity: str
    rows: tuple[tuple[int, dict[str, Any]], ...]


class ClientBeClassWorkbookConflict(RuntimeError):
    pass


class ClientBeClassWorkbookUnavailable(RuntimeError):
    pass


class BoundCaseCookingReconciliationPort(Protocol):
    def reconcile(self, case_no: str) -> object: ...


class ClientBeClassWorkbookImportRepositoryPort(Protocol):
    def acquire_lock(self, key: str) -> bool: ...
    def release_lock(self, key: str) -> None: ...
    def load_workbook_receipt(self, key: str): ...
    def load_workbook_claim(self, key: str) -> str | None: ...
    def load_row_receipt(self, key: str): ...
    def source_state(self, payload: dict[str, object]) -> str: ...
    def resolve_client_case_binding(self, name, phone, *, for_update: bool): ...
    def available_case_candidates(self, name, phone, *, for_update: bool, case_no=None) -> tuple[ClientBeClassCaseCandidate, ...]: ...
    def claim_workbook(self, key, fingerprint, correlation_id) -> str: ...
    def claim_row(self, key, fingerprint, correlation_id) -> str: ...
    def create_bound_source_if_absent(self, payload, client_case, *, allow_additional_case: bool = False) -> int | None: ...
    def require_matching_client_root(self, receipt) -> None: ...
    def bound_case_no_for_root(self, root_id: int | None) -> str | None: ...
    def bound_sources_for_query(self, query_no: str): ...
    def bound_case_nos_for_workbook(self, digest: str) -> tuple[str, ...]: ...
    def save_row_receipt(self, *args) -> str | None: ...
    def save_workbook_receipt(
        self, *args
    ) -> None: ...


class ClientBeClassWorkbookImportService:
    def __init__(
        self,
        repository: ClientBeClassWorkbookImportRepositoryPort,
        reconciliation: BoundCaseCookingReconciliationPort,
        unit_of_work_factory: Callable[[], UnitOfWork],
        review_recorder: Callable[..., str] | None = None,
        pairing_rechecks=None,
    ) -> None:
        self._repository = repository
        self._reconciliation = reconciliation
        self._unit_of_work_factory = unit_of_work_factory
        self._review_recorder = review_recorder
        # Kept only as an ignored compatibility input for restricted legacy
        # import scripts; current owner flows do not enqueue anomaly work.
        del pairing_rechecks

    def _persist_review(self, connection, **kwargs):
        recorder = self._review_recorder or record_invalid_beclass_row
        return recorder(connection, **kwargs)

    def preview(self, source_path: str, *, manual_pairing: bool = False) -> ClientBeClassWorkbookPreview:
        return self._preview_workbook(_load_workbook(source_path), manual_pairing)

    def _preview_workbook(
        self,
        workbook: _Workbook,
        manual_pairing: bool,
        confirmed_rows: frozenset[int] = frozenset(),
    ) -> ClientBeClassWorkbookPreview:
        outcomes: Counter[str] = Counter()
        issues: list[ClientBeClassWorkbookRowIssue] = []
        manual_rows: list[ClientBeClassManualRow] = []
        candidates: dict[str, ClientBeClassCaseCandidate] = {}
        for row_number, row in workbook.rows:
            # The confirmed row positions belong to the immutable workbook.
            # Check each selected target under lock at Apply, even if it disappeared.
            if row_number in confirmed_rows:
                outcomes["manual"] += 1
                continue
            outcome, issue = self._preview_row(row_number, row)
            if manual_pairing and (
                outcome == "create"
                or issue and issue.issue_codes[0] in _AMBIGUOUS_BINDINGS
            ):
                payload = _normalized_payload(row)
                available = self._repository.available_case_candidates(
                    payload["name"], payload["phone"], for_update=False
                )
                if available and outcome != "create":
                    manual_rows.append(ClientBeClassManualRow(
                        row_number, payload["query_no"], payload["name"],
                        mask_client_beclass_phone(payload["phone"]), payload["city"],
                        payload["created_at"], tuple(item.case_no for item in available),
                    ))
                    candidates.update((item.case_no, item) for item in available)
                    outcome, issue = "manual", None
                elif not available and outcome == "create":
                    outcome, issue = "existing_conflict", _case_unavailable_issue(
                        row_number, payload["query_no"]
                    )
            outcomes[outcome] += 1
            if issue is not None:
                issues.append(issue)
        return _preview_from_outcomes(
            workbook, outcomes, tuple(issues), tuple(manual_rows),
            tuple(candidates.values()), confirmed_rows,
        )

    def apply(
        self,
        source_path: str,
        key: str,
        supplied_preview: str,
        actor: str,
        correlation_id: str,
        original_review_identity: str | None = None,
        *,
        manual_pairings: tuple[tuple[int, str], ...] | None = None,
    ) -> ClientBeClassWorkbookReceipt:
        # Restricted historical callers may still provide the retired pairing
        # lineage hint; it is intentionally ignored and never persisted.
        del original_review_identity
        if not self._repository.acquire_lock(key):
            raise ClientBeClassWorkbookUnavailable("client_beclass_workbook_coordinator_lock_timeout")
        try:
            workbook = _load_workbook(source_path)
            pairings = manual_pairings or ()
            if len({case_no.casefold() for _, case_no in pairings}) != len(pairings):
                raise ValueError("client_beclass_manual_pairings_not_unique")
            selections: dict[int, list[str]] = {}
            for row_number, case_no in pairings:
                selections.setdefault(row_number, []).append(case_no)
            if selections and not selections.keys() <= {
                row_number for row_number, row in workbook.rows if not validate_client_beclass_row(row)
            }:
                raise ValueError("client_beclass_manual_pairing_row_invalid")
            request_fingerprint = workbook.digest
            if selections:
                request_fingerprint = fingerprint_payload({
                    "digest": workbook.digest,
                    "preview": supplied_preview,
                    "pairings": sorted(pairings),
                }).value
            replay = self._stored_replay_and_reconcile(key, workbook.digest, request_fingerprint)
            if replay is not None:
                return replay
            prior_claim = self._workbook_claim(key) if selections else None
            if prior_claim is not None and prior_claim != request_fingerprint:
                raise ClientBeClassWorkbookConflict("client_beclass_workbook_idempotency_conflict")
            if prior_claim is None:
                preview = self._preview_workbook(workbook, manual_pairings is not None, frozenset(selections))
                if preview.preview_fingerprint != supplied_preview:
                    raise ClientBeClassWorkbookConflict("client_beclass_preview_stale")
                if preview.manual_rows:
                    raise ValueError("client_beclass_manual_pairings_required")
                self._claim_workbook(key, request_fingerprint, correlation_id)
            row_issues: list[ClientBeClassWorkbookRowIssue] = []
            bindings: list[ClientBeClassManualBinding] = []
            outcomes: Counter[str] = Counter()
            for row_number, row in workbook.rows:
                if row_number in selections:
                    outcome = self._apply_manual_row(
                        workbook, row_number, row, selections[row_number], actor,
                        correlation_id, row_issues, bindings,
                    )
                else:
                    outcome = self._apply_row(
                        workbook, row_number, row, actor, correlation_id, row_issues,
                        check_case_availability=manual_pairings is not None,
                    )
                outcomes[outcome] += 1
            _assert_conservation(len(workbook.rows), outcomes)
            receipt = ClientBeClassWorkbookReceipt(workbook.digest, len(workbook.rows), outcomes["created"], outcomes["exact_replay"], outcomes["review_required"], outcomes["existing_conflict"], outcomes["existing_source"], False, tuple(row_issues), tuple(bindings))
            self._save_workbook_receipt(
                key,
                request_fingerprint,
                supplied_preview,
                actor,
                receipt,
            )
            return receipt
        finally:
            self._repository.release_lock(key)

    def _workbook_claim(self, key: str) -> str | None:
        with self._unit_of_work_factory() as unit_of_work:
            fingerprint = self._repository.load_workbook_claim(key)
            unit_of_work.commit()
            return fingerprint

    def _apply_manual_row(
        self,
        workbook: _Workbook,
        row_number: int,
        row: dict[str, Any],
        case_nos: list[str],
        actor: str,
        correlation_id: str,
        issues: list[ClientBeClassWorkbookRowIssue],
        bindings: list[ClientBeClassManualBinding],
    ) -> str:
        payload = _normalized_payload(row)
        selected_bindings = [
            ClientBeClassManualBinding(row_number, payload["query_no"], case_no)
            for case_no in sorted(case_nos)
        ]
        source_prefix = _source_identity(workbook.digest, row_number)
        with self._unit_of_work_factory() as unit_of_work:
            pending = []
            for binding in selected_bindings:
                case_no = binding.case_no
                fingerprint = fingerprint_payload({"source": payload, "case_no": case_no}).value
                source_identity = f"{source_prefix}:manual:{fingerprint}"
                stored = self._repository.load_row_receipt(source_identity)
                if stored is not None:
                    _require_same_fingerprint(stored, fingerprint)
                    self._repository.require_matching_client_root(stored)
                    if self._repository.bound_case_no_for_root(stored["root_id"]) == case_no:
                        continue
                    break
                candidates = self._repository.available_case_candidates(
                    payload["name"], payload["phone"], case_no=case_no, for_update=True
                )
                if len(candidates) != 1:
                    break
                pending.append((candidates[0], source_identity, fingerprint))
            else:
                if not pending or (
                    len(pending) == len(selected_bindings)
                    and len({item.client_id for item, _, _ in pending}) == 1
                    and self._write_manual_bindings(payload, pending, actor, correlation_id)
                ):
                    unit_of_work.commit()
                    bindings.extend(selected_bindings)
                    return "created"
        issues.append(_case_unavailable_issue(row_number, payload["query_no"]))
        return "existing_conflict"

    def _write_manual_bindings(self, payload, pending, actor, correlation_id) -> bool:
        for index, (case, source_identity, fingerprint) in enumerate(pending):
            self._repository.claim_row(source_identity, fingerprint, correlation_id)
            root_id = self._repository.create_bound_source_if_absent(
                payload, {"id": case.client_id, "case_no": case.case_no},
                allow_additional_case=index > 0,
            )
            if root_id is None:
                return False
            self._reconciliation.reconcile(case.case_no)
            self._repository.save_row_receipt(
                source_identity, fingerprint, root_id, "created", None, actor
            )
        return True

    def _preview_row(
        self,
        row_number: int,
        row: dict[str, Any],
    ) -> tuple[str, ClientBeClassWorkbookRowIssue | None]:
        errors = validate_client_beclass_row(row)
        payload = _normalized_payload(row)
        if errors:
            return "review_required", ClientBeClassWorkbookRowIssue(
                row_number,
                payload.get("query_no"),
                tuple(sorted(errors)),
                _client_validation_issue_codes(errors),
            )
        source_state = self._repository.source_state(payload)
        if source_state == "exact":
            return "existing_source", None
        if source_state == "conflict":
            return "existing_conflict", ClientBeClassWorkbookRowIssue(
                row_number,
                payload.get("query_no"),
                ("查詢序號",),
                ("client_beclass_source_payload_conflict",),
            )
        resolution = self._repository.resolve_client_case_binding(
            payload["name"], payload["phone"], for_update=False
        )
        if resolution.status is ClientCaseBindingStatus.UNIQUE:
            return "create", None
        return "existing_conflict", ClientBeClassWorkbookRowIssue(
            row_number,
            payload.get("query_no"),
            ("查詢序號", "姓名", "行動電話"),
            (resolution.issue_code,),
        )

    # Why: every branch must persist the row receipt and review in the same outer row transaction.
    def _apply_row(
        self,
        workbook: _Workbook,
        row_number: int,
        row: dict[str, Any],
        actor: str,
        correlation_id: str,
        row_issues: list[ClientBeClassWorkbookRowIssue] | None = None,
        *,
        check_case_availability: bool = False,
    ) -> str:
        source_identity = _source_identity(workbook.digest, row_number)
        payload = _normalized_payload(row)
        fingerprint = fingerprint_payload(payload).value
        with self._unit_of_work_factory() as unit_of_work:
            stored = self._repository.load_row_receipt(source_identity)
            if stored is not None:
                _require_same_fingerprint(stored, fingerprint)
                self._repository.require_matching_client_root(stored)
                case_no = self._repository.bound_case_no_for_root(
                    stored.get("root_id")
                )
                if case_no is not None:
                    self._reconciliation.reconcile(case_no)
                unit_of_work.commit()
                return "exact_replay"
            self._repository.claim_row(source_identity, fingerprint, correlation_id)
            errors = validate_client_beclass_row(row)
            if errors:
                if row_issues is not None:
                    row_issues.append(ClientBeClassWorkbookRowIssue(row_number, payload.get("query_no"), tuple(sorted(errors)), _client_validation_issue_codes(errors)))
                review_identity = self._persist_review(
                    self._repository.connection, source_kind=BeClassImportSourceKind.CLIENT,
                    source_content_digest=workbook.digest, source_sheet=workbook.sheet_identity,
                    source_row=row_number, identifier=canonical_review_identifier(BeClassImportSourceKind.CLIENT, payload.get("query_no"), row_number),
                    source_payload=_safe_review_payload(payload),
                    issue_codes=_client_validation_issue_codes(errors),
                )
                self._repository.save_row_receipt(source_identity, fingerprint, None, "review_required", review_identity, actor)
                unit_of_work.commit()
                return "review_required"
            source_state = self._repository.source_state(payload)
            if source_state == "exact":
                bound_sources = self._repository.bound_sources_for_query(
                    str(payload["query_no"])
                )
                for bound_source in bound_sources:
                    self._reconciliation.reconcile(bound_source["case_no"])
                self._repository.save_row_receipt(
                    source_identity,
                    fingerprint,
                    bound_sources[0]["root_id"] if bound_sources else None,
                    "existing_source",
                    None,
                    actor,
                )
                unit_of_work.commit()
                return "existing_source"
            if source_state == "conflict":
                if row_issues is not None:
                    row_issues.append(ClientBeClassWorkbookRowIssue(row_number, payload.get("query_no"), ("查詢序號",), ("client_beclass_source_payload_conflict",)))
                outcome = self._save_review_outcome(
                    workbook, row_number, payload, source_identity, fingerprint,
                    actor, "client_beclass_source_payload_conflict",
                )
                unit_of_work.commit()
                return outcome
            resolution = self._repository.resolve_client_case_binding(
                payload["name"], payload["phone"], for_update=True
            )
            if resolution.status is not ClientCaseBindingStatus.UNIQUE:
                if row_issues is not None:
                    row_issues.append(ClientBeClassWorkbookRowIssue(row_number, payload.get("query_no"), ("姓名", "行動電話"), (resolution.issue_code,)))
                outcome = self._save_review_outcome(
                    workbook, row_number, payload, source_identity, fingerprint,
                    actor, resolution.issue_code,
                    _binding_review_payload(payload, resolution),
                )
                unit_of_work.commit()
                return outcome
            bound_root = resolution.bound_root()
            if check_case_availability and not self._repository.available_case_candidates(
                payload["name"], payload["phone"], case_no=bound_root["case_no"], for_update=True
            ):
                if row_issues is not None:
                    row_issues.append(_case_unavailable_issue(row_number, payload["query_no"]))
                return "existing_conflict"
            source_id = self._repository.create_bound_source_if_absent(
                payload, bound_root
            )
            if source_id is None:
                outcome = "existing_source"
                review_identity = None
                if self._repository.source_state(payload) == "conflict":
                    outcome = "existing_conflict"
                    if row_issues is not None:
                        row_issues.append(ClientBeClassWorkbookRowIssue(row_number, payload.get("query_no"), ("查詢序號",), ("client_beclass_source_payload_conflict",)))
                    review_identity = self._record_review(
                        workbook, row_number, payload,
                        "client_beclass_source_payload_conflict",
                    )
                self._repository.save_row_receipt(source_identity, fingerprint, None, outcome, review_identity, actor)
                unit_of_work.commit()
                return outcome
            self._reconciliation.reconcile(str(bound_root["case_no"]))
            self._repository.save_row_receipt(source_identity, fingerprint, source_id, "created", None, actor)
            unit_of_work.commit()
            return "created"

    def _save_review_outcome(
        self, workbook, row_number, payload, source_identity, fingerprint, actor,
        issue_code, review_payload=None,
    ) -> str:
        review_identity = self._record_review(
            workbook, row_number, payload, issue_code, review_payload
        )
        self._repository.save_row_receipt(
            source_identity, fingerprint, None, "existing_conflict",
            review_identity, actor,
        )
        return "existing_conflict"

    def _record_review(
        self, workbook, row_number, payload, issue_code, review_payload=None
    ) -> str:
        return self._persist_review(
            self._repository.connection, source_kind=BeClassImportSourceKind.CLIENT,
            source_content_digest=workbook.digest, source_sheet=workbook.sheet_identity,
            source_row=row_number,
            identifier=canonical_review_identifier(
                BeClassImportSourceKind.CLIENT, payload["query_no"], row_number,
            ),
            source_payload=review_payload or _safe_review_payload(payload),
            issue_codes=(issue_code,),
        )

    def _stored_replay_and_reconcile(
        self,
        key: str,
        digest: str,
        request_fingerprint: str,
    ) -> ClientBeClassWorkbookReceipt | None:
        with self._unit_of_work_factory() as unit_of_work:
            stored = self._repository.load_workbook_receipt(key)
            if stored is None:
                unit_of_work.commit()
                return None
            if stored["request_fingerprint"] != request_fingerprint:
                raise ClientBeClassWorkbookConflict(
                    "client_beclass_workbook_idempotency_conflict"
                )
            payload = json.loads(stored["result_snapshot"])
            if payload.get("row_issues") is not None:
                payload["row_issues"] = tuple(ClientBeClassWorkbookRowIssue(**item) for item in payload["row_issues"])
            payload["manual_bindings"] = tuple(
                ClientBeClassManualBinding(**item) for item in payload.get("manual_bindings", ())
            )
            for case_no in self._repository.bound_case_nos_for_workbook(digest):
                self._reconciliation.reconcile(case_no)
            unit_of_work.commit()
            return ClientBeClassWorkbookReceipt(
                **{
                    **payload,
                    "replayed_workbook": True,
                }
            )

    def _claim_workbook(self, key: str, digest: str, correlation_id: str) -> None:
        with self._unit_of_work_factory() as unit_of_work:
            if self._repository.claim_workbook(key, digest, correlation_id) == "conflict":
                raise ClientBeClassWorkbookConflict("client_beclass_workbook_idempotency_conflict")
            unit_of_work.commit()

    def _save_workbook_receipt(
        self,
        key: str,
        digest: str,
        preview: str,
        actor: str,
        receipt: ClientBeClassWorkbookReceipt,
    ) -> None:
        with self._unit_of_work_factory() as unit_of_work:
            self._repository.save_workbook_receipt(
                key, digest, preview, actor, receipt.as_dict()
            )
            unit_of_work.commit()


def _load_workbook(source_path: str) -> _Workbook:
    path = Path(source_path)
    validate_xlsx_workbook(path)
    digest = sha256(path.read_bytes()).hexdigest()
    with pd.ExcelFile(path, engine="openpyxl") as excel:
        candidates = [(index, name, excel.parse(sheet_name=name, dtype=object)) for index, name in enumerate(excel.sheet_names)]
    matches = [(index, frame) for index, _, frame in candidates if not frame.dropna(how="all").empty and CLIENT_BECLASS_REQUIRED_HEADERS <= {str(column).strip() for column in frame.columns}]
    if len(matches) != 1:
        raise ValueError("client_beclass_workbook_sheet_contract_not_unique")
    sheet_index, frame = matches[0]
    rows = tuple((ordinal, {str(key).strip(): value for key, value in row.items()}) for ordinal, (_, row) in enumerate(frame.iterrows(), start=2) if not _blank_row(row))
    return _Workbook(digest, sha256(f"sheet:{sheet_index}".encode()).hexdigest(), rows)


def _preview_from_outcomes(
    workbook: _Workbook,
    outcomes: Counter[str],
    row_issues: tuple[ClientBeClassWorkbookRowIssue, ...] = (),
    manual_rows: tuple[ClientBeClassManualRow, ...] = (),
    candidates: tuple[ClientBeClassCaseCandidate, ...] = (),
    confirmed_rows: frozenset[int] = frozenset(),
) -> ClientBeClassWorkbookPreview:
    row_contracts = tuple(
        (
            row_number,
            fingerprint_payload(_normalized_payload(row)).value,
            tuple(sorted(validate_client_beclass_row(row))),
        )
        for row_number, row in workbook.rows
    )
    fingerprint_inputs = {
        "digest": workbook.digest,
        "sheet": workbook.sheet_identity,
        "rows": row_contracts,
        "outcomes": dict(sorted(outcomes.items())),
        "row_issues": tuple(
            (item.source_row, item.query_no, item.fields, item.issue_codes)
            for item in row_issues
        ),
    }
    if manual_rows or confirmed_rows:
        fingerprint_inputs["manual_rows"] = sorted(
            confirmed_rows | {row.source_row for row in manual_rows}
        )
    fingerprint = fingerprint_payload(fingerprint_inputs).value
    return ClientBeClassWorkbookPreview(
        workbook.digest,
        workbook.sheet_identity,
        len(workbook.rows),
        outcomes["create"],
        outcomes["review_required"],
        outcomes["existing_conflict"],
        outcomes["existing_source"],
        fingerprint,
        row_issues,
        manual_rows,
        candidates,
    )


_AMBIGUOUS_BINDINGS = {
    "client_case_binding_multiple_clients", "client_case_binding_case_not_unique",
}


def _case_unavailable_issue(row_number, query_no):
    return ClientBeClassWorkbookRowIssue(
        row_number, query_no, ("HCM 案號",), ("case_import_candidate_stale",)
    )


def _normalized_payload(row: dict[str, Any]) -> dict[str, object]:
    details = {key: _text(value) for key, value in row.items() if key not in {"項次", "查詢序號", "報名時間", "姓名", "Email", "行動電話", "市話", "分機", "縣市", "郵遞區號", "地址", "補助款退款:銀行代號+分行代號", "銀行帳號", "管理者註記事項", "出生年", "月", "日"} and not str(key).startswith("Unnamed") and _text(value)}
    return {"query_no": _text(row.get("查詢序號")), "created_at": _text(row.get("報名時間")), "name": _text(row.get("姓名")), "email": _text(row.get("Email")), "phone": _phone(row.get("行動電話")), "tel": _text(row.get("市話")), "ext": _text(row.get("分機")), "city": _text(row.get("縣市")), "zip_code": _text(row.get("郵遞區號")), "address": _text(row.get("地址")), "refund_bank_code": _digits(row.get("補助款退款:銀行代號+分行代號")), "refund_account_no": _digits(row.get("銀行帳號")), "admin_notes": _text(row.get("管理者註記事項")), "birth_date": _birth_date(row), "survey_details": json.dumps(details, ensure_ascii=False, sort_keys=True, separators=(",", ":"))}


def _safe_review_payload(payload: dict[str, object]) -> dict[str, object]:
    return {"has_query_no": bool(payload.get("query_no")), "has_name": bool(payload.get("name")), "has_phone": bool(payload.get("phone")), "source_field_count": len(payload)}


def _binding_review_payload(payload, resolution) -> dict[str, object]:
    return {
        **_safe_review_payload(payload),
        "client_candidate_count": resolution.client_candidate_count,
        "case_candidate_count": resolution.case_candidate_count,
    }


def _birth_date(row: dict[str, Any]) -> str | None:
    try:
        year = int(row.get("出生年")); year += 1911 if year < 1900 else 0
        return f"{year:04d}-{int(row.get('月')):02d}-{int(row.get('日')):02d}"
    except (TypeError, ValueError):
        return None


def _phone(value: object) -> str | None:
    digits = _digits(value)
    if digits and len(digits) == 9 and digits.startswith("9"):
        return f"0{digits}"
    return digits


def _digits(value: object) -> str | None:
    text = _text(value)
    if text is None:
        return None
    return "".join(character for character in text if character.isdigit()) or None


def _text(value: object) -> str | None:
    return None if value is None or pd.isna(value) or not str(value).strip() else str(value).strip()


def _blank_row(row) -> bool:
    return all(value is None or pd.isna(value) or not str(value).strip() for value in row.values)


def _source_identity(digest: str, row_number: int) -> str:
    return f"client-beclass-workbook:{digest}:row:{row_number}"


def _require_same_fingerprint(stored, fingerprint: str) -> None:
    if stored["request_fingerprint"] != fingerprint:
        raise ClientBeClassWorkbookConflict("client_beclass_source_identity_conflict")


def _assert_conservation(row_count: int, outcomes: Counter[str]) -> None:
    if sum(outcomes.values()) != row_count:
        raise RuntimeError("client_beclass_workbook_outcomes_not_conserved")

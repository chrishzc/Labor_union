"""
File: staff_historical_workbook_adoption.py
Description: 編排 Staff 歷史 workbook 的 Preview、逐列採納、replay 與 terminal receipt。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Callable

from domains.case_import.beclass_import_review import BeClassImportSourceKind
from domains.case_import.staff_historical_adoption import plan_staff_scalar_merge
from infrastructure.mysql.staff_historical_adoption_repository import MySqlStaffHistoricalAdoptionRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.case_import.beclass_review_intake import masked_review_identifier, record_invalid_beclass_row
from subsystems.case_import.staff_historical_adoption import adopt_existing_staff, record_created_staff_adoption, record_staff_adoption_outcome
from subsystems.case_import.staff_historical_workbook import StaffHistoricalWorkbook, StaffHistoricalWorkbookRow, load_staff_historical_workbook


@dataclass(frozen=True, slots=True)
class StaffHistoricalWorkbookPreview:
    source_content_digest: str
    source_row_count: int
    created_count: int
    adopted_existing_count: int
    blocked_identity_count: int
    identity_conflict_count: int
    review_required_count: int
    preview_fingerprint: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StaffHistoricalWorkbookReceipt:
    source_content_digest: str
    source_row_count: int
    created_count: int
    adopted_existing_count: int
    exact_replay_count: int
    blocked_identity_count: int
    identity_conflict_count: int
    review_required_count: int
    preview_fingerprint: str
    replayed_workbook: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class StaffHistoricalWorkbookConflict(RuntimeError):
    pass


class StaffHistoricalWorkbookUnavailable(RuntimeError):
    pass


class StaffHistoricalWorkbookService:
    def __init__(self, connection, workbook_repository, unit_of_work_factory: Callable[[], object]) -> None:
        self._connection = connection
        self._workbook_repository = workbook_repository
        self._unit_of_work_factory = unit_of_work_factory

    def preview(self, source_path: str, source_revision: str | None = None) -> StaffHistoricalWorkbookPreview:
        return self._preview(load_staff_historical_workbook(source_path, source_revision))

    def apply(self, source_path: str, source_revision: str | None, preview_fingerprint: str, key: str, actor: str, correlation_id: str) -> StaffHistoricalWorkbookReceipt:
        workbook = load_staff_historical_workbook(source_path, source_revision)
        preview = self._preview(workbook)
        if preview.preview_fingerprint != preview_fingerprint:
            raise StaffHistoricalWorkbookConflict("staff_historical_workbook_preview_stale")
        if not self._workbook_repository.acquire_lock(key):
            raise StaffHistoricalWorkbookUnavailable("staff_historical_workbook_lock_timeout")
        try:
            replay = self._workbook_repository.load_receipt(key)
            if replay is not None:
                return self._replay(replay, workbook.source_content_digest)
            fresh_preview = self._preview(workbook)
            if fresh_preview.preview_fingerprint != preview.preview_fingerprint:
                raise StaffHistoricalWorkbookConflict("staff_historical_workbook_preview_stale")
            with self._unit_of_work_factory() as unit_of_work:
                claim = self._workbook_repository.claim(key, workbook.source_content_digest, correlation_id)
                if claim == "conflict":
                    raise StaffHistoricalWorkbookConflict("staff_historical_workbook_idempotency_conflict")
                unit_of_work.commit()
            receipt = self._apply_rows(workbook, fresh_preview.preview_fingerprint)
            with self._unit_of_work_factory() as unit_of_work:
                self._workbook_repository.save_receipt(key, workbook.source_content_digest, actor, fresh_preview.preview_fingerprint, receipt.as_dict())
                unit_of_work.commit()
            return receipt
        finally:
            self._workbook_repository.release_lock(key)

    def _preview(self, workbook: StaffHistoricalWorkbook) -> StaffHistoricalWorkbookPreview:
        counts = _counts()
        for row in workbook.rows:
            outcome, reviewed = self._preview_row(row)
            counts[outcome] += 1
            counts["review_required"] += int(reviewed)
        return StaffHistoricalWorkbookPreview(workbook.source_content_digest, len(workbook.rows), counts["created"], counts["adopted_existing"], counts["blocked_identity"], counts["identity_conflict"], counts["review_required"], _preview_fingerprint(workbook, counts))

    def _preview_row(self, row: StaffHistoricalWorkbookRow) -> tuple[str, bool]:
        identity = str(row.record.get("identity_card") or "")
        name = str(row.record.get("name") or "")
        if not identity or "身分證字號" in row.errors or not name or "姓名" in row.errors:
            return "blocked_identity", True
        rows = MySqlStaffHistoricalAdoptionRepository(self._connection).load_staff(identity, for_update=False)
        if _identity_conflicts(rows, row.record):
            return "identity_conflict", True
        if not rows:
            return "created", bool(row.errors)
        merge = plan_staff_scalar_merge(rows[0], row.record)
        name_changed = str(rows[0].get("name") or "") != name
        return "adopted_existing", bool(row.errors or merge.conflict_fields or name_changed)

    def _apply_rows(self, workbook: StaffHistoricalWorkbook, preview_fingerprint: str) -> StaffHistoricalWorkbookReceipt:
        counts = _counts()
        for row in workbook.rows:
            outcome, reviewed = self._apply_row(workbook, row)
            counts[outcome] += 1
            counts["review_required"] += int(reviewed)
        _assert_outcomes(len(workbook.rows), counts)
        return StaffHistoricalWorkbookReceipt(workbook.source_content_digest, len(workbook.rows), counts["created"], counts["adopted_existing"], counts["exact_replay"], counts["blocked_identity"], counts["identity_conflict"], counts["review_required"], preview_fingerprint, False)

    def _apply_row(self, workbook: StaffHistoricalWorkbook, row: StaffHistoricalWorkbookRow) -> tuple[str, bool]:
        identity = str(row.record.get("identity_card") or "")
        name = str(row.record.get("name") or "")
        if not identity or "身分證字號" in row.errors or not name or "姓名" in row.errors:
            return self._record_terminal_review(workbook, row, "blocked_identity", None)
        repository = MySqlStaffHistoricalAdoptionRepository(self._connection)
        roots = repository.load_staff(identity, for_update=False)
        if _identity_conflicts(roots, row.record):
            staff_id = None if len(roots) != 1 else int(roots[0]["id"])
            return self._record_terminal_review(workbook, row, "identity_conflict", staff_id)
        if roots:
            result = adopt_existing_staff(self._connection, source_content_digest=workbook.source_content_digest, source_row=row.source_row, identity_card=identity, historical_record=row.record, source_sheet=workbook.sheet_identity, review_payload=_review_payload(row.record), validation_issue_codes=tuple(f"staff_field_invalid:{field}" for field in row.errors), bank_accounts=row.bank_accounts, relations=row.relations)
            return ("exact_replay", bool(row.errors)) if result.replayed else ("adopted_existing", bool(row.errors or result.conflict_fields))
        return self._create_new_staff(workbook, row)

    def _record_terminal_review(self, workbook, row, outcome, staff_id) -> tuple[str, bool]:
        with MySqlUnitOfWork(self._connection) as unit_of_work:
            review_identity = _record_review(self._connection, workbook, row, _issues(row, outcome))
            replayed = record_staff_adoption_outcome(self._connection, source_content_digest=workbook.source_content_digest, source_row=row.source_row, staff_id=staff_id, historical_record=row.record, review_identity=review_identity, outcome=outcome)
            unit_of_work.commit()
        return ("exact_replay", True) if replayed else (outcome, True)

    def _create_new_staff(self, workbook, row) -> tuple[str, bool]:
        with MySqlUnitOfWork(self._connection) as unit_of_work:
            repository = MySqlStaffHistoricalAdoptionRepository(self._connection)
            identity_card = str(row.record["identity_card"])
            if repository.load_staff(identity_card, for_update=True):
                raise RuntimeError("staff_historical_adoption_stale")
            staff_id = repository.create_staff(row.record)
            bank_changed, bank_conflict = repository.merge_bank_accounts(staff_id, row.bank_accounts)
            del bank_changed
            relation_conflicts = []
            for table_name, values in row.relations.items():
                _, conflict = repository.merge_relation(staff_id, table_name, values)
                if conflict:
                    relation_conflicts.append(table_name)
            issues = tuple(sorted(set(tuple(f"staff_field_invalid:{field}" for field in row.errors) + tuple(f"historical_nonempty_conflict:{field}" for field in relation_conflicts + (["bank_accounts"] if bank_conflict else [])))))
            review_identity = _record_review(self._connection, workbook, row, issues) if issues else None
            replayed = record_created_staff_adoption(self._connection, source_content_digest=workbook.source_content_digest, source_row=row.source_row, staff_id=staff_id, historical_record=row.record, review_identity=review_identity)
            if replayed:
                raise RuntimeError("staff_historical_created_replay_after_insert")
            unit_of_work.commit()
        return "created", bool(issues)

    def _replay(self, stored, digest: str) -> StaffHistoricalWorkbookReceipt:
        if str(stored["request_fingerprint"]) != digest:
            raise StaffHistoricalWorkbookConflict("staff_historical_workbook_idempotency_conflict")
        return StaffHistoricalWorkbookReceipt(**{**json.loads(stored["result_snapshot"]), "replayed_workbook": True})


def _record_review(connection, workbook, row, issues: tuple[str, ...]) -> str:
    return record_invalid_beclass_row(connection, source_kind=BeClassImportSourceKind.STAFF, source_content_digest=workbook.source_content_digest, source_sheet=workbook.sheet_identity, source_row=row.source_row, masked_identifier=masked_review_identifier(BeClassImportSourceKind.STAFF, row.record.get("identity_card"), row.source_row), source_payload=_review_payload(row.record), issue_codes=issues)


def _issues(row, outcome: str) -> tuple[str, ...]:
    base = tuple(f"staff_field_invalid:{field}" for field in row.errors)
    return tuple(sorted(set(base + (outcome,))))


def _review_payload(record: dict[str, object]) -> dict[str, object]:
    return {"source_field_count": len(record), "has_identity_card": bool(record.get("identity_card")), "has_name": bool(record.get("name")), "has_phone": bool(record.get("phone")), "has_address": bool(record.get("address"))}


def _counts() -> dict[str, int]:
    return {name: 0 for name in ("created", "adopted_existing", "exact_replay", "blocked_identity", "identity_conflict", "review_required")}


def _identity_conflicts(roots, historical_record: dict[str, object]) -> bool:
    if len(roots) > 1:
        return True
    if not roots:
        return False
    current_name = str(roots[0].get("name") or "")
    historical_name = str(historical_record.get("name") or "")
    if current_name == historical_name:
        return False
    return not plan_staff_scalar_merge(roots[0], historical_record).source_is_newer


def _preview_fingerprint(workbook, counts) -> str:
    return fingerprint_payload({"digest": workbook.source_content_digest, "sheet": workbook.sheet_identity, "rows": tuple((row.source_row, fingerprint_payload(row.record).value, row.errors) for row in workbook.rows), "counts": counts}).value


def _assert_outcomes(source_rows: int, counts: dict[str, int]) -> None:
    terminal = sum(counts[name] for name in ("created", "adopted_existing", "exact_replay", "blocked_identity", "identity_conflict"))
    if terminal != source_rows:
        raise RuntimeError("staff_historical_row_outcomes_not_conserved")


__all__ = [
    "StaffHistoricalWorkbookConflict",
    "StaffHistoricalWorkbookPreview",
    "StaffHistoricalWorkbookReceipt",
    "StaffHistoricalWorkbookService",
    "StaffHistoricalWorkbookUnavailable",
]

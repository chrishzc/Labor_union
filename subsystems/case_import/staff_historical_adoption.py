"""
File: staff_historical_adoption.py
Description: 編排 Staff 歷史來源 replay、保守 scalar merge 與 adoption receipt。
"""

from __future__ import annotations

from dataclasses import dataclass

from domains.case_import.staff_historical_adoption import plan_staff_scalar_merge
from domains.case_import.beclass_import_review import BeClassImportSourceKind
from infrastructure.mysql.staff_historical_adoption_repository import MySqlStaffHistoricalAdoptionRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.case_import.beclass_review_intake import masked_review_identifier, record_invalid_beclass_row


@dataclass(frozen=True, slots=True)
class StaffHistoricalAdoptionResult:
    outcome: str
    staff_id: int | None
    changed_fields: tuple[str, ...]
    conflict_fields: tuple[str, ...]
    replayed: bool = False


def record_created_staff_adoption(
    connection,
    *,
    source_content_digest: str,
    source_row: int,
    staff_id: int,
    historical_record: dict[str, object],
    review_identity: str | None,
) -> bool:
    return record_staff_adoption_outcome(
        connection,
        source_content_digest=source_content_digest,
        source_row=source_row,
        staff_id=staff_id,
        historical_record=historical_record,
        review_identity=review_identity,
        outcome="created",
    )


def record_staff_adoption_outcome(
    connection,
    *,
    source_content_digest: str,
    source_row: int,
    staff_id: int | None,
    historical_record: dict[str, object],
    review_identity: str | None,
    outcome: str,
) -> bool:
    repository = MySqlStaffHistoricalAdoptionRepository(connection)
    source_identity = f"staff-workbook:{source_content_digest}:row:{source_row}"
    source_fingerprint = fingerprint_payload(historical_record).value
    key = f"staff-historical-adoption:{source_content_digest}:row:{source_row}"
    command_fingerprint = fingerprint_payload(
        {"source_identity": source_identity, "source_fingerprint": source_fingerprint}
    ).value
    if not repository.claim(key, command_fingerprint, source_identity):
        receipt = repository.find_receipt(key)
        if receipt is None or str(receipt["command_fingerprint"]) != command_fingerprint:
            raise RuntimeError("staff_historical_adoption_idempotency_conflict")
        if str(receipt["outcome"]) in {"created", "adopted_existing"}:
            _require_matching_replay_root(repository, receipt, historical_record)
            return True
        return False
    repository.save_receipt(
        key=key,
        command_fingerprint=command_fingerprint,
        source_identity=source_identity,
        source_fingerprint=source_fingerprint,
        preview_fingerprint=fingerprint_payload(
            {"outcome": outcome, "resolved_staff_id": staff_id}
        ).value,
        staff_id=staff_id,
        outcome=outcome,
        changed_fields={"scalar_fields": sorted(historical_record)},
        review_identity=review_identity,
    )
    return False


# 此函式刻意維持單列 identity、review、receipt 的同一 outer UoW，拆開會模糊 commit owner。
def adopt_existing_staff(
    connection,
    *,
    source_content_digest: str,
    source_row: int,
    identity_card: str,
    historical_record: dict[str, object],
    source_sheet: str,
    review_payload: dict[str, object],
    validation_issue_codes: tuple[str, ...] = (),
    bank_accounts: tuple[tuple[object, ...], ...] = (),
    relations: dict[str, tuple[tuple[object, ...], ...]] | None = None,
) -> StaffHistoricalAdoptionResult:
    repository = MySqlStaffHistoricalAdoptionRepository(connection)
    source_identity = f"staff-workbook:{source_content_digest}:row:{source_row}"
    normalized_relations = relations or {}
    source_fingerprint = fingerprint_payload({
        "historical_record": historical_record,
        "bank_accounts": bank_accounts,
        "relations": normalized_relations,
    }).value
    key = f"staff-historical-adoption:{source_content_digest}:row:{source_row}"
    command_fingerprint = fingerprint_payload(
        {"source_identity": source_identity, "source_fingerprint": source_fingerprint}
    ).value
    with MySqlUnitOfWork(connection) as unit_of_work:
        receipt = repository.find_receipt(key)
        if receipt is not None:
            if str(receipt["command_fingerprint"]) != command_fingerprint:
                raise RuntimeError("staff_historical_adoption_idempotency_conflict")
            stored_outcome = str(receipt["outcome"])
            if stored_outcome in {"created", "adopted_existing"}:
                _require_matching_replay_root(repository, receipt, historical_record)
            unit_of_work.commit()
            stored_staff_id = receipt["staff_id"]
            replayed = stored_outcome in {"created", "adopted_existing"}
            return StaffHistoricalAdoptionResult(
                stored_outcome,
                None if stored_staff_id is None else int(stored_staff_id),
                (),
                (),
                replayed,
            )
        if not repository.claim(key, command_fingerprint, source_identity):
            raise RuntimeError("staff_historical_adoption_claim_without_receipt")
        rows = repository.load_staff(identity_card, for_update=True)
        if len(rows) != 1:
            raise RuntimeError("staff_historical_adoption_identity_ambiguous")
        existing = rows[0]
        merge = plan_staff_scalar_merge(existing, historical_record)
        name_changed = (
            str(existing.get("name") or "").strip()
            != str(historical_record.get("name") or "").strip()
        )
        changed_groups: list[str] = []
        relation_conflicts: list[str] = []
        bank_changed, bank_conflict = repository.merge_bank_accounts(
            int(existing["id"]),
            bank_accounts,
            replace_existing=merge.source_is_newer,
        )
        if bank_changed:
            changed_groups.append("bank_accounts")
        if bank_conflict:
            relation_conflicts.append("bank_accounts")
        for table_name, incoming in sorted(normalized_relations.items()):
            changed, conflict = repository.merge_relation(
                int(existing["id"]),
                table_name,
                incoming,
                replace_existing=merge.source_is_newer,
            )
            if changed:
                changed_groups.append(table_name)
            if conflict:
                relation_conflicts.append(table_name)
        traceability_issues = (
            ("historical_name_changed",)
            if name_changed and merge.source_is_newer
            else ()
        )
        review_issues = tuple(sorted(set(validation_issue_codes + traceability_issues + tuple(
            f"historical_nonempty_conflict:{field}" for field in merge.conflict_fields
        ) + tuple(f"historical_nonempty_conflict:{field}" for field in relation_conflicts))))
        review_identity = None
        if review_issues:
            review_identity = record_invalid_beclass_row(
                connection,
                source_kind=BeClassImportSourceKind.STAFF,
                source_content_digest=source_content_digest,
                source_sheet=source_sheet,
                source_row=source_row,
                masked_identifier=masked_review_identifier(
                    BeClassImportSourceKind.STAFF, identity_card, source_row
                ),
                source_payload=review_payload,
                issue_codes=review_issues,
            )
        repository.apply_scalar_patch(int(existing["id"]), dict(merge.patch))
        repository.save_receipt(
            key=key,
            command_fingerprint=command_fingerprint,
            source_identity=source_identity,
            source_fingerprint=source_fingerprint,
            preview_fingerprint=merge.preview_fingerprint.value,
            staff_id=int(existing["id"]),
            outcome="adopted_existing",
            changed_fields={
                "scalar_fields": sorted(merge.patch),
                "relation_groups": sorted(changed_groups),
            },
            review_identity=review_identity,
        )
        unit_of_work.commit()
    return StaffHistoricalAdoptionResult(
        "adopted_existing",
        int(existing["id"]),
        tuple(sorted(merge.patch)),
        tuple(sorted(set(merge.conflict_fields + tuple(relation_conflicts)))),
    )


def _require_matching_replay_root(repository, receipt, historical_record) -> None:
    identity_card = str(historical_record.get("identity_card") or "").strip().upper()
    rows = repository.load_staff(identity_card, for_update=True) if identity_card else ()
    if len(rows) != 1:
        raise RuntimeError("staff_historical_adoption_replay_root_drift")
    current = rows[0]
    stored_staff_id = receipt.get("staff_id")
    if stored_staff_id is None or int(current["id"]) != int(stored_staff_id):
        raise RuntimeError("staff_historical_adoption_replay_root_drift")


__all__ = [
    "StaffHistoricalAdoptionResult",
    "adopt_existing_staff",
    "record_created_staff_adoption",
    "record_staff_adoption_outcome",
]

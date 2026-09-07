"""Staff-owned Query/Preview/Apply workflow for six canonical relations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from domains.staff.case_preference_manual import (
    CasePreferenceManualError, CasePreferenceManualPreview, CasePreferenceManualSnapshot,
    RELATION_KEYS, Relations, normalize_relations, preview_fingerprint, snapshot_fingerprint,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey

_COMMAND_FAMILY = "staff_case_preference_manual/v1"


class StaffCasePreferenceManualRepository(Protocol):
    def staff_exists(self, staff_id: int) -> bool: ...
    def lock_staff(self, staff_id: int) -> None: ...
    def load_relations(self, staff_id: int, *, for_update: bool) -> Relations: ...
    def find_receipt(self, key: IdempotencyKey, *, for_update: bool) -> Mapping[str, Any] | None: ...
    def replace_relations(self, staff_id: int, relations: Relations) -> None: ...
    def save_receipt(self, *, key: IdempotencyKey, request_fingerprint: PreviewFingerprint,
                     preview_fingerprint: PreviewFingerprint, actor: str, reason: str,
                     result: Mapping[str, Any]) -> None: ...


@dataclass(frozen=True, slots=True)
class CasePreferenceManualApplyRequest:
    expected_snapshot_fingerprint: PreviewFingerprint
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class CasePreferenceManualReceipt:
    staff_id: int
    relations: Relations
    snapshot_fingerprint: PreviewFingerprint
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    replayed: bool = False


class StaffCasePreferenceManualWorkflow:
    def __init__(self, repository: StaffCasePreferenceManualRepository, unit_of_work_factory: Callable[[], Any]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def query(self, staff_id: int) -> CasePreferenceManualSnapshot:
        self._require_staff(staff_id)
        relations = normalize_relations(self._repository.load_relations(staff_id, for_update=False))
        return CasePreferenceManualSnapshot(staff_id, relations, snapshot_fingerprint(staff_id, relations))

    def preview(self, staff_id: int, proposed: Mapping[str, object]) -> CasePreferenceManualPreview:
        current = self.query(staff_id)
        after = normalize_relations(proposed)
        return CasePreferenceManualPreview(
            staff_id, current.relations, after, current.snapshot_fingerprint,
            preview_fingerprint(staff_id, current.relations, after, current.snapshot_fingerprint),
        )

    def apply(self, staff_id: int, proposed: Mapping[str, object], request: CasePreferenceManualApplyRequest) -> CasePreferenceManualReceipt:
        after = normalize_relations(proposed)
        command_fingerprint = fingerprint_payload({
            "actor": request.actor.actor_id, "aggregate_identity": str(staff_id),
            "command_family": _COMMAND_FAMILY,
            "relations": {key: [item.canonical_payload() for item in after[key]] for key in RELATION_KEYS},
            "reason": request.reason.strip(),
            "expected_snapshot_fingerprint": request.expected_snapshot_fingerprint.value,
            "preview_fingerprint": request.preview_fingerprint.value,
        })
        with self._unit_of_work_factory() as unit_of_work:
            # The parent row is the aggregate lock; relation-row locks follow it.
            self._repository.lock_staff(staff_id)
            replay = self._repository.find_receipt(request.idempotency_key, for_update=True)
            if replay is not None:
                if str(replay["request_fingerprint"]) != command_fingerprint.value:
                    raise CasePreferenceManualError("staff_case_preference_idempotency_conflict")
                unit_of_work.commit()
                return _receipt_from_result(replay["result"], request.idempotency_key, replayed=True)
            fresh = normalize_relations(self._repository.load_relations(staff_id, for_update=True))
            fresh_snapshot = snapshot_fingerprint(staff_id, fresh)
            if fresh_snapshot != request.expected_snapshot_fingerprint:
                raise CasePreferenceManualError("staff_case_preference_stale_snapshot")
            expected_preview = preview_fingerprint(staff_id, fresh, after, fresh_snapshot)
            if expected_preview != request.preview_fingerprint:
                raise CasePreferenceManualError("staff_case_preference_stale_preview")
            self._repository.replace_relations(staff_id, after)
            persisted = normalize_relations(self._repository.load_relations(staff_id, for_update=True))
            if persisted != after:
                raise CasePreferenceManualError("staff_case_preference_persisted_mismatch")
            result = {
                "staff_id": staff_id,
                "relations": {key: [item.canonical_payload() for item in persisted[key]] for key in RELATION_KEYS},
                "snapshot_fingerprint": snapshot_fingerprint(staff_id, persisted).value,
                "preview_fingerprint": request.preview_fingerprint.value,
                "idempotency_key": request.idempotency_key.value,
                "replayed": False,
            }
            self._repository.save_receipt(
                key=request.idempotency_key, request_fingerprint=command_fingerprint,
                preview_fingerprint=request.preview_fingerprint, actor=request.actor.actor_id,
                reason=request.reason.strip(), result=result,
            )
            unit_of_work.commit()
            return _receipt_from_result(result, request.idempotency_key, replayed=False)

    def _require_staff(self, staff_id: int) -> None:
        if not self._repository.staff_exists(staff_id):
            raise CasePreferenceManualError("staff_not_found")


def _receipt_from_result(result: Mapping[str, Any], key: IdempotencyKey, *, replayed: bool) -> CasePreferenceManualReceipt:
    relations = normalize_relations(result["relations"])
    return CasePreferenceManualReceipt(
        int(result["staff_id"]), relations,
        PreviewFingerprint(str(result["snapshot_fingerprint"])),
        PreviewFingerprint(str(result["preview_fingerprint"])), key, replayed,
    )


__all__ = ["CasePreferenceManualApplyRequest", "CasePreferenceManualReceipt", "StaffCasePreferenceManualWorkflow"]

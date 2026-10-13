"""Query/Preview/Apply for existing Staff qualification facts; one outer commit."""
from typing import Protocol, Any, Callable

from domains.staff.qualification_editing import (
    QualificationEditingError, QualificationFacts, normalize_facts,
    snapshot_fingerprint, preview_fingerprint,
)
from shared_kernel.fingerprints import fingerprint_payload

COMMAND_FAMILY = "staff_qualification_editing/v1"


class QualificationEditingRepository(Protocol):
    def load(self, staff_id: int, *, for_update: bool) -> QualificationFacts: ...
    def persist(self, staff_id: int, before: QualificationFacts, after: QualificationFacts) -> None: ...
    def find_receipt(self, key: str) -> dict | None: ...
    def save_receipt(self, key: str, request_fingerprint: str, preview: str, actor: str, reason: str, result: dict) -> None: ...


class StaffQualificationEditingWorkflow:
    def __init__(self, repository: QualificationEditingRepository, unit_of_work_factory: Callable[[], Any]):
        self.repository = repository
        self.unit_of_work_factory = unit_of_work_factory

    def query(self, staff_id: int):
        facts = self.repository.load(staff_id, for_update=False)
        return {"staff_id": staff_id, "before": facts.payload(), "after": facts.payload(),
                "snapshot_fingerprint": snapshot_fingerprint(staff_id, facts).value, "preview_fingerprint": None}

    def preview(self, staff_id: int, values):
        after = normalize_facts(values)
        before = self.repository.load(staff_id, for_update=False)
        return {"staff_id": staff_id, "before": before.payload(), "after": after.payload(),
                "snapshot_fingerprint": snapshot_fingerprint(staff_id, before).value,
                "preview_fingerprint": preview_fingerprint(staff_id, before, after).value}

    def apply(self, staff_id: int, values, *, expected_snapshot: str, preview: str,
              key: str, actor: str, reason: str, correlation: str):
        after = normalize_facts(values)
        if not reason.strip():
            raise QualificationEditingError("staff_qualification_reason_required")
        command = fingerprint_payload({"staff_id": staff_id, "facts": after.payload(), "actor": actor,
                                       "reason": reason.strip(), "expected_snapshot": expected_snapshot, "preview": preview}).value
        with self.unit_of_work_factory() as uow:
            # Lock the parent first: protects empty child sets and competing manual edits.
            before = self.repository.load(staff_id, for_update=True)
            replay = self.repository.find_receipt(key)
            if replay is not None:
                if replay["request_fingerprint"] != command:
                    raise QualificationEditingError("staff_qualification_idempotency_conflict")
                uow.commit()
                return {**replay["result"], "replayed": True}
            if snapshot_fingerprint(staff_id, before).value != expected_snapshot:
                raise QualificationEditingError("staff_qualification_stale_snapshot")
            if preview_fingerprint(staff_id, before, after).value != preview:
                raise QualificationEditingError("staff_qualification_stale_preview")
            self.repository.persist(staff_id, before, after)
            persisted = self.repository.load(staff_id, for_update=True)
            if persisted != after:
                raise QualificationEditingError("staff_qualification_persisted_mismatch")
            result = {"staff_id": staff_id, "before": before.payload(), "after": persisted.payload(),
                      "snapshot_fingerprint": snapshot_fingerprint(staff_id, persisted).value,
                      "preview_fingerprint": preview, "idempotency_key": key, "replayed": False,
                      "correlation_id": correlation}
            self.repository.save_receipt(key, command, preview, actor, reason.strip(), result)
            uow.commit()
            return result

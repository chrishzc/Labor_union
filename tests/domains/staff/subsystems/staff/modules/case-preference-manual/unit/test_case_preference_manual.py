from dataclasses import dataclass, field, replace

import pytest

from domains.staff.case_preference_manual import (
    ALL_RELATION_KEYS, READ_ONLY_RELATION_SPECS, RELATION_KEYS, RelationValue,
    normalize_relations, preview_fingerprint, snapshot_fingerprint,
)
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.staff.case_preference_manual_workflow import (
    CasePreferenceManualApplyRequest, StaffCasePreferenceManualWorkflow,
)


def _relations():
    return {
        "service_regions": [{"value": "北區", "detail": "保留區域說明"}],
        "service_periods": [{"value": "8小時", "detail": None}],
        "cooking_skills": [{"value": "葷食", "detail": None}],
        "holiday_availability": [{"value": "端午節", "detail": None}],
        "rest_schedule": [{"value": "週休1日", "detail": None}],
        "baby_types": [{"value": "單胞胎", "detail": None}],
    }


@dataclass
class _Uow:
    committed: bool = False
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def commit(self): self.committed = True


@dataclass
class _Repo:
    relations: dict = field(default_factory=_relations)
    transportation: tuple = (RelationValue("機車"),)
    receipts: dict = field(default_factory=dict)
    events: list[str] = field(default_factory=list)
    writes: int = 0
    def staff_exists(self, staff_id): self.events.append("staff_exists"); return staff_id == 531
    def lock_staff(self, staff_id): self.events.append("lock_staff"); assert staff_id == 531
    def load_relations(self, staff_id, *, for_update):
        self.events.append("load_update" if for_update else "load_read")
        return self.relations
    def find_receipt(self, key, *, for_update):
        self.events.append("receipt_lock" if for_update else "receipt_read")
        return self.receipts.get(key.value)
    def replace_relations(self, staff_id, relations):
        self.events.append("replace"); self.writes += 1; self.relations = relations
    def save_receipt(self, *, key, request_fingerprint, preview_fingerprint, actor, reason, result):
        self.events.append("save_receipt"); self.receipts[key.value] = {"request_fingerprint": request_fingerprint.value, "result": result}


def _workflow(repo): return StaffCasePreferenceManualWorkflow(repo, _Uow)


def _request(preview, key="staff-manual-1", reason="保留既有細節"):
    return CasePreferenceManualApplyRequest(
        preview.snapshot_fingerprint, preview.preview_fingerprint,
        IdempotencyKey(key), ActorContext("admin:test"), reason, CorrelationId("staff-manual-test"),
    )


def test_query_preview_are_zero_write_and_include_details_without_transport_write_scope():
    repo = _Repo(); workflow = _workflow(repo)
    queried = workflow.query(531)
    preview = workflow.preview(531, _relations())
    assert queried.relations["service_regions"][0].detail == "保留區域說明"
    assert preview.before == preview.after
    assert repo.writes == 0
    assert ALL_RELATION_KEYS == (*RELATION_KEYS, "transportation")
    assert READ_ONLY_RELATION_SPECS["transportation"][0] == "staff_transportation"
    assert repo.transportation == (RelationValue("機車"),)


def test_apply_locks_parent_before_relation_rows_and_preserves_detail_and_transportation():
    repo = _Repo(); workflow = _workflow(repo)
    preview = workflow.preview(531, _relations())
    receipt = workflow.apply(531, _relations(), _request(preview))
    assert repo.events[repo.events.index("lock_staff") : repo.events.index("replace")] == ["lock_staff", "receipt_lock", "load_update"]
    assert receipt.relations["service_regions"][0].detail == "保留區域說明"
    assert repo.transportation == (RelationValue("機車"),)


def test_apply_rejects_fresh_stale_snapshot_before_replace():
    repo = _Repo(); workflow = _workflow(repo)
    preview = workflow.preview(531, _relations())
    repo.relations["service_regions"] = ({"value": "東區", "detail": None},)
    with pytest.raises(ValueError, match="stale_snapshot"):
        workflow.apply(531, _relations(), _request(preview))
    assert repo.writes == 0


def test_apply_replay_is_idempotent_and_changed_payload_conflicts():
    repo = _Repo(); workflow = _workflow(repo)
    proposed = _relations(); preview = workflow.preview(531, proposed); request = _request(preview)
    first = workflow.apply(531, proposed, request)
    replay = workflow.apply(531, proposed, request)
    assert first.replayed is False and replay.replayed is True and repo.writes == 1
    with pytest.raises(ValueError, match="idempotency_conflict"):
        workflow.apply(531, proposed, replace(request, reason="不同原因"))


def test_domain_contract_is_strict_and_fingerprints_bind_before_after():
    before = normalize_relations(_relations())
    after = normalize_relations({**_relations(), "service_regions": [{"value": "東區", "detail": None}]})
    snapshot = snapshot_fingerprint(531, before)
    assert snapshot != snapshot_fingerprint(532, before)
    assert preview_fingerprint(531, before, after, snapshot) != preview_fingerprint(531, before, before, snapshot)
    with pytest.raises(ValueError, match="keys_invalid"):
        normalize_relations({**_relations(), "transportation": []})
    with pytest.raises(ValueError, match="duplicate"):
        normalize_relations({**_relations(), "service_regions": [
            {"value": "其他", "detail": "第一筆"},
            {"value": "其他", "detail": "第二筆"},
        ]})

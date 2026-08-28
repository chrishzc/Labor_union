from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from domains.staff_payables.overpayment_recovery import (
    StaffOverpaymentRecovery,
    StaffOverpaymentRecoveryStatus,
    StaffRecoveryIncomingBankFact,
    build_staff_overpayment_recovery_adjustment_candidate,
    build_staff_overpayment_recovery_collection_candidate,
)
from shared_kernel.errors import ErrorCategory
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.staff_payables.overpayment_recovery import (
    StaffOverpaymentRecoveryAction,
    StaffOverpaymentRecoveryApplyRequest,
    StaffOverpaymentRecoveryError,
    StaffOverpaymentRecoveryFacts,
    StaffOverpaymentRecoverySelection,
    StaffOverpaymentRecoveryWorkflow,
)
from subsystems.staff_payables.overpayment_recovery_matching import (
    StaffOverpaymentRecoveryMatchingApplyRequest,
    StaffOverpaymentRecoveryMatchingFacts,
    StaffOverpaymentRecoveryMatchingSelection,
    StaffOverpaymentRecoveryMatchingWorkflow,
)
from api.routes.staff_payout import (
    _recovery_preview_payload,
    preview_overpayment_recovery_collection,
)


def _recovery(amount: int = 1_000, version: int = 4) -> StaffOverpaymentRecovery:
    return StaffOverpaymentRecovery(
        "staff-overpayment-recovery:1", 7, MoneyNTD(amount),
        StaffOverpaymentRecoveryStatus.OPEN, version,
    )


def _incoming(amount: int = 1_000, staff_id: int = 7) -> StaffRecoveryIncomingBankFact:
    return StaffRecoveryIncomingBankFact(
        "finance-import-row:11", staff_id, MoneyNTD(amount), "2026-08-11", True,
    )


def test_collection_uses_canonical_incoming_and_can_settle_recovery():
    candidate = build_staff_overpayment_recovery_collection_candidate(
        _recovery(), _incoming(),
    )

    assert candidate.remaining_after == MoneyNTD(0)
    assert candidate.resulting_status is StaffOverpaymentRecoveryStatus.RECOVERED
    assert candidate.bank_fact_identity == "finance-import-row:11"


def test_collection_can_only_reduce_existing_recovery_for_matching_staff():
    with pytest.raises(ValueError, match="staff_overpayment_recovery_amount_exceeded"):
        build_staff_overpayment_recovery_collection_candidate(_recovery(), _incoming(1_001))
    with pytest.raises(ValueError, match="staff_overpayment_recovery_target_ambiguous"):
        build_staff_overpayment_recovery_collection_candidate(_recovery(), _incoming(staff_id=8))


def test_adjustment_is_non_cash_and_requires_authorization_for_full_remaining():
    candidate = build_staff_overpayment_recovery_adjustment_candidate(
        _recovery(), MoneyNTD(1_000), adjustment_authorized=True,
    )

    assert candidate.resulting_status is StaffOverpaymentRecoveryStatus.ADJUSTED
    with pytest.raises(ValueError, match="staff_overpayment_recovery_adjustment_forbidden"):
        build_staff_overpayment_recovery_adjustment_candidate(
            _recovery(), MoneyNTD(1_000), adjustment_authorized=False,
        )
    with pytest.raises(ValueError, match="staff_overpayment_recovery_adjustment_amount_invalid"):
        build_staff_overpayment_recovery_adjustment_candidate(
            _recovery(), MoneyNTD(500), adjustment_authorized=True,
        )


class _UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        return None


class _Repository:
    def __init__(self, facts):
        self.facts = facts
        self.receipt = None
        self.persisted = []

    def load(self, _selection, *, for_update):
        self.persisted.append(("load", for_update))
        return self.facts

    def find_receipt(self, _key):
        return self.receipt

    def persist(self, _request, preview, receipt, fingerprint):
        self.persisted.append(("persist", preview.candidate.bank_fact_identity))
        from subsystems.staff_payables.overpayment_recovery import StoredStaffOverpaymentRecoveryReceipt
        self.receipt = StoredStaffOverpaymentRecoveryReceipt(fingerprint, receipt)


def _collection_selection():
    return StaffOverpaymentRecoverySelection(
        "staff-overpayment-recovery:1", StaffOverpaymentRecoveryAction.COLLECT,
        "finance-import-row:11",
        matching_identity="staff-recovery-match:1", matching_version=1,
    )


def _apply_request(preview):
    return StaffOverpaymentRecoveryApplyRequest(
        _collection_selection(), ExpectedVersion(4), ExpectedVersion(9),
        preview.fingerprint, IdempotencyKey("staff-recovery-collection:1"),
        ActorContext("finance-admin"), "Record returned overpayment.",
        CorrelationId("staff-recovery-collection"),
    )


def test_workflow_requires_preview_versions_and_replays_same_command():
    facts = StaffOverpaymentRecoveryFacts(_recovery(), 9, _incoming())
    repository = _Repository(facts)
    workflow = StaffOverpaymentRecoveryWorkflow(repository, _UnitOfWork)
    preview = workflow.preview(_collection_selection(), CorrelationId("preview"))
    request = _apply_request(preview)

    first = workflow.apply(request)
    replay = workflow.apply(request)

    assert first.resulting_status == "recovered"
    assert replay == first
    assert repository.persisted == [
        ("load", False), ("load", True), ("persist", "finance-import-row:11"),
    ]


def test_workflow_rejects_stale_recovery_before_persisting():
    preview_facts = StaffOverpaymentRecoveryFacts(_recovery(version=4), 9, _incoming())
    preview = StaffOverpaymentRecoveryWorkflow(_Repository(preview_facts), _UnitOfWork).preview(
        _collection_selection(), CorrelationId("preview"),
    )
    repository = _Repository(StaffOverpaymentRecoveryFacts(_recovery(version=5), 9, _incoming()))
    workflow = StaffOverpaymentRecoveryWorkflow(repository, _UnitOfWork)

    with pytest.raises(StaffOverpaymentRecoveryError) as raised:
        workflow.apply(_apply_request(preview))

    assert raised.value.error.category is ErrorCategory.CONFLICT
    assert raised.value.error.code == "staff_overpayment_recovery_stale"
    assert repository.persisted == [("load", True)]


def test_collection_preview_requires_existing_immutable_matching_identity_and_version():
    with pytest.raises(ValueError, match="staff_overpayment_recovery_matching_required"):
        StaffOverpaymentRecoverySelection(
            "staff-overpayment-recovery:1", StaffOverpaymentRecoveryAction.COLLECT,
            "finance-import-row:11",
        )
    with pytest.raises(ValueError, match="staff_overpayment_recovery_matching_invalid"):
        StaffOverpaymentRecoverySelection(
            "staff-overpayment-recovery:1", StaffOverpaymentRecoveryAction.COLLECT,
            "finance-import-row:11", matching_identity="staff-recovery-match:1",
            matching_version=0,
        )


def test_adjustment_cannot_carry_matching_or_bank_row_identity():
    with pytest.raises(ValueError, match="staff_overpayment_recovery_action_invalid"):
        StaffOverpaymentRecoverySelection(
            "staff-overpayment-recovery:1", StaffOverpaymentRecoveryAction.ADJUST,
            adjustment_amount=MoneyNTD(1), matching_version=1,
        )


def test_unmatched_collection_endpoint_requires_immutable_matching():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as raised:
        preview_overpayment_recovery_collection()

    assert raised.value.status_code == 410
    assert raised.value.detail["error"]["code"] == "staff_overpayment_recovery_matching_required"


def test_unmatched_staff_collection_http_endpoint_returns_typed_410():
    from api.main import app

    response = TestClient(app).post(
        "/api/v1/staff-payables/overpayment-recoveries/collection/preview"
    )

    assert response.status_code == 410
    assert response.json()["detail"]["error"]["code"] == "resource_retired"
    assert "replacement" not in response.json()["detail"]["error"]


def test_collection_preview_payload_does_not_accept_client_money_values():
    preview = StaffOverpaymentRecoveryWorkflow(
        _Repository(StaffOverpaymentRecoveryFacts(_recovery(), 9, _incoming())),
        _UnitOfWork,
    ).preview(_collection_selection(), CorrelationId("preview"))

    payload = _recovery_preview_payload(preview)

    assert payload["received_amount_ntd"] == 1_000
    assert payload["remaining_after_ntd"] == 0


def test_matching_apply_binds_one_staff_return_to_current_recovery():
    workflow = StaffOverpaymentRecoveryMatchingWorkflow(_MatchingRepository(), _UnitOfWork)
    selection = StaffOverpaymentRecoveryMatchingSelection("staff-overpayment-recovery:1", "11")
    preview = workflow.preview(selection, CorrelationId("staff-matching-preview"))
    receipt = workflow.apply(StaffOverpaymentRecoveryMatchingApplyRequest(
        selection, ExpectedVersion(4), ExpectedVersion(9), preview.fingerprint,
        IdempotencyKey("staff-matching-key"), ActorContext("admin:1"),
        "staff remittance proof reviewed", CorrelationId("staff-matching-apply"),
    ))
    assert receipt.staff_id == 7
    assert receipt.finance_import_row_identity == "11"


def test_matching_schema_reserves_bank_row_once():
    from pathlib import Path
    schema = Path("db/schema_parts/173_staff_overpayment_recovery_matching.sql").read_text(encoding="utf-8")
    assert "UNIQUE KEY uq_staff_recovery_matching_bank_row" in schema


class _MatchingRepository:
    def load_matching(self, _selection, *, for_update):
        return StaffOverpaymentRecoveryMatchingFacts(7, 4, 9, True)

    def find_matching_receipt(self, _key):
        return None

    def persist_matching(self, _request, _preview, _receipt, _fingerprint):
        return None

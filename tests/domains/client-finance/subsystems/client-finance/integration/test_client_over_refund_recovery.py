import pytest

from domains.client_finance.over_refund_recovery import (
    ClientOverRefundRecovery,
    ClientOverRefundRecoveryStatus,
    ClientRecoveryIncomingBankFact,
    build_client_over_refund_recovery_candidate,
    build_client_over_refund_recovery_adjustment_candidate,
)
from shared_kernel.money import MoneyNTD
from shared_kernel.identities import CorrelationId
from shared_kernel.identities import ActorContext, ExpectedVersion, IdempotencyKey
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.client_finance.over_refund_recovery_workflow import (
    ClientOverRefundRecoveryFacts,
    ClientOverRefundRecoverySelection,
    ClientOverRefundRecoveryWorkflow,
    ClientOverRefundRecoveryAction,
    ClientOverRefundRecoveryApplyRequest,
)
from subsystems.client_finance.over_refund_recovery_matching_workflow import (
    ClientOverRefundRecoveryMatchingApplyRequest,
    ClientOverRefundRecoveryMatchingFacts,
    ClientOverRefundRecoveryMatchingSelection,
    ClientOverRefundRecoveryMatchingWorkflow,
)


def test_full_recovery_settles_the_recovery_root() -> None:
    candidate = build_client_over_refund_recovery_candidate(_recovery(250), _incoming(250))

    assert candidate.remaining_after == MoneyNTD(0)
    assert candidate.resulting_status is ClientOverRefundRecoveryStatus.RECOVERED


def test_partial_recovery_is_only_a_remaining_balance_remedy() -> None:
    candidate = build_client_over_refund_recovery_candidate(_recovery(250), _incoming(100))

    assert candidate.remaining_after == MoneyNTD(150)
    assert candidate.resulting_status is ClientOverRefundRecoveryStatus.PARTIALLY_RECOVERED


def test_recovery_rejects_an_incoming_amount_above_remaining() -> None:
    try:
        build_client_over_refund_recovery_candidate(_recovery(250), _incoming(251))
    except ValueError as error:
        assert str(error) == "client_over_refund_recovery_amount_exceeded"
    else:
        raise AssertionError("recovery must not absorb excess incoming cash")


def test_authorized_adjustment_only_settles_the_selected_recovery() -> None:
    partial = build_client_over_refund_recovery_adjustment_candidate(
        _recovery(250),
        MoneyNTD(100),
        adjustment_authorized=True,
    )
    settled = build_client_over_refund_recovery_adjustment_candidate(
        _recovery(250),
        MoneyNTD(250),
        adjustment_authorized=True,
    )

    assert partial.remaining_after == MoneyNTD(150)
    assert partial.resulting_status is ClientOverRefundRecoveryStatus.OPEN
    assert settled.remaining_after == MoneyNTD(0)
    assert settled.resulting_status is ClientOverRefundRecoveryStatus.ADJUSTED


def test_adjustment_requires_explicit_authorization() -> None:
    try:
        build_client_over_refund_recovery_adjustment_candidate(
            _recovery(250),
            MoneyNTD(100),
            adjustment_authorized=False,
        )
    except ValueError as error:
        assert str(error) == "client_over_refund_recovery_adjustment_forbidden"
    else:
        raise AssertionError("unprivileged adjustment must be rejected")


def test_schema_allows_zero_remaining_only_for_a_closed_recovery() -> None:
    from pathlib import Path

    schema = Path(
        "db/schema_parts/171_client_over_refund_recovery_adjustment.sql"
    ).read_text(encoding="utf-8")

    assert "amount_due_ntd = 0 AND status IN ('recovered', 'adjusted')" in schema


def test_preview_fingerprint_is_canonical_for_the_selected_bank_row() -> None:
    workflow = ClientOverRefundRecoveryWorkflow(_PreviewRepository(), _NeverUsedUnitOfWork)

    preview = workflow.preview(
        ClientOverRefundRecoverySelection(
            "115000001", "client-over-refund-recovery:1", "row:1",
            matching_identity="client-recovery-match:1", matching_version=1,
        ),
        CorrelationId("test-client-over-refund-preview"),
    )

    assert len(preview.fingerprint.value) == 64


def test_adjustment_apply_rebuilds_authorized_candidate_before_persisting() -> None:
    repository = _AdjustmentRepository()
    workflow = ClientOverRefundRecoveryWorkflow(repository, _UnitOfWork)
    selection = ClientOverRefundRecoverySelection(
        "115000001",
        "client-over-refund-recovery:1",
        action=ClientOverRefundRecoveryAction.ADJUST,
        adjustment_amount=MoneyNTD(100),
    )
    preview = workflow.preview(selection, CorrelationId("client-adjustment-preview"))

    receipt = workflow.apply(
        ClientOverRefundRecoveryApplyRequest(
            selection,
            ExpectedVersion(1),
            ExpectedVersion(4),
            preview.fingerprint,
            IdempotencyKey("client-adjustment-key"),
            ActorContext("admin:1"),
            "approved write-off",
            CorrelationId("client-adjustment-apply"),
        )
    )

    assert receipt.remaining_after_ntd == 150
    assert receipt.resulting_status == "open"
    assert repository.persisted is not None


def test_collection_preview_requires_existing_immutable_matching_identity_and_version() -> None:
    with pytest.raises(ValueError, match="client_over_refund_recovery_matching_required"):
        ClientOverRefundRecoverySelection(
            "115000001", "client-over-refund-recovery:1", "row:1",
        )

    with pytest.raises(ValueError, match="client_over_refund_recovery_matching_invalid"):
        ClientOverRefundRecoverySelection(
            "115000001", "client-over-refund-recovery:1", "row:1",
            matching_identity="client-recovery-match:1", matching_version=0,
        )


def test_adjustment_cannot_carry_matching_or_bank_row_identity() -> None:
    with pytest.raises(ValueError, match="client_over_refund_recovery_action_invalid"):
        ClientOverRefundRecoverySelection(
            "115000001", "client-over-refund-recovery:1",
            action=ClientOverRefundRecoveryAction.ADJUST,
            adjustment_amount=MoneyNTD(100), matching_version=1,
        )


def test_matching_apply_preserves_bank_fact_and_recovery_versions() -> None:
    repository = _MatchingRepository()
    workflow = ClientOverRefundRecoveryMatchingWorkflow(repository, _UnitOfWork)
    selection = ClientOverRefundRecoveryMatchingSelection(
        "115000001", "client-over-refund-recovery:1", "1"
    )
    preview = workflow.preview(selection, CorrelationId("client-matching-preview"))

    receipt = workflow.apply(ClientOverRefundRecoveryMatchingApplyRequest(
        selection, ExpectedVersion(1), ExpectedVersion(4), preview.fingerprint,
        IdempotencyKey("client-matching-key"), ActorContext("admin:1"),
        "bank remittance proof reviewed", CorrelationId("client-matching-apply"),
    ))

    assert receipt.finance_import_row_identity == "1"
    assert receipt.recovery_version == 1
    assert repository.persisted is not None


def test_matching_schema_keeps_bank_row_single_use() -> None:
    from pathlib import Path

    schema = Path("db/schema_parts/172_client_over_refund_recovery_matching.sql").read_text(encoding="utf-8")
    assert "UNIQUE KEY uq_client_recovery_matching_bank_row" in schema
    assert "client_over_refund_recovery_matched" in schema


def _recovery(amount: int) -> ClientOverRefundRecovery:
    return ClientOverRefundRecovery(
        "client-over-refund-recovery:1",
        "115000001",
        MoneyNTD(amount),
        ClientOverRefundRecoveryStatus.OPEN,
        1,
    )


def _incoming(amount: int) -> ClientRecoveryIncomingBankFact:
    return ClientRecoveryIncomingBankFact(
        "row:1",
        "115000001",
        MoneyNTD(amount),
        "2026-08-11",
        True,
    )


class _PreviewRepository:
    def load(self, selection, *, for_update):
        assert selection.finance_import_row_identity == "row:1"
        assert not for_update
        return ClientOverRefundRecoveryFacts(_recovery(250), _incoming(250), 4)


class _NeverUsedUnitOfWork:
    def __enter__(self):
        raise AssertionError("preview must not start a transaction")


class _AdjustmentRepository:
    def __init__(self) -> None:
        self.persisted = None

    def load(self, selection, *, for_update):
        assert selection.action is ClientOverRefundRecoveryAction.ADJUST
        return ClientOverRefundRecoveryFacts(_recovery(250), None, 4, True)

    def find_receipt(self, key):
        return None

    def persist(self, request, preview, receipt, command_fingerprint):
        self.persisted = (request, preview, receipt, command_fingerprint)


class _UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        return None


class _MatchingRepository:
    def __init__(self) -> None:
        self.persisted = None

    def load_matching(self, selection, *, for_update):
        assert selection.finance_import_row_identity == "1"
        return ClientOverRefundRecoveryMatchingFacts(1, 4, True)

    def find_matching_receipt(self, key):
        return None

    def persist_matching(self, request, preview, receipt, command_fingerprint):
        self.persisted = (request, preview, receipt, command_fingerprint)

import pytest
from datetime import date

from domains.government_subsidy.anomaly_remediation import (
    GovernmentSubsidyClaimDriftOwnerFact,
    GovernmentSubsidyClaimDriftRepairPath,
    GovernmentSubsidyIncomingRecoveryFact,
    GovernmentSubsidyIntegrityOwnerFact,
    GovernmentSubsidyIntegrityRepairPath,
    GovernmentSubsidyRecoveryRoot,
    GovernmentSubsidyRecoveryStatus,
    GovernmentSubsidyOutgoingReturnFact,
    GovernmentSubsidyReturnObligationFact,
    build_return_reconciliation_with_excess_candidate,
    build_recovery_reconciliation_candidate,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import IdempotencyKey
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion
from shared_kernel.money import MoneyNTD
from infrastructure.mysql.government_subsidy_anomaly_owner_repository import (
    GovernmentSubsidyOwnerSourceUnavailable,
    GovernmentSubsidyRecoveryAtomicCreationRequired,
    MySqlGovernmentSubsidyAnomalyRecoveryRepository,
)
from subsystems.government_subsidy.anomaly_recovery_workflow import (
    ApplyGovernmentSubsidyReturnReconciliationWithExcess,
    ClaimDriftCorrectionApplyRequest,
    ConfirmGovernmentSubsidyReturnReconciliationWithExcess,
    GovernmentSubsidyAnomalyRecoveryApplication,
    GovernmentSubsidyReturnReconciliationWithExcessReceipt,
    IntegrityRepairApplyRequest,
    RecoveryCreateApplyRequest,
    RecoveryReconcileApplyRequest,
    return_reconciliation_with_excess_command_fingerprint,
)
from subsystems.government_subsidy.anomaly_owner_readback import (
    GovernmentSubsidyAnomalyOwnerReadback,
)


def test_integrity_requires_fresh_projection_consistency_and_rejects_generic_repair() -> None:
    drift = GovernmentSubsidyIntegrityOwnerFact(
        7, 3, "snapshot-7", True, True, False,
        GovernmentSubsidyIntegrityRepairPath.DERIVED_REBUILD,
    )
    assert drift.predicate_active is True
    assert drift.unresolved_reason_codes == ("projection_inconsistent",)

    blocked = GovernmentSubsidyIntegrityOwnerFact(
        7, 3, "snapshot-7", True, True, False,
        GovernmentSubsidyIntegrityRepairPath.STRUCTURAL_AMBIGUITY,
    )
    assert blocked.predicate_active is True
    assert "structural_ambiguity" in blocked.unresolved_reason_codes


def test_submitted_claim_drift_needs_append_only_correction_lineage() -> None:
    fact = GovernmentSubsidyClaimDriftOwnerFact(
        claim_item_id=9,
        batch_id=7,
        owner_version=4,
        owner_snapshot_token="snapshot-9",
        authoritative_complete=True,
        drift_detected=True,
        submitted=True,
        frozen_claim_immutable=True,
        fresh_schedule_matches=False,
        correction_lineage_complete=False,
        financial_invariants_valid=True,
        repair_path=GovernmentSubsidyClaimDriftRepairPath.SUBMITTED_CORRECTION,
        scheduling_snapshot_identity="scheduling-assignment:17",
        scheduling_snapshot_token="schedule-token-17",
        scheduling_snapshot_version=5,
    )
    assert fact.predicate_active is True
    assert "correction_lineage_incomplete" in fact.unresolved_reason_codes
    assert "frozen_claim_mutated" not in fact.unresolved_reason_codes


def test_government_recovery_root_only_reconciles_with_typed_incoming_fact() -> None:
    root = GovernmentSubsidyRecoveryRoot(
        recovery_identity="recovery-1",
        source_outgoing_bank_fact_identity="outgoing-17",
        original_return_obligation_identity="return-1",
        lawful_amount_ntd=MoneyNTD(500),
        actual_amount_ntd=MoneyNTD(750),
        government_payer_identity="hccg",
        version=0,
        status=GovernmentSubsidyRecoveryStatus.OPEN,
        actor="admin:1",
        reason="duplicate outbound payment",
        evidence_reference="evidence-1",
        idempotency_key=IdempotencyKey("recovery-1-create"),
        receipt_reference="receipt-1",
    )
    candidate = build_recovery_reconciliation_candidate(
        root,
        GovernmentSubsidyIncomingRecoveryFact("incoming-18", MoneyNTD(250), "hccg"),
    )
    assert candidate.remaining_after_ntd == MoneyNTD(0)
    assert candidate.resulting_status is GovernmentSubsidyRecoveryStatus.RECONCILED

    with pytest.raises(ValueError, match="payer_mismatch"):
        build_recovery_reconciliation_candidate(
            root,
            GovernmentSubsidyIncomingRecoveryFact("incoming-19", MoneyNTD(250), "other-payer"),
        )


def test_return_excess_candidate_is_only_available_when_actual_exceeds_lawful() -> None:
    obligation, outgoing = _return_excess_context()
    candidate = build_return_reconciliation_with_excess_candidate(obligation, outgoing)
    assert candidate.lawful_amount_ntd == MoneyNTD(500)
    assert candidate.actual_amount_ntd == MoneyNTD(750)
    assert candidate.excess_amount_ntd == MoneyNTD(250)
    assert candidate.recovery_identity == "government-subsidy-recovery:outgoing-excess-1"

    with pytest.raises(ValueError, match="operation_not_applicable"):
        build_return_reconciliation_with_excess_candidate(
            obligation,
            GovernmentSubsidyOutgoingReturnFact(
                18,
                "outgoing-normal-1",
                "outgoing",
                date(2026, 8, 31),
                MoneyNTD(500),
                "hccg",
                obligation.recipient_snapshot_token,
            ),
        )


class _Repository:
    def read_integrity(self, batch_id):
        return GovernmentSubsidyIntegrityOwnerFact(
            batch_id, 1, "snapshot", True, True, True,
            GovernmentSubsidyIntegrityRepairPath.DERIVED_REBUILD,
        )

    def read_claim_drift(self, claim_item_id):
        return GovernmentSubsidyClaimDriftOwnerFact(
            claim_item_id, 7, 1, "snapshot", True, False, False, True, True, True, True,
            GovernmentSubsidyClaimDriftRepairPath.DRAFT_REVISION,
            "scheduling-assignment:17", "schedule-token-17", 5, True,
        )

    def read_return_overage(self, payable_identity):
        return None


def test_readback_is_closed_to_the_three_owner_issue_codes() -> None:
    readback = GovernmentSubsidyAnomalyOwnerReadback(_Repository())
    assert readback.read("GOVSUB-003", "7").predicate_active is False
    assert readback.read("GOVSUB-005", "11:7:9").claim_item_id == 9
    with pytest.raises(ValueError, match="not_supported"):
        readback.read("GOVSUB-006", "over-1")


def test_application_uses_fresh_owner_lock_and_single_commit_for_integrity_repair() -> None:
    repository = _ApplicationRepository()
    application = GovernmentSubsidyAnomalyRecoveryApplication(repository, _uow)
    preview = application.preview_integrity(7)
    receipt = application.apply_integrity(
        IntegrityRepairApplyRequest(
            7,
            ExpectedVersion(preview.expected_version),
            preview.repair_path,
            preview.fingerprint,
            IdempotencyKey("integrity-apply-1"),
            ActorContext("admin:1"),
            "rebuild derived projection",
            CorrelationId("correlation-1"),
        )
    )
    assert receipt == "integrity-receipt-1"
    assert repository.integrity_locks == [False, True]
    assert _Uow.commits == 1


def test_structural_integrity_ambiguity_cannot_enter_preview() -> None:
    repository = _ApplicationRepository(structural=True)
    application = GovernmentSubsidyAnomalyRecoveryApplication(repository, _uow)
    with pytest.raises(ValueError, match="not_eligible"):
        application.preview_integrity(7)


def test_consistent_integrity_projection_cannot_create_a_rebuild_event() -> None:
    repository = _ApplicationRepository()
    repository.projection_consistent = True
    application = GovernmentSubsidyAnomalyRecoveryApplication(repository, _uow)
    with pytest.raises(ValueError, match="not_eligible"):
        application.preview_integrity(7)


def test_integrity_apply_contract_only_allows_derived_rebuild() -> None:
    with pytest.raises(ValueError, match="generic_repair_forbidden"):
        IntegrityRepairApplyRequest(
            7,
            ExpectedVersion(2),
            GovernmentSubsidyIntegrityRepairPath.TYPED_APPEND_ONLY,
            build_recovery_reconciliation_candidate(
                _ApplicationRepository().recovery,
                GovernmentSubsidyIncomingRecoveryFact(
                    "incoming-unused", MoneyNTD(100), "hccg"
                ),
            ).fingerprint,
            IdempotencyKey("typed-integrity-forbidden"),
            ActorContext("admin:1"),
            "must use the existing typed correction owner",
            CorrelationId("correlation-integrity-forbidden"),
        )


def test_recovery_application_reconciles_only_typed_incoming_fact() -> None:
    repository = _ApplicationRepository()
    application = GovernmentSubsidyAnomalyRecoveryApplication(repository, _uow)
    root = repository.recovery
    candidate = build_recovery_reconciliation_candidate(
        root, GovernmentSubsidyIncomingRecoveryFact("incoming-1", MoneyNTD(100), "hccg")
    )
    receipt = application.apply_recovery_reconciliation(
        RecoveryReconcileApplyRequest(
            root.recovery_identity,
            GovernmentSubsidyIncomingRecoveryFact("incoming-1", MoneyNTD(100), "hccg"),
            ExpectedVersion(root.version),
            candidate.fingerprint,
            IdempotencyKey("reconcile-1"),
            ActorContext("admin:1"),
            "reconcile canonical incoming fact",
            CorrelationId("correlation-2"),
        )
    )
    assert receipt == "reconcile-receipt-1"
    assert _Uow.commits == 1


def test_return_excess_application_commits_lawful_allocation_and_recovery_once() -> None:
    repository = _ApplicationRepository()
    rechecks = _Rechecks()
    application = GovernmentSubsidyAnomalyRecoveryApplication(
        repository,
        _uow,
        rechecks,
    )
    preview = application.preview_return_reconciliation_with_excess("return-1", 17)
    candidate = preview.candidate
    request = ApplyGovernmentSubsidyReturnReconciliationWithExcess(
        candidate.overpayment_identity,
        candidate.payable_identity,
        candidate.finance_import_row_id,
        ExpectedVersion(candidate.expected_overpayment_version),
        ExpectedVersion(candidate.expected_payable_version),
        ConfirmGovernmentSubsidyReturnReconciliationWithExcess(
            candidate.fingerprint,
            True,
        ),
        IdempotencyKey("return-excess-1"),
        ActorContext("admin:1"),
        "confirm canonical outgoing excess",
        "bank-evidence-17",
        CorrelationId("return-excess-correlation-1"),
    )
    result = application.apply_return_reconciliation_with_excess(request)

    assert result.receipt.lawful_amount_ntd == 500
    assert result.receipt.excess_amount_ntd == 250
    assert result.readback.recovery_identity == candidate.recovery_identity
    assert repository.return_excess_locks == [False, True]
    assert repository.return_excess_applies == 1
    assert _Uow.commits == 1
    assert rechecks.requests[0].definition_code.value == "GOVSUB-007"
    assert rechecks.requests[0].subject_ids == ("return-1",)

    replay = application.apply_return_reconciliation_with_excess(request)
    assert replay.receipt == result.receipt
    assert replay.readback == result.readback
    assert repository.return_excess_applies == 1
    assert repository.return_excess_locks == [False, True]
    assert _Uow.commits == 0


def test_claim_correction_binds_exact_fresh_scheduling_snapshot() -> None:
    repository = _ApplicationRepository()
    application = GovernmentSubsidyAnomalyRecoveryApplication(repository, _uow)
    preview = application.preview_claim_drift(9)
    receipt = application.apply_claim_drift(
        ClaimDriftCorrectionApplyRequest(
            claim_item_id=9,
            expected_version=ExpectedVersion(preview.expected_version),
            repair_path=preview.repair_path,
            scheduling_snapshot_identity=preview.scheduling_snapshot_identity,
            scheduling_snapshot_token=preview.scheduling_snapshot_token,
            scheduling_snapshot_version=preview.scheduling_snapshot_version,
            successor_revision_identity="claim-revision:9:2",
            financial_consequence_reference="financial-disposition:no-change:9:2",
            preview_fingerprint=preview.fingerprint,
            idempotency_key=IdempotencyKey("claim-correction-1"),
            actor=ActorContext("admin:1"),
            reason="accept fresh Scheduling facts",
            correlation_id=CorrelationId("claim-correction-correlation"),
        )
    )
    assert receipt == "claim-correction-receipt-1"
    assert repository.claim_locks == [False, True]


def test_mysql_adapter_fails_closed_when_owner_source_is_missing() -> None:
    adapter = MySqlGovernmentSubsidyAnomalyRecoveryRepository(_Connection([None]))
    with pytest.raises(GovernmentSubsidyOwnerSourceUnavailable, match="unavailable"):
        adapter.read_integrity(7)


def test_mysql_receipt_requires_exact_command_fingerprint() -> None:
    expected = build_recovery_reconciliation_candidate(
        _ApplicationRepository().recovery,
        GovernmentSubsidyIncomingRecoveryFact("incoming-1", MoneyNTD(100), "hccg"),
    ).fingerprint
    adapter = MySqlGovernmentSubsidyAnomalyRecoveryRepository(
        _Connection([
            {
                "command_fingerprint": "0" * 64,
                "result_snapshot": '{"receipt_reference":"receipt-1"}',
            }
        ])
    )
    with pytest.raises(ValueError, match="idempotency_conflict"):
        adapter.find_receipt(IdempotencyKey("same-key"), expected)


def test_mysql_recovery_create_fails_closed_until_atomic_owner_uow_exists() -> None:
    root = _ApplicationRepository().recovery
    connection = _Connection([])
    repository = MySqlGovernmentSubsidyAnomalyRecoveryRepository(connection)
    with pytest.raises(
        GovernmentSubsidyRecoveryAtomicCreationRequired,
        match="atomic_excess_uow_required",
    ):
        repository.create_recovery_root(
            RecoveryCreateApplyRequest(
                root,
                CorrelationId("recovery-create-correlation"),
            )
        )
    assert connection.executed == []


def test_mysql_existing_recovery_reconcile_validates_bank_and_appends_event() -> None:
    root = _ApplicationRepository().recovery
    incoming = GovernmentSubsidyIncomingRecoveryFact(
        "incoming-recovery-1",
        MoneyNTD(100),
        "hccg",
    )
    candidate = build_recovery_reconciliation_candidate(root, incoming)
    request = RecoveryReconcileApplyRequest(
        recovery_identity=root.recovery_identity,
        incoming=incoming,
        expected_version=ExpectedVersion(root.version),
        preview_fingerprint=candidate.fingerprint,
        idempotency_key=IdempotencyKey("reconcile-existing-1"),
        actor=ActorContext("admin:1"),
        reason="reconcile canonical incoming bank fact",
        correlation_id=CorrelationId("reconcile-existing-correlation"),
    )
    connection = _Connection(
        [
            {
                "direction": "incoming",
                "amount_ntd": 100,
                "classification_type": "government_subsidy",
            }
        ]
    )
    repository = MySqlGovernmentSubsidyAnomalyRecoveryRepository(connection)
    receipt = repository.persist_recovery_reconciliation(request, candidate)
    assert receipt == "government-subsidy-recovery-reconcile:reconcile-existing-1"
    assert any("UPDATE government_subsidy_recoveries" in sql for sql, _ in connection.executed)
    assert any("INSERT INTO government_subsidy_recovery_events" in sql for sql, _ in connection.executed)
    assert any("government_subsidy_anomaly_apply_receipts" in sql for sql, _ in connection.executed)


def test_mysql_return_excess_uses_exact_bank_lineage_and_one_owner_write_set() -> None:
    obligation, outgoing = _return_excess_context()
    token = obligation.recipient_snapshot_token
    context_connection = _Connection(
        [
            {
                "overpayment_identity": "overpayment-1",
                "payer_identity": "hccg",
                "overpayment_remaining_ntd": 500,
                "overpayment_status": "return_payable",
                "overpayment_version": 4,
                "payable_identity": "return-1",
                "lawful_remaining_ntd": 500,
                "payable_status": "payable",
                "payable_version": 2,
                "agency_identity": "hccg",
                "recipient_snapshot_token": token,
            },
            {
                "finance_import_row_id": 17,
                "bank_fact_identity": "outgoing-excess-1",
                "direction": "outgoing",
                "debit": 750,
                "credit": 0,
                "transaction_date": date(2026, 8, 31),
                "classification_type": "government_subsidy",
                "resolved_counterparty_account": "1234567890",
                "existing_payout_id": None,
                "existing_recovery_identity": None,
            },
            [
                {
                    "bank_code": "812",
                    "account_number": "1234567890",
                    "account_name": "新竹市政府",
                    "effective_from": date(2026, 1, 1),
                }
            ],
        ]
    )
    repository = MySqlGovernmentSubsidyAnomalyRecoveryRepository(context_connection)
    loaded_obligation, loaded_outgoing = repository.load_return_reconciliation_with_excess_context(
        "return-1",
        17,
        for_update=True,
    )
    candidate = build_return_reconciliation_with_excess_candidate(
        loaded_obligation,
        loaded_outgoing,
    )
    request = ApplyGovernmentSubsidyReturnReconciliationWithExcess(
        "overpayment-1",
        "return-1",
        17,
        ExpectedVersion(4),
        ExpectedVersion(2),
        ConfirmGovernmentSubsidyReturnReconciliationWithExcess(
            candidate.fingerprint,
            True,
        ),
        IdempotencyKey("return-excess-mysql-1"),
        ActorContext("admin:1"),
        "confirmed outgoing excess",
        "bank-evidence-17",
        CorrelationId("return-excess-mysql-correlation"),
    )
    write_connection = _Connection(
        [{"batch_id": 7, "transaction_id": 8, "projection_event_id": 9}]
    )
    write_repository = MySqlGovernmentSubsidyAnomalyRecoveryRepository(
        write_connection
    )
    receipt = write_repository.apply_return_reconciliation_with_excess(
        request,
        candidate,
        return_reconciliation_with_excess_command_fingerprint(request),
    )

    assert receipt.excess_amount_ntd == 250
    statements = [sql for sql, _ in write_connection.executed]
    assert any("UPDATE government_overpayment_return_payables" in sql for sql in statements)
    assert any("UPDATE government_subsidy_overpayments" in sql for sql in statements)
    assert any("INSERT INTO government_overpayment_return_payouts" in sql for sql in statements)
    assert any("INSERT INTO government_subsidy_recoveries" in sql for sql in statements)
    assert any("INSERT INTO government_subsidy_outbox" in sql for sql in statements)
    assert any("government_subsidy_anomaly_apply_receipts" in sql for sql in statements)
    assert not any("UPDATE finance_import_rows" in sql for sql in statements)


class _Uow:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        _Uow.commits += 1

    commits = 0


def _uow():
    _Uow.commits = 0
    return _Uow()


class _ApplicationRepository(_Repository):
    def __init__(self, structural=False):
        self.structural = structural
        self.projection_consistent = False
        self.integrity_locks = []
        self.claim_locks = []
        self.return_excess_locks = []
        self.return_excess_applies = 0
        self.return_excess_receipt = None
        self.commits = 0
        self.recovery = GovernmentSubsidyRecoveryRoot(
            "recovery-1", "outgoing-1", "return-1", MoneyNTD(500), MoneyNTD(600),
            "hccg", 0, GovernmentSubsidyRecoveryStatus.OPEN, "admin:1", "overage",
            "evidence-1", IdempotencyKey("create-1"), "receipt-1",
        )

    def load_integrity(self, batch_id, *, for_update):
        self.integrity_locks.append(for_update)
        return GovernmentSubsidyIntegrityOwnerFact(
            batch_id, 2, "snapshot-7", True, not self.structural,
            self.projection_consistent,
            GovernmentSubsidyIntegrityRepairPath.STRUCTURAL_AMBIGUITY if self.structural else GovernmentSubsidyIntegrityRepairPath.DERIVED_REBUILD,
        )

    def persist_integrity_repair(self, request, fact):
        return "integrity-receipt-1"

    def load_claim_drift(self, claim_item_id, *, for_update):
        self.claim_locks.append(for_update)
        return GovernmentSubsidyClaimDriftOwnerFact(
            claim_item_id=claim_item_id,
            batch_id=7,
            owner_version=5,
            owner_snapshot_token="claim-owner-token",
            authoritative_complete=True,
            drift_detected=True,
            submitted=True,
            frozen_claim_immutable=True,
            fresh_schedule_matches=False,
            correction_lineage_complete=False,
            financial_invariants_valid=True,
            repair_path=GovernmentSubsidyClaimDriftRepairPath.SUBMITTED_CORRECTION,
            scheduling_snapshot_identity="scheduling-assignment:17",
            scheduling_snapshot_token="schedule-token-17",
            scheduling_snapshot_version=5,
        )

    def persist_claim_drift_correction(self, request, fact):
        return "claim-correction-receipt-1"

    def load_recovery(self, recovery_identity, *, for_update):
        return self.recovery

    def persist_recovery_reconciliation(self, request, candidate):
        return "reconcile-receipt-1"

    def load_return_reconciliation_with_excess_context(
        self, payable_identity, finance_import_row_id, *, for_update
    ):
        assert payable_identity == "return-1"
        assert finance_import_row_id == 17
        self.return_excess_locks.append(for_update)
        return _return_excess_context()

    def find_return_reconciliation_with_excess_receipt(self, key, command_fingerprint):
        return self.return_excess_receipt

    def apply_return_reconciliation_with_excess(
        self, request, candidate, command_fingerprint
    ):
        self.return_excess_applies += 1
        self.recovery = GovernmentSubsidyRecoveryRoot(
            candidate.recovery_identity,
            candidate.bank_fact_identity,
            candidate.payable_identity,
            candidate.lawful_amount_ntd,
            candidate.actual_amount_ntd,
            candidate.government_payer_identity,
            0,
            GovernmentSubsidyRecoveryStatus.OPEN,
            request.actor.actor_id,
            request.reason,
            request.evidence_reference,
            request.idempotency_key,
            "government-subsidy-return-excess:return-excess-1",
        )
        self.return_excess_receipt = GovernmentSubsidyReturnReconciliationWithExcessReceipt(
            "government-subsidy-return-excess:return-excess-1",
            candidate.recovery_identity,
            candidate.overpayment_identity,
            candidate.payable_identity,
            candidate.bank_fact_identity,
            candidate.lawful_amount_ntd.amount,
            candidate.actual_amount_ntd.amount,
            candidate.excess_amount_ntd.amount,
            candidate.expected_overpayment_version + 1,
            candidate.expected_payable_version + 1,
        )
        return self.return_excess_receipt

    def find_receipt(self, key, command_fingerprint):
        return None


class _Rechecks:
    def __init__(self):
        self.requests = []

    def append_government_subsidy_recheck(self, request):
        self.requests.append(request)


def _return_excess_context():
    token = fingerprint_payload(
        {
            "payer_identity": "hccg",
            "bank_code": "812",
            "account_number": "1234567890",
            "account_name": "新竹市政府",
            "effective_date": "2026-01-01",
        }
    ).value
    return (
        GovernmentSubsidyReturnObligationFact(
            "overpayment-1",
            "return-1",
            4,
            2,
            MoneyNTD(500),
            MoneyNTD(500),
            "hccg",
            token,
            "return_payable",
            "payable",
        ),
        GovernmentSubsidyOutgoingReturnFact(
            17,
            "outgoing-excess-1",
            "outgoing",
            date(2026, 8, 31),
            MoneyNTD(750),
            "hccg",
            token,
        ),
    )


class _Connection:
    def __init__(self, responses):
        self.responses = list(responses)
        self.executed = []

    def cursor(self):
        return _Cursor(self)


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.lastrowid = 1
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, parameters=()):
        self.connection.executed.append((sql, parameters))

    def fetchone(self):
        return self.connection.responses.pop(0)

    def fetchall(self):
        result = self.connection.responses.pop(0)
        return [] if result is None else result

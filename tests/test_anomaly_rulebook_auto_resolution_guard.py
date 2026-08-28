"""
File: test_anomaly_rulebook_auto_resolution_guard.py
Description: 驗證異常自動解除必須具備 owner 規則書契約與終態根事實。
"""

from dataclasses import dataclass
from datetime import date

from domains.anomalies.registry import (
    AlertWorkflowStatus,
    DesiredAlertState,
    default_anomaly_registry,
    reduce_current_alert,
    resolve_alert_workflow,
)
from subsystems.anomalies.alert_workflow import AnomalyApplication, ProjectAlertRequest
from subsystems.anomalies.root_fact_projection_workflow import (
    _rulebook_guarded_candidate,
)
from subsystems.anomalies.staff_payables_anomaly_source import _overdue_request


_RULEBOOK_BLOCKED_CODES = (
    "BECLASS-001",
    "DOC-SEND-001",
    "GOVSUB-001",
    "GOVSUB-002",
    "GOVSUB-004",
    "GOVSUB-005",
    "GOVSUB-007",
    "HISTORICAL-ORDER-001",
    "IMPORT-001",
    "IMPORT-003",
    "IMPORT-006",
    "LINE-002",
    "LINE-004",
    "LINE-001",
    "LINE-005",
    "LINE-006",
    "ORDER-001",
    "ORDER-002",
    "ORDER-003",
    "ORDER-004",
    "PAYOUT-002",
    "PAYOUT-003",
    "SCHEDULE-001",
    "SCHEDULE-002",
    "SCHEDULE-003",
    "SCHEDULE-005",
    "SCHEDULE-006",
    "SUBSIDYADVANCE-001",
    "client_refund_underpayment",
    "finance_import_manual_review",
    "staff_payout_overpayment",
    "staff_payout_underpayment",
)

_RULEBOOK_ALLOWED_PREDICATES = {
    "CLIENTPAYABLE-001": "client_payable_overdue_remaining_zero_after_locked_owner_readback",
    "CLIENTREFUND-001": "client_refund_return_linkage_and_progress_terminal",
    "GOVSUB-003": "government_subsidy_current_revision_integrity_clear",
    "GOVSUB-006": "government_overpayment_authorized_disposition_committed",
    "IMPORT-004": "hcm_review_all_occurrences_owner_terminal_after_locked_readback",
    "PAYOUT-001": "staff_payable_balance_zero_after_locked_owner_readback",
    "RECEIVABLE-001": "client_receivable_overdue_remaining_zero_after_locked_owner_readback",
    "RETURN-001": "client_subsidy_return_overdue_remaining_zero_after_locked_owner_readback",
    "client_over_refund_recovery_open": "client_over_refund_recovery_remaining_zero",
    "staff_overpayment_recovery_open": "staff_overpayment_recovery_remaining_zero",
}


def test_rulebook_allowlist_has_exact_versioned_terminal_predicates() -> None:
    registry = default_anomaly_registry()
    actual = {}
    for code in registry.codes():
        contract = registry.auto_resolution_contract(code)
        if contract is not None:
            assert contract.contract_version == 1
            assert contract.owner_rulebook_reference
            actual[code] = contract.terminal_predicate

    assert actual == _RULEBOOK_ALLOWED_PREDICATES


def test_codes_without_completed_owner_rulebook_contract_cannot_auto_resolve() -> None:
    registry = default_anomaly_registry()

    for code in _RULEBOOK_BLOCKED_CODES:
        assert registry.auto_resolution_contract(code) is None
        active = _desired(registry, code, active=True, source_version=1)
        current = reduce_current_alert(registry, active, None)
        assert current is not None

        resulting = reduce_current_alert(
            registry,
            _desired(registry, code, active=False, source_version=2),
            current,
        )

        assert resulting is not None
        assert resulting.predicate_active is True
        assert resulting.workflow_status is AlertWorkflowStatus.OPEN


def test_tracking_resolution_reopens_while_owner_root_remains_active() -> None:
    registry = default_anomaly_registry()
    current = reduce_current_alert(
        registry,
        _desired(registry, "ORDER-001", active=True, source_version=1),
        None,
    )
    assert current is not None
    tracked_as_resolved = resolve_alert_workflow(
        current,
        current.workflow_version,
        "legacy tracking only",
    )

    resulting = reduce_current_alert(
        registry,
        _desired(registry, "ORDER-001", active=False, source_version=2),
        tracked_as_resolved,
    )

    assert resulting is not None
    assert resulting.predicate_active is True
    assert resulting.workflow_status is AlertWorkflowStatus.OPEN


def test_blocked_inactive_scan_preserves_last_actionable_display_snapshot() -> None:
    registry = default_anomaly_registry()
    current = reduce_current_alert(
        registry,
        _desired(registry, "ORDER-001", active=True, source_version=1),
        None,
    )
    assert current is not None
    repository = _ProjectionRepository(current, {"problem": "original detail"})
    application = AnomalyApplication(registry, repository, _UnitOfWork)

    resulting = application.project(
        ProjectAlertRequest(
            _desired(registry, "ORDER-001", active=False, source_version=2),
            "event-2",
            "consumer-1",
            "partition-1",
            {"problem": "detector reported no problem"},
        )
    )

    assert resulting.predicate_active is True
    assert repository.saved_display_snapshot == {"problem": "original detail"}


def test_blocked_finance_scan_records_rulebook_guard_as_active_snapshot() -> None:
    registry = default_anomaly_registry()
    current = reduce_current_alert(
        registry,
        _desired(
            registry,
            "finance_import_manual_review",
            active=True,
            source_version=1,
        ),
        None,
    )
    candidate = _Candidate(
        _desired(
            registry,
            "finance_import_manual_review",
            active=False,
            source_version=2,
        ),
        {"root_condition_active": False, "reason_codes": []},
    )

    guarded = _rulebook_guarded_candidate(registry, current, candidate)

    assert guarded.root_fact_snapshot["root_condition_active"] is True
    assert guarded.root_fact_snapshot["reason_codes"] == [
        "auto_resolution_rulebook_contract_missing"
    ]


def test_completed_owner_rulebook_contract_allows_terminal_root_to_resolve() -> None:
    registry = default_anomaly_registry()
    contract = registry.auto_resolution_contract("GOVSUB-003")
    assert contract is not None
    assert contract.owner_rulebook_reference
    assert contract.terminal_predicate == "government_subsidy_current_revision_integrity_clear"
    current = reduce_current_alert(
        registry,
        _desired(registry, "GOVSUB-003", active=True, source_version=1),
        None,
    )
    assert current is not None

    resulting = reduce_current_alert(
        registry,
        _desired(registry, "GOVSUB-003", active=False, source_version=2),
        current,
    )

    assert resulting is not None
    assert resulting.predicate_active is False
    assert resulting.workflow_status is AlertWorkflowStatus.RESOLVED


def test_positive_staff_payable_balance_cannot_be_hidden_by_terminal_status() -> None:
    request = _overdue_request(
        {
            "obligation_identity": "staff-obligation:test",
            "staff_id": 7,
            "amount_due_ntd": 0,
            "balance_ntd": 1200,
            "due_date": date(2026, 8, 1),
            "obligation_status": "settled",
            "projection_status": "completed",
            "root_version": 3,
        },
        date(2026, 8, 8),
    )

    assert request.desired.active is True


def _desired(registry, code: str, *, active: bool, source_version: int):
    definition = registry.require(code)
    return DesiredAlertState(
        definition_code=code,
        source_identity=f"test-source:{code}",
        source_version=source_version,
        active=active,
        fingerprint_values={field: f"test-{field}" for field in definition.fingerprint_fields},
    )


@dataclass(frozen=True)
class _Candidate:
    desired: DesiredAlertState
    root_fact_snapshot: dict[str, object]


class _ProjectionRepository:
    def __init__(self, current, display_snapshot) -> None:
        self.current = current
        self.display_snapshot = display_snapshot
        self.saved_display_snapshot = None

    def load_current(self, _fingerprint, *, for_update):
        assert for_update is True
        return self.current, self.display_snapshot

    def checkpoint_matches(self, _request):
        return False

    def save_projection(
        self,
        _definition,
        _previous,
        _resulting,
        display_snapshot,
    ):
        self.saved_display_snapshot = display_snapshot

    def append_projector_event(self, _previous, _resulting, _request):
        return None

    def save_checkpoint(self, _request):
        return None


class _UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        return None

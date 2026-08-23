"""
File: test_matching_coordination_initial_snapshot.py
Description: 驗證 M3 初始 criteria snapshot 的 owner projection 與交易邊界。
"""

from datetime import date, datetime, time, timezone

import pytest

from domains.orders.terms import (
    OrderAggregateFacts,
    OrderTerms,
    ServiceTimeTerms,
)
from domains.scheduling.matching_coordination import (
    SOURCE_KINDS,
    MatchingSourceVersion,
    canonical_source_tuple,
)
from shared_kernel.clock import FixedBusinessClock
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.orders.service_date_confirmation_workflow import (
    ServiceDateConfirmationFacts,
)
from subsystems.scheduling.matching_coordination_application import (
    InitialCriteriaSourceFacts,
    MatchingCoordinationApplication,
)
from subsystems.scheduling.matching_coordination_contracts import (
    ApplyInitialCriteriaSnapshot,
    PreviewInitialCriteriaSnapshot,
)


NOW = datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc)


def _initial_sources() -> tuple[MatchingSourceVersion, ...]:
    return canonical_source_tuple(
        (
            MatchingSourceVersion("orders_terms", "CASE-001", 3, "a" * 64),
            MatchingSourceVersion(
                "orders_service_dates", "CASE-001", 2, "b" * 64
            ),
            *(
                MatchingSourceVersion.not_consulted(kind)
                for kind in SOURCE_KINDS[2:]
            ),
        )
    )


def _initial_facts(*, confirmed: bool = True) -> InitialCriteriaSourceFacts:
    terms = OrderAggregateFacts(
        case_no="CASE-001",
        version=3,
        terms=OrderTerms(
            planned_start_date=date(2026, 9, 1),
            service_days=2,
            service_hours_per_day=8,
            floor_fee=MoneyNTD(1000),
            service_time=ServiceTimeTerms(time(8), time(16), 0),
            requires_cooking=True,
        ),
        service_data_locked=False,
        client_identity_status="confirmed",
    )
    dates = ServiceDateConfirmationFacts(
        case_no="CASE-001",
        order_version=3,
        scheduling_version=2,
        contracted_service_days=2,
        suggested_dates=(date(2026, 9, 1), date(2026, 9, 2)),
        selectable_dates=(date(2026, 9, 1), date(2026, 9, 2)),
        current_version=2 if confirmed else None,
        current_dates=(date(2026, 9, 1), date(2026, 9, 2)) if confirmed else (),
    )
    return InitialCriteriaSourceFacts("CASE-001", terms, dates, _initial_sources())


class _Reader:
    def __init__(self, facts: InitialCriteriaSourceFacts, operations: list[str]) -> None:
        self.facts = facts
        self.operations = operations

    def load_initial(self, case_no: str) -> InitialCriteriaSourceFacts:
        assert case_no == "CASE-001"
        self.operations.append("initial")
        return self.facts

    def load_initial_fresh(
        self, case_no: str, *, for_update: bool
    ) -> InitialCriteriaSourceFacts:
        assert case_no == "CASE-001"
        assert for_update is True
        self.operations.append("initial_fresh")
        return self.facts


class _Repository:
    def __init__(self, operations: list[str]) -> None:
        self.operations = operations
        self.receipts = []

    def claim_or_replay(self, key, fingerprint, correlation_id):
        self.operations.append("claim")
        return None

    def lock_matching_root(self, case_no: str) -> None:
        self.operations.append("lock")

    def append_lineage(self, command, facts, receipt) -> None:
        self.operations.append("lineage")

    def save_receipt(self, command, fingerprint, receipt) -> None:
        self.operations.append("receipt")
        self.receipts.append(receipt)

    def append_typed_intents(self, command, receipt) -> None:
        self.operations.append("intents")


class _Unit:
    def __init__(self, operations: list[str]) -> None:
        self.operations = operations

    def __enter__(self):
        self.operations.append("begin")
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def commit(self) -> None:
        self.operations.append("commit")


def _application(operations: list[str]) -> tuple[MatchingCoordinationApplication, _Repository]:
    repository = _Repository(operations)
    application = MatchingCoordinationApplication(
        _Reader(_initial_facts(), operations),
        repository,
        lambda: _Unit(operations),
        clock=FixedBusinessClock(NOW),
    )
    return application, repository


def _common() -> dict[str, object]:
    return {
        "case_no": "CASE-001",
        "actor": ActorContext("admin_user_id:1"),
        "reason": "initialize matching criteria",
        "correlation_id": CorrelationId("corr-initial-1"),
        "idempotency_key": IdempotencyKey("matching:CASE-001:initial:1"),
        "expected_source_versions": _initial_sources(),
    }


def test_initial_preview_projects_only_approved_owner_fields_and_is_zero_write() -> None:
    operations: list[str] = []
    application, repository = _application(operations)

    result = application.preview(PreviewInitialCriteriaSnapshot(**_common()))

    assert dict(result.criteria) == {
        "confirmed_service_dates": ("2026-09-01", "2026-09-02"),
        "planned_start_date": "2026-09-01",
        "requires_cooking": True,
        "service_days": 2,
        "service_hours_per_day": 8,
        "service_time": {
            "start_time": "08:00:00",
            "end_time": "16:00:00",
            "end_day_offset": 0,
        },
    }
    assert operations == ["initial"]
    assert repository.receipts == []


def test_initial_apply_fresh_reads_and_commits_snapshot_receipt_once() -> None:
    operations: list[str] = []
    application, repository = _application(operations)
    preview = application.preview(PreviewInitialCriteriaSnapshot(**_common()))
    operations.clear()

    receipt = application.apply(
        ApplyInitialCriteriaSnapshot(
            **_common(),
            preview_fingerprint=PreviewFingerprint(preview.fingerprint.value),
        )
    )

    assert receipt.result_state == "criteria_snapshotted"
    assert receipt.preview_fingerprint == preview.fingerprint
    assert receipt.package_id is None
    assert receipt.outbox_intent_ids == ()
    assert operations == [
        "begin",
        "claim",
        "lock",
        "initial_fresh",
        "lineage",
        "receipt",
        "intents",
        "commit",
    ]
    assert repository.receipts == [receipt]


def test_initial_facts_fail_closed_without_confirmed_service_dates() -> None:
    with pytest.raises(ValueError, match="confirmed service dates"):
        _initial_facts(confirmed=False)

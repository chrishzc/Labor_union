"""
File: test_matching_coordination_application.py
Description: 驗證 M3 application 的讀寫邊界、交易順序與 replay 安全性。
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from domains.scheduling.matching_coordination import (
    CandidateEligibility,
    MatchingCandidateResult,
    MatchingPackage,
    MatchingPackageMode,
    MatchingPackageState,
    MatchingSegment,
    MatchingSourceVersion,
    SOURCE_KINDS,
    build_criteria_diff,
    build_criteria_snapshot,
    build_willingness_lineage,
    build_zero_candidate_alternative,
)
from domains.scheduling.staff_availability import StaffAvailabilityFacts
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.scheduling.matching_coordination_application import (
    MatchingApplicationError,
    MatchingCoordinationApplication,
    ServiceDateRematchPreviewInput,
)
from subsystems.scheduling.matching_coordination_contracts import (
    ApplyCaregiverSelection,
    ApplyCriteriaDiffResend,
    ApplyCustomerMatchingDecision,
    ApplyServiceDateChangeRematch,
    ApplyZeroCandidateAlternative,
    MatchingApplyReceipt,
    MatchingCommandName,
    PreviewCriteriaDiffResend,
    PreviewMatchingPackage,
    PreviewServiceDateChangeRematch,
    PreviewZeroCandidateAlternative,
    QueryMatchingCoordination,
)
from subsystems.scheduling.matching_coordination_workflow import (
    MatchingCoordinationFacts,
    MatchingCoordinationWorkflow,
    MatchingCoordinationWorkflowError,
)


def _sources(seed: str = "c") -> tuple[MatchingSourceVersion, ...]:
    return tuple(MatchingSourceVersion(kind, f"{kind}:1", 1, seed * 64) for kind in SOURCE_KINDS)


def _facts(seed: str = "c", *, no_candidate: bool = False) -> MatchingCoordinationFacts:
    sources = _sources(seed)
    snapshot = build_criteria_snapshot(
        snapshot_id="snapshot-1",
        case_no="CASE-001",
        criteria_version=1,
        criteria={"service_days": 2},
        source_versions=sources,
        created_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
    )
    candidate = MatchingCandidateResult(
        "candidate-1", 7, CandidateEligibility.ELIGIBLE, (), willingness="willing"
    )
    package = MatchingPackage(
        package_id="package-1",
        version=1,
        mode=MatchingPackageMode.SINGLE,
        segments=(MatchingSegment(7, (date(2026, 9, 1), date(2026, 9, 2)), 1),),
        required_service_dates=(date(2026, 9, 1), date(2026, 9, 2)),
        candidate_results=() if no_candidate else (candidate,),
        criteria_snapshot_id=snapshot.snapshot_id,
        source_versions=sources,
        state=MatchingPackageState.NO_CANDIDATE if no_candidate else MatchingPackageState.PROPOSED,
    )
    return MatchingCoordinationFacts(
        snapshot=snapshot,
        package=package,
        candidates=() if no_candidate else (candidate,),
        source_versions=sources,
    )


def _common(facts: MatchingCoordinationFacts, key: str = "matching:case-001:1") -> dict[str, object]:
    return {
        "case_no": "CASE-001",
        "actor": ActorContext("admin_user_id:1"),
        "reason": "matching review",
        "correlation_id": CorrelationId("corr-matching-1"),
        "idempotency_key": IdempotencyKey(key),
        "expected_source_versions": facts.source_versions,
    }


class _Reader:
    def __init__(self, facts: MatchingCoordinationFacts, operations: list[str]) -> None:
        self.facts = facts
        self.operations = operations

    def load(self, case_no: str) -> MatchingCoordinationFacts:
        self.operations.append("load")
        assert case_no == self.facts.snapshot.case_no
        return self.facts

    def load_fresh(self, case_no: str, *, for_update: bool) -> MatchingCoordinationFacts:
        self.operations.append("fresh")
        assert for_update is True
        return self.facts


class _UnlockedReader:
    def __init__(self, facts: MatchingCoordinationFacts) -> None:
        self.facts = facts

    def load(self, case_no: str) -> MatchingCoordinationFacts:
        return self.facts


class _Repository:
    def __init__(self, operations: list[str]) -> None:
        self.operations = operations
        self.replay: MatchingApplyReceipt | None = None
        self.conflict = False
        self.saved: list[MatchingApplyReceipt] = []

    def claim_or_replay(self, key, command_fingerprint, correlation_id):
        self.operations.append("claim")
        if self.conflict:
            raise MatchingApplicationError(
                TypedError(
                    ErrorCategory.IDEMPOTENCY_MISMATCH,
                    "matching_idempotency_conflict",
                    "matching_idempotency_conflict",
                    correlation_id,
                )
            )
        return self.replay

    def lock_matching_root(self, case_no: str) -> None:
        self.operations.append("lock")

    def append_lineage(self, command, facts, receipt) -> None:
        self.operations.append("lineage")

    def append_typed_intents(self, command, receipt) -> None:
        self.operations.append("intents")

    def save_receipt(self, command, command_fingerprint, receipt) -> None:
        self.operations.append("receipt")
        self.saved.append(receipt)


class _Unit:
    def __init__(self, operations: list[str]) -> None:
        self.operations = operations
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        self.operations.append("begin")
        return self

    def __exit__(self, exception_type, exception, traceback):
        if exception_type is not None or self.commits == 0:
            self.rollbacks += 1
        return False

    def commit(self) -> None:
        self.commits += 1
        self.operations.append("commit")


class _RecordingWorkflow(MatchingCoordinationWorkflow):
    def __init__(self, operations: list[str]) -> None:
        super().__init__()
        self.operations = operations
        self.received_preview: PreviewFingerprint | None = None

    def apply(self, request, facts, *, preview_fingerprint, fresh_effects_match=True):
        self.operations.append("workflow")
        self.received_preview = preview_fingerprint
        return MatchingApplyReceipt(
            receipt_id=f"{request.idempotency_key.value}:receipt",
            command_name=request.command_name,
            command_fingerprint=fingerprint_payload({"command": request.idempotency_key.value}),
            preview_fingerprint=preview_fingerprint,
            source_versions=facts.source_versions,
            decision_event_id=None,
            package_id=facts.package.package_id if facts.package else None,
            outbox_intent_ids=(),
            result_state="recorded",
        )


class _ServiceDateInputLoader:
    def __init__(
        self,
        operations: list[str],
        inputs: ServiceDateRematchPreviewInput,
    ) -> None:
        self.operations = operations
        self.inputs = inputs

    def __call__(self, command, *, for_update: bool):
        self.operations.append(f"service-date:{for_update}")
        assert command.case_no == self.inputs.case_no
        return self.inputs


def _application(facts: MatchingCoordinationFacts, operations: list[str], workflow=None):
    repository = _Repository(operations)
    unit = _Unit(operations)
    application = MatchingCoordinationApplication(
        _Reader(facts, operations),
        repository,
        lambda: unit,
        workflow=workflow,
    )
    return application, repository, unit


def test_query_returns_full_typed_result_and_is_read_only() -> None:
    operations: list[str] = []
    facts = _facts()
    application, repository, unit = _application(facts, operations)
    result = application.query(
        QueryMatchingCoordination(
            case_no="CASE-001",
            actor=ActorContext("admin_user_id:1"),
            correlation_id=CorrelationId("corr-matching-query-1"),
            expected_source_versions=facts.source_versions,
        )
    )

    assert result.case_no == "CASE-001"
    assert result.snapshot.snapshot_id == "snapshot-1"
    assert result.package is not None
    assert result.candidates[0].candidate_id == "candidate-1"
    assert operations == ["load"]
    assert repository.saved == []
    assert unit.commits == 0


def test_preview_is_zero_write() -> None:
    operations: list[str] = []
    facts = _facts()
    application, repository, unit = _application(facts, operations)
    command = PreviewMatchingPackage(**_common(facts), criteria_snapshot_id="snapshot-1", required_service_dates=facts.package.required_service_dates)

    result = application.preview(command)

    assert result.package_id == "package-1"
    assert operations == ["load"]
    assert repository.saved == []
    assert unit.commits == 0


def test_apply_order_and_single_commit() -> None:
    operations: list[str] = []
    facts = _facts()
    workflow = _RecordingWorkflow(operations)
    application, repository, unit = _application(facts, operations, workflow)
    command = ApplyCustomerMatchingDecision(
        **_common(facts),
        criteria_snapshot_id="snapshot-1",
        package_id="package-1",
        package_version=1,
        candidate_id="candidate-1",
        decision="accepted",
        preview_fingerprint=facts.package.fingerprint,
    )

    application.apply(command)

    assert operations == ["begin", "claim", "lock", "fresh", "workflow", "lineage", "receipt", "intents", "commit"]
    assert unit.commits == 1
    assert unit.rollbacks == 0
    assert len(repository.saved) == 1


def test_service_date_apply_locks_shifted_owner_facts_and_commits_rematch() -> None:
    operations: list[str] = []
    facts = _facts()
    inputs = ServiceDateRematchPreviewInput(
        case_no="CASE-001",
        assignment_id=17,
        original_staff_id=7,
        original_service_dates=(date(2026, 9, 1),),
        shifted_service_dates=(date(2026, 9, 3),),
        availability=StaffAvailabilityFacts(7, 4, (), ()),
    )
    workflow = MatchingCoordinationWorkflow()
    preview = workflow.preview_service_date_shift(
        PreviewServiceDateChangeRematch(
            **_common(facts, "preview:service-date:1"),
            criteria_snapshot_id="snapshot-1",
            package_id="package-1",
            assignment_id=17,
            original_staff_id=7,
            original_service_dates=inputs.original_service_dates,
            shifted_service_dates=inputs.shifted_service_dates,
        ),
        facts,
        inputs.availability,
    )
    repository = _Repository(operations)
    unit = _Unit(operations)
    application = MatchingCoordinationApplication(
        _Reader(facts, operations),
        repository,
        lambda: unit,
        workflow=workflow,
        service_date_input_loader=_ServiceDateInputLoader(operations, inputs),
    )
    command = ApplyServiceDateChangeRematch(
        **_common(facts, "matching:service-date:1"),
        criteria_snapshot_id="snapshot-1",
        package_id="package-1",
        assignment_id=17,
        original_staff_id=7,
        original_service_dates=inputs.original_service_dates,
        shifted_service_dates=inputs.shifted_service_dates,
        preview_fingerprint=preview.source_fingerprint,
    )

    receipt = application.apply(command)

    assert receipt.result_state == "rematch_required"
    assert receipt.preview_fingerprint == preview.source_fingerprint
    assert operations == [
        "begin",
        "claim",
        "lock",
        "fresh",
        "service-date:True",
        "lineage",
        "receipt",
        "intents",
        "commit",
    ]
    assert unit.commits == 1
    assert unit.rollbacks == 0


def test_service_date_apply_rejects_stale_preview_and_rolls_back() -> None:
    operations: list[str] = []
    facts = _facts()
    inputs = ServiceDateRematchPreviewInput(
        case_no="CASE-001",
        assignment_id=17,
        original_staff_id=7,
        original_service_dates=(date(2026, 9, 1),),
        shifted_service_dates=(date(2026, 9, 3),),
        availability=StaffAvailabilityFacts(7, 4, (), ()),
    )
    repository = _Repository(operations)
    unit = _Unit(operations)
    application = MatchingCoordinationApplication(
        _Reader(facts, operations),
        repository,
        lambda: unit,
        service_date_input_loader=_ServiceDateInputLoader(operations, inputs),
    )
    command = ApplyServiceDateChangeRematch(
        **_common(facts, "matching:service-date:stale"),
        criteria_snapshot_id="snapshot-1",
        package_id="package-1",
        assignment_id=17,
        original_staff_id=7,
        original_service_dates=inputs.original_service_dates,
        shifted_service_dates=inputs.shifted_service_dates,
        preview_fingerprint=PreviewFingerprint("0" * 64),
    )

    with pytest.raises(MatchingCoordinationWorkflowError) as captured:
        application.apply(command)

    assert captured.value.error.code == "matching_invalid_replay_snapshot"
    assert operations == [
        "begin",
        "claim",
        "lock",
        "fresh",
        "service-date:True",
    ]
    assert repository.saved == []
    assert unit.commits == 0
    assert unit.rollbacks == 1


def test_apply_fails_closed_when_owner_fresh_lock_loader_is_absent() -> None:
    operations: list[str] = []
    facts = _facts()
    repository = _Repository(operations)
    unit = _Unit(operations)
    application = MatchingCoordinationApplication(
        _UnlockedReader(facts), repository, lambda: unit
    )
    command = ApplyCustomerMatchingDecision(
        **_common(facts),
        criteria_snapshot_id="snapshot-1",
        package_id="package-1",
        package_version=1,
        candidate_id="candidate-1",
        decision="accepted",
        preview_fingerprint=facts.package.fingerprint,
    )

    with pytest.raises(MatchingApplicationError) as captured:
        application.apply(command)

    assert captured.value.error.code == "matching_lock_set_stale"
    assert operations == ["begin", "claim", "lock"]
    assert unit.commits == 0
    assert unit.rollbacks == 1


def test_replay_returns_receipt_without_new_writes_or_commit() -> None:
    operations: list[str] = []
    facts = _facts()
    application, repository, unit = _application(facts, operations)
    replay = MatchingApplyReceipt(
        "receipt-replay",
        MatchingCommandName.APPLY_CUSTOMER_DECISION,
        fingerprint_payload({"command": "replay"}),
        facts.package.fingerprint,
        facts.source_versions,
        None,
        "package-1",
        (),
        "accepted",
    )
    repository.replay = replay
    command = ApplyCustomerMatchingDecision(
        **_common(facts),
        criteria_snapshot_id="snapshot-1",
        package_id="package-1",
        package_version=1,
        candidate_id="candidate-1",
        decision="accepted",
        preview_fingerprint=facts.package.fingerprint,
    )

    assert application.apply(command) is replay
    assert operations == ["begin", "claim"]
    assert unit.commits == 0
    assert repository.saved == []


def test_same_key_mismatch_is_typed_conflict_and_rolls_back() -> None:
    operations: list[str] = []
    facts = _facts()
    application, repository, unit = _application(facts, operations)
    repository.conflict = True
    command = ApplyCustomerMatchingDecision(
        **_common(facts),
        criteria_snapshot_id="snapshot-1",
        package_id="package-1",
        package_version=1,
        candidate_id="candidate-1",
        decision="accepted",
        preview_fingerprint=facts.package.fingerprint,
    )

    with pytest.raises(MatchingApplicationError) as captured:
        application.apply(command)

    assert captured.value.error.code == "matching_idempotency_conflict"
    assert operations == ["begin", "claim"]
    assert unit.commits == 0
    assert unit.rollbacks == 1


def test_workflow_error_rolls_back_before_any_append() -> None:
    operations: list[str] = []
    facts = _facts()
    application, repository, unit = _application(facts, operations)
    command = ApplyCustomerMatchingDecision(
        **_common(_facts("d")),
        criteria_snapshot_id="snapshot-1",
        package_id="package-1",
        package_version=1,
        candidate_id="candidate-1",
        decision="accepted",
        preview_fingerprint=facts.package.fingerprint,
    )

    with pytest.raises(MatchingCoordinationWorkflowError) as captured:
        application.apply(command)

    assert captured.value.error.code == "matching_source_version_conflict"
    assert operations == ["begin", "claim", "lock", "fresh"]
    assert unit.commits == 0
    assert unit.rollbacks == 1
    assert repository.saved == []


@pytest.mark.parametrize("kind", ["criteria", "zero", "selection"])
def test_apply_forwards_command_preview_fingerprint(kind: str) -> None:
    operations: list[str] = []
    facts = _facts(no_candidate=kind == "zero")
    workflow = _RecordingWorkflow(operations)
    application, _, _ = _application(facts, operations, workflow)

    if kind == "criteria":
        before = facts.snapshot
        after = build_criteria_snapshot(
            snapshot_id="snapshot-2",
            case_no="CASE-001",
            criteria_version=2,
            criteria={"service_days": 3},
            source_versions=facts.source_versions,
            created_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
        )
        lineage = build_willingness_lineage(
            event_id="willingness-before-1",
            candidate_id="candidate-1",
            staff_id=7,
            snapshot=before,
            previous_state="pending",
            current_state="willing",
            affected_criteria=("service_days",),
        )
        facts = MatchingCoordinationFacts(
            snapshot=after,
            package=facts.package,
            candidates=facts.candidates,
            source_versions=facts.source_versions,
            criteria_snapshots=(before, after),
            willingness_lineage=(lineage,),
        )
        application, _, _ = _application(facts, operations, workflow)
        expected = build_criteria_diff(
            before,
            after,
            facts.candidates,
            willingness_lineage=facts.willingness_lineage,
        ).fingerprint
        command = ApplyCriteriaDiffResend(
            **_common(facts),
            before_snapshot_id="snapshot-1",
            after_snapshot_id="snapshot-2",
            preview_fingerprint=expected,
            recipient_ids=(),
        )
    elif kind == "zero":
        alternative = MatchingCoordinationWorkflow().preview(
            PreviewZeroCandidateAlternative(
                **_common(facts),
                criteria_snapshot_id="snapshot-1",
                policy_id="policy-v1",
                policy_version=1,
                relaxed_criteria=("service_days",),
            ),
            facts,
        )
        expected = alternative.preview_fingerprint
        command = ApplyZeroCandidateAlternative(
            **_common(facts),
            criteria_snapshot_id="snapshot-1",
            alternative_id=alternative.alternative_id,
            policy_id="policy-v1",
            policy_version=1,
            relaxed_criteria=("service_days",),
            preview_fingerprint=expected,
        )
    else:
        expected = fingerprint_payload({"selection": "candidate-1"})
        command = ApplyCaregiverSelection(
            **_common(facts),
            criteria_snapshot_id="snapshot-1",
            package_id="package-1",
            package_version=1,
            candidate_id="candidate-1",
            willingness="willing",
            reason_code=None,
            affected_criteria=(),
            preview_fingerprint=expected,
        )

    application.apply(command)
    assert workflow.received_preview == expected


def test_service_date_apply_rebuilds_preview_from_locked_owner_facts() -> None:
    operations: list[str] = []
    facts = _facts()
    availability = StaffAvailabilityFacts(7, 4, (), ())
    preview_command = ApplyServiceDateChangeRematch(
        **_common(facts, "matching:service-date:1"),
        criteria_snapshot_id=facts.snapshot.snapshot_id,
        package_id=facts.package.package_id,
        assignment_id=31,
        original_staff_id=7,
        original_service_dates=(date(2026, 9, 1),),
        shifted_service_dates=(date(2026, 9, 3),),
        preview_fingerprint=fingerprint_payload({"placeholder": True}),
    )
    outcome = MatchingCoordinationWorkflow().preview_service_date_shift(
        preview_command,
        facts,
        availability,
    )
    command = ApplyServiceDateChangeRematch(
        **_common(facts, "matching:service-date:1"),
        criteria_snapshot_id=facts.snapshot.snapshot_id,
        package_id=facts.package.package_id,
        assignment_id=31,
        original_staff_id=7,
        original_service_dates=(date(2026, 9, 1),),
        shifted_service_dates=(date(2026, 9, 3),),
        preview_fingerprint=outcome.source_fingerprint,
    )

    def load_service_date_input(request, *, for_update: bool):
        assert request == command
        assert for_update is True
        operations.append("service-date-lock")
        return ServiceDateRematchPreviewInput(
            case_no="CASE-001",
            assignment_id=31,
            original_staff_id=7,
            original_service_dates=(date(2026, 9, 1),),
            shifted_service_dates=(date(2026, 9, 3),),
            availability=availability,
        )

    repository = _Repository(operations)
    unit = _Unit(operations)
    application = MatchingCoordinationApplication(
        _Reader(facts, operations),
        repository,
        lambda: unit,
        service_date_input_loader=load_service_date_input,
    )

    receipt = application.apply(command)

    assert receipt.command_name is MatchingCommandName.APPLY_SERVICE_DATE_REMATCH
    assert receipt.preview_fingerprint == outcome.source_fingerprint
    assert receipt.result_state == "rematch_required"
    assert operations == [
        "begin",
        "claim",
        "lock",
        "fresh",
        "service-date-lock",
        "lineage",
        "receipt",
        "intents",
        "commit",
    ]

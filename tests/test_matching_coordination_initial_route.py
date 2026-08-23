"""
File: test_matching_coordination_initial_route.py
Description: 驗證 M3 typed Query／Preview／Apply public HTTP contract、service-date owner read與server identity。
"""

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.dependencies.matching_coordination as composition_module
from api.dependencies.admin_auth import require_system_admin
from api.dependencies.matching_coordination import (
    MatchingCoordinationComposition,
    _load_service_date_input,
    get_matching_coordination_composition,
)
from api.routes.matching_coordination import router
from domains.scheduling.matching_coordination import (
    SOURCE_KINDS,
    CandidateEligibility,
    MatchingCandidateResult,
    MatchingPackage,
    MatchingPackageMode,
    MatchingSegment,
    MatchingSourceVersion,
    build_criteria_snapshot,
    build_zero_candidate_alternative,
)
from domains.scheduling.staff_availability import StaffAvailabilityFacts
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling.matching_coordination_contracts import (
    MatchingApplyReceipt,
    MatchingCommandName,
    ApplyCriteriaDiffResend,
    ApplyCaregiverSelection,
    ApplyCustomerMatchingDecision,
    ApplyZeroCandidateAlternative,
    ApplyServiceDateChangeRematch,
    CriteriaDiffView,
    PreviewCriteriaDiffResend,
    PreviewMatchingPackage,
    PreviewRematch,
    PreviewServiceDateChangeRematch,
    ApplyRematch,
    PreviewZeroCandidateAlternative,
    alternative_view,
    package_view,
    snapshot_view,
)
from subsystems.scheduling.matching_coordination_workflow import (
    ServiceDateShiftAvailabilityConfirmation,
)
from subsystems.scheduling.matching_coordination_query import (
    MatchingCoordinationQueryResult,
)


def _sources() -> tuple[MatchingSourceVersion, ...]:
    return tuple(
        MatchingSourceVersion(kind, f"{kind}:CASE-001", 1, "a" * 64)
        for kind in SOURCE_KINDS
    )


def _source_body() -> dict[str, object]:
    return {
        "items": [
            {
                "source_kind": item.source_kind,
                "source_id": item.source_id,
                "version": item.version,
                "fingerprint": item.fingerprint,
            }
            for item in _sources()
        ]
    }


class _Application:
    def __init__(self) -> None:
        self.preview_command = None
        self.apply_command = None
        self.query_command = None
        self.snapshot = build_criteria_snapshot(
            snapshot_id="matching:CASE-001:criteria:1:aaaaaaaaaaaaaaaa",
            case_no="CASE-001",
            criteria_version=1,
            criteria={"confirmed_service_dates": ("2026-09-01",)},
            source_versions=_sources(),
            created_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
        )

    def query(self, command):
        self.query_command = command
        return MatchingCoordinationQueryResult(
            case_no="CASE-001",
            snapshot=snapshot_view(self.snapshot),
            package=None,
            candidates=(),
            source_versions=_sources(),
            refusal_history=(),
            willingness_lineage=(),
            expected_source_versions_match=True,
        )

    def preview(self, command):
        self.preview_command = command
        if isinstance(command, PreviewCriteriaDiffResend):
            return CriteriaDiffView(
                before_snapshot_id=command.before_snapshot_id,
                after_snapshot_id=command.after_snapshot_id,
                added=(),
                removed=(),
                changed=("region",),
                unchanged=(),
                affected_candidate_ids=(),
                affected_recipient_ids=(),
                resend_eligible=False,
                diff_fingerprint=fingerprint_payload(
                    {
                        "before": command.before_snapshot_id,
                        "after": command.after_snapshot_id,
                    }
                ),
            )
        if isinstance(command, (PreviewMatchingPackage, PreviewRematch)):
            candidate = MatchingCandidateResult(
                "candidate-1",
                7,
                CandidateEligibility.ELIGIBLE,
                (),
                coverage_evidence=(date(2026, 9, 1),),
                willingness="willing",
                staff_name="王小明",
            )
            return package_view(
                MatchingPackage(
                    package_id="package-preview-1",
                    version=1,
                    mode=MatchingPackageMode.SINGLE,
                    segments=(MatchingSegment(7, (date(2026, 9, 1),), 1),),
                    required_service_dates=(date(2026, 9, 1),),
                    candidate_results=(candidate,),
                    criteria_snapshot_id=self.snapshot.snapshot_id,
                    source_versions=_sources(),
                )
            )
        if isinstance(command, PreviewZeroCandidateAlternative):
            return alternative_view(
                build_zero_candidate_alternative(
                    alternative_id="alternative-preview-1",
                    policy_id=command.policy_id,
                    policy_version=command.policy_version,
                    relaxed_criteria=command.relaxed_criteria,
                    unchanged_hard_criteria=("confirmed_service_dates",),
                    risk_warnings=("explicit_manual_confirmation_required",),
                )
            )
        return snapshot_view(self.snapshot)

    def preview_service_date_rematch(self, command):
        self.preview_command = command
        return ServiceDateShiftAvailabilityConfirmation(
            intent_id="matching:CASE-001:service-date-approval:31:" + "b" * 64,
            case_no="CASE-001",
            assignment_id=command.assignment_id,
            staff_id=command.original_staff_id,
            original_service_dates=command.original_service_dates,
            shifted_service_dates=command.shifted_service_dates,
            source_fingerprint=fingerprint_payload({"service_date": "shifted"}),
        )

    def apply(self, command):
        self.apply_command = command
        if isinstance(command, ApplyServiceDateChangeRematch):
            return MatchingApplyReceipt(
                receipt_id=f"{command.idempotency_key.value}:receipt",
                command_name=MatchingCommandName.APPLY_SERVICE_DATE_REMATCH,
                command_fingerprint=fingerprint_payload(
                    {"command": "service-date-rematch"}
                ),
                preview_fingerprint=command.preview_fingerprint,
                source_versions=_sources(),
                decision_event_id=None,
                package_id=command.package_id,
                outbox_intent_ids=(),
                result_state="rematch_required",
            )
        if isinstance(command, ApplyRematch):
            return MatchingApplyReceipt(
                receipt_id=f"{command.idempotency_key.value}:receipt",
                command_name=MatchingCommandName.APPLY_REMATCH,
                command_fingerprint=fingerprint_payload({"command": "rematch"}),
                preview_fingerprint=command.preview_fingerprint,
                source_versions=_sources(),
                decision_event_id=None,
                package_id=command.package_id,
                outbox_intent_ids=(),
                result_state="rematch_required",
            )
        if isinstance(command, ApplyZeroCandidateAlternative):
            result_state = (
                "alternative_agreed_pending_owning_workflows"
                if command.decision == "agree"
                else "awaiting_matching"
            )
            return MatchingApplyReceipt(
                receipt_id=f"{command.idempotency_key.value}:receipt",
                command_name=MatchingCommandName.APPLY_ZERO_CANDIDATE_ALTERNATIVE,
                command_fingerprint=fingerprint_payload(
                    {"command": "zero-candidate"}
                ),
                preview_fingerprint=command.preview_fingerprint,
                source_versions=_sources(),
                decision_event_id=None,
                package_id=None,
                outbox_intent_ids=(),
                result_state=result_state,
            )
        if isinstance(command, ApplyCustomerMatchingDecision):
            return MatchingApplyReceipt(
                receipt_id=f"{command.idempotency_key.value}:receipt",
                command_name=MatchingCommandName.APPLY_CUSTOMER_DECISION,
                command_fingerprint=fingerprint_payload(
                    {"command": "customer-decision"}
                ),
                preview_fingerprint=command.preview_fingerprint,
                source_versions=_sources(),
                decision_event_id=f"{command.idempotency_key.value}:decision",
                package_id=command.package_id,
                outbox_intent_ids=(),
                result_state=command.decision,
            )
        if isinstance(command, ApplyCaregiverSelection):
            return MatchingApplyReceipt(
                receipt_id=f"{command.idempotency_key.value}:receipt",
                command_name=MatchingCommandName.APPLY_CAREGIVER_SELECTION,
                command_fingerprint=fingerprint_payload(
                    {"command": "caregiver-selection"}
                ),
                preview_fingerprint=command.preview_fingerprint,
                source_versions=_sources(),
                decision_event_id=f"{command.idempotency_key.value}:decision",
                package_id=command.package_id,
                outbox_intent_ids=(),
                result_state=command.willingness,
            )
        if isinstance(command, ApplyCriteriaDiffResend):
            return MatchingApplyReceipt(
                receipt_id=f"{command.idempotency_key.value}:receipt",
                command_name=MatchingCommandName.APPLY_CRITERIA_DIFF_RESEND,
                command_fingerprint=fingerprint_payload(
                    {"command": "criteria-diff"}
                ),
                preview_fingerprint=command.preview_fingerprint,
                source_versions=_sources(),
                decision_event_id=None,
                package_id=None,
                outbox_intent_ids=tuple(
                    f"{command.idempotency_key.value}:criteria-resend:{recipient_id}"
                    for recipient_id in command.recipient_ids
                ),
                result_state="intent_queued",
            )
        return MatchingApplyReceipt(
            receipt_id=f"{command.idempotency_key.value}:receipt",
            command_name=MatchingCommandName.APPLY_INITIAL_CRITERIA,
            command_fingerprint=fingerprint_payload({"command": "initial"}),
            preview_fingerprint=self.snapshot.fingerprint,
            source_versions=_sources(),
            decision_event_id=None,
            package_id=None,
            outbox_intent_ids=(),
            result_state="criteria_snapshotted",
        )


def _client(application: _Application) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_system_admin] = lambda: AdminPrincipal(
        1, "system-admin", "System Admin", "system_admin"
    )
    app.dependency_overrides[get_matching_coordination_composition] = lambda: (
        MatchingCoordinationComposition(object(), application)
    )
    return TestClient(app)


def test_production_composition_wires_m3_owned_query_ports(monkeypatch) -> None:
    class _Connection:
        closed = False

        def close(self) -> None:
            self.closed = True

    connection = _Connection()
    monkeypatch.setattr(composition_module, "get_connection", lambda: connection)

    dependency = composition_module.get_matching_coordination_composition()
    composition = next(dependency)
    facts_reader = composition.application._facts_reader
    repository = composition.application._repository

    assert facts_reader._ports["matching_criteria_snapshot"] is repository
    assert facts_reader._ports["candidate_pool"]._connection is connection
    assert facts_reader._ports["matching_package"] is repository
    assert facts_reader._ports["incumbent_assignment"]._connection is connection
    assert facts_reader._ports["staff_profile_definition"] is facts_reader._ports[
        "staff_profile_values"
    ]
    assert facts_reader._ports["staff_lifecycle"]._connection is connection
    assert facts_reader._ports["scheduling_availability"]._service_dates is not None
    assert facts_reader._ports["scheduling_effective_generation"]._order_terms is not None

    try:
        next(dependency)
    except StopIteration:
        pass
    assert connection.closed is True


def test_preview_initial_criteria_is_closed_typed_and_server_derives_actor() -> None:
    application = _Application()
    response = _client(application).post(
        "/api/v1/matching-coordination/CASE-001/preview/initial-criteria",
        headers={"X-Correlation-ID": "corr-preview-1"},
        json={
            "reason": "initialize matching",
            "expected_source_versions": _source_body(),
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["snapshot_id"].startswith("matching:CASE-001")
    assert application.preview_command.actor.actor_id == "system-admin"
    assert application.preview_command.correlation_id.value == "corr-preview-1"


def test_preview_criteria_diff_is_read_only_closed_and_server_derives_identity() -> None:
    application = _Application()
    client = _client(application)
    response = client.post(
        "/api/v1/matching-coordination/CASE-001/preview/criteria-diff",
        headers={"X-Correlation-ID": "corr-criteria-diff-1"},
        json={
            "reason": "criteria changed",
            "expected_source_versions": _source_body(),
            "before_snapshot_id": "snapshot-before",
            "after_snapshot_id": "snapshot-after",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["changed"] == ["region"]
    command = application.preview_command
    assert isinstance(command, PreviewCriteriaDiffResend)
    assert command.actor.actor_id == "system-admin"
    assert command.correlation_id.value == "corr-criteria-diff-1"
    assert command.before_snapshot_id == "snapshot-before"
    assert command.after_snapshot_id == "snapshot-after"
    assert command.idempotency_key.value.startswith("preview:")
    rejected = client.post(
        "/api/v1/matching-coordination/CASE-001/preview/criteria-diff",
        json={
            "reason": "criteria changed",
            "expected_source_versions": _source_body(),
            "before_snapshot_id": "snapshot-before",
            "after_snapshot_id": "snapshot-after",
            "recipient_ids": ["candidate-1"],
        },
    )
    assert rejected.status_code == 422


def test_query_route_is_read_only_closed_and_server_derives_actor() -> None:
    application = _Application()
    client = _client(application)

    response = client.post(
        "/api/v1/matching-coordination/CASE-001/query",
        headers={"X-Correlation-ID": "corr-query-1"},
        json={},
    )

    assert response.status_code == 200
    assert response.json()["data"]["case_no"] == "CASE-001"
    assert application.query_command.actor.actor_id == "system-admin"
    assert application.query_command.expected_source_versions is None
    rejected = client.post(
        "/api/v1/matching-coordination/CASE-001/query",
        json={"reason": "query must not accept mutation fields"},
    )
    assert rejected.status_code == 422


def test_apply_initial_criteria_requires_headers_and_returns_typed_receipt() -> None:
    application = _Application()
    client = _client(application)
    body = {
        "reason": "initialize matching",
        "expected_source_versions": _source_body(),
        "preview_fingerprint": application.snapshot.fingerprint.value,
    }

    missing = client.post(
        "/api/v1/matching-coordination/CASE-001/apply/initial-criteria",
        json=body,
    )
    assert missing.status_code == 422

    response = client.post(
        "/api/v1/matching-coordination/CASE-001/apply/initial-criteria",
        headers={
            "Idempotency-Key": "matching:CASE-001:initial:1",
            "X-Correlation-ID": "corr-apply-1",
        },
        json=body,
    )
    assert response.status_code == 200
    assert response.json()["data"]["command_name"] == "ApplyInitialCriteriaSnapshot"
    assert response.json()["data"]["result_state"] == "criteria_snapshotted"
    assert application.apply_command.actor.actor_id == "system-admin"


def test_apply_criteria_diff_requires_headers_and_maps_closed_command() -> None:
    application = _Application()
    client = _client(application)
    body = {
        "reason": "approved criteria recontact",
        "expected_source_versions": _source_body(),
        "before_snapshot_id": "snapshot-before",
        "after_snapshot_id": "snapshot-after",
        "preview_fingerprint": "d" * 64,
        "recipient_ids": ["candidate-1"],
    }
    response = client.post(
        "/api/v1/matching-coordination/CASE-001/apply/criteria-diff",
        headers={
            "Idempotency-Key": "matching:case-001:criteria-diff:1",
            "X-Correlation-ID": "corr-criteria-diff-apply-1",
        },
        json=body,
    )

    assert response.status_code == 200
    assert response.json()["data"]["command_name"] == "ApplyCriteriaDiffResend"
    assert response.json()["data"]["result_state"] == "intent_queued"
    command = application.apply_command
    assert isinstance(command, ApplyCriteriaDiffResend)
    assert command.actor.actor_id == "system-admin"
    assert command.recipient_ids == ("candidate-1",)
    assert command.before_snapshot_id == "snapshot-before"
    assert command.after_snapshot_id == "snapshot-after"
    assert command.preview_fingerprint.value == "d" * 64
    missing_headers = client.post(
        "/api/v1/matching-coordination/CASE-001/apply/criteria-diff",
        json=body,
    )
    assert missing_headers.status_code == 422
    extra_group = client.post(
        "/api/v1/matching-coordination/CASE-001/apply/criteria-diff",
        headers={
            "Idempotency-Key": "matching:case-001:criteria-diff:2",
            "X-Correlation-ID": "corr-criteria-diff-apply-2",
        },
        json={**body, "route_group": "group1_original_willing_reconfirm"},
    )
    assert extra_group.status_code == 422


def test_apply_caregiver_selection_maps_union_choice_and_closed_evidence() -> None:
    application = _Application()
    client = _client(application)
    body = {
        "reason": "union staff selected caregiver",
        "expected_source_versions": _source_body(),
        "criteria_snapshot_id": application.snapshot.snapshot_id,
        "package_id": "package-1",
        "package_version": 1,
        "candidate_id": "candidate-1",
        "willingness": "willing",
        "preview_fingerprint": "e" * 64,
    }
    response = client.post(
        "/api/v1/matching-coordination/CASE-001/apply/caregiver-selection",
        headers={
            "Idempotency-Key": "matching:case-001:caregiver:1",
            "X-Correlation-ID": "corr-caregiver-selection-1",
        },
        json=body,
    )

    assert response.status_code == 200
    assert response.json()["data"]["command_name"] == "ApplyCaregiverSelection"
    command = application.apply_command
    assert isinstance(command, ApplyCaregiverSelection)
    assert command.actor.actor_id == "system-admin"
    assert command.candidate_id == "candidate-1"
    assert command.willingness == "willing"
    assert command.reason_code is None
    assert command.affected_criteria == ()
    invalid_unwilling = client.post(
        "/api/v1/matching-coordination/CASE-001/apply/caregiver-selection",
        headers={
            "Idempotency-Key": "matching:case-001:caregiver:2",
            "X-Correlation-ID": "corr-caregiver-selection-2",
        },
        json={**body, "willingness": "unwilling"},
    )
    assert invalid_unwilling.status_code == 422


def test_apply_customer_decision_maps_union_choice_without_owner_writes() -> None:
    application = _Application()
    client = _client(application)
    body = {
        "reason": "customer accepted union selection",
        "expected_source_versions": _source_body(),
        "criteria_snapshot_id": application.snapshot.snapshot_id,
        "package_id": "package-1",
        "package_version": 1,
        "candidate_id": "candidate-1",
        "decision": "accepted",
        "preview_fingerprint": "f" * 64,
    }
    response = client.post(
        "/api/v1/matching-coordination/CASE-001/apply/customer-decision",
        headers={
            "Idempotency-Key": "matching:case-001:customer:1",
            "X-Correlation-ID": "corr-customer-decision-1",
        },
        json=body,
    )

    assert response.status_code == 200
    assert response.json()["data"]["command_name"] == "ApplyCustomerMatchingDecision"
    command = application.apply_command
    assert isinstance(command, ApplyCustomerMatchingDecision)
    assert command.actor.actor_id == "system-admin"
    assert command.decision == "accepted"
    assert command.candidate_id == "candidate-1"
    injected_owner_write = client.post(
        "/api/v1/matching-coordination/CASE-001/apply/customer-decision",
        headers={
            "Idempotency-Key": "matching:case-001:customer:2",
            "X-Correlation-ID": "corr-customer-decision-2",
        },
        json={**body, "assignment_id": 99},
    )
    assert injected_owner_write.status_code == 422


def test_apply_zero_candidate_maps_explicit_union_compromise_decision() -> None:
    application = _Application()
    client = _client(application)
    body = {
        "reason": "union staff approved explicit compromise",
        "expected_source_versions": _source_body(),
        "criteria_snapshot_id": application.snapshot.snapshot_id,
        "alternative_id": "alternative-preview-1",
        "policy_id": "policy-v1",
        "policy_version": 1,
        "relaxed_criteria": ["confirmed_service_dates"],
        "decision": "agree",
        "preview_fingerprint": "1" * 64,
    }
    response = client.post(
        "/api/v1/matching-coordination/CASE-001/apply/zero-candidate",
        headers={
            "Idempotency-Key": "matching:case-001:zero:1",
            "X-Correlation-ID": "corr-zero-apply-1",
        },
        json=body,
    )

    assert response.status_code == 200
    assert response.json()["data"]["result_state"] == (
        "alternative_agreed_pending_owning_workflows"
    )
    command = application.apply_command
    assert isinstance(command, ApplyZeroCandidateAlternative)
    assert command.actor.actor_id == "system-admin"
    assert command.relaxed_criteria == ("confirmed_service_dates",)
    assert command.decision == "agree"
    injected_order_write = client.post(
        "/api/v1/matching-coordination/CASE-001/apply/zero-candidate",
        headers={
            "Idempotency-Key": "matching:case-001:zero:2",
            "X-Correlation-ID": "corr-zero-apply-2",
        },
        json={**body, "new_order_end_date": "2026-09-30"},
    )
    assert injected_order_write.status_code == 422


def test_rematch_preview_and_apply_keep_assignment_as_typed_handoff() -> None:
    application = _Application()
    client = _client(application)
    preview_body = {
        "reason": "fresh effects require rematch",
        "expected_source_versions": _source_body(),
        "criteria_snapshot_id": application.snapshot.snapshot_id,
        "package_id": "package-preview-1",
    }
    preview = client.post(
        "/api/v1/matching-coordination/CASE-001/preview/rematch",
        headers={"X-Correlation-ID": "corr-rematch-preview-1"},
        json=preview_body,
    )

    assert preview.status_code == 200
    assert preview.json()["data"]["package_id"] == "package-preview-1"
    assert isinstance(application.preview_command, PreviewRematch)
    apply = client.post(
        "/api/v1/matching-coordination/CASE-001/apply/rematch",
        headers={
            "Idempotency-Key": "matching:case-001:rematch:1",
            "X-Correlation-ID": "corr-rematch-apply-1",
        },
        json={
            **preview_body,
            "preview_fingerprint": preview.json()["data"]["fingerprint"],
        },
    )
    assert apply.status_code == 200
    assert apply.json()["data"]["result_state"] == "rematch_required"
    command = application.apply_command
    assert isinstance(command, ApplyRematch)
    assert command.actor.actor_id == "system-admin"
    assert command.package_id == "package-preview-1"


def test_preview_package_accepts_only_explicit_admin_segments() -> None:
    application = _Application()
    response = _client(application).post(
        "/api/v1/matching-coordination/CASE-001/preview/package",
        headers={"X-Correlation-ID": "corr-package-1"},
        json={
            "reason": "工會人員選擇單一照服員",
            "expected_source_versions": _source_body(),
            "criteria_snapshot_id": application.snapshot.snapshot_id,
            "required_service_dates": ["2026-09-01"],
            "segments": [
                {
                    "staff_id": 7,
                    "service_dates": ["2026-09-01"],
                    "sequence": 1,
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["candidate_results"][0]["staff_name"] == "王小明"
    assert application.preview_command.segments[0].staff_id == 7
    assert application.preview_command.actor.actor_id == "system-admin"

    missing_segments = _client(_Application()).post(
        "/api/v1/matching-coordination/CASE-001/preview/package",
        json={
            "reason": "missing explicit selection",
            "expected_source_versions": _source_body(),
            "criteria_snapshot_id": application.snapshot.snapshot_id,
            "required_service_dates": ["2026-09-01"],
        },
    )
    assert missing_segments.status_code == 422


def test_initial_routes_reject_extra_body_fields() -> None:
    response = _client(_Application()).post(
        "/api/v1/matching-coordination/CASE-001/preview/initial-criteria",
        json={
            "reason": "initialize matching",
            "expected_source_versions": _source_body(),
            "actor": "client-controlled",
        },
    )
    assert response.status_code == 422


def test_service_date_preview_preserves_owner_identity_and_returns_typed_outcome() -> None:
    application = _Application()
    response = _client(application).post(
        "/api/v1/matching-coordination/CASE-001/preview/service-date-rematch",
        headers={"X-Correlation-ID": "corr-service-date-preview-1"},
        json={
            "reason": "服務日期異動後確認原照服員",
            "expected_source_versions": _source_body(),
            "criteria_snapshot_id": application.snapshot.snapshot_id,
            "package_id": "package-preview-1",
            "assignment_id": 31,
            "original_staff_id": 17,
            "original_service_dates": ["2026-09-01"],
            "shifted_service_dates": ["2026-09-02"],
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["outcome_kind"] == "availability_confirmation"
    command = application.preview_command
    assert isinstance(command, PreviewServiceDateChangeRematch)
    assert command.assignment_id == 31
    assert command.original_staff_id == 17
    assert command.original_service_dates == (date(2026, 9, 1),)
    assert command.shifted_service_dates == (date(2026, 9, 2),)
    assert command.actor.actor_id == "system-admin"


def test_service_date_apply_requires_identity_headers_and_maps_closed_command() -> None:
    application = _Application()
    client = _client(application)
    body = {
        "reason": "服務日期異動後重新媒合",
        "expected_source_versions": _source_body(),
        "criteria_snapshot_id": application.snapshot.snapshot_id,
        "package_id": "package-preview-1",
        "assignment_id": 31,
        "original_staff_id": 17,
        "original_service_dates": ["2026-09-01"],
        "shifted_service_dates": ["2026-09-02"],
        "preview_fingerprint": fingerprint_payload(
            {"service_date": "shifted"}
        ).value,
    }

    missing_headers = client.post(
        "/api/v1/matching-coordination/CASE-001/apply/service-date-rematch",
        json=body,
    )
    response = client.post(
        "/api/v1/matching-coordination/CASE-001/apply/service-date-rematch",
        headers={
            "Idempotency-Key": "matching:case-001:service-date:1",
            "X-Correlation-ID": "corr-service-date-apply-1",
        },
        json=body,
    )

    assert missing_headers.status_code == 422
    assert response.status_code == 200
    assert response.json()["data"]["command_name"] == (
        "ApplyServiceDateChangeRematch"
    )
    assert response.json()["data"]["result_state"] == "rematch_required"
    command = application.apply_command
    assert isinstance(command, ApplyServiceDateChangeRematch)
    assert command.actor.actor_id == "system-admin"
    assert command.assignment_id == 31
    assert command.original_staff_id == 17
    assert command.preview_fingerprint.value == body["preview_fingerprint"]


@pytest.mark.parametrize("for_update", [False, True])
def test_service_date_loader_uses_shifted_dates_and_propagates_lock_mode(
    for_update: bool,
) -> None:
    original_date = date(2026, 9, 1)
    shifted_date = date(2026, 9, 2)
    command = PreviewServiceDateChangeRematch(
        case_no="CASE-001",
        actor=ActorContext("system-admin"),
        reason="service date shift",
        correlation_id=CorrelationId("corr-service-date-loader-1"),
        idempotency_key=IdempotencyKey("preview:service-date-loader-1"),
        expected_source_versions=_sources(),
        criteria_snapshot_id="criteria-1",
        assignment_id=31,
        original_staff_id=17,
        original_service_dates=(original_date,),
        shifted_service_dates=(shifted_date,),
    )

    class _ServiceDates:
        def load_service_dates(self, case_no, *, for_update: bool):
            assert (case_no, for_update) == ("CASE-001", expected_lock)
            return SimpleNamespace(current_version=2, current_dates=(original_date,))

    class _Assignments:
        def load_current_assignments(self, case_no, *, for_update: bool):
            assert (case_no, for_update) == ("CASE-001", expected_lock)
            return SimpleNamespace(
                effective_assignments=(
                    SimpleNamespace(
                        assignment_id=31,
                        staff_id=17,
                        official_service_dates=(original_date,),
                    ),
                )
            )

    class _Availability:
        def load_matching_facts(self, staff_id, service_dates, *, for_update: bool):
            assert (staff_id, service_dates, for_update) == (
                17,
                (shifted_date,),
                expected_lock,
            )
            return StaffAvailabilityFacts(17, 4, (), ())

    expected_lock = for_update
    result = _load_service_date_input(
        command,
        service_dates=_ServiceDates(),
        incumbent_assignment=_Assignments(),
        staff_availability=_Availability(),
        for_update=for_update,
    )

    assert result.original_service_dates == (original_date,)
    assert result.shifted_service_dates == (shifted_date,)


def test_preview_zero_candidate_uses_admin_selected_relaxed_criteria() -> None:
    application = _Application()
    response = _client(application).post(
        "/api/v1/matching-coordination/CASE-001/preview/zero-candidate",
        headers={"X-Correlation-ID": "corr-zero-1"},
        json={
            "reason": "工會人員選擇放寬條件",
            "expected_source_versions": _source_body(),
            "criteria_snapshot_id": application.snapshot.snapshot_id,
            "policy_id": "union-admin-manual-relaxation",
            "policy_version": 1,
            "relaxed_criteria": ["requires_cooking"],
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["relaxed_criteria"] == ["requires_cooking"]
    assert application.preview_command.relaxed_criteria == ("requires_cooking",)
    assert application.preview_command.actor.actor_id == "system-admin"

"""
File: test_service_before_replacement_api.py
Description: 驗證服務前換人 typed Q/P/A API、權限與 fail-closed DI。
"""

from datetime import date
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
import pytest

from api.dependencies.service_before_replacement import (
    get_service_before_replacement_application,
)
from api.routes.service_before_replacement import (
    _apply_payload,
    _call,
    _preview_payload,
    _query_payload,
    query_service_before_replacement as query_route,
    router,
    _server_actor,
)
from api.schemas.service_before_replacement import (
    ActualServiceProofView,
    CandidatePoolReuseProofView,
    ServiceBeforeReplacementApplyBody,
    ServiceBeforeReplacementPreviewBody,
    ServiceBeforeReplacementPreviewView,
    ServiceBeforeReplacementQueryView,
)
from domains.scheduling.service_before_replacement import (
    ReplacementScenario,
    query_service_before_replacement,
)
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion
from shared_kernel.errors import ErrorCategory, FieldError, TypedError
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling.service_before_replacement_workflow import ServiceBeforeReplacementWorkflowError
from subsystems.scheduling.service_before_replacement_workflow import (
    ReplacementApplyResult,
    ReplacementApplyStatus,
    ServiceBeforeReplacementQueryRequest,
)
from tests.test_service_before_replacement import _facts


def test_routes_are_case_scoped_and_exact_qpa_paths():
    assert {route.path for route in router.routes} == {
        "/api/v1/orders/{case_no}/service-before-replacement",
        "/api/v1/orders/{case_no}/service-before-replacement/preview",
        "/api/v1/orders/{case_no}/service-before-replacement/apply",
    }


def test_preview_and_apply_bodies_are_strict_and_canonical():
    with pytest.raises(ValidationError):
        ServiceBeforeReplacementPreviewBody.model_validate(
            {"scenario": "R-01", "reason": "replace", "evidence": ["a"], "status": "done"}
        )
    with pytest.raises(ValidationError):
        ServiceBeforeReplacementApplyBody.model_validate(
            {
                "scenario": "R-01",
                "reason": "replace",
                "evidence": ["a"],
                "expected_generation_version": True,
                "expected_event_version": 1,
                "expected_aggregate_version": 1,
                "prior_generation_identity": "generation:1",
                "prior_event_identity": "event:1",
                "prior_aggregate_identity": "aggregate:1",
                "preview_fingerprint": "a" * 64,
            }
        )
    with pytest.raises(ValidationError):
        ServiceBeforeReplacementPreviewBody.model_validate(
            {"scenario": "R-01", "reason": "replace", "evidence": ["b", "a"]}
        )


def test_query_projection_is_typed_and_zero_write_facts_are_visible():
    view = ServiceBeforeReplacementQueryView.model_validate(
        _query_payload(query_service_before_replacement(_facts()))
    )
    assert view.outcome == "ready"
    assert view.actual_service_day_count == 0
    assert view.root_delta is not None
    assert view.impacted_roots


def test_response_validators_reject_noncanonical_proof_dates_and_referral_facts():
    with pytest.raises(ValidationError):
        ActualServiceProofView.model_validate(
            {
                "case_no": "CASE-1",
                "service_dates": ["2026-08-29", "2026-08-28"],
                "source_identity": "official-service:1",
                "source_version": 1,
                "fingerprint": "a" * 64,
            }
        )

    reuse = {
        "pool_identity": "pool:1",
        "round_identity": "round:1",
        "coverage_version": 1,
        "availability_version": 1,
        "willingness_version": 1,
        "fingerprint": "a" * 64,
        "same_round": True,
        "coverage_valid": True,
        "availability_valid": True,
        "willingness_valid": True,
        "fresh": True,
        "accepted_candidate": True,
    }
    with pytest.raises(ValidationError):
        CandidatePoolReuseProofView.model_validate(reuse)

    referral = _query_payload(
        query_service_before_replacement(_facts(service_dates=(date(2026, 8, 28),)))
    )
    referral["retained_roots"] = [
        {
            "kind": "matching_plan",
            "root_id": "matching-plan:1",
            "case_no": referral["case_no"],
            "current": True,
            "caregiver_bound": True,
        }
    ]
    with pytest.raises(ValidationError):
        ServiceBeforeReplacementQueryView.model_validate(referral)


def test_ready_preview_requires_prior_and_replacement_facts():
    from domains.scheduling.service_before_replacement import preview_service_before_replacement

    payload = _preview_payload(preview_service_before_replacement(_facts()))
    payload["prior_event_identity"] = None
    with pytest.raises(ValidationError):
        ServiceBeforeReplacementPreviewView.model_validate(payload)


def test_actor_is_server_derived_and_narrowed_to_orders_capability():
    principal = AdminPrincipal(
        9,
        "orders-owner",
        "Orders Owner",
        "admin",
        capabilities=frozenset({"orders.historical_review.remediate", "system.administration"}),
    )
    actor = _server_actor(principal)
    assert actor.actor_id == "admin:9"
    assert actor.permission_scope == ("orders.historical_review.remediate",)


def test_production_dependency_yields_composed_application_and_closes_connection(monkeypatch):
    import api.dependencies.service_before_replacement as dependency

    class Connection:
        closed = False

        def close(self):
            self.closed = True

    connection = Connection()
    application = object()
    monkeypatch.setattr(dependency, "get_connection", lambda: connection)
    monkeypatch.setattr(
        dependency,
        "build_service_before_replacement_application",
        lambda value: application if value is connection else None,
    )

    provider = get_service_before_replacement_application(
        correlation_id="request-correlation"
    )
    assert next(provider) is application
    provider.close()
    assert connection.closed is True


def test_application_query_forwards_the_typed_request_without_positional_guessing():
    request = ServiceBeforeReplacementQueryRequest(
        "CASE-QUERY", "R-02", CorrelationId("query-correlation")
    )
    seen = []

    class Workflow:
        def query(self, value):
            seen.append(value)
            return "query-result"

    from api.dependencies.service_before_replacement import ServiceBeforeReplacementApplication

    assert ServiceBeforeReplacementApplication(Workflow()).query(request) == "query-result"
    assert seen == [request]


def test_loader_unavailable_is_a_typed_source_503():
    from infrastructure.mysql.service_before_replacement_loader import (
        ServiceBeforeReplacementSourceUnavailable,
    )

    with pytest.raises(HTTPException) as raised:
        _call(
            lambda: (_ for _ in ()).throw(
                ServiceBeforeReplacementSourceUnavailable(
                    "replacement_signback_incomplete"
                )
            ),
            "unused",
            CorrelationId("query-correlation"),
        )
    assert raised.value.status_code == 503
    assert raised.value.detail["error"]["code"] == "replacement_source_unavailable"
    assert raised.value.detail["error"]["domain_blockers"] == [
        "replacement_signback_incomplete"
    ]


def test_query_route_fails_closed_without_guessing_scenario():
    with pytest.raises(HTTPException) as raised:
        query_route("CASE-QUERY", application=SimpleNamespace())
    assert raised.value.status_code == 503
    assert raised.value.detail["error"]["code"] == "replacement_scenario_required"


def test_query_route_passes_explicit_scenario_to_application():
    request = ServiceBeforeReplacementQueryRequest(
        "CASE-QUERY", "R-02", CorrelationId("query-correlation")
    )
    seen = []

    class Application:
        def query(self, value):
            seen.append(value)
            return query_service_before_replacement(_facts())

    query_route(
        "CASE-QUERY",
        scenario="R-02",
        correlation_id="query-correlation",
        application=Application(),
    )
    assert seen and seen[0] == request


def test_outcome_unknown_without_error_is_always_unavailable():
    result = ReplacementApplyResult(ReplacementApplyStatus.OUTCOME_UNKNOWN, "CASE-QUERY")
    with pytest.raises(ServiceBeforeReplacementWorkflowError) as raised:
        _apply_payload(SimpleNamespace(apply=lambda command: result), SimpleNamespace(correlation_id=CorrelationId("apply-correlation")))
    assert raised.value.error.code == "replacement_outcome_unknown"
    assert raised.value.error.correlation_id.value == "apply-correlation"


def test_direct_workflow_errors_are_normalized_without_losing_error_context():
    original = TypedError(
        ErrorCategory.CONFLICT,
        "replacement_stale_version",
        "stale",
        CorrelationId("workflow-correlation"),
        field_errors=(FieldError("expected_version", "stale", "refresh"),),
        current_version=ExpectedVersion(8),
    )

    with pytest.raises(HTTPException) as raised:
        _call(
            lambda: (_ for _ in ()).throw(ServiceBeforeReplacementWorkflowError(original)),
            "unused",
            CorrelationId("route-correlation"),
        )

    payload = raised.value.detail["error"]
    assert payload["code"] == "replacement_version_conflict"
    assert payload["correlation_id"] == "workflow-correlation"
    assert payload["field_errors"] == [{"field": "expected_version", "code": "stale", "message": "refresh"}]
    assert payload["current_version"] == 8


def test_schema_recomputes_actual_service_proof_and_requires_it_for_nonzero_count():
    payload = _query_payload(query_service_before_replacement(_facts()))
    payload["actual_service_proof"]["fingerprint"] = "0" * 64
    with pytest.raises(ValidationError, match="actual_service_proof_fingerprint_mismatch"):
        ServiceBeforeReplacementQueryView.model_validate(payload)

    referral = _query_payload(
        query_service_before_replacement(_facts(service_dates=(date(2026, 8, 28),)))
    )
    referral["actual_service_proof"] = None
    with pytest.raises(ValidationError, match="replacement_actual_service_requires_service_proof"):
        ServiceBeforeReplacementQueryView.model_validate(referral)


def test_preview_root_delta_must_match_all_three_canonical_root_sets():
    from domains.scheduling.service_before_replacement import preview_service_before_replacement

    payload = _preview_payload(preview_service_before_replacement(_facts()))
    payload["root_delta"]["created"] = []
    with pytest.raises(ValidationError, match="replacement_root_delta_mismatch"):
        ServiceBeforeReplacementPreviewView.model_validate(payload)


def test_successor_and_reuse_nested_versions_are_bound_to_top_level_facts():
    successor = _query_payload(
        query_service_before_replacement(_facts(ReplacementScenario.R07))
    )
    successor["successor_round"]["event_version"] = successor["event_version"]
    successor["successor_round"]["fingerprint"] = fingerprint_payload(
        {
            "kind": "successor-round",
            **{
                key: successor["successor_round"][key]
                for key in (
                    "case_no", "round_identity", "generation_identity", "event_identity",
                    "generation_version", "event_version", "candidate_count",
                    "zero_candidate_disposition",
                )
            },
        }
    ).value
    with pytest.raises(ValidationError, match="successor_round_version_mismatch"):
        ServiceBeforeReplacementQueryView.model_validate(successor)

    payload = _query_payload(query_service_before_replacement(_facts()))
    reuse = {
        "pool_identity": "pool:1",
        "round_identity": "round:1",
        "coverage_version": 2,
        "availability_version": 3,
        "willingness_version": 4,
        "same_round": True,
        "coverage_valid": True,
        "availability_valid": True,
        "willingness_valid": True,
        "fresh": True,
        "accepted_candidate": False,
        "case_no": payload["case_no"],
        "successor_round_identity": "round:1",
        "generation_version": payload["generation_version"],
        "event_version": payload["event_version"],
        "candidate_identity": "candidate:1",
    }
    reuse["fingerprint"] = fingerprint_payload(reuse).value
    payload["candidate_pool_reuse_proof"] = reuse
    ServiceBeforeReplacementQueryView.model_validate(payload)
    reuse["generation_version"] += 1
    reuse["fingerprint"] = fingerprint_payload(
        {key: value for key, value in reuse.items() if key != "fingerprint"}
    ).value
    with pytest.raises(ValidationError, match="candidate_pool_reuse_version_mismatch"):
        ServiceBeforeReplacementQueryView.model_validate(payload)


def test_successor_zero_candidate_disposition_is_strict():
    successor = _query_payload(
        query_service_before_replacement(_facts(ReplacementScenario.R07))
    )
    successor["successor_round"]["zero_candidate_disposition"] = None
    successor["successor_round"]["fingerprint"] = fingerprint_payload(
        {
            "kind": "successor-round",
            **{
                key: successor["successor_round"][key]
                for key in (
                    "case_no", "round_identity", "generation_identity", "event_identity",
                    "generation_version", "event_version", "candidate_count",
                    "zero_candidate_disposition",
                )
            },
        }
    ).value
    with pytest.raises(ValidationError, match="successor_round_zero_candidate_disposition_required"):
        ServiceBeforeReplacementQueryView.model_validate(successor)


def test_rpre_openapi_declares_typed_errors_and_required_idempotency_key():
    app = FastAPI()
    app.include_router(router)
    paths = app.openapi()["paths"]
    for path, method in (
        ("/api/v1/orders/{case_no}/service-before-replacement", "get"),
        ("/api/v1/orders/{case_no}/service-before-replacement/preview", "post"),
        ("/api/v1/orders/{case_no}/service-before-replacement/apply", "post"),
    ):
        operation = paths[path][method]
        for status in ("400", "404", "409", "422", "503"):
            assert operation["responses"][status]["content"]["application/json"]["schema"]["$ref"].endswith(
                "/GlobalTypedErrorResponseView"
            )

    apply_parameters = paths[
        "/api/v1/orders/{case_no}/service-before-replacement/apply"
    ]["post"]["parameters"]
    idempotency = next(item for item in apply_parameters if item["name"] == "Idempotency-Key")
    assert idempotency["required"] is True
    assert idempotency["schema"]["pattern"] == r"^[a-z0-9][a-z0-9._:-]{0,190}$"


def test_preview_request_carries_canonical_reason_and_evidence_to_loader():
    from subsystems.scheduling.service_before_replacement_workflow import (
        ServiceBeforeReplacementPreviewRequest,
    )

    request = ServiceBeforeReplacementPreviewRequest(
        "CASE-QUERY",
        "R-02",
        __import__("shared_kernel.identities", fromlist=["CorrelationId"]).CorrelationId("corr"),
        "replace",
        ("evidence:1",),
    )
    assert request.reason == "replace"
    assert request.evidence == ("evidence:1",)

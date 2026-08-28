"""
File: test_historical_operational_baseline_api.py
Description: 驗證歷史作業基準 typed API 的 identity、schema、capability、receipt 與 fresh readback。
"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
from pydantic import ValidationError
import pytest

from api.dependencies.admin_auth import require_historical_order_review_remediator
from api.routes.historical_operational_baseline import (
    _apply_payload,
    _bound_identity,
    _preview_payload,
    _query_payload,
    router,
)
from api.schemas.historical_operational_baseline import (
    HistoricalOperationalBaselineApplyBody,
    HistoricalOperationalBaselineApplyView,
    HistoricalOperationalBaselineIntentBody,
    HistoricalOperationalBaselinePreviewView,
    HistoricalOperationalBaselineQueryView,
)
from domains.orders.historical_operational_baseline import (
    HistoricalBaselineEvidenceMode,
    HistoricalBaselineLineage,
    HistoricalOperationalBaselineFacts,
    HistoricalOperationalBaselineRequest,
    HistoricalOrderIdentity,
    HistoricalOrderProvenanceIdentity,
    build_historical_operational_baseline_candidate,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.historical_operational_baseline_workflow import (
    HistoricalOperationalBaselinePreview,
    HistoricalOperationalBaselineQuery,
    HistoricalOperationalBaselineReceipt,
)


def _fp(character: str) -> PreviewFingerprint:
    return PreviewFingerprint(character * 64)


def _identity() -> HistoricalOrderIdentity:
    return HistoricalOrderIdentity("order:CASE-1", "CASE-1")


def _facts(*, with_baseline: bool = False):
    prior = (
        HistoricalBaselineLineage(
            "historical-operational-baseline-event:1",
            _identity(),
            8,
            4,
            _fp("a"),
        )
        if with_baseline
        else None
    )
    return HistoricalOperationalBaselineFacts(
        _identity(),
        HistoricalOrderProvenanceIdentity("historical-orders:book:row:2", 17),
        4,
        _fp("a"),
        prior,
    )


def _preview():
    request = HistoricalOperationalBaselineRequest(
        _identity(),
        8,
        4,
        _fp("a"),
        HistoricalBaselineEvidenceMode.RETAINED,
        "人工核對歷史流程",
        "evidence:CASE-1",
    )
    candidate = build_historical_operational_baseline_candidate(
        _facts(),
        request,
    )
    return HistoricalOperationalBaselinePreview(
        candidate,
        ExpectedVersion(4),
        _fp("b"),
    )


def test_query_and_preview_payloads_match_strict_public_contract() -> None:
    query_view = HistoricalOperationalBaselineQueryView.model_validate(
        _query_payload(HistoricalOperationalBaselineQuery(_facts(with_baseline=True)))
    )
    preview_view = HistoricalOperationalBaselinePreviewView.model_validate(
        _preview_payload(_preview())
    )

    assert query_view.order_identity == "order:CASE-1"
    assert query_view.current_baseline.selected_step == 8
    assert query_view.current_baseline.step_projection[-1].state == "in_progress"
    assert preview_view.selected_step == 8
    assert preview_view.step_projection[0].state == (
        "historical_baseline_completed"
    )


def test_intent_schema_rejects_generic_status_and_invalid_evidence_shape() -> None:
    payload = {
        "order_identity": "order:CASE-1",
        "selected_step": 8,
        "expected_orders_version": 4,
        "expected_baseline_binding_fingerprint": "a" * 64,
        "evidence_mode": "retained",
        "reason": "人工核對",
        "evidence_reference": "evidence:CASE-1",
        "status": "訂單完成",
    }
    with pytest.raises(ValidationError):
        HistoricalOperationalBaselineIntentBody.model_validate(payload)

    payload.pop("status")
    payload["document_kind"] = "signed-contract"
    payload["affected_steps"] = [6]
    with pytest.raises(ValidationError):
        HistoricalOperationalBaselineIntentBody.model_validate(payload)


def test_apply_schema_requires_preview_fingerprint_and_strict_integer_step() -> None:
    payload = {
        "order_identity": "order:CASE-1",
        "selected_step": True,
        "expected_orders_version": 4,
        "expected_baseline_binding_fingerprint": "a" * 64,
        "evidence_mode": "retained",
        "reason": "人工核對",
        "evidence_reference": "evidence:CASE-1",
    }
    with pytest.raises(ValidationError):
        HistoricalOperationalBaselineApplyBody.model_validate(payload)


def test_apply_payload_requires_exact_committed_event_readback() -> None:
    receipt = HistoricalOperationalBaselineReceipt(
        _identity(),
        "historical-operational-baseline-event:1",
        "historical-operational-baseline-receipt:1",
        8,
        4,
        _fp("b"),
        _fp("c"),
    )

    class Application:
        def apply(self, _command):
            return receipt

        def query(self, identity, correlation):
            assert identity == _identity()
            assert correlation == CorrelationId("correlation:hob")
            return HistoricalOperationalBaselineQuery(_facts(with_baseline=True))

    command = SimpleNamespace(
        identity=_identity(),
        correlation_id=CorrelationId("correlation:hob"),
        expected_owner_binding_fingerprint=_fp("a"),
    )
    view = HistoricalOperationalBaselineApplyView.model_validate(
        _apply_payload(Application(), command)
    )

    assert view.receipt.baseline_event_identity == (
        "historical-operational-baseline-event:1"
    )
    assert view.readback.current_baseline.selected_step == 8


def test_apply_payload_fails_closed_when_readback_is_not_the_receipt_event() -> None:
    receipt = HistoricalOperationalBaselineReceipt(
        _identity(),
        "historical-operational-baseline-event:other",
        "historical-operational-baseline-receipt:1",
        8,
        4,
        _fp("b"),
        _fp("c"),
    )

    class Application:
        def apply(self, _command):
            return receipt

        def query(self, _identity, _correlation):
            return HistoricalOperationalBaselineQuery(_facts(with_baseline=True))

    with pytest.raises(
        RuntimeError,
        match="historical_operational_baseline_readback_mismatch",
    ):
        _apply_payload(
            Application(),
            SimpleNamespace(
                identity=_identity(),
                correlation_id=CorrelationId("correlation:hob"),
                expected_owner_binding_fingerprint=_fp("a"),
            ),
        )


def test_orders_owner_capability_and_exact_case_identity_are_required() -> None:
    request = SimpleNamespace(state=SimpleNamespace())
    unscoped = AdminPrincipal(
        None,
        "unscoped",
        "Unscoped",
        "line_viewer",
        capabilities=frozenset(),
    )
    with pytest.raises(HTTPException) as denied:
        require_historical_order_review_remediator(request, unscoped)
    assert denied.value.status_code == 403

    owner = AdminPrincipal(
        None,
        "orders-owner",
        "Orders Owner",
        "line_viewer",
        capabilities=frozenset({"orders.historical_review.remediate"}),
    )
    assert require_historical_order_review_remediator(request, owner) is owner

    with pytest.raises(HTTPException) as mismatched:
        _bound_identity(
            "CASE-1",
            "order:CASE-2",
            CorrelationId("correlation:identity"),
        )
    assert mismatched.value.status_code == 422


def test_route_contract_is_case_scoped_and_not_a_generic_status_editor() -> None:
    paths = {route.path for route in router.routes}
    assert paths == {
        "/api/v1/orders/{case_no}/historical-operational-baseline",
        "/api/v1/orders/{case_no}/historical-operational-baseline/preview",
        "/api/v1/orders/{case_no}/historical-operational-baseline/apply",
    }
    assert all("status" not in path for path in paths)

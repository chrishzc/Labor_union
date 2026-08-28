"""Typed API contract tests for HPROJ v2 persisted readback."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pymysql.err import InterfaceError, OperationalError

from api.dependencies.admin_auth import require_historical_order_review_remediator
from api.dependencies.historical_baseline_projector import (
    HistoricalBaselineProjectorQueryApplication,
    get_historical_baseline_projector_query_application,
)
from api.routes.historical_baseline_projector import (
    query_historical_baseline_projection_delivery,
    query_latest_historical_baseline_projection,
    router,
)
from api.schemas.historical_baseline_projector import (
    HistoricalBaselineProjectorReadModelView,
)
from infrastructure.mysql.historical_baseline_projector_delivery import (
    HistoricalBaselineDeliveryStatus,
)
from infrastructure.mysql.historical_baseline_projector_read_model import (
    HistoricalBaselineAlertDisplayView,
    HistoricalBaselineCurrentAlertView,
    HistoricalBaselineDeliveryView,
    HistoricalBaselineMembershipView,
    HistoricalBaselinePostCommitReadbackView,
    HistoricalBaselineProjectorReadModel,
    HistoricalBaselineReceiptView,
    HistoricalBaselineRepairReferralView,
)
from shared_kernel.fingerprints import PreviewFingerprint


_CASE_NO = "CASE-HPROJ-API-001"
_DELIVERY_ID = "1" * 64
_RECEIPT_ID = "2" * 64
_DIGEST = PreviewFingerprint("a" * 64)
_UMBRELLA = PreviewFingerprint("b" * 64)
_ALERT = PreviewFingerprint("c" * 64)


class _ReadPort:
    def __init__(self, model=None):
        self.model = model
        self.by_case = []
        self.by_delivery = []

    def query_latest_by_case(self, case_no):
        self.by_case.append(case_no)
        return self.model

    def query_by_delivery_identity(self, delivery_identity):
        self.by_delivery.append(delivery_identity)
        return self.model


class _FailingReadPort:
    def __init__(self, error):
        self.error = error

    def query_latest_by_case(self, case_no):
        del case_no
        raise self.error

    def query_by_delivery_identity(self, delivery_identity):
        del delivery_identity
        raise self.error


def _model(
    status=HistoricalBaselineDeliveryStatus.PROCESSED,
    *,
    active_count=1,
):
    delivery = HistoricalBaselineDeliveryView(
        delivery_identity=_DELIVERY_ID,
        source_trigger_identity="hproj.case-hproj-api-001.owner-repair-1",
        payload_digest=_DIGEST,
        source_kind="owner_repair",
        source_domain="orders",
        source_event_identity="orders:repair:1",
        source_version=1,
        partition_key=_CASE_NO,
        projection_sequence=1,
        projector_receipt_identity=_RECEIPT_ID,
        status=status,
        attempt_count=1,
        max_attempts=5,
        next_attempt_at=None,
        lease_owner=None,
        lease_expires_at=None,
        last_error_code=None,
    )
    receipt = HistoricalBaselineReceiptView(
        projector_receipt_identity=_RECEIPT_ID,
        source_trigger_identity=delivery.source_trigger_identity,
        source_trigger_version=1,
        payload_digest=_DIGEST,
        idempotency_key="hproj.case-hproj-api-001.project-1",
        case_no=_CASE_NO,
        order_identity=f"order:{_CASE_NO}",
        catalog_identity=_DIGEST,
        catalog_version=2,
        whole_vector_fingerprint=_DIGEST,
        whole_vector_count=21,
        emitted_occurrence_set_digest=_DIGEST,
        emitted_occurrence_set_count=active_count,
        emitted_occurrence_identities=tuple(
            PreviewFingerprint(f"{index + 30:064x}")
            for index in range(active_count)
        ),
        active_membership_set_digest=_DIGEST,
        active_membership_set_count=active_count,
        umbrella_identity=_UMBRELLA,
        projection_sequence=1,
        current_alert_fingerprint=_ALERT,
        expected_readback_digest=_DIGEST,
        result_state="held_active" if active_count else "projected",
    )
    memberships = tuple(
        HistoricalBaselineMembershipView(
            membership_identity=PreviewFingerprint(f"{index + 3:064x}"),
            set_ordinal=index + 1,
            occurrence_identity=PreviewFingerprint(f"{index + 30:064x}"),
        )
        for index in range(active_count)
    )
    referrals = tuple(
        HistoricalBaselineRepairReferralView(
            step=index + 2,
            contract_id=f"historical.contract.{index + 1}",
            owner_domain="orders",
            repair_target="orders.historical-repair",
            repair_capability="orders.historical_review.remediate",
        )
        for index in range(active_count)
    )
    alert = HistoricalBaselineCurrentAlertView(
        fingerprint=_ALERT,
        definition_code="HISTORICAL-BASELINE-ROOTS-001",
        definition_version=1,
        source_domain="historical_baseline",
        source_identity=_UMBRELLA,
        source_version=1,
        predicate_active=active_count > 0,
        workflow_status="open" if active_count else "resolved",
        workflow_version=1,
        projection_version=1,
        display=HistoricalBaselineAlertDisplayView(
            case_no=_CASE_NO,
            earliest_blocked_step=None if not referrals else referrals[0].step,
            active_count=active_count,
            repair_referrals=referrals,
            projection_fingerprint=_DIGEST,
        ),
    )
    readback = HistoricalBaselinePostCommitReadbackView(
        readback_identity=PreviewFingerprint("d" * 64),
        readback_attempt=1,
        expected_readback_digest=_DIGEST,
        actual_readback_digest=_DIGEST,
        emitted_occurrence_set_digest=_DIGEST,
        emitted_occurrence_set_count=active_count,
        active_membership_set_digest=_DIGEST,
        active_membership_set_count=active_count,
        state_event_set_digest=_DIGEST,
        successor_set_digest=_DIGEST,
        workflow_event_set_digest=_DIGEST,
        current_alert_fingerprint=_ALERT,
        result="exact",
        error_code=None,
    )
    return HistoricalBaselineProjectorReadModel(
        delivery=delivery,
        receipt=receipt,
        active_memberships=memberships,
        post_commit_readback=readback,
        current_alert=alert,
    )


def _pending_model():
    delivery = HistoricalBaselineDeliveryView(
        delivery_identity=_DELIVERY_ID,
        source_trigger_identity="hproj.case-hproj-api-001.baseline-1",
        payload_digest=_DIGEST,
        source_kind="baseline_confirmed",
        source_domain="orders",
        source_event_identity="orders:baseline:1",
        source_version=1,
        partition_key=_CASE_NO,
        projection_sequence=None,
        projector_receipt_identity=None,
        status=HistoricalBaselineDeliveryStatus.PENDING,
        attempt_count=0,
        max_attempts=5,
        next_attempt_at=None,
        lease_owner=None,
        lease_expires_at=None,
        last_error_code=None,
    )
    return HistoricalBaselineProjectorReadModel(
        delivery=delivery,
        receipt=None,
        active_memberships=(),
        post_commit_readback=None,
        current_alert=None,
    )


def test_case_query_returns_strict_projector_readback_and_server_referrals():
    port = _ReadPort(_model())
    application = HistoricalBaselineProjectorQueryApplication(port)

    response = query_latest_historical_baseline_projection(
        case_no=_CASE_NO,
        correlation_header="hproj-api-case-query",
        principal=object(),
        application=application,
    )
    view = HistoricalBaselineProjectorReadModelView.model_validate(response.data)

    assert port.by_case == [_CASE_NO]
    assert view.delivery.status == "processed"
    assert view.receipt is not None
    assert view.receipt.active_membership_set_count == 1
    assert view.current_alert is not None
    assert view.current_alert.display.repair_referrals[0].owner_domain == "orders"
    assert view.reconciliation.status == "processed"
    assert view.reconciliation.referral == "none"


def test_fastapi_route_serializes_the_strict_read_model_without_raw_objects():
    application = HistoricalBaselineProjectorQueryApplication(_ReadPort(_model()))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_historical_order_review_remediator] = (
        lambda: object()
    )
    app.dependency_overrides[get_historical_baseline_projector_query_application] = (
        lambda: application
    )

    response = TestClient(app).get(
        f"/api/v1/orders/{_CASE_NO}/historical-baseline-projector",
        headers={"X-Correlation-ID": "hproj-api-http"},
    )

    assert response.status_code == 200
    view = HistoricalBaselineProjectorReadModelView.model_validate(
        response.json()["data"]
    )
    assert view.delivery.delivery_identity == _DELIVERY_ID
    assert view.current_alert is not None
    assert view.current_alert.definition_code == "HISTORICAL-BASELINE-ROOTS-001"


def test_delivery_query_exposes_outcome_unknown_without_fake_reconcile_mutation():
    model = _model(HistoricalBaselineDeliveryStatus.COMMITTED_UNVERIFIED)
    port = _ReadPort(model)
    response = query_historical_baseline_projection_delivery(
        delivery_identity=_DELIVERY_ID,
        correlation_header="hproj-api-delivery-query",
        principal=object(),
        application=HistoricalBaselineProjectorQueryApplication(port),
    )
    view = HistoricalBaselineProjectorReadModelView.model_validate(response.data)

    assert port.by_delivery == [_DELIVERY_ID]
    assert view.reconciliation.status == "outcome_unknown"
    assert (
        view.reconciliation.reason_code
        == "projector_emitted_occurrence_snapshot_not_persisted"
    )
    assert view.reconciliation.referral == "retry_original_trigger_reconcile"
    assert all(route.methods == {"GET"} for route in router.routes)


def test_pending_case_delivery_remains_visible_and_is_not_ready():
    port = _ReadPort(_pending_model())
    response = query_latest_historical_baseline_projection(
        case_no=_CASE_NO,
        correlation_header=None,
        principal=object(),
        application=HistoricalBaselineProjectorQueryApplication(port),
    )
    view = HistoricalBaselineProjectorReadModelView.model_validate(response.data)

    assert view.receipt is None
    assert view.active_memberships == []
    assert view.current_alert is None
    assert view.reconciliation.status == "not_ready"
    assert view.reconciliation.referral == "wait_for_projector_commit"


def test_not_found_uses_typed_eight_field_error_envelope():
    with pytest.raises(HTTPException) as error:
        query_latest_historical_baseline_projection(
            case_no=_CASE_NO,
            correlation_header="hproj-api-not-found",
            principal=object(),
            application=HistoricalBaselineProjectorQueryApplication(_ReadPort()),
        )

    assert error.value.status_code == 404
    payload = error.value.detail["error"]
    assert payload["category"] == "not_found"
    assert payload["code"] == "historical_baseline_projection_not_found"
    assert set(payload) == {
        "category",
        "code",
        "message",
        "field_errors",
        "domain_blockers",
        "retryable",
        "correlation_id",
        "current_version",
    }


@pytest.mark.parametrize("mysql_code", [1205, 1213, 2003, 2006, 2013])
@pytest.mark.parametrize("error_type", [OperationalError, InterfaceError])
def test_retryable_mysql_read_errors_return_typed_503_with_retry_after(
    mysql_code,
    error_type,
):
    application = HistoricalBaselineProjectorQueryApplication(
        _FailingReadPort(error_type(mysql_code, "database unavailable"))
    )

    with pytest.raises(HTTPException) as error:
        query_latest_historical_baseline_projection(
            case_no=_CASE_NO,
            correlation_header="hproj-api-retryable",
            principal=object(),
            application=application,
        )

    assert error.value.status_code == 503
    assert error.value.headers == {"Retry-After": "1"}
    payload = error.value.detail["error"]
    assert payload["category"] == "unavailable"
    assert payload["code"] == "historical_baseline_projection_unavailable"
    assert payload["retryable"] is True


@pytest.mark.parametrize("error_type", [OperationalError, InterfaceError])
def test_nonretryable_mysql_read_errors_fail_closed_as_typed_500(error_type):
    application = HistoricalBaselineProjectorQueryApplication(
        _FailingReadPort(error_type(1064, "database failure"))
    )

    with pytest.raises(HTTPException) as error:
        query_latest_historical_baseline_projection(
            case_no=_CASE_NO,
            correlation_header="hproj-api-nonretryable",
            principal=object(),
            application=application,
        )

    assert error.value.status_code == 500
    assert error.value.headers is None
    payload = error.value.detail["error"]
    assert payload["category"] == "internal"
    assert payload["code"] == "historical_baseline_projection_failed"
    assert payload["retryable"] is False


def test_public_schema_rejects_extra_fields_and_cross_identity_drift():
    port = _ReadPort(_model())
    response = query_latest_historical_baseline_projection(
        case_no=_CASE_NO,
        correlation_header="hproj-api-schema",
        principal=object(),
        application=HistoricalBaselineProjectorQueryApplication(port),
    )
    payload = dict(response.data)
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        HistoricalBaselineProjectorReadModelView.model_validate(payload)

    payload = dict(response.data)
    payload["reconciliation"] = {
        **payload["reconciliation"],
        "delivery_identity": "f" * 64,
    }
    with pytest.raises(
        ValidationError,
        match="historical_baseline_reconciliation_delivery_mismatch",
    ):
        HistoricalBaselineProjectorReadModelView.model_validate(payload)


def test_public_schema_rejects_mismatched_active_count_and_ordinal():
    response = query_latest_historical_baseline_projection(
        case_no=_CASE_NO,
        correlation_header="hproj-api-conservation",
        principal=object(),
        application=HistoricalBaselineProjectorQueryApplication(_ReadPort(_model())),
    )
    payload = dict(response.data)
    payload["active_memberships"] = [
        {**payload["active_memberships"][0], "set_ordinal": 2}
    ]
    with pytest.raises(
        ValidationError,
        match="historical_baseline_membership_ordinal_mismatch",
    ):
        HistoricalBaselineProjectorReadModelView.model_validate(payload)


def test_application_does_not_expose_write_or_commit_surface():
    application = HistoricalBaselineProjectorQueryApplication(_ReadPort(_model()))

    assert not hasattr(application, "apply")
    assert not hasattr(application, "retry")
    assert not hasattr(application, "reconcile")
    assert not hasattr(application, "commit")

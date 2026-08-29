"""
File: test_line_identity_api_routes.py
Description: 驗證 canonical LINE identity API 的 typed payload、驗證身分與單一登記編排。
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.routes import line_identity
from api.schemas.line_identity import (
    AdminIdentityBindingRequest,
    CanonicalLineReviewDecisionPreviewRequest,
    CanonicalLineReviewDecisionRequest,
    CustomerIdentityApplyRequest,
    CustomerIdentityRequest,
    ProvisionalRegistrationRequest,
    ProvisionalRegistrationPreviewRequest,
)
from domains.line.identities import LineReviewRequestId, LineUserId
from domains.line.identity_binding import LineBindingSubjectType
from domains.line.review import (
    LineReviewDecision,
    LineReviewSnapshot,
    LineReviewStatus,
    LineReviewType,
    build_review_decision_candidate,
)


def test_runtime_config_exposes_only_safe_public_origin(monkeypatch) -> None:
    monkeypatch.setenv("LINE_LIFF_ID", "2000000000-test")
    monkeypatch.setenv("LINE_PUBLIC_BASE_URL", "https://line-test.example.dev/")

    response = line_identity.identity_runtime_config()

    assert response.data.public_base_url == "https://line-test.example.dev"
    monkeypatch.setenv("LINE_PUBLIC_BASE_URL", "https://user:secret@example.dev/path?token=x")
    assert line_identity.identity_runtime_config().data.public_base_url is None
from infrastructure.line.liff_token_verifier import (
    InvalidLiffTokenError,
    LiffVerificationUnavailableError,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, ExpectedVersion
from subsystems.case_import.provisional_registration_types import (
    ProvisionalRegistrationReceipt,
)
from subsystems.line.identity_contracts import (
    LineIdentityApplyResult,
    LineIdentityApplyStatus,
    LineIdentityPreview,
    LineIdentityPreviewStatus,
)
from subsystems.line.review_contracts import (
    ApplyLineReviewDecisionResult,
    LineReviewCommandOutcome,
    PreviewLineReviewDecisionResult,
)


def test_registration_route_uses_combined_identity_application(monkeypatch) -> None:
    captured = []
    application = SimpleNamespace(
        apply_registration=lambda *arguments: captured.append(arguments)
        or (
            ProvisionalRegistrationReceipt(5, 17, 23, "王小美", False, True),
            LineIdentityApplyResult(
                LineIdentityApplyStatus.BOUND,
                LineUserId("U-registration"),
                LineBindingSubjectType.CUSTOMER,
                "17",
            ),
        )
    )
    monkeypatch.setattr(line_identity, "_verified_line_user_id", lambda _: LineUserId("U-registration"))
    monkeypatch.setattr(line_identity, "publish_line_wakeup_best_effort", lambda: None)

    response = line_identity.apply_provisional_registration(_registration_payload(), application)

    assert response.data.identity_status == "bound"
    assert captured[0][0].line_user_id == "U-registration"
    assert captured[0][1] == LineUserId("U-registration")


def test_registration_preview_returns_zero_write_binding_and_payload_fingerprints(monkeypatch) -> None:
    payload_fingerprint = fingerprint_payload({"registration": "payload"})
    preview_fingerprint = fingerprint_payload({"registration": "preview"})
    application = SimpleNamespace(
        preview_registration=lambda *_: SimpleNamespace(
            status="ready",
            expected_binding_version=ExpectedVersion(3),
            payload_fingerprint=payload_fingerprint,
            preview_fingerprint=preview_fingerprint,
        )
    )
    monkeypatch.setattr(line_identity, "_verified_line_user_id", lambda _: LineUserId("U-registration"))

    response = line_identity.preview_provisional_registration(
        _registration_preview_payload(),
        application,
    )

    assert response.data.status == "ready"
    assert response.data.expected_binding_version == 3
    assert response.data.payload_fingerprint == payload_fingerprint.value
    assert response.data.preview_fingerprint == preview_fingerprint.value


def test_customer_apply_wakes_worker_after_committed_application(monkeypatch) -> None:
    calls = []
    wakes = []
    application = SimpleNamespace(
        apply_customer=lambda *arguments: calls.append(arguments) or LineIdentityApplyResult(
            LineIdentityApplyStatus.BOUND,
            LineUserId("U-customer"),
            LineBindingSubjectType.CUSTOMER,
            "17",
            receipt_identity="line-binding:U-customer:1",
        )
    )
    monkeypatch.setattr(line_identity, "get_line_identity_application", lambda: application)
    monkeypatch.setattr(line_identity, "_verified_line_user_id", lambda _: LineUserId("U-customer"))
    monkeypatch.setattr(line_identity, "publish_line_wakeup_best_effort", lambda: wakes.append(True))

    response = line_identity.apply_customer(
        CustomerIdentityApplyRequest(
            flow_id="flow-1",
            name="王小美",
            phone="0912345678",
            expected_version=0,
            preview_fingerprint="a" * 64,
        )
    )

    assert response.data.status == "bound"
    assert len(calls) == 1
    assert wakes == [True]


@pytest.mark.parametrize(
    ("failure", "status_code", "code", "retryable"),
    [
        (InvalidLiffTokenError("raw provider detail"), 401, "liff_token_invalid", False),
        (
            LiffVerificationUnavailableError("raw provider detail"),
            503,
            "liff_verification_unavailable",
            True,
        ),
    ],
)
def test_verified_liff_errors_are_typed_and_do_not_leak_provider_detail(
    monkeypatch,
    failure,
    status_code,
    code,
    retryable,
) -> None:
    verifier = SimpleNamespace(verify=lambda _: (_ for _ in ()).throw(failure))
    monkeypatch.setattr(line_identity, "get_liff_token_verifier", lambda: verifier)

    with pytest.raises(HTTPException) as captured:
        line_identity._verified_line_user_id(
            CustomerIdentityRequest(
                flow_id="flow-1",
                line_id_token="signed-token",
                name="王小美",
                phone="0912345678",
            )
        )

    error = captured.value.detail["error"]
    assert captured.value.status_code == status_code
    assert error["code"] == code
    assert error["retryable"] is retryable
    assert "raw provider detail" not in error["message"]


def test_admin_preview_is_zero_write_intent_and_defers_password_authentication(monkeypatch) -> None:
    captured = []
    application = SimpleNamespace(
        preview_admin=lambda *arguments: captured.append(arguments)
        or LineIdentityPreview(
            LineIdentityPreviewStatus.AUTHENTICATION_PENDING,
            LineUserId("U-admin"),
            None,
            ExpectedVersion(0),
            fingerprint_payload({"admin": "preview"}),
        )
    )
    monkeypatch.setattr(line_identity, "get_line_identity_application", lambda: application)
    monkeypatch.setattr(line_identity, "_verified_line_user_id", lambda _: LineUserId("U-admin"))

    response = line_identity.preview_admin(
        AdminIdentityBindingRequest(
            flow_id="flow-admin",
            username="operator",
            password="secret-value",
        )
    )

    assert response.data.status == "authentication_pending"
    assert response.data.candidate is None
    assert captured[0][2].username == "operator"


def test_registration_uses_verified_line_identity_and_wakes_new_task(monkeypatch) -> None:
    captured = []
    wakes = []
    application = SimpleNamespace(
        apply_registration=lambda *arguments: captured.append(arguments)
        or (
            ProvisionalRegistrationReceipt(5, 17, 23, "王小美", False, True),
            LineIdentityApplyResult(
                LineIdentityApplyStatus.BOUND,
                LineUserId("U-registration"),
                LineBindingSubjectType.CUSTOMER,
                "17",
            ),
        )
    )
    monkeypatch.setattr(line_identity, "_verified_line_user_id", lambda _: LineUserId("U-registration"))
    monkeypatch.setattr(line_identity, "publish_line_wakeup_best_effort", lambda: wakes.append(True))

    response = line_identity.apply_provisional_registration(
        _registration_payload(), application
    )

    assert captured[0][0].line_user_id == "U-registration"
    assert response.data.beclass_record_id == 23
    assert wakes == [True]


def test_registration_maps_customer_owner_conflict_to_typed_409(monkeypatch) -> None:
    application = SimpleNamespace(
        apply_registration=lambda *_: (_ for _ in ()).throw(
            RuntimeError("customer_identity_binding_conflict")
        )
    )
    monkeypatch.setattr(line_identity, "_verified_line_user_id", lambda _: LineUserId("U-registration"))

    with pytest.raises(HTTPException) as captured:
        line_identity.apply_provisional_registration(_registration_payload(), application)

    assert captured.value.status_code == 409
    assert captured.value.detail["code"] == "customer_identity_binding_conflict"


def test_review_route_requires_preview_fingerprint_before_apply(monkeypatch) -> None:
    actor = ActorContext("admin:7", ("line.identity.review",))
    snapshot = LineReviewSnapshot(
        LineReviewRequestId(41),
        LineReviewType.STAFF_VERIFICATION,
        LineReviewStatus.PENDING,
        ExpectedVersion(0),
        LineUserId("U-staff-review"),
        LineBindingSubjectType.STAFF,
        "12",
        fingerprint_payload({"review": 41}),
    )
    candidate = build_review_decision_candidate(
        snapshot,
        LineReviewDecision.APPROVE,
        expected_version=ExpectedVersion(0),
        actor=actor,
        reason="資料核對完成",
    )
    captured = []
    application = SimpleNamespace(
        preview=lambda command: captured.append(command)
        or PreviewLineReviewDecisionResult(snapshot, candidate),
        decide=lambda command: captured.append(command)
        or ApplyLineReviewDecisionResult(LineReviewCommandOutcome.CREATED, snapshot),
    )
    monkeypatch.setattr(line_identity, "get_line_identity_review_application", lambda: application)
    monkeypatch.setattr(line_identity, "admin_actor_context", lambda _: actor)
    monkeypatch.setattr(line_identity, "publish_line_wakeup_best_effort", lambda: None)

    preview = line_identity.preview_review_decision(
        41,
        LineReviewDecision.APPROVE,
        CanonicalLineReviewDecisionPreviewRequest(
            expected_version=0,
            reason="資料核對完成",
        ),
        SimpleNamespace(),
    )
    applied = line_identity.decide_review(
        41,
        LineReviewDecision.APPROVE,
        CanonicalLineReviewDecisionRequest(
            expected_version=0,
            reason="資料核對完成",
            preview_fingerprint=preview.data.preview_fingerprint,
            idempotency_key="review-apply:41",
        ),
        SimpleNamespace(state=SimpleNamespace()),
        SimpleNamespace(),
    )

    assert preview.data.before_status == "pending"
    assert preview.data.after_status == "approved"
    assert captured[1].preview_fingerprint == candidate.fingerprint
    assert applied.data.request_id == 41
    assert applied.data.outcome == "created"
    assert applied.data.receipt_identity == "line-review:41:pending"


def test_direct_review_decision_route_is_retired() -> None:
    with pytest.raises(HTTPException) as captured:
        line_identity.retired_direct_review_decision(
            41,
            LineReviewDecision.APPROVE,
            SimpleNamespace(),
        )

    assert captured.value.status_code == 410
    assert captured.value.detail["code"] == "line_review_preview_required"


def _registration_payload():
    return ProvisionalRegistrationRequest(
        **_registration_preview_payload().model_dump(),
        expected_binding_version=0,
        preview_fingerprint="a" * 64,
    )


def _registration_preview_payload():
    return ProvisionalRegistrationPreviewRequest(
        name="王小美",
        phone="0912345678",
        expected_date="2026-10-01",
        service_days=26,
        address="台北市中山區",
    )

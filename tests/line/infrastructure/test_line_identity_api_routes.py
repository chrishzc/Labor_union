"""HTTP-boundary regressions for canonical LINE identity mutations."""

from types import SimpleNamespace

from api.routes import line_identity
from api.schemas.line_identity import (
    CustomerIdentityRequest,
    ProvisionalRegistrationRequest,
)
from domains.line.identities import LineUserId
from domains.line.identity_binding import LineBindingSubjectType
from subsystems.case_import.provisional_registration_types import (
    ProvisionalRegistrationReceipt,
)
from subsystems.line.identity_contracts import (
    LineIdentityApplyResult,
    LineIdentityApplyStatus,
)


def test_customer_apply_wakes_worker_after_committed_application(monkeypatch) -> None:
    calls = []
    wakes = []
    application = SimpleNamespace(
        apply_customer=lambda *arguments: calls.append(arguments) or LineIdentityApplyResult(
            LineIdentityApplyStatus.BOUND,
            LineUserId("U-customer"),
            LineBindingSubjectType.CUSTOMER,
            "17",
        )
    )
    monkeypatch.setattr(line_identity, "get_line_identity_application", lambda: application)
    monkeypatch.setattr(line_identity, "_verified_line_user_id", lambda _: LineUserId("U-customer"))
    monkeypatch.setattr(line_identity, "publish_line_wakeup_best_effort", lambda: wakes.append(True))

    response = line_identity.apply_customer(
        CustomerIdentityRequest(flow_id="flow-1", name="王小美", phone="0912345678")
    )

    assert response.data.status == "bound"
    assert len(calls) == 1
    assert wakes == [True]


def test_registration_uses_verified_line_identity_and_wakes_new_task(monkeypatch) -> None:
    captured = []
    wakes = []
    application = SimpleNamespace(
        apply=lambda intent: captured.append(intent) or ProvisionalRegistrationReceipt(
            5, 17, 23, "王小美", False, True
        )
    )
    monkeypatch.setattr(line_identity, "_verified_line_user_id", lambda _: LineUserId("U-registration"))
    monkeypatch.setattr(line_identity, "publish_line_wakeup_best_effort", lambda: wakes.append(True))

    response = line_identity.apply_provisional_registration(
        _registration_payload(), application
    )

    assert captured[0].line_user_id == "U-registration"
    assert response.data.beclass_record_id == 23
    assert wakes == [True]


def _registration_payload():
    return ProvisionalRegistrationRequest(
        name="王小美",
        phone="0912345678",
        expected_date="2026-10-01",
        service_days=26,
        address="台北市中山區",
    )

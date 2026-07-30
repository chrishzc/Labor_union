from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.routes import matches
from services.admin_auth_service import AdminPrincipal


def _client() -> TestClient:
    app = FastAPI()
    app.dependency_overrides[matches.require_system_admin] = lambda: _principal()
    app.include_router(matches.router)
    return TestClient(app)


def _payload():
    return {
        "segments": [
            {
                "staff_id": 11,
                "assigned_start_date": "2026-08-01",
                "assigned_end_date": "2026-08-15",
            },
            {
                "staff_id": 22,
                "assigned_start_date": "2026-08-16",
                "assigned_end_date": "2026-08-31",
            },
        ],
        "created_by": "admin-1",
        "as_of": "2026-07-28",
    }


def test_matching_plan_created_is_wrapped_and_forwarded(monkeypatch):
    expected = {
        "plan_id": 7,
        "case_no": "CASE-7",
        "version": 1,
        "status": "proposed",
        "result": "created",
        "segments": [{"segment_order": 1, "staff_id": 11}],
    }
    calls = []

    def fake_create_matching_plan_version(**kwargs):
        calls.append(kwargs)
        return expected

    monkeypatch.setattr(
        matches,
        "create_matching_plan_version",
        fake_create_matching_plan_version,
    )

    response = _client().post(
        "/api/v1/orders/CASE-7/matching-plans",
        json=_payload(),
    )

    assert response.status_code == 200
    assert response.json()["data"] == expected
    assert calls == [
        {
            "case_no": "CASE-7",
            "segments": _payload()["segments"],
            "created_by": "admin-1",
            "as_of": "2026-07-28",
        }
    ]


def test_matching_plan_existing_is_not_rewritten(monkeypatch):
    expected = {
        "plan_id": 7,
        "case_no": "CASE-7",
        "version": 3,
        "status": "proposed",
        "result": "existing",
        "segments": [{"segment_order": 1, "staff_id": 11}],
    }
    monkeypatch.setattr(
        matches,
        "create_matching_plan_version",
        lambda **kwargs: expected,
    )

    response = _client().post(
        "/api/v1/orders/CASE-7/matching-plans",
        json=_payload(),
    )

    assert response.status_code == 200
    assert response.json()["data"] == expected
    assert response.json()["data"]["result"] == "existing"
    assert response.json()["data"]["version"] == 3


def test_matching_plan_invalid_shape_does_not_call_service(monkeypatch):
    called = False

    def fake_create_matching_plan_version(**kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        matches,
        "create_matching_plan_version",
        fake_create_matching_plan_version,
    )

    payload = _payload()
    del payload["as_of"]
    response = _client().post(
        "/api/v1/orders/CASE-7/matching-plans",
        json=payload,
    )

    assert response.status_code == 422
    assert called is False


def test_matching_plan_internal_error_is_not_disclosed(monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("database password and SQL details")

    monkeypatch.setattr(matches, "create_matching_plan_version", fail)

    response = _client().post(
        "/api/v1/orders/CASE-7/matching-plans",
        json=_payload(),
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "建立多月嫂配對計畫版本失敗"}
    assert "database password" not in response.text


@pytest.mark.parametrize(
    ("message", "expected_status"),
    [
        ("case not found", 404),
        ("case is not in negotiation stage", 409),
        ("segments must be contiguous without gaps", 422),
    ],
)
def test_matching_plan_value_errors_have_stable_http_status(
    monkeypatch,
    message,
    expected_status,
):
    monkeypatch.setattr(
        matches,
        "create_matching_plan_version",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError(message)),
    )

    response = _client().post(
        "/api/v1/orders/CASE-7/matching-plans",
        json=_payload(),
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": message}


def test_matching_plan_rejects_spoofed_created_by(monkeypatch):
    called = False

    def fake_create(**_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(matches, "create_matching_plan_version", fake_create)
    payload = _payload()
    payload["created_by"] = "other-admin"

    response = _client().post(
        "/api/v1/orders/CASE-7/matching-plans",
        json=payload,
    )

    assert response.status_code == 403
    assert called is False


def _principal(username: str = "admin-1") -> AdminPrincipal:
    return AdminPrincipal(
        id=1,
        username=username,
        display_name="Admin",
        role="system_admin",
    )


def test_matching_communication_routes_are_registered():
    paths = {route.path for route in matches.router.routes}
    assert {
        "/api/v1/orders/{case_no}/matching-plans/active",
        "/api/v1/orders/{case_no}/matching-plans/{plan_id}/contact-state",
        "/api/v1/orders/{case_no}/matching-plans/{plan_id}/segments/{segment_id}/information",
        "/api/v1/orders/{case_no}/matching-plans/{plan_id}/segments/{segment_id}/willingness",
        "/api/v1/orders/{case_no}/matching-plans/{plan_id}/resumes",
        "/api/v1/orders/{case_no}/matching-plans/{plan_id}/cancel",
    }.issubset(paths)


def test_active_matching_plan_route_forwards_case(monkeypatch):
    monkeypatch.setattr(
        matches,
        "get_active_matching_plan_state",
        lambda case_no: {"plan": {"case_no": case_no}},
    )

    response = matches.get_active_matching_plan_state_route(
        "CASE-7",
        _principal(),
    )

    assert response.data == {"plan": {"case_no": "CASE-7"}}


def test_matching_information_route_forwards_authenticated_actor(monkeypatch):
    calls = []
    monkeypatch.setattr(
        matches,
        "send_matching_plan_information",
        lambda *args: calls.append(args) or {"status": "queued"},
    )

    response = matches.send_matching_plan_information_route(
        matches.MatchingPlanInformationRequest(
            event_key="info-1",
            actor="admin-1",
            info_type=1,
        ),
        "CASE-7",
        8,
        9,
        _principal(),
    )

    assert response.data == {"status": "queued"}
    assert calls == [("CASE-7", 8, 9, 1, "info-1", "admin-1")]


def test_matching_resume_route_rejects_spoofed_actor(monkeypatch):
    called = False

    def fake_send(*args):
        nonlocal called
        called = True

    monkeypatch.setattr(matches, "send_matching_plan_resumes", fake_send)
    with pytest.raises(Exception) as captured:
        matches.send_matching_plan_resumes_route(
            matches.MatchingPlanResumeRequest(
                event_key="resume-1",
                actor="other-admin",
                note="共同服務",
            ),
            "CASE-7",
            8,
            _principal(),
        )

    assert getattr(captured.value, "status_code", None) == 403
    assert called is False


def test_anomaly_center_resume_route_uses_legacy_service(monkeypatch):
    calls = []
    monkeypatch.setattr(
        matches,
        "send_legacy_resume_for_case",
        lambda case_no: calls.append(case_no) or 19,
    )

    response = matches.send_resume_for_case("CASE-7", _principal())

    assert response.data == {"match_id": 19}
    assert calls == ["CASE-7"]

from api.routes import assignment_schedule_rest_dates as route
from api.schemas.orders import AssignmentLeaveResolutionBatchPreviewRequest


def _request():
    return {
        "contract_version": "assignment-leave-substitution-batch-preview/v1",
        "case_no": "CASE-1",
        "original_assignment_id": 7,
        "items": [
            {
                "original_schedule_id": 10,
                "work_date": "2026-08-10",
            "resolution_type": "defer_following_assignments",
            "substitute_staff_id": None,
            "is_double_pay": False,
            },
            {
                "original_schedule_id": 11,
                "work_date": "2026-08-15",
            "resolution_type": "substitute",
            "substitute_staff_id": 9,
            "is_double_pay": False,
            },
        ],
    }


def test_batch_preview_route_forwards_one_request_and_returns_one_fingerprint(monkeypatch):
    captured = []

    def fake_preview(request):
        captured.append(request)
        return {
            "status": "ready",
            "preview_fingerprint": "a" * 64,
            "service_plan_transition": {"before": {}, "after": {}},
        }

    monkeypatch.setattr(route, "preview_assignment_leave_resolution_batch", fake_preview)
    response = route.preview_assignment_leave_resolution_batch_route(
        AssignmentLeaveResolutionBatchPreviewRequest(**_request()), 7
    )
    assert captured == [_request()]
    assert response.data["preview_fingerprint"] == "a" * 64


def test_batch_preview_route_rejects_path_assignment_mismatch(monkeypatch):
    called = False

    def fake_preview(_request):
        nonlocal called
        called = True

    monkeypatch.setattr(route, "preview_assignment_leave_resolution_batch", fake_preview)
    try:
        route.preview_assignment_leave_resolution_batch_route(
            AssignmentLeaveResolutionBatchPreviewRequest(**_request()), 8
        )
    except Exception as error:
        assert getattr(error, "status_code", None) == 422
    else:
        raise AssertionError("expected HTTPException")
    assert called is False

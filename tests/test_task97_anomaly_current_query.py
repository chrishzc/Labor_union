"""Current-only Anomalies list contract and signed cursor regression."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.anomaly_registry import get_current_issue_query_application
from api.main import app
from domains.anomalies.current_issue import CurrentIssueCandidate, CurrentIssueProjection
from subsystems.anomalies.current_issue_query import (
    CurrentIssueCursorCodec,
    CurrentIssueListRequest,
    CurrentIssueQueryApplication,
)


NOW = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
SECRET = b"task97-current-issue-query-secret"


def _projection(key: str, *, blocking: bool, severity: str, minutes: int) -> CurrentIssueProjection:
    candidate = CurrentIssueCandidate(
        key,
        "SCHEDULE-006",
        "scheduling",
        "assignment",
        "assignment",
        key,
        1,
        severity,
        blocking,
        {},
        {"case_no": key, "generation": 1},
    )
    started = NOW + timedelta(minutes=minutes)
    return CurrentIssueProjection(candidate, started, started)


class _Repository:
    def __init__(self, rows):
        self.rows = tuple(rows)
        self.calls = []

    def query_current_page(self, request, after, fetch_limit):
        self.calls.append((request, after, fetch_limit))
        rows = self.rows
        if after is not None:
            last_key = after[3]
            rows = rows[next(index for index, row in enumerate(rows) if row.issue_key == last_key) + 1 :]
        return rows[:fetch_limit]


def test_signed_cursor_is_filter_bound_and_replays_next_page() -> None:
    rows = (
        _projection("ci_" + "1" * 64, blocking=True, severity="blocking", minutes=0),
        _projection("ci_" + "2" * 64, blocking=False, severity="warning", minutes=1),
    )
    repository = _Repository(rows)
    application = CurrentIssueQueryApplication(repository, CurrentIssueCursorCodec(SECRET))
    request = CurrentIssueListRequest(owner_domain="scheduling", limit=1)

    first = application.query(request)
    second = application.query(
        CurrentIssueListRequest(owner_domain="scheduling", limit=1, cursor=first.next_cursor)
    )

    assert [item.issue_key for item in first.items] == [rows[0].issue_key]
    assert [item.issue_key for item in second.items] == [rows[1].issue_key]
    assert first.next_cursor is not None
    assert second.next_cursor is None
    assert repository.calls[0][2] == 2

    try:
        application.query(
            CurrentIssueListRequest(owner_domain="orders", limit=1, cursor=first.next_cursor)
        )
    except ValueError as error:
        assert str(error) == "anomaly_cursor_invalid"
    else:  # pragma: no cover
        raise AssertionError("cursor reuse with different filters must fail closed")


def test_cursor_tampering_fails_closed() -> None:
    row = _projection("ci_" + "3" * 64, blocking=True, severity="blocking", minutes=0)
    codec = CurrentIssueCursorCodec(SECRET)
    request = CurrentIssueListRequest(limit=1)
    cursor = codec.encode(request, row)

    try:
        codec.decode(CurrentIssueListRequest(limit=1, cursor=cursor[:-1] + "A"))
    except ValueError as error:
        assert str(error) == "anomaly_cursor_invalid"
    else:  # pragma: no cover
        raise AssertionError("tampered cursor must fail closed")


def test_current_list_route_has_only_current_filters_and_typed_page() -> None:
    row = _projection("ci_" + "4" * 64, blocking=True, severity="blocking", minutes=0)
    application = CurrentIssueQueryApplication(_Repository((row,)), CurrentIssueCursorCodec(SECRET))
    app.dependency_overrides[require_system_admin] = lambda: object()
    app.dependency_overrides[get_current_issue_query_application] = lambda: application
    client = TestClient(app)
    try:
        response = client.get("/api/v1/anomalies?owner_domain=scheduling&limit=50")
        obsolete = client.get("/api/v1/anomalies?active_only=true")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["data"] == {
        "items": [
            {
                "issue_key": row.issue_key,
                "definition_code": "SCHEDULE-006",
                "owner_domain": "scheduling",
                "severity": "blocking",
                "blocking": True,
                "episode_started_at": NOW.isoformat().replace("+00:00", "Z"),
                "last_verified_at": NOW.isoformat().replace("+00:00", "Z"),
            }
        ],
        "next_cursor": None,
    }
    assert obsolete.status_code == 422


def test_current_list_route_maps_invalid_cursor_to_stable_code() -> None:
    application = CurrentIssueQueryApplication(_Repository(()), CurrentIssueCursorCodec(SECRET))
    app.dependency_overrides[require_system_admin] = lambda: object()
    app.dependency_overrides[get_current_issue_query_application] = lambda: application
    client = TestClient(app)
    try:
        response = client.get("/api/v1/anomalies?cursor=malformed")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "anomaly_cursor_invalid"

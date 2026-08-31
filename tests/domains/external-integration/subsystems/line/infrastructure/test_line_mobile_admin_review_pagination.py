"""
File: test_line_mobile_admin_review_pagination.py
Description: 驗證 Mobile Admin 月嫂審核採真正 numbered server pagination，且 canonical cursor 查詢不退步。
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.routes import line_identity, line_mobile_admin
from api.dependencies.admin_auth import AdminPrincipal
from domains.line.identity_binding import LineBindingSubjectType, LineIdentityBindingStatus
from subsystems.line.identity_management_contracts import LineIdentityCurrentFactReadbackStatus
from domains.line.review import LineReviewStatus, LineReviewType
from infrastructure.mysql.line_identity_review_repository import (
    MySqlLineIdentityReviewRepository,
    _review_list_statement,
)
from subsystems.line.review_contracts import LineReviewListQuery, LineReviewPage


def _assignment_plan_query_payload(case_no="CASE-1"):
    return {
        "case_no": case_no,
        "order_version": 2,
        "scheduling_version": 3,
        "scheduling_generation": 4,
        "client_finance_version": 5,
        "payroll_version": 6,
        "contracted_service_days": 1,
        "service_hours_per_day": 8,
        "service_started": False,
        "assignments": [
            {
                "assignment_id": 11,
                "candidate_key": None,
                "staff_id": 7,
                "sequence": 1,
                "assigned_start_date": "2026-09-01",
                "assigned_end_date": "2026-09-01",
                "official_service_dates": ["2026-09-01"],
                "actual_hours": None,
                "lineage_source_assignment_ids": [],
            }
        ],
    }


def _assignment_plan_preview_payload(case_no="CASE-1"):
    payload = _assignment_plan_query_payload(case_no)
    return {
        **{key: value for key, value in payload.items() if key not in {"contracted_service_days", "service_hours_per_day", "service_started"}},
        "cancelled_assignment_ids": [],
        "preview_fingerprint": "a" * 64,
    }


class _Cursor:
    def __init__(self) -> None:
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def execute(self, sql, parameters) -> None:
        self.calls.append((sql, parameters))

    def fetchone(self):
        return {"total": 123}

    def fetchall(self):
        return []


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def test_numbered_review_repository_counts_and_pages_in_sql() -> None:
    cursor = _Cursor()
    query = LineReviewListQuery(
        statuses=(LineReviewStatus.PENDING,),
        review_types=(LineReviewType.STAFF_VERIFICATION,),
        page=3,
        page_size=25,
    )

    result = MySqlLineIdentityReviewRepository(_Connection(cursor)).list(query)

    assert len(cursor.calls) == 2
    count_sql, count_parameters = cursor.calls[0]
    page_sql, page_parameters = cursor.calls[1]
    assert count_sql.startswith("SELECT COUNT(*) AS total FROM line_review_requests WHERE ")
    assert "review_status IN (%s)" in count_sql
    assert "review_type IN (%s)" in count_sql
    assert count_parameters == ("pending", "staff_verification")
    assert page_sql.endswith("ORDER BY id DESC LIMIT %s OFFSET %s")
    assert page_parameters == ("pending", "staff_verification", 25, 50)
    assert result == LineReviewPage((), None, 3, 25, 123)


def test_mobile_review_route_returns_numbered_envelope_without_cursor(monkeypatch) -> None:
    captured = []
    application = SimpleNamespace(
        list=lambda query: captured.append(query) or LineReviewPage((), None, 2, 25, 123)
    )
    monkeypatch.setattr(line_mobile_admin, "_mobile_admin_actor", lambda _: SimpleNamespace())
    monkeypatch.setattr(
        line_mobile_admin,
        "get_line_identity_review_application",
        lambda: application,
    )
    payload = line_mobile_admin._ReviewListRequest.model_validate(
        {
            "line_id_token": "verified-token",
            "review_status": "pending",
            "review_type": "staff_verification",
            "page": 2,
            "page_size": 25,
        }
    )

    response = line_mobile_admin.identity_reviews(payload)

    assert captured == [
        LineReviewListQuery(
            statuses=(LineReviewStatus.PENDING,),
            review_types=(LineReviewType.STAFF_VERIFICATION,),
            page=2,
            page_size=25,
        )
    ]
    assert response.data.model_dump() == {
        "items": [],
        "page": 2,
        "page_size": 25,
        "total": 123,
    }


def test_mobile_scheduling_review_forwards_query_preview_apply_and_fresh_readback(monkeypatch) -> None:
    captured = {"queries": 0, "preview": [], "apply": []}
    receipt = object()

    class _Application:
        def query(self, case_no):
            captured["queries"] += 1
            assert case_no == "CASE-1"
            return object()

        def preview(self, request):
            captured["preview"].append(request)
            return object()

        def apply(self, request):
            captured["apply"].append(request)
            return receipt

    application = _Application()
    monkeypatch.setattr(line_mobile_admin, "_scheduling_mobile_actor", lambda *_: SimpleNamespace(actor_id="admin:7"))
    monkeypatch.setattr(line_mobile_admin, "_query_payload", lambda _: _assignment_plan_query_payload())
    monkeypatch.setattr(line_mobile_admin, "_scheduling_review_preview_payload", lambda _: _assignment_plan_preview_payload())
    monkeypatch.setattr(
        line_mobile_admin,
        "_materialize",
        lambda value: {
            "case_no": "CASE-1",
            "order_version": 2,
            "scheduling_generation": 5,
            "scheduling_version": 4,
            "client_finance_version": 6,
            "payroll_version": 7,
            "cancelled_assignment_ids": [],
            "created_assignment_keys": ["CASE-1:1"],
            "preview_fingerprint": "a" * 64,
        } if value is receipt else value,
    )

    query_response = line_mobile_admin.scheduling_review_query(
        line_mobile_admin._SchedulingReviewQueryRequest.model_validate(
            {"line_id_token": "verified-token", "case_no": "CASE-1"}
        ),
        application,
    )
    assert query_response.data.case_no == "CASE-1"

    segment = {
        "staff_id": 7,
        "assigned_start_date": "2026-09-01",
        "assigned_end_date": "2026-09-01",
        "official_service_dates": ["2026-09-01"],
    }
    preview_response = line_mobile_admin.scheduling_review_preview(
        line_mobile_admin._SchedulingReviewPreviewRequest.model_validate(
            {"line_id_token": "verified-token", "case_no": "CASE-1", "segments": [segment]}
        ),
        application,
    )
    assert preview_response.data.preview_fingerprint == "a" * 64
    assert "client_finance_impact" not in preview_response.data.model_dump()
    assert "payroll_impact" not in preview_response.data.model_dump()
    assert "orders_impact" not in preview_response.data.model_dump()
    assert captured["preview"][0].intent.segments[0].staff_id == 7

    apply_response = line_mobile_admin.scheduling_review_apply(
        line_mobile_admin._SchedulingReviewApplyRequest.model_validate(
            {
                "line_id_token": "verified-token",
                "case_no": "CASE-1",
                "segments": [segment],
                "expected_order_version": 2,
                "expected_scheduling_version": 3,
                "expected_client_finance_version": 5,
                "expected_payroll_version": 6,
                "preview_fingerprint": "a" * 64,
                "idempotency_key": "mobile-scheduling-review:case-1:1",
                "reason": "人工確認排班調整",
            }
        ),
        application,
    )
    assert len(captured["apply"]) == 1
    assert apply_response.data.receipt.case_no == "CASE-1"
    assert apply_response.data.readback.case_no == "CASE-1"
    assert captured["queries"] == 2


def test_scheduling_mobile_auth_uses_persisted_session_and_current_role_scoped_fact(monkeypatch) -> None:
    principal = AdminPrincipal(7, "reviewer", "Reviewer", "line_agent")
    fact = SimpleNamespace(
        root_status=LineIdentityBindingStatus.BOUND,
        readback_status=LineIdentityCurrentFactReadbackStatus.COMPLETE,
        root_bindings=(SimpleNamespace(
            subject_type=LineBindingSubjectType.ADMIN,
            subject_reference="7",
        ),),
    )
    monkeypatch.setattr(
        line_mobile_admin,
        "get_liff_token_verifier",
        lambda: SimpleNamespace(verify=lambda _: SimpleNamespace(line_user_id="U-admin")),
    )
    actor = line_mobile_admin._scheduling_mobile_actor(
        "verified-token",
        principal,
        SimpleNamespace(current_fact=lambda line_user_id: fact),
    )

    assert actor.actor_id == "admin:7"
    assert "line.review.decide" in actor.permission_scope


def test_scheduling_mobile_auth_rejects_legacy_or_unpersisted_identity(monkeypatch) -> None:
    monkeypatch.setattr(
        line_mobile_admin,
        "get_liff_token_verifier",
        lambda: SimpleNamespace(verify=lambda _: SimpleNamespace(line_user_id="U-admin")),
    )
    with pytest.raises(HTTPException) as captured:
        line_mobile_admin._scheduling_mobile_actor(
            "verified-token",
            AdminPrincipal(None, "development-bypass", "Local", "system_admin"),
            SimpleNamespace(),
        )

    assert captured.value.status_code == 403


def test_canonical_review_numbered_route_is_additive(monkeypatch) -> None:
    captured = []
    application = SimpleNamespace(
        list=lambda query: captured.append(query) or LineReviewPage((), None, 2, 25, 123)
    )
    monkeypatch.setattr(
        line_identity,
        "get_line_identity_review_application",
        lambda: application,
    )

    response = line_identity.list_reviews_numbered(
        review_status=LineReviewStatus.PENDING,
        review_type=LineReviewType.STAFF_VERIFICATION,
        page=2,
        page_size=25,
    )

    assert captured == [
        LineReviewListQuery(
            statuses=(LineReviewStatus.PENDING,),
            review_types=(LineReviewType.STAFF_VERIFICATION,),
            page=2,
            page_size=25,
        )
    ]
    assert response.data.model_dump() == {
        "items": [],
        "page": 2,
        "page_size": 25,
        "total": 123,
    }


def test_canonical_review_get_keeps_keyset_cursor_contract(monkeypatch) -> None:
    query = LineReviewListQuery(page_size=25, cursor="42")
    sql, parameters = _review_list_statement(query)
    assert "id < %s" in sql
    assert "OFFSET" not in sql
    assert parameters == (42, 26)

    application = SimpleNamespace(list=lambda _: LineReviewPage((), "17"))
    monkeypatch.setattr(
        line_identity,
        "get_line_identity_review_application",
        lambda: application,
    )
    response = line_identity.list_reviews(page_size=25, cursor="42")

    assert response.data.items == []
    assert response.data.next_cursor == "17"

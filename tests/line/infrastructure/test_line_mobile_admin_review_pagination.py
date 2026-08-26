"""
File: test_line_mobile_admin_review_pagination.py
Description: 驗證 Mobile Admin 月嫂審核採真正 numbered server pagination，且 canonical cursor 查詢不退步。
"""

from types import SimpleNamespace

from api.routes import line_identity, line_mobile_admin
from domains.line.review import LineReviewStatus, LineReviewType
from infrastructure.mysql.line_identity_review_repository import (
    MySqlLineIdentityReviewRepository,
    _review_list_statement,
)
from subsystems.line.review_contracts import LineReviewListQuery, LineReviewPage


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

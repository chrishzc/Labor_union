"""
File: test_import_warning_auto_resolution_guard.py
Description: 驗證 legacy 匯入警示只能依明列規則書終態契約自動解除。
"""

from types import SimpleNamespace

import pytest

from infrastructure.mysql import import_warning_auto_resolution as subject
from subsystems.case_import import hcm_resubmission_outbox_consumer as hcm_consumer


def test_unknown_terminal_predicate_fails_before_any_tracking_write(monkeypatch) -> None:
    monkeypatch.setattr(
        subject,
        "_append_auto_resolved_event",
        lambda *_args, **_kwargs: pytest.fail("must not write"),
    )

    with pytest.raises(
        ValueError,
        match="import_warning_auto_resolution_rulebook_contract_missing",
    ):
        subject._resolve_rows(
            object(),
            (_row("HCM-FIELD-001"),),
            owner_event_identity="event-1",
            projector_identity="projector-1",
            terminal_predicate="event_received",
        )


def test_terminal_predicate_cannot_resolve_another_logical_code(monkeypatch) -> None:
    monkeypatch.setattr(
        subject,
        "_append_auto_resolved_event",
        lambda *_args, **_kwargs: pytest.fail("must not write"),
    )

    with pytest.raises(
        ValueError,
        match="import_warning_auto_resolution_predicate_mismatch",
    ):
        subject._resolve_rows(
            object(),
            (_row("FINANCE-ROW-001"),),
            owner_event_identity="event-1",
            projector_identity="projector-1",
            terminal_predicate=subject.HCM_FIELD_CORRECTION_TERMINAL_PREDICATE,
        )


def test_hcm_field_terminal_contract_allows_exact_owner_projection(monkeypatch) -> None:
    captured = []
    monkeypatch.setattr(
        subject,
        "_append_auto_resolved_event",
        lambda _connection, row, **_kwargs: captured.append(row["logical_code"]),
    )

    count = subject._resolve_rows(
        object(),
        (_row("HCM-FIELD-002"),),
        owner_event_identity="event-1",
        projector_identity="projector-1",
        terminal_predicate=subject.HCM_FIELD_CORRECTION_TERMINAL_PREDICATE,
    )

    assert count == 1
    assert captured == ["HCM-FIELD-002"]


def test_hcm_consumer_payload_requires_canonical_review_identity() -> None:
    assert hcm_consumer._payload(
        {"event_identity": "event-1", "review_identity": "review-1"}
    ) == {"event_identity": "event-1", "review_identity": "review-1"}
    with pytest.raises(ValueError, match="outbox_payload_invalid"):
        hcm_consumer._payload(
            {"event_identity": "event-1", "occurrence_identity": "legacy-warning"}
        )


def test_hcm_consumer_does_not_use_legacy_occurrence_for_fresh_guard() -> None:
    calls = []

    class _Repository:
        def load_facts(self, review_identity, *, for_update):
            calls.append((review_identity, for_update))
            return SimpleNamespace(
                review_identity="review-1",
                review_version=4,
                logical_code="HCM-FIELD-001",
                root_fingerprint="current-root",
                case_no="CASE-1",
                client_id=5,
                review_binding_id=7,
            )

    class _Runtime:
        def hcm_resubmission_repository(self, _connection):
            return _Repository()

    hcm_consumer._require_fresh_terminal_root(
        "connection",
        {
            "event_identity": "event-1",
            "canonical_review_identity": "review-1",
            "expected_review_version": 3,
            "resulting_review_version": 4,
            "case_no": "CASE-1",
            "client_id": 5,
            "review_binding_id": 7,
            "root_after_fingerprint": "current-root",
            "prior_occurrence_id": 3,
        },
        {"event_identity": "event-1", "review_identity": "review-1", "occurrence_identity": "legacy"},
        _Runtime(),
    )
    assert calls == [("review-1", True)]


def test_hcm_claim_serializes_pending_events_for_same_review() -> None:
    connection = _ClaimConnection()

    assert hcm_consumer._claim(connection) is None

    statement = connection.statement
    assert "NOT EXISTS" in statement
    assert "earlier_event.review_binding_id=event.review_binding_id" in statement
    assert "earlier.id<outbox.id" in statement
    assert "earlier.published_at IS NULL" in statement


def test_hcm_consumer_accepts_canonical_repository_payload_and_replay_is_noop() -> None:
    event = {
        "id": 11,
        "bounded_snapshot": {
            "event_identity": "event-1",
            "review_identity": "review-1",
        },
        "correction_event_id": 7,
        "event_identity": "event-1",
        "canonical_review_identity": "review-1",
        "expected_review_version": 3,
        "resulting_review_version": 4,
        "case_no": "CASE-1",
        "client_id": 5,
        "review_binding_id": 7,
        "root_after_fingerprint": "current-root",
    }
    connection = _ConsumeConnection(event)

    class _Repository:
        def load_facts(self, review_identity, *, for_update):
            assert (review_identity, for_update) == ("review-1", True)
            return SimpleNamespace(
                review_identity="review-1",
                review_version=4,
                logical_code="HCM-FIELD-001",
                root_fingerprint="current-root",
                case_no="CASE-1",
                client_id=5,
                review_binding_id=7,
            )

    class _Runtime:
        def hcm_resubmission_repository(self, _connection):
            return _Repository()

        def failure_unit_of_work(self, _connection):
            return _NoopUow()

    runtime = _Runtime()
    assert hcm_consumer.consume_hcm_resubmission_outbox(connection, runtime=runtime) == 1
    assert connection.commits == 1
    assert hcm_consumer.consume_hcm_resubmission_outbox(connection, runtime=runtime) == 0


def test_hcm_consumer_rejects_legacy_only_payload_before_repository_access() -> None:
    event = {
        "id": 12,
        "bounded_snapshot": {
            "event_identity": "event-legacy",
            "occurrence_identity": "warning-1",
        },
        "correction_event_id": 8,
        "event_identity": "event-legacy",
        "canonical_review_identity": "review-1",
        "expected_review_version": 0,
        "resulting_review_version": 1,
        "case_no": "CASE-1",
        "client_id": 5,
        "review_binding_id": 7,
        "root_after_fingerprint": "current-root",
    }
    connection = _ConsumeConnection(event)
    accessed = []

    class _Runtime:
        def hcm_resubmission_repository(self, _connection):
            accessed.append(True)
            raise AssertionError("legacy payload must fail before loading canonical facts")

        def failure_unit_of_work(self, _connection):
            return _NoopUow()

    assert hcm_consumer.consume_hcm_resubmission_outbox(connection, runtime=_Runtime()) == 0
    assert accessed == []
    assert connection.rollbacks >= 1


def test_hcm_auto_resolution_rechecks_current_owner_root(monkeypatch) -> None:
    class _Repository:
        def __init__(self, connection) -> None:
            assert connection == "connection"

        def load_facts(self, review_identity, *, for_update):
            assert review_identity == "review-1"
            assert for_update is True
            return SimpleNamespace(
                review_identity="review-1",
                review_version=4,
                logical_code="HCM-FIELD-001",
                root_fingerprint="current-root",
                case_no="CASE-1",
                client_id=5,
                review_binding_id=7,
            )

    class _Runtime:
        def hcm_resubmission_repository(self, _connection):
            return _Repository("connection")

    hcm_consumer._require_fresh_terminal_root(
        "connection",
        {
            "event_identity": "event-1",
            "canonical_review_identity": "review-1",
            "expected_review_version": 3,
            "resulting_review_version": 4,
            "case_no": "CASE-1",
            "client_id": 5,
            "review_binding_id": 7,
            "root_after_fingerprint": "current-root",
        },
        {"event_identity": "event-1", "review_identity": "review-1"},
        _Runtime(),
    )


def test_hcm_auto_resolution_rejects_root_drift_after_apply(monkeypatch) -> None:
    class _Repository:
        def __init__(self, _connection) -> None:
            pass

        def load_facts(self, _review_identity, *, for_update):
            assert for_update is True
            return SimpleNamespace(
                review_identity="review-1",
                review_version=4,
                logical_code="HCM-FIELD-001",
                root_fingerprint="newer-root",
                case_no="CASE-1",
                client_id=5,
                review_binding_id=7,
            )

    class _Runtime:
        def hcm_resubmission_repository(self, _connection):
            return _Repository(_connection)

    with pytest.raises(
        ValueError,
        match="hcm_resubmission_auto_resolution_root_stale",
    ):
        hcm_consumer._require_fresh_terminal_root(
            object(),
            {
                "event_identity": "event-1",
                "canonical_review_identity": "review-1",
                "expected_review_version": 3,
                "resulting_review_version": 4,
                "case_no": "CASE-1",
                "client_id": 5,
                "review_binding_id": 7,
                "root_after_fingerprint": "applied-root",
            },
            {"event_identity": "event-1", "review_identity": "review-1"},
            _Runtime(),
        )


@pytest.mark.parametrize(
    ("event_overrides", "error"),
    [
        ({"event_identity": "other-event"}, "event_mismatch"),
        ({"case_no": "OTHER"}, "binding_mismatch"),
        ({"client_id": 99}, "binding_mismatch"),
        ({"review_binding_id": 99}, "binding_mismatch"),
    ],
)
def test_hcm_auto_resolution_rejects_cross_event_or_binding(
    monkeypatch,
    event_overrides,
    error,
) -> None:
    class _Repository:
        def __init__(self, _connection) -> None:
            pass

        def load_facts(self, _review_identity, *, for_update):
            assert for_update is True
            return SimpleNamespace(
                review_identity="review-1",
                review_version=4,
                logical_code="HCM-FIELD-001",
                root_fingerprint="current-root",
                case_no="CASE-1",
                client_id=5,
                review_binding_id=7,
            )

    class _Runtime:
        def hcm_resubmission_repository(self, _connection):
            return _Repository(_connection)
    event = {
        "event_identity": "event-1",
        "canonical_review_identity": "review-1",
        "expected_review_version": 3,
        "resulting_review_version": 4,
        "case_no": "CASE-1",
        "client_id": 5,
        "review_binding_id": 7,
        "root_after_fingerprint": "current-root",
        **event_overrides,
    }

    with pytest.raises(ValueError, match=error):
        hcm_consumer._require_fresh_terminal_root(
            object(),
            event,
            {"event_identity": "event-1", "review_identity": "review-1"},
            _Runtime(),
        )


def _row(logical_code: str):
    return {
        "id": 1,
        "occurrence_identity": "warning-1",
        "logical_code": logical_code,
        "tracking_status": "open",
        "tracking_version": 1,
    }


def _aggregate_row(status: str | None, issue_code: str):
    return {"tracking_status": status, "issue_codes": [issue_code]}


class _ClaimCursor:
    def __init__(self, connection) -> None:
        self._connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, _parameters=None):
        self._connection.statement = statement

    def fetchone(self):
        return None


class _ClaimConnection:
    statement = ""

    def cursor(self):
        return _ClaimCursor(self)


class _NoopUow:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        return None


class _ConsumeCursor:
    def __init__(self, connection):
        self._connection = connection
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, _parameters=None):
        if statement.lstrip().startswith("UPDATE case_import_hcm_correction_outbox SET published_at"):
            self.rowcount = 1
        elif statement.lstrip().startswith("UPDATE case_import_hcm_correction_outbox SET attempts"):
            self.rowcount = 1

    def fetchone(self):
        event = self._connection.pending_event
        self._connection.pending_event = None
        return event


class _ConsumeConnection:
    def __init__(self, event):
        self.pending_event = event
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return _ConsumeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

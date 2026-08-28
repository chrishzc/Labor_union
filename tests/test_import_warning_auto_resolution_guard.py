"""
File: test_import_warning_auto_resolution_guard.py
Description: 驗證 legacy 匯入警示只能依明列規則書終態契約自動解除。
"""

from types import SimpleNamespace

import pytest

from infrastructure.mysql import import_warning_auto_resolution as subject
from subsystems.anomalies import hcm_resubmission_outbox_consumer as hcm_consumer


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


def test_review_aggregate_keeps_umbrella_active_until_last_occurrence() -> None:
    review = {
        "review_identity": "review-1",
        "source_row": 7,
        "masked_case_identity": "CASE-***-1",
    }
    first = subject._review_resolution_state(
        review,
        (
            _aggregate_row("auto_resolved", "hcm_field_missing:name"),
            _aggregate_row("open", "hcm_field_invalid:phone"),
            _aggregate_row("open", "hcm_field_missing:city"),
        ),
    )
    second = subject._review_resolution_state(
        review,
        (
            _aggregate_row("auto_resolved", "hcm_field_missing:name"),
            _aggregate_row("auto_resolved", "hcm_field_invalid:phone"),
            _aggregate_row("open", "hcm_field_missing:city"),
        ),
    )
    final = subject._review_resolution_state(
        review,
        (
            _aggregate_row("auto_resolved", "hcm_field_missing:name"),
            _aggregate_row("auto_resolved", "hcm_field_invalid:phone"),
            _aggregate_row("auto_resolved", "hcm_field_missing:city"),
        ),
    )

    assert first.active is True and first.unresolved_count == 2
    assert second.active is True and second.unresolved_count == 1
    assert final.active is False and final.unresolved_count == 0


def test_manual_tracking_close_does_not_clear_review_umbrella() -> None:
    state = subject._review_resolution_state(
        {
            "review_identity": "review-1",
            "source_row": 7,
            "masked_case_identity": "CASE-***-1",
        },
        (
            _aggregate_row("auto_resolved", "hcm_field_missing:name"),
            _aggregate_row("closed", "hcm_field_invalid:phone"),
        ),
    )

    assert state.active is True
    assert state.unresolved_issue_codes == ("hcm_field_invalid:phone",)


def test_missing_tracking_task_does_not_clear_review_umbrella() -> None:
    state = subject._review_resolution_state(
        {
            "review_identity": "review-1",
            "source_row": 7,
            "masked_case_identity": "CASE-***-1",
        },
        (_aggregate_row(None, "hcm_field_missing:name"),),
    )

    assert state.active is True
    assert state.unresolved_count == 1


@pytest.mark.parametrize(
    ("unresolved_count", "expected_active"),
    [(2, True), (1, True), (0, False)],
)
def test_hcm_consumer_reprojects_exact_review_umbrella(
    monkeypatch,
    unresolved_count,
    expected_active,
) -> None:
    captured = []
    state = SimpleNamespace(
        review_identity="review-1",
        source_row=7,
        masked_case_identity="CASE-***-1",
        unresolved_issue_codes=("issue-1",) if unresolved_count else (),
        unresolved_count=unresolved_count,
        active=expected_active,
    )
    monkeypatch.setattr(
        hcm_consumer,
        "load_import_warning_review_resolution_state",
        lambda *_args, **_kwargs: state,
    )

    projection = object()

    class _Application:
        def __init__(self, *_args):
            pass

        def project(self, request):
            captured.append(request)
            return projection

    class _Repository:
        def __init__(self, connection):
            assert connection == "connection"

        def load_current(self, _fingerprint, *, for_update):
            assert for_update is True
            return projection, {}

    monkeypatch.setattr(hcm_consumer, "AnomalyApplication", _Application)
    monkeypatch.setattr(hcm_consumer, "MySqlAnomalyRepository", _Repository)

    hcm_consumer._project_review_umbrella(
        "connection",
        {"correction_event_id": 9, "event_identity": "correction-9"},
        {"occurrence_identity": "warning-1"},
    )

    request = captured[0]
    assert request.desired.source_identity == "review-1"
    assert request.desired.source_version == 10
    assert request.desired.active is expected_active
    assert request.partition_identity == "IMPORT-004:review-1"
    assert request.display_snapshot["unresolved_count"] == unresolved_count


def test_hcm_consumer_fails_closed_when_umbrella_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        hcm_consumer,
        "load_import_warning_review_resolution_state",
        lambda *_args, **_kwargs: SimpleNamespace(
            review_identity="review-1",
            source_row=7,
            masked_case_identity="CASE-***-1",
            unresolved_issue_codes=(),
            unresolved_count=0,
            active=False,
        ),
    )

    class _MissingRepository:
        def __init__(self, _connection):
            pass

        def load_current(self, _fingerprint, *, for_update):
            assert for_update is True
            return None

    monkeypatch.setattr(hcm_consumer, "MySqlAnomalyRepository", _MissingRepository)

    with pytest.raises(ValueError, match="hcm_import_review_umbrella_missing"):
        hcm_consumer._project_review_umbrella(
            object(),
            {"correction_event_id": 9, "event_identity": "correction-9"},
            {"occurrence_identity": "warning-1"},
        )


def test_hcm_claim_serializes_pending_events_for_same_review() -> None:
    connection = _ClaimConnection()

    assert hcm_consumer._claim(connection) is None

    statement = connection.statement
    assert "NOT EXISTS" in statement
    assert "earlier_event.review_binding_id=event.review_binding_id" in statement
    assert "earlier.id<outbox.id" in statement
    assert "earlier.published_at IS NULL" in statement


def test_hcm_auto_resolution_rechecks_current_owner_root(monkeypatch) -> None:
    class _Repository:
        def __init__(self, connection) -> None:
            assert connection == "connection"

        def load_facts(self, occurrence_identity, *, for_update):
            assert occurrence_identity == "warning-1"
            assert for_update is True
            return SimpleNamespace(
                logical_code="HCM-FIELD-001",
                root_fingerprint="current-root",
                occurrence_id=3,
                case_no="CASE-1",
                client_id=5,
                review_binding_id=7,
            )

    monkeypatch.setattr(hcm_consumer, "MySqlHcmResubmissionRepository", _Repository)

    hcm_consumer._require_fresh_terminal_root(
        "connection",
        {
            "event_identity": "event-1",
            "prior_occurrence_id": 3,
            "case_no": "CASE-1",
            "client_id": 5,
            "review_binding_id": 7,
            "root_after_fingerprint": "current-root",
        },
        {"event_identity": "event-1", "occurrence_identity": "warning-1"},
    )


def test_hcm_auto_resolution_rejects_root_drift_after_apply(monkeypatch) -> None:
    class _Repository:
        def __init__(self, _connection) -> None:
            pass

        def load_facts(self, _occurrence_identity, *, for_update):
            assert for_update is True
            return SimpleNamespace(
                logical_code="HCM-FIELD-001",
                root_fingerprint="newer-root",
                occurrence_id=3,
                case_no="CASE-1",
                client_id=5,
                review_binding_id=7,
            )

    monkeypatch.setattr(hcm_consumer, "MySqlHcmResubmissionRepository", _Repository)

    with pytest.raises(
        ValueError,
        match="hcm_resubmission_auto_resolution_root_stale",
    ):
        hcm_consumer._require_fresh_terminal_root(
            object(),
            {
                "event_identity": "event-1",
                "prior_occurrence_id": 3,
                "case_no": "CASE-1",
                "client_id": 5,
                "review_binding_id": 7,
                "root_after_fingerprint": "applied-root",
            },
            {"event_identity": "event-1", "occurrence_identity": "warning-1"},
        )


@pytest.mark.parametrize(
    ("event_overrides", "error"),
    [
        ({"event_identity": "other-event"}, "event_mismatch"),
        ({"prior_occurrence_id": 99}, "binding_mismatch"),
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

        def load_facts(self, _occurrence_identity, *, for_update):
            assert for_update is True
            return SimpleNamespace(
                logical_code="HCM-FIELD-001",
                root_fingerprint="current-root",
                occurrence_id=3,
                case_no="CASE-1",
                client_id=5,
                review_binding_id=7,
            )

    monkeypatch.setattr(hcm_consumer, "MySqlHcmResubmissionRepository", _Repository)
    event = {
        "event_identity": "event-1",
        "prior_occurrence_id": 3,
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
            {"event_identity": "event-1", "occurrence_identity": "warning-1"},
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

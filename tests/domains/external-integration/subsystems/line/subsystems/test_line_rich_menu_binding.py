"""
File: test_line_rich_menu_binding.py
Description: 驗證 Rich Menu 發布後的 durable identity binding 與 worker 整合契約。
"""

import json
from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from types import SimpleNamespace

import pytest
import requests

from domains.line.identities import LineRichMenuPublicationId, LineUserId
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingSnapshot,
    LineIdentityBindingStatus,
)
from shared_kernel.identities import ExpectedVersion
from infrastructure.line.rich_menu_api_adapter import LineRichMenuApiAdapter
from subsystems.line.outbox_contracts import LineOutboxWorkItem
from subsystems.line.rich_menu_binding import (
    LineRichMenuBindingWorker,
    RICH_MENU_BINDING_INTENT,
    schedule_rich_menu_binding,
)
from subsystems.line.rich_menu_contracts import (
    LineRichMenuProviderOutcome,
    LineRichMenuProviderOutcomeType,
)
from subsystems.line.rich_menu_worker import LineRichMenuWorker

NOW = datetime(2026, 8, 11, 4, tzinfo=timezone.utc)


class RecordingOutbox:
    def menu_provider_lock(self, line_user_id):
        return nullcontext(True)

    def __init__(self, claimed=(), *, latest=7, lease_valid=True, reset_pending=False) -> None:
        self.appended = []
        self.claimed = tuple(claimed)
        self.completed = []
        self.latest = latest
        self.lease_valid = lease_valid
        self.reset_pending = reset_pending

    def append(self, intent) -> None:
        self.appended.append(intent)

    def claim(self, query):
        assert query.intent_type == RICH_MENU_BINDING_INTENT
        result, self.claimed = self.claimed, ()
        return result

    def complete(self, command) -> None:
        self.completed.append(command)

    def lock_menu_user(self, line_user_id):
        pass

    def lock_menu_lease(self, item, now):
        return self.lease_valid and now < item.lease_expires_at

    def latest_menu_intent_id(self, line_user_id):
        return self.latest

    def menu_reset_pending(self, line_user_id):
        return self.reset_pending


class FakeUow:
    def __init__(
        self,
        outbox,
        provider_menu_id="richmenu-staff",
        identities=None,
    ) -> None:
        self.outbox = outbox
        self.rich_menu_publications = PublishedMenus(provider_menu_id)
        self.identities = identities or BoundIdentities((_bound_staff(),))
        self.audit = SimpleNamespace(append=lambda _: None)
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self) -> None:
        self.committed = True


class PublishedMenus:
    def __init__(self, provider_menu_id) -> None:
        self.provider_menu_id = provider_menu_id

    def published_provider_menu_id(self, menu_definition_id, *, before_publication_id=None):
        assert menu_definition_id in {"staff_menu", "union_staff_menu"}
        return self.provider_menu_id

    def record(self, command):
        self.recorded = command
        self.provider_menu_id = command.provider_outcome.provider_menu_id


class BoundIdentities:
    def __init__(self, bindings) -> None:
        self.bindings = tuple(bindings)
        self.requested_subject_type = None

    def list_bound_by_subject_type(self, subject_type):
        self.requested_subject_type = subject_type
        return self.bindings

    def list_by_user(self, line_user_id, *, lock=False):
        return tuple(binding for binding in self.bindings if binding.line_user_id == line_user_id)


class RecordingProvider:
    def __init__(self, outcome) -> None:
        self.outcome = outcome
        self.calls = []

    def link_to_user(self, provider_menu_id, line_user_id):
        self.calls.append((provider_menu_id, line_user_id))
        return self.outcome

    def get_user_rich_menu(self, line_user_id):
        return self.outcome


def test_bound_staff_schedules_versioned_menu_binding_intent() -> None:
    outbox = RecordingOutbox()
    binding = LineIdentityBindingSnapshot(
        LineUserId("U-staff"),
        LineIdentityBindingStatus.BOUND,
        ExpectedVersion(2),
        LineBindingSubjectType.STAFF,
        "12",
    )

    schedule_rich_menu_binding(FakeUow(outbox), binding)

    intent = outbox.appended[0]
    assert intent.intent_type == RICH_MENU_BINDING_INTENT
    assert intent.idempotency_identity == "rich-menu-bind:U-staff:2"
    assert json.loads(intent.payload_json)["menu_definition_id"] == "staff_menu"


def test_worker_links_latest_published_menu_and_completes() -> None:
    item = _work_item()
    outbox = RecordingOutbox((item,))
    provider = RecordingProvider(
        LineRichMenuProviderOutcome(
            LineRichMenuProviderOutcomeType.SUCCESS,
            provider_menu_id="richmenu-staff",
        )
    )
    worker = LineRichMenuBindingWorker(
        lambda: FakeUow(outbox), provider, "worker-1", lambda: NOW
    )

    assert worker.run_once() == 1

    assert provider.calls == [("richmenu-staff", LineUserId("U-staff"))]
    assert outbox.completed[0].succeeded is True


def test_worker_uses_publication_pinned_provider_menu() -> None:
    item = _work_item(provider_menu_id="richmenu-union-v3")
    outbox = RecordingOutbox((item,))
    provider = RecordingProvider(_successful_outcome("richmenu-union-v3"))
    worker = LineRichMenuBindingWorker(
        lambda: FakeUow(outbox, provider_menu_id=None),
        provider,
        "worker-1",
        lambda: NOW,
    )

    worker.run_once()

    assert provider.calls == [("richmenu-union-v3", LineUserId("U-staff"))]


def test_worker_uses_current_menu_when_older_publication_work_arrives_late() -> None:
    outbox = RecordingOutbox((_work_item(provider_menu_id="old-publication"),))
    provider = RecordingProvider(_successful_outcome("richmenu-staff"))
    worker = LineRichMenuBindingWorker(
        lambda: FakeUow(outbox), provider, "worker-1", lambda: NOW,
    )

    worker.run_once()

    assert provider.calls == [("richmenu-staff", LineUserId("U-staff"))]
    assert outbox.completed[0].succeeded


@pytest.mark.parametrize("superseded", [False, True])
def test_successful_publication_fans_out_only_if_current(superseded) -> None:
    binding = _bound_admin("U-union")
    outbox = RecordingOutbox()
    identities = BoundIdentities((binding,))
    unit_of_work = FakeUow(outbox, identities=identities)
    if superseded:
        unit_of_work.rich_menu_publications.published_provider_menu_id = lambda _: "newer-menu"
    worker = LineRichMenuWorker(
        lambda: unit_of_work,
        RecordingProvider(_successful_outcome("richmenu-union-v3")),
        lambda *_: "image/reference",
        "worker-1",
        lambda: NOW,
    )
    item = SimpleNamespace(
        definition_json=_union_menu_definition(),
        publication=SimpleNamespace(
            publication_id=LineRichMenuPublicationId(12), menu_definition_id="union_staff_menu",
        ),
    )

    worker._record(
        item,
        "image/reference",
        _successful_outcome("richmenu-union-v3"),
        None,
    )

    assert unit_of_work.committed is True
    if superseded:
        assert outbox.appended == []
        return
    intent = outbox.appended[0]
    assert identities.requested_subject_type is LineBindingSubjectType.ADMIN
    assert intent.idempotency_identity == "rich-menu-rebind:12:U-union"
    assert json.loads(intent.payload_json)["provider_menu_id"] == "richmenu-union-v3"


def test_provider_rejection_is_terminal() -> None:
    outbox = RecordingOutbox((_work_item(),))
    provider = RecordingProvider(
        LineRichMenuProviderOutcome(
            LineRichMenuProviderOutcomeType.REJECTED,
            error_code="line_rich_menu_rejected",
            error_message="rejected",
        )
    )
    worker = LineRichMenuBindingWorker(
        lambda: FakeUow(outbox), provider, "worker-1", lambda: NOW
    )

    worker.run_once()

    assert outbox.completed[0].retryable is False
    assert outbox.completed[0].error_code == "line_rich_menu_rejected"


def _work_item(provider_menu_id=None):
    payload = {"line_user_id": "U-staff", "menu_definition_id": "staff_menu"}
    if provider_menu_id is not None:
        payload["provider_menu_id"] = provider_menu_id
    return LineOutboxWorkItem(
        7,
        "line_identity",
        "U-staff",
        RICH_MENU_BINDING_INTENT,
        json.dumps(payload),
        1,
        5,
        "worker-1",
        NOW + timedelta(seconds=90),
        NOW + timedelta(minutes=10),
        True,
    )


def _bound_staff():
    return LineIdentityBindingSnapshot(
        LineUserId("U-staff"), LineIdentityBindingStatus.BOUND, ExpectedVersion(1),
        LineBindingSubjectType.STAFF, "12",
    )


def _response(status, menu_id=None, retry_after=None, request_id=None):
    headers = {"Retry-After": retry_after} if retry_after else {}
    if request_id:
        headers["x-line-request-id"] = request_id
    return SimpleNamespace(
        status_code=status,
        json=lambda: {"richMenuId": menu_id} if menu_id else {},
        headers=headers,
        close=lambda: None,
    )


def _run_http_attempt(item, responses, *, now=NOW, latest=7, lease_valid=True, audit=None, reset_pending=False):
    outbox = RecordingOutbox((item,), latest=latest, lease_valid=lease_valid, reset_pending=reset_pending)
    calls = []
    outcomes = iter(responses)

    def request(method, url, **kwargs):
        calls.append(method)
        assert "X-Line-Retry-Key" not in kwargs["headers"]
        response = next(outcomes)
        if isinstance(response, Exception):
            raise response
        return response

    provider = LineRichMenuApiAdapter("test-token", lambda _: None, session=SimpleNamespace(request=request))
    uow = FakeUow(outbox)
    if audit is not None:
        uow.audit = SimpleNamespace(append=audit.append)
    worker = LineRichMenuBindingWorker(lambda: uow, provider, "worker-1", lambda: now)
    assert worker.run_once() == 1
    return calls, outbox.completed[0] if outbox.completed else None


@pytest.mark.parametrize("link_response", [_response(200), requests.Timeout(), requests.ConnectionError()])
def test_verified_readback_completes_even_if_post_ack_is_missing(link_response):
    audit = []
    calls, result = _run_http_attempt(
        _work_item(), [link_response, _response(200, "richmenu-staff")], audit=audit,
    )
    assert calls == ["post", "get"]
    assert result.succeeded
    assert audit[0].action == "line.rich_menu.binding.verified"


@pytest.mark.parametrize("readback", [_response(404), _response(200, "old-menu"), _response(200)])
def test_post_200_without_matching_readback_stays_pending(readback):
    audit = []
    calls, result = _run_http_attempt(_work_item(), [_response(200), readback], audit=audit)
    assert calls == ["post", "get"]
    assert not result.succeeded and result.retryable
    assert 15 <= result.retry_after_seconds <= 22
    assert audit == []


@pytest.mark.parametrize("status", [429, 503])
def test_retry_after_then_recovery_uses_readback_before_resending(status):
    calls, result = _run_http_attempt(
        _work_item(), [_response(status, retry_after="72"), _response(404)],
    )
    assert calls == (["post"] if status == 429 else ["post", "get"])
    assert result.retryable and result.retry_after_seconds == 72
    now = NOW + timedelta(seconds=72)
    reclaimed = replace(_work_item(), attempt_count=2, lease_expires_at=now + timedelta(seconds=90))
    calls, result = _run_http_attempt(
        reclaimed, [_response(404), _response(200), _response(200, "richmenu-staff")], now=now,
    )
    assert calls == ["get", "post", "get"]
    assert result.succeeded


def test_retry_after_accepts_http_date():
    date = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=120), usegmt=True)
    calls, result = _run_http_attempt(_work_item(), [_response(429, retry_after=date)])
    assert calls == ["post"]
    assert result.retryable and 100 <= result.retry_after_seconds <= 120


def test_reclaimed_attempt_detects_prior_success_without_posting():
    calls, result = _run_http_attempt(
        replace(_work_item(), attempt_count=2), [_response(200, "richmenu-staff")],
    )
    assert calls == ["get"]
    assert result.succeeded


def test_retry_with_unavailable_readback_never_blindly_posts():
    calls, result = _run_http_attempt(replace(_work_item(), attempt_count=2), [_response(503)])
    assert calls == ["get"]
    assert result.retryable and 30 <= result.retry_after_seconds <= 45


@pytest.mark.parametrize("status", [401, 403, 404])
def test_permanent_link_failure_stops(status):
    calls, result = _run_http_attempt(_work_item(), [_response(status)])
    assert calls == ["post"]
    assert not result.retryable
    assert result.error_code == (
        "line_rich_menu_link_menu_missing" if status == 404 else f"line_http_{status}"
    )


@pytest.mark.parametrize(("diagnostics", "expected_code", "expected_calls"), [
    ([_response(400)], "line_rich_menu_readback_user_invalid", ["post", "get"]),
    ([_response(404), _response(404)], "line_rich_menu_image_unavailable", ["post", "get", "get"]),
    ([_response(404), _response(200)], "line_http_400", ["post", "get", "get"]),
    ([_response(503)], "line_http_400", ["post", "get"]),
])
def test_link_bad_request_uses_read_only_checks_and_keeps_line_request_id(
    diagnostics, expected_code, expected_calls,
):
    calls, result = _run_http_attempt(
        _work_item(), [_response(400, request_id="test-line-request"), *diagnostics],
    )
    assert calls == expected_calls
    assert not result.retryable
    assert result.error_code == expected_code
    assert result.error_message == "LINE rich menu link HTTP 400 (x-line-request-id: test-line-request)"


@pytest.mark.parametrize(("attempt_count", "retry_after", "code"), [
    (5, "1", "rich_menu_binding_attempts_exhausted"),
    (2, "600", "rich_menu_binding_deadline_exhausted"),
])
def test_attempt_and_deadline_limits_stop_rescheduling(attempt_count, retry_after, code):
    calls, result = _run_http_attempt(
        replace(_work_item(), attempt_count=attempt_count), [_response(429, retry_after=retry_after)],
    )
    assert calls == ["get"]
    assert not result.retryable and result.error_code == code


def test_late_job_and_lost_lease_are_fenced_before_any_provider_call():
    calls, result = _run_http_attempt(_work_item(), [], latest=8)
    assert calls == []
    assert result.error_code == "rich_menu_binding_superseded"
    calls, result = _run_http_attempt(_work_item(), [], lease_valid=False)
    assert calls == [] and result is None


def test_personal_link_waits_for_an_active_revocation_to_restore_default():
    calls, result = _run_http_attempt(_work_item(), [], reset_pending=True)
    assert calls == []
    assert result.retryable and result.error_code == "rich_menu_binding_waiting_for_reset"


def test_manual_resync_reads_back_before_reapplying():
    item = replace(_work_item(), idempotency_identity="rich-menu-manual-resync:1:test")
    calls, result = _run_http_attempt(item, [_response(200, "richmenu-staff")])
    assert calls == ["get"]
    assert result.succeeded
    calls, result = _run_http_attempt(
        item, [_response(200, "old-menu"), _response(200), _response(200, "richmenu-staff")],
    )
    assert calls == ["get", "post", "get"]
    assert result.succeeded

    calls, result = _run_http_attempt(item, [_response(400)])
    assert calls == ["get"]
    assert not result.retryable
    assert result.error_code == "line_rich_menu_readback_user_invalid"


def _bound_admin(line_user_id):
    return LineIdentityBindingSnapshot(
        LineUserId(line_user_id),
        LineIdentityBindingStatus.BOUND,
        ExpectedVersion(1),
        LineBindingSubjectType.ADMIN,
        "7",
    )


def _successful_outcome(provider_menu_id):
    return LineRichMenuProviderOutcome(
        LineRichMenuProviderOutcomeType.SUCCESS,
        provider_menu_id=provider_menu_id,
    )


def _union_menu_definition():
    return json.dumps(
        {
            "id": "union_staff_menu",
            "audience_role": "union_staff",
        },
        sort_keys=True,
        separators=(",", ":"),
    )

"""
File: test_line_rich_menu_provider_saga.py
Description: 驗證 Rich Menu provider 分步 saga、cleanup crash redrive 與失敗邊界。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

import pytest
import requests

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.identities import LineRichMenuPublicationId
from domains.line.rich_menu import (
    LineRichMenuPublicationSnapshot,
    LineRichMenuPublicationStatus,
)
from infrastructure.line.rich_menu_api_adapter import LineRichMenuApiAdapter
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.ports import (
    LineRichMenuCleanupWorkItem,
    LineRichMenuPublicationStep,
    LineRichMenuStepAttemptEvent,
    LineRichMenuStepAttemptOutcome,
    LineRichMenuStepReceipt,
)
from subsystems.line.rich_menu_contracts import (
    LineRichMenuProviderOutcome,
    LineRichMenuProviderOutcomeType,
    LineRichMenuProviderRequest,
    LineRichMenuPublicationWorkItem,
)
from subsystems.line.rich_menu_worker import LineRichMenuWorker


NOW = datetime(2026, 8, 20, 4, tzinfo=timezone.utc)


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = {}

    def json(self):
        return self._payload


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class _Outbox:
    def __init__(self):
        self.items = []

    def append(self, item):
        self.items.append(item)


class _Identities:
    def list_bound_by_subject_type(self, _subject_type):
        return ()


class _PublicationRepository:
    def __init__(
        self,
        item,
        *,
        previous_provider_menu_id=None,
        receipts=(),
        attempts=(),
        batches=None,
        receipt_failures=0,
    ):
        self.item = item
        self.previous_provider_menu_id = previous_provider_menu_id
        self.receipts = list(receipts)
        self.attempts = list(attempts)
        self.batches = list(batches or [(item,)])
        self.recorded = []
        self.anomalies = []
        self.receipt_failures = receipt_failures

    def claim(self, _query):
        return self.batches.pop(0) if self.batches else ()

    def list_step_receipts(self, _publication_id):
        return tuple(self.receipts)

    def append_step_receipt(self, receipt):
        if self.receipt_failures:
            self.receipt_failures -= 1
            raise RuntimeError("simulated_process_crash_after_provider_success")
        self.receipts.append(receipt)
        return receipt

    def list_step_attempt_events(self, _publication_id, step=None):
        return tuple(
            event for event in self.attempts if step is None or event.step is step
        )

    def append_step_attempt_event(self, event):
        self.attempts.append(event)
        return event

    def append_cleanup_anomaly(self, anomaly):
        self.anomalies.append(anomaly)

    def persist_cleanup_target(self, publication_id, lease_owner, provider_menu_id):
        self.cleanup_targets = getattr(self, "cleanup_targets", [])
        self.cleanup_targets.append((publication_id, lease_owner, provider_menu_id))

    def published_provider_menu_id(self, _menu_definition_id):
        return self.previous_provider_menu_id

    def record(self, command):
        self.recorded.append(command)
        return self.item.publication


class _Uow:
    def __init__(self, repository):
        self.rich_menu_publications = repository
        self.identities = _Identities()
        self.outbox = _Outbox()
        self.active = False
        self.commit_count = 0

    def __enter__(self):
        self.active = True
        return self

    def __exit__(self, *_):
        self.active = False
        return False

    def commit(self):
        self.commit_count += 1


class _Provider:
    def __init__(self, uow, outcomes):
        self.uow = uow
        self.outcomes = {key: list(value) for key, value in outcomes.items()}
        self.calls = []

    def _call(self, step, *args):
        assert self.uow.active is False
        self.calls.append((step, args))
        outcome = self.outcomes[step].pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def create(self, request):
        return self._call("create", request)

    def upload(self, request, provider_menu_id):
        return self._call("upload", request, provider_menu_id)

    def upsert_alias(self, request, provider_menu_id):
        return self._call("link", request, provider_menu_id)

    def switch_default(self, request, provider_menu_id):
        return self._call("switch", request, provider_menu_id)

    def delete(self, provider_menu_id):
        return self._call("cleanup", provider_menu_id)


def _outcome(kind, provider_menu_id=None):
    if kind is LineRichMenuProviderOutcomeType.SUCCESS:
        return LineRichMenuProviderOutcome(kind, provider_menu_id=provider_menu_id)
    return LineRichMenuProviderOutcome(kind, error_code="provider_failure", error_message="provider failure")


def _definition() -> str:
    return canonical_line_payload_json(
        {
            "id": "default_menu",
            "name": "預設選單",
            "audience_role": "customer",
            "set_as_default": True,
            "rich_menu_alias_id": "default-alias",
            "size": {"width": 2500, "height": 843},
            "chat_bar_text": "選單",
            "buttons": [
                {
                    "bounds": {"x": 0, "y": 0, "width": 2500, "height": 843},
                    "action": {"type": "message", "text": "開始"},
                }
            ],
        }
    )


def _item() -> LineRichMenuPublicationWorkItem:
    snapshot = LineRichMenuPublicationSnapshot(
        LineRichMenuPublicationId(7),
        "default_menu",
        3,
        LineRichMenuPublicationStatus.QUEUED,
    )
    return LineRichMenuPublicationWorkItem(
        snapshot,
        _definition(),
        "rich-menu/default.png",
        0,
        3,
        "worker-1",
        NOW + timedelta(minutes=5),
        CorrelationId("line-rich-menu:7"),
    )


def _cleanup_item() -> LineRichMenuCleanupWorkItem:
    item = _item()
    return LineRichMenuCleanupWorkItem(
        LineRichMenuPublicationSnapshot(
            item.publication.publication_id,
            item.publication.menu_definition_id,
            item.publication.configuration_revision,
            LineRichMenuPublicationStatus.PUBLISHED,
        ),
        item.definition_json,
        item.image_object_reference,
        item.attempt_count + 1,
        item.maximum_attempts,
        item.lease_owner,
        item.lease_expires_at,
        item.correlation_id,
        "new-menu",
        "old-menu",
    )
def _worker(repository, provider):
    uow = _Uow(repository)
    provider.uow = uow
    return LineRichMenuWorker(
        lambda: uow,
        provider,
        lambda *_: "rich-menu/default.png",
        "worker-1",
        lambda: NOW,
    )


def test_adapter_exposes_stepwise_calls_with_stable_retry_keys():
    session = _Session(
        [
            _Response(200, {"richMenuId": "richmenu-7"}),
            _Response(200),
            _Response(200),
            _Response(200),
            _Response(200),
        ]
    )
    adapter = LineRichMenuApiAdapter("token", lambda _reference: (b"png", "image/png"), session=session)
    request = LineRichMenuProviderRequest(LineRichMenuPublicationId(7), _definition(), "image/ref")

    assert adapter.create(request).provider_menu_id == "richmenu-7"
    assert adapter.upload(request, "richmenu-7").provider_menu_id == "richmenu-7"
    assert adapter.upsert_alias(request, "richmenu-7").provider_menu_id == "richmenu-7"
    assert adapter.switch_default(request, "richmenu-7").provider_menu_id == "richmenu-7"
    assert adapter.delete("old-menu").provider_menu_id == "old-menu"
    assert session.calls[0][2]["headers"]["X-Line-Retry-Key"] == str(
        uuid5(NAMESPACE_URL, "line-rich-menu:7:create")
    )
    assert session.calls[1][2]["headers"]["X-Line-Retry-Key"] == str(
        uuid5(NAMESPACE_URL, "line-rich-menu:7:upload")
    )


def test_alias_conflict_is_idempotent_only_when_existing_target_matches():
    session = _Session(
        [
            _Response(409),
            _Response(200, {"richMenuId": "richmenu-7"}),
        ]
    )
    adapter = LineRichMenuApiAdapter(
        "token",
        lambda _reference: (b"png", "image/png"),
        session=session,
    )
    request = LineRichMenuProviderRequest(
        LineRichMenuPublicationId(7),
        _definition(),
        "image/ref",
    )

    outcome = adapter.upsert_alias(request, "richmenu-7")

    assert outcome.outcome_type is LineRichMenuProviderOutcomeType.SUCCESS
    assert [call[0] for call in session.calls] == ["post", "get"]


def test_alias_conflict_with_different_target_fails_closed_without_overwrite():
    session = _Session(
        [
            _Response(409),
            _Response(200, {"richMenuId": "other-menu"}),
        ]
    )
    adapter = LineRichMenuApiAdapter(
        "token",
        lambda _reference: (b"png", "image/png"),
        session=session,
    )
    request = LineRichMenuProviderRequest(
        LineRichMenuPublicationId(7),
        _definition(),
        "image/ref",
    )

    outcome = adapter.upsert_alias(request, "richmenu-7")

    assert outcome.outcome_type is LineRichMenuProviderOutcomeType.REJECTED
    assert outcome.error_code == "line_rich_menu_alias_target_conflict"
    assert [call[0] for call in session.calls] == ["post", "get"]


def test_worker_resumes_from_create_receipt_without_recreating_asset():
    item = _item()
    create_fingerprint = fingerprint_payload(
        {
            "publication_id": 7,
            "step": "create",
            "definition_json": item.definition_json,
            "image_object_reference": item.image_object_reference,
            "provider_menu_id": None,
        }
    )
    receipt = LineRichMenuStepReceipt(
        item.publication.publication_id,
        LineRichMenuPublicationStep.CREATE,
        create_fingerprint,
        IdempotencyKey("line-rich-menu:7:create"),
        NOW,
        "richmenu-7",
    )
    repository = _PublicationRepository(item, receipts=(receipt,))
    provider = _Provider(
        None,
        {
            "create": [],
            "upload": [_outcome(LineRichMenuProviderOutcomeType.SUCCESS, "richmenu-7")],
            "link": [_outcome(LineRichMenuProviderOutcomeType.SUCCESS, "richmenu-7")],
            "switch": [_outcome(LineRichMenuProviderOutcomeType.SUCCESS, "richmenu-7")],
            "cleanup": [],
        },
    )

    assert _worker(repository, provider).run_once() == 1
    assert [step for step, _ in provider.calls] == ["upload", "link", "switch"]
    assert [event.step for event in repository.attempts] == [
        LineRichMenuPublicationStep.UPLOAD,
        LineRichMenuPublicationStep.LINK,
        LineRichMenuPublicationStep.SWITCH,
    ]
    assert all(
        event.outcome is LineRichMenuStepAttemptOutcome.SUCCESS
        for event in repository.attempts
    )
    assert repository.recorded[-1].provider_outcome.outcome_type is LineRichMenuProviderOutcomeType.SUCCESS


def test_worker_retries_only_failed_step_without_recreating_asset():
    item = _item()
    repository = _PublicationRepository(item, batches=[(item,), (item,)])
    provider = _Provider(
        None,
        {
            "create": [_outcome(LineRichMenuProviderOutcomeType.SUCCESS, "richmenu-7")],
            "upload": [
                _outcome(LineRichMenuProviderOutcomeType.RATE_LIMITED),
                _outcome(LineRichMenuProviderOutcomeType.SUCCESS, "richmenu-7"),
            ],
            "link": [_outcome(LineRichMenuProviderOutcomeType.SUCCESS, "richmenu-7")],
            "switch": [_outcome(LineRichMenuProviderOutcomeType.SUCCESS, "richmenu-7")],
            "cleanup": [],
        },
    )
    worker = _worker(repository, provider)

    assert worker.run_once() == 1
    assert worker.run_once() == 1
    assert [step for step, _ in provider.calls] == [
        "create",
        "upload",
        "upload",
        "link",
        "switch",
    ]
    assert [event.outcome for event in repository.attempts] == [
        LineRichMenuStepAttemptOutcome.SUCCESS,
        LineRichMenuStepAttemptOutcome.RATE_LIMITED,
        LineRichMenuStepAttemptOutcome.SUCCESS,
        LineRichMenuStepAttemptOutcome.SUCCESS,
        LineRichMenuStepAttemptOutcome.SUCCESS,
    ]
    assert [
        event.attempt_number
        for event in repository.attempts
        if event.step is LineRichMenuPublicationStep.UPLOAD
    ] == [1, 2]


@pytest.mark.parametrize(
    ("failure", "expected_outcome"),
    [
        (requests.Timeout("provider timeout"), LineRichMenuStepAttemptOutcome.TIMEOUT),
        (
            requests.ConnectionError("provider unavailable"),
            LineRichMenuStepAttemptOutcome.UNAVAILABLE,
        ),
    ],
)
def test_worker_reclaims_timeout_or_unavailable_with_same_provider_retry_key(
    failure,
    expected_outcome,
):
    item = _item()
    repository = _PublicationRepository(item, batches=[(item,), (item,)])
    session = _Session(
        [
            failure,
            _Response(200, {"richMenuId": "richmenu-7"}),
            _Response(200),
            _Response(200),
            _Response(200),
        ]
    )
    provider = LineRichMenuApiAdapter(
        "token",
        lambda _reference: (b"png", "image/png"),
        session=session,
    )
    worker = _worker(repository, provider)

    assert worker.run_once() == 1
    assert repository.attempts[-1].outcome is expected_outcome
    assert repository.recorded[-1].provider_outcome.outcome_type.value == expected_outcome.value

    assert worker.run_once() == 1
    create_calls = [call for call in session.calls if call[1].endswith("/richmenu")]
    assert len(create_calls) == 2
    assert create_calls[0][2]["headers"]["X-Line-Retry-Key"] == create_calls[1][2][
        "headers"
    ]["X-Line-Retry-Key"]
    assert repository.recorded[-1].provider_outcome.outcome_type is LineRichMenuProviderOutcomeType.SUCCESS


def test_worker_unknown_provider_exception_is_lost_ack_and_retries_without_leaking():
    item = _item()
    repository = _PublicationRepository(item, batches=[(item,), (item,)])
    session = _Session(
        [
            RuntimeError("sensitive-provider-token"),
            _Response(200, {"richMenuId": "richmenu-7"}),
            _Response(200),
            _Response(200),
            _Response(200),
        ]
    )
    provider = LineRichMenuApiAdapter(
        "token",
        lambda _reference: (b"png", "image/png"),
        session=session,
    )
    worker = _worker(repository, provider)

    assert worker.run_once() == 1
    assert repository.attempts[-1].outcome is LineRichMenuStepAttemptOutcome.LOST_ACK
    first_outcome = repository.recorded[-1].provider_outcome
    assert first_outcome.outcome_type is LineRichMenuProviderOutcomeType.UNAVAILABLE
    assert "sensitive-provider-token" not in (first_outcome.error_message or "")

    assert worker.run_once() == 1
    create_calls = [call for call in session.calls if call[1].endswith("/richmenu")]
    assert len(create_calls) == 2
    assert create_calls[0][2]["headers"]["X-Line-Retry-Key"] == create_calls[1][2][
        "headers"
    ]["X-Line-Retry-Key"]
    assert repository.recorded[-1].provider_outcome.outcome_type is LineRichMenuProviderOutcomeType.SUCCESS


def test_cleanup_failure_keeps_publication_published_and_records_anomaly():
    item = _item()
    repository = _PublicationRepository(item, previous_provider_menu_id="old-menu")
    provider = _Provider(
        None,
        {
            "create": [_outcome(LineRichMenuProviderOutcomeType.SUCCESS, "new-menu")],
            "upload": [_outcome(LineRichMenuProviderOutcomeType.SUCCESS, "new-menu")],
            "link": [_outcome(LineRichMenuProviderOutcomeType.SUCCESS, "new-menu")],
            "switch": [_outcome(LineRichMenuProviderOutcomeType.SUCCESS, "new-menu")],
            "cleanup": [_outcome(LineRichMenuProviderOutcomeType.UNAVAILABLE)],
        },
    )

    assert _worker(repository, provider).run_once() == 1
    assert repository.recorded[-1].provider_outcome.outcome_type is LineRichMenuProviderOutcomeType.SUCCESS
    assert len(repository.anomalies) == 1
    assert repository.attempts[-1].step is LineRichMenuPublicationStep.CLEANUP
    assert repository.attempts[-1].outcome is LineRichMenuStepAttemptOutcome.UNAVAILABLE
    assert [step for step, _ in provider.calls] == ["create", "upload", "link", "switch", "cleanup"]


def test_cleanup_only_redrive_never_replays_publication_steps_and_remains_published():
    item = _cleanup_item()
    repository = _PublicationRepository(item, batches=[(item,), (item,)])
    provider = _Provider(
        None,
        {
            "create": [],
            "upload": [],
            "link": [],
            "switch": [],
            "cleanup": [
                _outcome(LineRichMenuProviderOutcomeType.UNAVAILABLE),
                _outcome(LineRichMenuProviderOutcomeType.SUCCESS, "old-menu"),
            ],
        },
    )
    worker = _worker(repository, provider)

    assert worker.run_once() == 1
    assert worker.run_once() == 1

    assert [step for step, _ in provider.calls] == ["cleanup", "cleanup"]
    assert repository.recorded == []
    assert item.publication.status is LineRichMenuPublicationStatus.PUBLISHED
    assert [event.outcome for event in repository.attempts] == [
        LineRichMenuStepAttemptOutcome.UNAVAILABLE,
        LineRichMenuStepAttemptOutcome.SUCCESS,
    ]
    assert len(repository.anomalies) == 1
    assert repository.receipts[-1].step is LineRichMenuPublicationStep.CLEANUP


def test_cleanup_only_crash_is_durable_and_can_be_redriven_without_republishing():
    item = _cleanup_item()
    repository = _PublicationRepository(item, batches=[(item,), (item,)])
    provider = _Provider(
        None,
        {
            "create": [],
            "upload": [],
            "link": [],
            "switch": [],
            "cleanup": [
                TimeoutError("provider response lost"),
                _outcome(LineRichMenuProviderOutcomeType.SUCCESS, "old-menu"),
            ],
        },
    )
    worker = _worker(repository, provider)

    assert worker.run_once() == 1
    assert worker.run_once() == 1

    assert [step for step, _ in provider.calls] == ["cleanup", "cleanup"]
    assert repository.recorded == []
    assert [event.outcome for event in repository.attempts] == [
        LineRichMenuStepAttemptOutcome.LOST_ACK,
        LineRichMenuStepAttemptOutcome.SUCCESS,
    ]
    assert repository.anomalies[0].error_code == "line_rich_menu_cleanup_exception"


def test_cleanup_only_with_existing_ack_is_a_provider_zero_write_noop():
    item = _cleanup_item()
    request = LineRichMenuProviderRequest(
        item.publication.publication_id,
        item.definition_json,
        item.image_object_reference,
    )
    receipt = LineRichMenuStepReceipt(
        item.publication.publication_id,
        LineRichMenuPublicationStep.CLEANUP,
        fingerprint_payload(
            {
                "publication_id": item.publication.publication_id.value,
                "step": "cleanup",
                "definition_json": item.definition_json,
                "image_object_reference": item.image_object_reference,
                "provider_menu_id": item.previous_provider_menu_id,
            }
        ),
        IdempotencyKey("line-rich-menu:7:cleanup"),
        NOW,
        item.previous_provider_menu_id,
    )
    repository = _PublicationRepository(item, receipts=(receipt,))
    provider = _Provider(
        None,
        {"create": [], "upload": [], "link": [], "switch": [], "cleanup": []},
    )

    assert _worker(repository, provider).run_once() == 1
    assert provider.calls == []
    assert repository.recorded == []


def test_cleanup_only_fails_closed_when_ack_fingerprint_does_not_match():
    item = _cleanup_item()
    receipt = LineRichMenuStepReceipt(
        item.publication.publication_id,
        LineRichMenuPublicationStep.CLEANUP,
        fingerprint_payload({"different": True}),
        IdempotencyKey("line-rich-menu:7:cleanup"),
        NOW,
        item.previous_provider_menu_id,
    )
    repository = _PublicationRepository(item, receipts=(receipt,))
    provider = _Provider(
        None,
        {"create": [], "upload": [], "link": [], "switch": [], "cleanup": []},
    )

    with pytest.raises(
        RuntimeError,
        match="line_rich_menu_step_receipt_fingerprint_conflict",
    ):
        _worker(repository, provider).run_once()

    assert provider.calls == []
    assert repository.recorded == []


def test_success_attempt_without_ack_retries_same_step_and_then_advances():
    item = _item()
    event = LineRichMenuStepAttemptEvent(
        item.publication.publication_id,
        LineRichMenuPublicationStep.CREATE,
        1,
        fingerprint_payload(
            {
                "publication_id": 7,
                "step": "create",
                "definition_json": item.definition_json,
                "image_object_reference": item.image_object_reference,
                "provider_menu_id": None,
            }
        ),
        IdempotencyKey("line-rich-menu:7:create:attempt:1"),
        LineRichMenuStepAttemptOutcome.SUCCESS,
        NOW,
        item.correlation_id,
        "richmenu-7",
    )
    repository = _PublicationRepository(item, attempts=(event,))
    provider = _Provider(
        None,
        {
            "create": [_outcome(LineRichMenuProviderOutcomeType.SUCCESS, "richmenu-7")],
            "upload": [_outcome(LineRichMenuProviderOutcomeType.SUCCESS, "richmenu-7")],
            "link": [_outcome(LineRichMenuProviderOutcomeType.SUCCESS, "richmenu-7")],
            "switch": [_outcome(LineRichMenuProviderOutcomeType.SUCCESS, "richmenu-7")],
            "cleanup": [],
        },
    )

    assert _worker(repository, provider).run_once() == 1
    assert [step for step, _ in provider.calls] == ["create", "upload", "link", "switch"]
    outcome = repository.recorded[-1].provider_outcome
    assert outcome.outcome_type is LineRichMenuProviderOutcomeType.SUCCESS
    assert [
        event.attempt_number
        for event in repository.attempts
        if event.step is LineRichMenuPublicationStep.CREATE
    ] == [1, 2]


def test_process_crash_after_success_attempt_reclaims_same_key_and_does_not_skip_step():
    item = _item()
    repository = _PublicationRepository(
        item,
        batches=[(item,), (item,)],
        receipt_failures=1,
    )
    session = _Session(
        [
            _Response(200, {"richMenuId": "richmenu-7"}),
            _Response(200, {"richMenuId": "richmenu-7"}),
            _Response(200),
            _Response(200),
            _Response(200),
        ]
    )
    provider = LineRichMenuApiAdapter(
        "token",
        lambda _reference: (b"png", "image/png"),
        session=session,
    )
    worker = _worker(repository, provider)

    with pytest.raises(RuntimeError, match="simulated_process_crash"):
        worker.run_once()
    assert repository.recorded == []
    assert repository.attempts[-1].outcome is LineRichMenuStepAttemptOutcome.SUCCESS
    assert repository.receipts == []

    assert worker.run_once() == 1
    create_calls = [call for call in session.calls if call[1].endswith("/richmenu")]
    assert len(create_calls) == 2
    assert create_calls[0][2]["headers"]["X-Line-Retry-Key"] == create_calls[1][2][
        "headers"
    ]["X-Line-Retry-Key"]
    assert repository.recorded[-1].provider_outcome.outcome_type is LineRichMenuProviderOutcomeType.SUCCESS


def test_reclaim_fails_closed_when_attempt_fingerprint_does_not_match_request():
    item = _item()
    event = LineRichMenuStepAttemptEvent(
        item.publication.publication_id,
        LineRichMenuPublicationStep.CREATE,
        1,
        fingerprint_payload({"different": True}),
        IdempotencyKey("line-rich-menu:7:create:attempt:1"),
        LineRichMenuStepAttemptOutcome.LOST_ACK,
        NOW,
        item.correlation_id,
        error_code="line_rich_menu_provider_exception",
    )
    repository = _PublicationRepository(item, attempts=(event,))
    provider = _Provider(
        None,
        {"create": [], "upload": [], "link": [], "switch": [], "cleanup": []},
    )

    with pytest.raises(
        RuntimeError,
        match="line_rich_menu_step_attempt_fingerprint_conflict",
    ):
        _worker(repository, provider).run_once()

    assert provider.calls == []
    assert repository.recorded == []


def test_reclaim_fails_closed_when_success_retry_returns_different_provider_id():
    item = _item()
    event = LineRichMenuStepAttemptEvent(
        item.publication.publication_id,
        LineRichMenuPublicationStep.CREATE,
        1,
        fingerprint_payload(
            {
                "publication_id": 7,
                "step": "create",
                "definition_json": item.definition_json,
                "image_object_reference": item.image_object_reference,
                "provider_menu_id": None,
            }
        ),
        IdempotencyKey("line-rich-menu:7:create:attempt:1"),
        LineRichMenuStepAttemptOutcome.SUCCESS,
        NOW,
        item.correlation_id,
        "richmenu-7",
    )
    repository = _PublicationRepository(item, attempts=(event,))
    provider = _Provider(
        None,
        {
            "create": [
                _outcome(LineRichMenuProviderOutcomeType.SUCCESS, "different-menu")
            ],
            "upload": [],
            "link": [],
            "switch": [],
            "cleanup": [],
        },
    )

    with pytest.raises(
        RuntimeError,
        match="line_rich_menu_step_attempt_provider_id_conflict",
    ):
        _worker(repository, provider).run_once()

    assert [step for step, _ in provider.calls] == ["create"]
    assert repository.receipts == []
    assert repository.recorded == []

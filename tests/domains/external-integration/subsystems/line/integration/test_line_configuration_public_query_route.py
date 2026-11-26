"""
File: test_line_configuration_public_query_route.py
Description: 驗證 LINE Configuration safe GET、Rich Menu successor guard 與其他種類相容性。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from api.dependencies.admin_auth import (
    require_admin,
    require_line_configuration_manager,
    require_line_configuration_reader,
)
from api.exception_handlers import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.routes import line_configurations, line_faq_layout
from api.schemas.line_configurations import (
    LineConfigurationPreviewView,
    LineConfigurationSafePublicView,
    LineConfigurationSnapshotView,
)
from domains.line.configuration import LineConfigurationKind, LineConfigurationSnapshot
from domains.line.identities import LineConfigurationRevision
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.knowledge_retrieval.faq_catalog import KnowledgeCatalogUnavailable
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.configuration_contracts import (
    ApplyLineConfigurationResult,
    LineConfigurationCommandOutcome,
    LineConfigurationQueryContractError,
    LineConfigurationQueryUnavailableError,
    LineConfigurationSafeResult,
    LineConfigurationSafeState,
)
from subsystems.line.faq_chat_layout import FAQ_CHAT_LAYOUT_KIND, FaqChatLayoutApplication


def _principal() -> AdminPrincipal:
    return AdminPrincipal(1, "configuration-admin", "設定管理員", "operator")


def _client(monkeypatch: pytest.MonkeyPatch, application: object) -> TestClient:
    monkeypatch.setattr(
        line_configurations,
        "get_line_configuration_application",
        lambda: application,
    )
    app = FastAPI()
    app.include_router(line_configurations.router)
    app.dependency_overrides[require_line_configuration_reader] = _principal
    app.dependency_overrides[require_line_configuration_manager] = _principal
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    return TestClient(app)


class _Application:
    def __init__(self, safe_result: object) -> None:
        self.safe_result = safe_result
        self.safe_calls: list[tuple[object, object]] = []
        self.get_calls: list[LineConfigurationKind] = []
        self.preview_calls: list[LineConfigurationKind] = []
        self.apply_calls: list[LineConfigurationKind] = []

    def get_safe(self, query: object, actor: object) -> object:
        self.safe_calls.append((query, actor))
        if isinstance(self.safe_result, Exception):
            raise self.safe_result
        return self.safe_result

    def get(self, kind: LineConfigurationKind, _actor: object) -> LineConfigurationSnapshot:
        self.get_calls.append(kind)
        return LineConfigurationSnapshot(
            kind,
            LineConfigurationRevision(9),
            json.dumps(
                {
                    "menus": [],
                    "uri": "https://legacy.invalid/menu",
                    "provider_id": "legacy-provider-secret",
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        )

    def preview(
        self,
        kind: LineConfigurationKind,
        expected_revision: LineConfigurationRevision,
        definition: dict[str, object],
        _actor: object,
    ) -> object:
        self.preview_calls.append(kind)
        return SimpleNamespace(
            kind=kind,
            before_revision=expected_revision,
            resulting_revision=LineConfigurationRevision(expected_revision.value + 1),
            definition_json=json.dumps(
                definition,
                sort_keys=True,
                separators=(",", ":"),
            ),
            fingerprint=PreviewFingerprint("a" * 64),
        )

    def apply(self, **command: object) -> object:
        kind = command["kind"]
        expected_revision = command["expected_revision"]
        definition = command["definition"]
        assert isinstance(kind, LineConfigurationKind)
        assert isinstance(expected_revision, LineConfigurationRevision)
        assert isinstance(definition, dict)
        self.apply_calls.append(kind)
        return SimpleNamespace(
            snapshot=LineConfigurationSnapshot(
                kind,
                LineConfigurationRevision(expected_revision.value + 1),
                json.dumps(definition, sort_keys=True, separators=(",", ":")),
            )
        )


def test_safe_route_returns_exact_closed_redacted_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _Application(
        LineConfigurationSafeResult(
            LineConfigurationKind.RICH_MENUS,
            9,
            LineConfigurationSafeState.CONFIGURED,
        )
    )

    response = _client(monkeypatch, application).get(
        "/api/v1/line/configurations/rich_menus/safe",
        headers={"X-Correlation-ID": "configuration-safe-route"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Success",
        "data": {
            "kind": "rich_menus",
            "revision": 9,
            "state": "configured",
        },
        "error": None,
    }
    rendered = json.dumps(response.json()["data"], sort_keys=True)
    assert "legacy.invalid" not in rendered
    assert "provider-secret" not in rendered
    assert len(application.safe_calls) == 1


def test_safe_public_view_rejects_extra_or_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        LineConfigurationSafePublicView.model_validate(
            {
                "kind": "rich_menus",
                "revision": 1,
                "state": "configured",
                "definition": {"uri": "https://secret.invalid"},
            }
        )


@pytest.mark.parametrize(
    ("view", "payload"),
    [
        (
            LineConfigurationSnapshotView,
            {
                "kind": "liff",
                "revision": 1,
                "definition": {},
                "unexpected": True,
            },
        ),
        (
            LineConfigurationPreviewView,
            {
                "kind": "liff",
                "before_revision": 1,
                "resulting_revision": 2,
                "definition": {},
                "fingerprint": "not-a-fingerprint",
            },
        ),
    ],
)
def test_generic_output_views_reject_untyped_payloads(
    view: type[BaseModel],
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        view.model_validate(payload)


@pytest.mark.parametrize(
    ("failure", "expected_code", "expected_retryable"),
    [
        (
            LineConfigurationQueryContractError(),
            "line_configuration_query_contract_invalid",
            False,
        ),
        (
            LineConfigurationQueryUnavailableError(),
            "line_configuration_query_unavailable",
            True,
        ),
    ],
)
def test_safe_route_returns_redacted_global_typed_error(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    expected_code: str,
    expected_retryable: bool,
) -> None:
    response = _client(monkeypatch, _Application(failure)).get(
        "/api/v1/line/configurations/rich_menus/safe",
        headers={"X-Correlation-ID": "configuration-safe-failure"},
    )

    assert response.status_code == 503
    error = response.json()["detail"]["error"]
    assert error == {
        "category": "unavailable",
        "code": expected_code,
        "message": "LINE 設定查詢結果無法安全提供。",
        "field_errors": [],
        "domain_blockers": [],
        "retryable": expected_retryable,
        "correlation_id": "configuration-safe-failure",
        "current_version": None,
    }
    assert "secret" not in json.dumps(error, ensure_ascii=False).lower()


def test_safe_route_rejects_unknown_kind_with_global_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _client(
        monkeypatch,
        _Application(
            LineConfigurationSafeResult(
                LineConfigurationKind.RICH_MENUS,
                0,
                LineConfigurationSafeState.EMPTY,
            )
        ),
    ).get(
        "/api/v1/line/configurations/unknown_kind/safe",
        headers={"X-Correlation-ID": "configuration-safe-unknown"},
    )

    assert response.status_code == 422
    error = response.json()["detail"]["error"]
    assert error["category"] == "validation"
    assert error["correlation_id"] == "configuration-safe-unknown"


def test_generic_rich_menu_query_preview_and_apply_point_to_dedicated_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _Application(
        LineConfigurationSafeResult(
            LineConfigurationKind.RICH_MENUS,
            9,
            LineConfigurationSafeState.CONFIGURED,
        )
    )
    client = _client(monkeypatch, application)
    responses = (
        client.get("/api/v1/line/configurations/rich_menus"),
        client.post(
            "/api/v1/line/configurations/rich_menus/preview",
            json={"expected_revision": 9, "definition": {"menus": []}},
        ),
        client.put(
            "/api/v1/line/configurations/rich_menus",
            json={
                "expected_revision": 9,
                "definition": {"menus": []},
                "reason": "更新 Rich Menu 草稿",
                "idempotency_key": "rich-menu-draft:9",
                "correlation_id": "rich-menu-draft-9",
            },
        ),
    )

    for response in responses:
        assert response.status_code == 410
        assert response.json()["detail"]["error"]["code"] == (
            "line_rich_menu_generic_configuration_retired"
        )
        assert "/api/v1/line/rich-menus/draft" in response.text
    assert application.get_calls == []
    assert application.preview_calls == []
    assert application.apply_calls == []


def test_other_configuration_kinds_keep_generic_query_preview_and_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _Application(
        LineConfigurationSafeResult(
            LineConfigurationKind.LIFF,
            9,
            LineConfigurationSafeState.CONFIGURED,
        )
    )
    client = _client(monkeypatch, application)

    queried = client.get("/api/v1/line/configurations/liff")
    previewed = client.post(
        "/api/v1/line/configurations/liff/preview",
        json={"expected_revision": 9, "definition": {"pages": []}},
    )
    applied = client.put(
        "/api/v1/line/configurations/liff",
        json={
            "expected_revision": 9,
            "definition": {"pages": []},
            "reason": "更新 LIFF 設定",
            "idempotency_key": "liff-config:9",
            "correlation_id": "liff-config-9",
        },
    )

    assert queried.status_code == 200
    assert queried.json() == {
        "success": True,
        "message": "Success",
        "data": {
            "kind": "liff",
            "revision": 9,
            "definition": {
                "menus": [],
                "provider_id": "legacy-provider-secret",
                "uri": "https://legacy.invalid/menu",
            },
        },
        "error": None,
    }
    assert previewed.status_code == 200
    assert previewed.json() == {
        "success": True,
        "message": "Success",
        "data": {
            "kind": "liff",
            "before_revision": 9,
            "resulting_revision": 10,
            "definition": {"pages": []},
            "fingerprint": "a" * 64,
        },
        "error": None,
    }
    assert applied.status_code == 200
    assert applied.json() == {
        "success": True,
        "message": "LINE 設定版本已套用",
        "data": {
            "kind": "liff",
            "revision": 10,
            "definition": {"pages": []},
        },
        "error": None,
    }
    assert application.get_calls == [LineConfigurationKind.LIFF]
    assert application.preview_calls == [LineConfigurationKind.LIFF]
    assert application.apply_calls == [LineConfigurationKind.LIFF]


def test_faq_layout_cannot_read_or_write_through_generic_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _Application(None)
    client = _client(monkeypatch, application)
    path = "/api/v1/line/configurations/faq_chat_layout"
    for response in (
        client.get(path),
        client.get(f"{path}/safe"),
        client.post(f"{path}/preview", json={"expected_revision": 0, "definition": {}}),
        client.put(path, json={
            "expected_revision": 0,
            "definition": {},
            "reason": "bypass",
            "idempotency_key": "bypass",
            "correlation_id": "bypass",
        }),
    ):
        assert response.status_code == 404
        assert response.json()["detail"]["error"]["code"] == "faq_layout_dedicated_endpoint_required"
    assert not (application.get_calls or application.safe_calls or application.preview_calls or application.apply_calls)


class _FaqStore:
    def __init__(self) -> None:
        self.current = LineConfigurationSnapshot(FAQ_CHAT_LAYOUT_KIND, LineConfigurationRevision(0), "{}")
        self.operations = {}
        self.audit = []
        self.answers = {"QA-001": SimpleNamespace(question="服務如何申請？", answer="請先填寫需求登記。")}
        self.catalog_available = True
        self.available = True

    def get_answer(self, qa_id):
        if not self.catalog_available:
            raise KnowledgeCatalogUnavailable
        return self.answers.get(qa_id)

    def open(self):
        if not self.available:
            raise OSError("storage unavailable")
        return _FaqUnit(self)


class _FaqUnit:
    def __init__(self, store):
        self._store = store
        self._pending = None
        self.configurations = self
        self.audit = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, kind):
        assert kind is FAQ_CHAT_LAYOUT_KIND
        return self._store.current

    def get_by_idempotency_key(self, kind, key):
        assert kind is FAQ_CHAT_LAYOUT_KIND
        return self._store.operations.get(key.value)

    def apply(self, command):
        assert command.candidate.kind is FAQ_CHAT_LAYOUT_KIND
        assert command.candidate.before_revision == self._store.current.revision
        snapshot = LineConfigurationSnapshot(
            command.candidate.kind, command.candidate.resulting_revision, command.candidate.definition_json,
        )
        self._pending = (command.idempotency_key.value, snapshot)
        return ApplyLineConfigurationResult(LineConfigurationCommandOutcome.CREATED, snapshot)

    def commit(self):
        assert self._pending is not None
        key, snapshot = self._pending
        assert key not in self._store.operations
        self._store.operations[key] = snapshot
        self._store.current = snapshot
        self._store.audit.extend(self.audit)


_FAQ_LAYOUT_URL = "/api/v1/line/faq-layout"


def _faq_headers(key):
    return {"Idempotency-Key": key, "X-Correlation-ID": f"test:{key}"}


def _faq_client(store, capabilities=frozenset({"line.config.manage", "knowledge.manage"})):
    app = FastAPI()
    app.include_router(line_faq_layout.router)
    app.include_router(line_faq_layout.knowledge_router)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(
        None, "fixture", "Fixture", "operator", capabilities=capabilities,
    )
    app.dependency_overrides[line_faq_layout.get_faq_chat_layout_application] = lambda: FaqChatLayoutApplication(
        store.open, store.get_answer,
    )
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    return TestClient(app)


def test_faq_01_layout_draft_published_preview_and_invalid_writes_with_fake_ports():
    store = _FaqStore()
    client = _faq_client(store)
    create_url = f"{_FAQ_LAYOUT_URL}/categories"
    preview_url = f"{_FAQ_LAYOUT_URL}/preview"
    publish_url = f"{_FAQ_LAYOUT_URL}/publish"

    def query():
        return client.get(_FAQ_LAYOUT_URL).json()["data"]

    assert query()["published_revision"] is None
    missing_correlation = client.post(
        create_url, json={"name": "服務異動", "expected_revision": 0}, headers={"Idempotency-Key": "no-correlation"},
    )
    blank = client.post(
        create_url, json={"name": "  ", "expected_revision": 0}, headers=_faq_headers("blank"),
    )
    for response in (missing_correlation, blank):
        assert response.status_code == 422
        assert response.json()["detail"]["error"]["code"] == "faq_layout_invalid"
    assert query()["draft_revision"] == 0
    assert store.audit == []

    created = client.post(
        create_url, json={"name": "ＦＡＱ", "expected_revision": 0}, headers=_faq_headers("create"),
    )
    assert created.status_code == 200
    category_id = created.json()["data"]["category_id"]
    state = query()
    assert state["draft_revision"] == 1
    assert state["published_layout"] is None
    draft = state["draft_layout"]
    assert draft["categories"][0]["title"] == "ＦＡＱ"
    draft_preview = client.post(preview_url, json={"mode": "draft", "layout": draft, "category_id": category_id})
    assert draft_preview.status_code == 200
    assert draft_preview.json()["data"]["view"]["buttons"] == []
    published_preview = client.post(preview_url, json={"mode": "published", "category_id": category_id})
    assert published_preview.status_code == 404
    assert published_preview.json()["detail"]["error"]["code"] == "faq_category_not_published"

    duplicate = client.post(
        create_url, json={"name": " faq ", "expected_revision": 1}, headers=_faq_headers("duplicate"),
    )
    assert duplicate.status_code == 422
    assert duplicate.json()["detail"]["error"]["field_errors"][0]["code"] == "duplicate_category_name"
    assert client.post(
        publish_url, json={"expected_revision": 1}, headers=_faq_headers("empty-publish"),
    ).status_code == 422
    assert query() == state
    assert list(store.operations) == ["create"]
    assert len(store.audit) == 1

    draft["categories"][0]["questions"] = [{"qa_id": "QA-001", "label": "如何申請"}]
    preview = client.post(preview_url, json={"mode": "draft", "layout": draft, "category_id": category_id})
    expected_view = preview.json()["data"]["view"]
    assert expected_view["buttons"][0]["answer"] == "請先填寫需求登記。"
    assert client.put(
        f"{_FAQ_LAYOUT_URL}/draft", json={"expected_revision": 1, "layout": draft}, headers=_faq_headers("save"),
    ).status_code == 200
    stale = client.post(publish_url, json={"expected_revision": 1}, headers=_faq_headers("stale"))
    assert stale.status_code == 409
    assert stale.json()["detail"]["error"]["current_version"] == 2
    assert query()["published_layout"] is None

    published = client.post(publish_url, json={"expected_revision": 2}, headers=_faq_headers("publish"))
    assert published.status_code == 200
    assert published.json()["data"]["published_revision"] == 3
    assert client.post(
        publish_url, json={"expected_revision": 2}, headers=_faq_headers("publish"),
    ).json()["data"] == published.json()["data"]
    reopened = _faq_client(store)
    assert reopened.get(_FAQ_LAYOUT_URL).json()["data"]["published_layout"] == draft
    assert reopened.post(
        preview_url, json={"mode": "published", "category_id": category_id},
    ).json()["data"]["view"] == expected_view
    assert list(store.operations) == ["create", "save", "publish"]
    assert len(store.audit) == 3

    del store.answers["QA-001"]
    result = reopened.post(preview_url, json={"mode": "published", "category_id": category_id}).json()["data"]
    assert result["view"]["buttons"] == []
    assert result["issues"] == [{
        "code": "faq_question_not_published", "field": "categories[0].questions[0].qa_id", "qa_id": "QA-001",
    }]
    refused = reopened.post(publish_url, json={"expected_revision": 3}, headers=_faq_headers("retired-question"))
    assert refused.status_code == 422
    assert query()["published_revision"] == 3
    assert len(store.audit) == 3
    store.catalog_available = False
    failed = reopened.post(preview_url, json={"mode": "published", "category_id": category_id})
    assert failed.status_code == 503
    assert failed.json()["detail"]["error"]["code"] == "knowledge_catalog_unavailable"


def test_faq_04_layout_operation_receipt_replay_after_revision_advanced_with_fake_ports():
    store = _FaqStore()
    client = _faq_client(store)
    url = f"{_FAQ_LAYOUT_URL}/categories"
    command = {"name": "新分類", "expected_revision": 0}
    initial = client.post(url, json=command, headers=_faq_headers("create-primary"))
    assert initial.status_code == 200
    assert client.post(
        url, json={"name": "更新後分類", "expected_revision": 1}, headers=_faq_headers("another"),
    ).status_code == 200
    replayed = client.post(url, json=command, headers=_faq_headers("create-primary"))
    receipt = client.get(f"{_FAQ_LAYOUT_URL}/operations/create-primary", headers=_faq_headers("create-primary"))
    assert replayed.json()["data"] == receipt.json()["data"] == initial.json()["data"]
    assert client.get(_FAQ_LAYOUT_URL).json()["data"]["draft_revision"] == 2

    conflicting = client.post(url, json={**command, "name": "其他內容"}, headers=_faq_headers("create-primary"))
    assert conflicting.status_code == 409
    assert conflicting.json()["detail"]["error"]["code"] == "faq_layout_idempotency_conflict"
    missing = client.get(f"{_FAQ_LAYOUT_URL}/operations/missing", headers=_faq_headers("missing"))
    assert missing.status_code == 404
    assert list(store.operations) == ["create-primary", "another"]
    assert len(store.audit) == 2


def test_faq_layout_permissions_and_source_failure_remain_distinct_with_fake_ports():
    store = _FaqStore()
    knowledge_editor = _faq_client(store, frozenset({"knowledge.manage"}))
    assert knowledge_editor.get(_FAQ_LAYOUT_URL).status_code == 403
    categories = knowledge_editor.get("/api/v1/knowledge/faq-categories")
    assert categories.status_code == 200
    assert categories.json()["data"] == {"categories": []}
    store.available = False
    unavailable = _faq_client(store).get(_FAQ_LAYOUT_URL)
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"]["error"]["code"] == "faq_layout_unavailable"

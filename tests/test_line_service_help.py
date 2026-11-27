"""
File: test_line_service_help.py
Description: 驗證聊天室 FAQ Reply、管理題庫讀取、舊公開問答入口退役。
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.dependencies.admin_auth import require_admin
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.access.integration_capabilities import IntegrationCapability
from api.dependencies.line_faq_layout import get_service_help_faq_readers
from api.dependencies.line_ai_qa_catalog import load_line_ai_qa_catalog
from domains.knowledge_retrieval.qa_catalog import GovernedQaContent, encode_governed_qa
from domains.line.faq_chat_layout import FaqCategory, FaqLayout, FaqQuestionLink, project_category
from domains.line.identities import LineSourceType, LineUserId
from infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter
from subsystems.knowledge_retrieval.faq_catalog import PredecessorPublishedFaqCatalog, PublishedFaq, PublishedFaqCatalog
from subsystems.line.delivery_contracts import REPLY_ONLY_WEBHOOK_SOURCE
from subsystems.line.faq_chat_layout import FaqCategoryNotPublished, FaqLayoutUnavailable
from subsystems.line.predecessor_line_faq import PredecessorLineFaq
from subsystems.line.service_help_application import LineServiceHelpApplication, ServiceHelpFaqReaders
from subsystems.line.webhook_identity_handlers import LineWebhookIdentityHandlers


class _FaqRepository:
    def __init__(self):
        self.rows = {
            item.id: _faq_row(item.id, item.answer, question=item.question, aliases=item.aliases, tag=item.tag)
            for item in load_line_ai_qa_catalog() if item.enabled
        }
        self.official = dict(self.rows)
        self.legacy = {}
        self.unavailable = False

    @contextmanager
    def unit(self):
        if self.unavailable:
            raise OSError("synthetic unavailable repository")
        yield SimpleNamespace(knowledge=self)

    def published_faq_by_id(self, qa_id):
        row = self.official.get(qa_id)
        return [row] if row and row["source_identity"] == "line-common-qa:" + qa_id else []

    def published_faq_page(self, cursor, limit):
        official_faqs = [
            row
            for qa_id in sorted(self.official)
            if cursor is None or qa_id > cursor
            for row in self.published_faq_by_id(qa_id)
        ]
        return official_faqs[:limit]

    def published_faq_by_alias(self, text):
        return [
            row
            for rows in (self.published_faq_by_id(qa_id) for qa_id in self.official)
            for row in rows
            if text in (row["question"], *row["aliases"])
        ]

    def faq_by_legacy_text(self, text):
        return [
            self.official.get(qa_id, {"source_version": None})
            for qa_id in self.legacy.get(text, ())
        ]


def _faq_row(qa_id, answer, *, version=1, question="目前題目？", aliases=(), tag="媒合"):
    qa = GovernedQaContent(
        qa_id, "舊顯示名稱", tag, question, aliases, answer, "正式題庫來源",
        category_id="service_flow",
    )
    return {
        "content": encode_governed_qa(qa),
        "source_identity": qa.source_identity,
        "source_version": version,
        "source_uri": "正式題庫來源",
        "question": question,
        "aliases": aliases,
    }


class _Layout:
    def __init__(self, categories=()):
        self.published = FaqLayout(categories)
        self.catalog = None

    def category_names(self):
        return {"service_flow": "服務流程"}

    def published_layout(self):
        return self.published

    def preview_published(self, category_id):
        preview = project_category(self.published, category_id, self.catalog.get)
        if preview is None:
            raise FaqCategoryNotPublished()
        return preview


@pytest.fixture
def faq_repository():
    return _FaqRepository()


@pytest.fixture
def faq_layout():
    return _Layout()


@pytest.fixture
def client(faq_repository, faq_layout):
    catalog = PublishedFaqCatalog(faq_repository.unit)
    faq_layout.catalog = catalog
    # These route contracts use fake ports and do not exercise startup database or Redis work.
    client = TestClient(app)
    original = dict(app.dependency_overrides)
    app.dependency_overrides[get_service_help_faq_readers] = lambda: lambda: ServiceHelpFaqReaders(catalog, faq_layout)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(
        None, "fixture", "fixture", "operator",
        capabilities=frozenset({IntegrationCapability.KNOWLEDGE_READ.value}),
    )
    try:
        yield client
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)


@pytest.mark.parametrize(("method", "path"), [
    ("GET", "/line-service-help?tab=ai"),
    ("GET", "/line-service-help?tab=faq"),
    ("GET", "/api/v1/line/service-help/faq"),
    ("POST", "/api/v1/line/service-help/ask"),
])
def test_faq_retired_public_entrances_only_show_chat_guidance(client, method, path):
    response = client.request(method, path)
    assert response.status_code == 410
    assert "常見問題" in response.text
    assert "target=ai_assistant" not in response.text
    assert "<script" not in response.text


@pytest.mark.parametrize("suffix", ["", "/preview"])
def test_faq_legacy_liff_feedback_cannot_start_a_write(client, suffix):
    response = client.post("/api/v1/line/feedback" + suffix, json={
        "source_response_id": "knowledge-answer-request:3",
        "outcome": "resolved", "response_revision": 1, "catalog_revision": 1,
        "idempotency_key": "faq-retired", "correlation_id": "faq-retired",
    })
    assert response.status_code == 410
    assert response.json()["detail"]["error"]["code"] == "line_service_help_retired"


def test_faq_admin_readback_rejects_unprivileged_user(client, monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, require_admin, lambda: AdminPrincipal(
        None, "fixture", "fixture", "operator", capabilities=frozenset(),
    ))
    assert client.get("/api/v1/line/faq-layout/published-questions").status_code == 403


def _private_inbox(*, text="", postback="", group=False):
    user = LineUserId("U" + "1" * 32)
    payload = {"message": {"type": "text", "text": text}} if text else {"postback": {"data": postback}}
    return SimpleNamespace(event=SimpleNamespace(
        event_id=SimpleNamespace(value="synthetic-faq"),
        payload_json=json.dumps(payload, ensure_ascii=False),
        source=SimpleNamespace(
            source_type=LineSourceType.GROUP if group else LineSourceType.USER,
            user_id=user,
        ),
    ))


def _reply_handlers(repository, layout, *, faq_reader=None):
    catalog = PublishedFaqCatalog(repository.unit)
    layout.catalog = catalog
    service_help = LineServiceHelpApplication(
        lambda: datetime.now(timezone.utc), faq_catalog=catalog, faq_layout=layout, faq_reader=faq_reader,
    )
    return LineWebhookIdentityHandlers(
        lambda: datetime.now(timezone.utc),
        lambda *_: "https://example.invalid/identity",
        service_help_application=service_help,
    )


def _reply_payload(handlers, *, text="", postback="", group=False):
    inbox = _private_inbox(text=text, postback=postback, group=group)
    requests = []
    unit = SimpleNamespace(
        delivery_tasks=SimpleNamespace(enqueue=requests.append),
        platform_users=SimpleNamespace(apply_friend_event=lambda _: None),
    )
    if text:
        inbox.event.occurred_at = datetime.now(timezone.utc)
        handled = handlers.handle_reply_message(inbox, unit)
    else:
        handled = handlers.handle_reply_postback(inbox, unit)
    if not handled:
        assert not requests
        return None
    [request] = requests
    assert request.source_aggregate_type == REPLY_ONLY_WEBHOOK_SOURCE
    return json.loads(request.payload_json)


def _body_actions(payload):
    return [button["action"] for button in payload["contents"]["body"]["contents"]]


def test_faq_02_official_version_is_shared_by_admin_and_line(client, faq_repository, faq_layout):
    qa_id = "qa-versioned"
    legacy = "這是上一張 LINE 卡片送出的問題？"
    handlers = _reply_handlers(faq_repository, faq_layout)
    faq_repository.legacy[legacy] = (qa_id,)
    official_a = "正式答案 A\n\n提醒：請先聯絡工會。"
    faq_repository.official[qa_id] = _faq_row(qa_id, official_a, question=legacy)
    faq_repository.rows[qa_id] = _faq_row(qa_id, "草稿答案 B", version=2, question="新問題？")

    def assert_shared_answer(expected, version):
        response = client.get("/api/v1/line/faq-layout/published-questions", params={"qa_id": qa_id})
        assert response.status_code == 200
        [item] = response.json()["data"]["items"]
        assert item["answer"] == expected
        assert item["version"] == version
        assert item["category"] == "服務流程"
        for kwargs in ({"text": legacy}, {"postback": f"faq:v1:question:{qa_id}"}):
            assert _reply_payload(handlers, **kwargs) == {"type": "text", "text": expected}

    assert_shared_answer(official_a, 1)
    faq_repository.official[qa_id] = faq_repository.rows[qa_id]
    assert_shared_answer("草稿答案 B", 2)
    faq_repository.rows[qa_id] = _faq_row(qa_id, "未發布 C", version=3)
    del faq_repository.official[qa_id]
    response = client.get("/api/v1/line/faq-layout/published-questions", params={"qa_id": qa_id})
    assert response.json()["data"]["items"] == []
    for kwargs in ({"text": legacy}, {"postback": f"faq:v1:question:{qa_id}"}):
        reply = _reply_payload(handlers, **kwargs)["text"]
        assert "返回常見問題" in reply
        assert all(old_answer not in reply for old_answer in ("正式答案 A", "草稿答案 B", "未發布 C"))


def test_faq_03_walks_all_official_pages_and_surfaces_unavailability(
    client, faq_repository, faq_layout, monkeypatch,
):
    path = "/api/v1/line/faq-layout/published-questions"
    ids = [f"faq-{index:03}" for index in range(101)]
    faq_repository.official = {qa_id: _faq_row(qa_id, qa_id) for qa_id in reversed(ids)}
    faq_repository.official["faq-not-a-qa"] = {"source_identity": "non-faq-source"}
    faq_repository.rows["faq-draft"] = _faq_row("faq-draft", "尚未發布")
    actual = []
    cursor = None
    for expected_count in (50, 50, 1):
        response = client.get(path, params={"cursor": cursor} if cursor else {})
        assert response.status_code == 200
        page = response.json()["data"]
        assert len(page["items"]) == expected_count
        actual.extend(item["qa_id"] for item in page["items"])
        cursor = page["next_cursor"]
    assert cursor is None
    assert actual == ids

    response = client.get(path, params={"cursor": "invalid/cursor"})
    assert response.status_code == 422
    assert response.json()["detail"]["error"]["code"] == "faq_cursor_invalid"
    faq_repository.unavailable = True
    response = client.get(path)
    assert response.status_code == 503
    assert response.json()["detail"]["error"]["code"] == "knowledge_catalog_unavailable"
    assert "data" not in response.json()

    faq_repository.unavailable = False
    def category_names_unavailable():
        raise FaqLayoutUnavailable
    monkeypatch.setattr(faq_layout, "category_names", category_names_unavailable)
    response = client.get(path)
    assert response.status_code == 503
    assert response.json()["detail"]["error"]["code"] == "faq_layout_unavailable"
    assert "data" not in response.json()


def test_faq_05_only_one_current_exact_legacy_match_is_answered(faq_repository, faq_layout):
    handlers = _reply_handlers(faq_repository, faq_layout)
    faq_repository.official = {
        "qa-one": _faq_row("qa-one", "新版正式答案"),
        "qa-two": _faq_row("qa-two", "另一題的答案", question="新版重複舊提問"),
    }
    faq_repository.legacy = {
        "舊版問題文字": ("qa-one",),
        "歧義的舊問題": ("qa-one", "qa-two"),
        "已停用文字": ("qa-retired",),
        "新版重複舊提問": ("qa-one",),
    }
    assert "新版正式答案" in _reply_payload(handlers, text="舊版問題文字")["text"]
    for text in ("歧義的舊問題", "已停用文字", "一般市民（最高40小時）", "新版重複舊提問"):
        payload = _reply_payload(handlers, text=text)
        assert "返回常見問題" in payload["text"]
        assert "新版正式答案" not in payload["text"]
    assert _reply_payload(handlers, text="舊版問題文") is None
    assert "返回常見問題" in _reply_payload(handlers, postback="faq:v1:question:unknown")["text"]
    faq_repository.unavailable = True
    assert "暫時無法使用" in _reply_payload(handlers, text="舊版問題文字")["text"]


def test_faq_05_predecessor_uses_seed_only_to_identify_a_question(faq_repository, faq_layout):
    seed = PublishedFaq(
        qa_id="qa-seed", category="服務流程", category_id=None, tag="",
        question="舊版按鈕文字", answer="種子檔答案", aliases=(),
        source_ref="種子來源", source_identity="line-common-qa:qa-seed", source_version=0, source_uri="",
    )
    catalog = Mock(spec=PredecessorPublishedFaqCatalog)
    catalog.get.return_value = None
    catalog.has_identity.return_value = False
    predecessor = PredecessorLineFaq(catalog, lambda: (seed,))
    handlers = _reply_handlers(
        faq_repository, faq_layout, faq_reader=lambda: ServiceHelpFaqReaders(catalog, None, predecessor),
    )
    guidance = _reply_payload(handlers, text=seed.question)
    assert "返回常見問題" in guidance["text"]
    assert seed.answer not in guidance["text"]

    faq_repository.official[seed.qa_id] = _faq_row(seed.qa_id, "正式答案")
    catalog.get.return_value = PublishedFaqCatalog(faq_repository.unit).get(seed.qa_id)
    assert _reply_payload(handlers, text=seed.question) == {"type": "text", "text": "正式答案"}


def test_faq_05_reply_budget_counts_only_answer_utf16_units(faq_repository, faq_layout):
    handlers = _reply_handlers(faq_repository, faq_layout)
    answer = "答" * 4998 + "😀"
    faq_repository.official = {
        "fits": _faq_row("fits", answer),
        "oversize": _faq_row("oversize", answer + "答"),
    }
    reply = _reply_payload(handlers, postback="faq:v1:question:fits")
    assert reply == {"type": "text", "text": answer}
    assert len(reply["text"].encode("utf-16-le")) // 2 == 5000
    fallback = _reply_payload(handlers, postback="faq:v1:question:oversize")
    assert "無法完整顯示" in fallback["text"]
    assert "請直接在此留言" in fallback["text"]
    assert answer not in fallback["text"]


def test_faq_05_postback_uses_verified_private_reply_and_paginates_menu(faq_repository, faq_layout):
    label = "長問題按鈕文字超過快速回覆的長度上限測試"
    faq_repository.official["qa-one"] = _faq_row("qa-one", "共用題目答案")
    categories = tuple(
        FaqCategory(
            f"section-{index}", f"分類{index}", f"分類標題{index}", "", "開啟 AI 客服",
            (FaqQuestionLink("qa-one", label),),
        )
        for index in range(7)
    )
    faq_layout.published = FaqLayout(categories)
    handlers = _reply_handlers(faq_repository, faq_layout)

    first = _reply_payload(handlers, text="常見問題")
    first_actions = _body_actions(first)
    assert [action["data"] for action in first_actions if action["type"] == "postback"] == [
        *[f"faq:v1:category:section-{index}" for index in range(6)],
        "faq:v1:menu:1",
    ]
    assert {action.get("text") for action in first_actions if action["type"] == "message"} == {
        "查詢服務進度", "修改登記資料",
    }
    assert all(action["type"] != "uri" for action in first_actions)
    assert len(first["quickReply"]["items"]) <= 13
    assert _reply_payload(handlers, postback="faq:v1:menu:999") == first
    second = _reply_payload(handlers, postback="faq:v1:menu:1")
    assert [a["data"] for a in _body_actions(second) if a["type"] == "postback"] == [
        "faq:v1:category:section-6", "faq:v1:menu:0",
    ]

    card = _reply_payload(handlers, postback="faq:v1:category:section-6")
    assert _body_actions(card) == [{"data": "faq:v1:question:qa-one", "label": label, "type": "postback"}]
    for item in card["quickReply"]["items"]:
        assert len(item["action"]["label"]) <= 20
    assert "開啟 AI 客服" not in json.dumps(card, ensure_ascii=False)
    for payload in (first, second, card, _reply_payload(handlers, postback="faq:v1:question:qa-one")):
        body = json.dumps(payload, ensure_ascii=False)
        assert "target=ai_assistant" not in body and "詢問 AI 客服" not in body
    assert _reply_payload(handlers, text="AI客服") == first
    assert _reply_payload(handlers, postback="faq:v1:question:qa-one", group=True) is None
    assert _reply_payload(handlers, text="常見問題", group=True) is None

    session = Mock()
    session.post.return_value = SimpleNamespace(status_code=200, headers={"x-line-request-id": "faq-fixture"})
    LineMessagingApiAdapter("fixture-token", session=session).reply("fixture-reply", card)
    session.post.assert_called_once()
    endpoint = session.post.call_args.args[0]
    body = json.loads(session.post.call_args.kwargs["data"])
    assert endpoint == "https://api.line.me/v2/bot/message/reply"
    assert body == {"replyToken": "fixture-reply", "messages": [card]}


def test_faq_05_unavailable_or_unpublished_menu_keeps_existing_service_actions(
    faq_repository, faq_layout, monkeypatch,
):
    handlers = _reply_handlers(faq_repository, faq_layout)
    no_publication = _reply_payload(handlers, text="常見問題")
    assert no_publication["type"] == "flex"
    assert not any(a["type"] == "postback" for a in _body_actions(no_publication))

    def layout_unavailable():
        raise FaqLayoutUnavailable
    monkeypatch.setattr(faq_layout, "published_layout", layout_unavailable)
    unavailable = _reply_payload(handlers, text="常見問題")
    assert "暫時無法使用" in unavailable["text"]
    for payload in (no_publication, unavailable):
        actions = [item["action"] for item in payload["quickReply"]["items"]]
        assert {"查詢服務進度", "修改登記資料"} <= {
            action.get("text") for action in actions
        }

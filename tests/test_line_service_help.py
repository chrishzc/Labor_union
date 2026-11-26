"""
File: test_line_service_help.py
Description: 驗證客服問答專屬 LIFF API（FAQ 列表與 AI 智慧問答檢索）以及靜態頁面路由。
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
from api.dependencies.knowledge_retrieval import get_published_faq_catalog
from api.dependencies.line_faq_layout import get_faq_chat_layout_application
from api.dependencies.line_ai_qa_catalog import load_line_ai_qa_catalog
from api.dependencies.line_identity import get_liff_token_verifier
from api.dependencies.llm_configuration import LlmSemanticTestResult, get_llm_configuration_application
from domains.knowledge_retrieval.qa_catalog import GovernedQaContent, encode_governed_qa
from domains.line.faq_chat_layout import FaqCategory, FaqLayout, FaqQuestionLink, project_category
from domains.line.identities import LineSourceType, LineUserId
from infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter
from subsystems.knowledge_retrieval.faq_catalog import PublishedFaqCatalog
from subsystems.line.delivery_contracts import REPLY_ONLY_WEBHOOK_SOURCE
from subsystems.line.faq_chat_layout import FaqCategoryNotPublished, FaqLayoutUnavailable
from subsystems.line.service_help_application import LineServiceHelpApplication
from subsystems.line.webhook_identity_handlers import LineWebhookIdentityHandlers


@pytest.fixture
def semantic_application():
    return Mock(spec=["test_semantics"])


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
def client(semantic_application, faq_repository, faq_layout):
    catalog = PublishedFaqCatalog(faq_repository.unit)
    faq_layout.catalog = catalog
    original = dict(app.dependency_overrides)
    app.dependency_overrides[get_published_faq_catalog] = lambda: catalog
    app.dependency_overrides[get_faq_chat_layout_application] = lambda: faq_layout
    app.dependency_overrides[get_llm_configuration_application] = lambda: semantic_application
    app.dependency_overrides[get_liff_token_verifier] = lambda: Mock(spec=["verify"])
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)


def test_service_help_page_returns_html(client):
    response = client.get("/line-service-help")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    content = response.text
    assert "新竹市月子工會" in content
    assert "常見問答" in content
    assert "AI 智慧問答" in content
    assert "AI 智慧問答助理" in content
    assert "tab-nav" not in content
    assert "依據規範" not in content


def test_service_help_faq_endpoint(client):
    response = client.get("/api/v1/line/service-help/faq")
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    data = body["data"]
    assert "items" in data
    assert "categories" in data
    assert len(data["items"]) >= 5

    qa_ids = {item["qa_id"] for item in data["items"]}
    assert "QA-001" in qa_ids
    assert "QA-005" in qa_ids


def test_service_help_ask_matched_question(client, semantic_application):
    question = "如果和月嫂合作不適合，可以更換月嫂嗎？"
    item = next(item for item in load_line_ai_qa_catalog() if item.id == "QA-001")
    semantic_application.test_semantics.return_value = LlmSemanticTestResult(
        "answered", "fixture", "fixture", 1, item.id, f"line-common-qa:{item.id}", 1,
        item.answer, item.answer, None,
    )
    response = client.post(
        "/api/v1/line/service-help/ask",
        json={"question": "如果和月嫂合作不適合，可以更換月嫂嗎？"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["outcome"] == "answered"
    assert body["data"]["answer_text"]
    assert body["data"]["qa_id"] == "QA-001"
    assert body["data"]["source_identity"] == "line-common-qa:QA-001"
    semantic_application.test_semantics.assert_called_once_with(question)


def test_service_help_ask_unsupported_question(client, semantic_application):
    semantic_application.test_semantics.return_value = LlmSemanticTestResult(
        "unsupported", "fixture", "fixture", 1, None, None, None, None, None, None,
    )
    response = client.post(
        "/api/v1/line/service-help/ask",
        json={"question": "請問如何火星登陸與太空梭維修？"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["outcome"] == "unsupported"
    assert "LINE 官方帳號聊天室" in body["data"]["suggestion"]


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


def _reply_handlers(repository, layout):
    catalog = PublishedFaqCatalog(repository.unit)
    layout.catalog = catalog
    service_help = LineServiceHelpApplication(
        lambda: datetime.now(timezone.utc), faq_catalog=catalog, faq_layout=layout,
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


def test_faq_02_official_version_is_shared_by_web_and_line(client, faq_repository, faq_layout):
    qa_id = "qa-versioned"
    legacy = "這是上一張 LINE 卡片送出的問題？"
    handlers = _reply_handlers(faq_repository, faq_layout)
    faq_repository.legacy[legacy] = (qa_id,)
    faq_repository.official[qa_id] = _faq_row(qa_id, "正式答案 A", question=legacy)
    faq_repository.rows[qa_id] = _faq_row(qa_id, "草稿答案 B", version=2, question="新問題？")

    def assert_shared_answer(expected, version):
        response = client.get("/api/v1/line/service-help/faq", params={"qa_id": qa_id})
        assert response.status_code == 200
        [item] = response.json()["data"]["items"]
        assert item["answer"] == expected
        assert item["version"] == version
        assert item["category"] == "服務流程"
        assert expected in _reply_payload(handlers, text=legacy)["text"]
        assert expected in _reply_payload(handlers, postback=f"faq:v1:question:{qa_id}")["text"]

    assert_shared_answer("正式答案 A", 1)
    faq_repository.official[qa_id] = faq_repository.rows[qa_id]
    assert_shared_answer("草稿答案 B", 2)
    faq_repository.rows[qa_id] = _faq_row(qa_id, "未發布 C", version=3)
    del faq_repository.official[qa_id]
    response = client.get("/api/v1/line/service-help/faq", params={"qa_id": qa_id})
    assert response.json()["data"]["items"] == []
    for kwargs in ({"text": legacy}, {"postback": f"faq:v1:question:{qa_id}"}):
        reply = _reply_payload(handlers, **kwargs)["text"]
        assert "返回常見問題" in reply
        assert all(old_answer not in reply for old_answer in ("正式答案 A", "草稿答案 B", "未發布 C"))


def test_faq_03_walks_all_official_pages_and_surfaces_unavailability(
    client, faq_repository, faq_layout, monkeypatch,
):
    path = "/api/v1/line/service-help/faq"
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
    assert any("target=ai_assistant" in action.get("uri", "") for action in first_actions)
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
    assert "target=ai_assistant" in card["contents"]["footer"]["contents"][-1]["action"]["uri"]
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
        assert {"查詢服務進度", "修改登記資料", "AI客服"} <= {
            action.get("text") for action in actions
        }

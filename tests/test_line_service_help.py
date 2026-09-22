"""
File: test_line_service_help.py
Description: 驗證客服問答專屬 LIFF API（FAQ 列表與 AI 智慧問答檢索）以及靜態頁面路由。
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.dependencies.line_ai_qa_catalog import load_line_ai_qa_catalog
from api.dependencies.line_identity import get_liff_token_verifier
from api.dependencies.llm_configuration import LlmSemanticTestResult, get_llm_configuration_application
from api.routes import line_service_help
from domains.knowledge_retrieval.qa_catalog import GovernedQaContent, encode_governed_qa


@pytest.fixture
def semantic_application():
    return Mock(spec=["test_semantics"])


@pytest.fixture
def client(monkeypatch, semantic_application):
    published = [
        {"content": encode_governed_qa(GovernedQaContent(
            item.id, item.category, item.tag, item.question, item.aliases,
            item.answer, item.source_ref,
        ))}
        for item in load_line_ai_qa_catalog() if item.enabled
    ]

    @contextmanager
    def published_catalog():
        def list_items(limit, status):
            assert (limit, status) == (100, "published")
            return published
        yield SimpleNamespace(knowledge=SimpleNamespace(list_items=list_items))

    monkeypatch.setattr(line_service_help, "open_knowledge_retrieval_unit_of_work", published_catalog)
    original = dict(app.dependency_overrides)
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
    assert "沒看到您想問的問題？" in content
    assert "ai-guide-banner" in content


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


def test_service_help_catalog_unavailable_is_not_replaced_by_builtin_faqs(client, monkeypatch):
    def unavailable():
        raise RuntimeError("synthetic unavailable repository")
    monkeypatch.setattr(line_service_help, "open_knowledge_retrieval_unit_of_work", unavailable)
    response = client.get("/api/v1/line/service-help/faq")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "knowledge_catalog_unavailable"

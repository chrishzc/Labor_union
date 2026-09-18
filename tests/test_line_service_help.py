"""
File: test_line_service_help.py
Description: 驗證客服問答專屬 LIFF API（FAQ 列表與 AI 智慧問答檢索）以及靜態頁面路由。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


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


def test_service_help_ask_matched_question(client):
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


def test_service_help_ask_unsupported_question(client):
    response = client.post(
        "/api/v1/line/service-help/ask",
        json={"question": "請問如何火星登陸與太空梭維修？"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["outcome"] == "unsupported"
    assert "LINE 官方帳號聊天室" in body["data"]["suggestion"]

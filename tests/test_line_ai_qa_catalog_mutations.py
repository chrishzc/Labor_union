from __future__ import annotations

import tempfile
from pathlib import Path

from api.dependencies.line_ai_qa_catalog import (
    LineAiQaCatalogItem,
    create_line_ai_qa_item,
    delete_line_ai_qa_item,
    load_line_ai_qa_catalog,
    save_line_ai_qa_catalog,
    toggle_line_ai_qa_item,
    update_line_ai_qa_item,
)


def test_line_ai_qa_catalog_crud_operations() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        test_file = Path(temp_dir) / "test_qa.jsonl"

        initial_items = [
            LineAiQaCatalogItem(
                id="QA-001",
                category="月嫂媒合",
                tag="更換月嫂",
                question="如果和月嫂合作不適合，可以更換月嫂嗎？",
                aliases=("可以換月嫂嗎？",),
                answer="可以更換。",
                enabled=True,
                source_ref="test.xlsx",
                notes=None,
            ),
            LineAiQaCatalogItem(
                id="QA-002",
                category="合約",
                tag="試用期",
                question="月嫂服務是否有試用期？",
                aliases=(),
                answer="",
                enabled=False,
                source_ref="test.xlsx",
                notes="無直接說明",
            ),
        ]
        save_line_ai_qa_catalog(initial_items, test_file)

        # 1. 讀取
        loaded = load_line_ai_qa_catalog(test_file)
        assert len(loaded) == 2
        assert loaded[0].id == "QA-001"
        assert loaded[0].status == "ready"
        assert loaded[1].status == "missing"

        # 2. 切換啟用狀態
        toggled = toggle_line_ai_qa_item("QA-002", enabled=True, path=test_file)
        assert toggled.enabled is True
        reloaded = load_line_ai_qa_catalog(test_file)
        assert reloaded[1].enabled is True

        # 3. 編輯更新
        updated = update_line_ai_qa_item(
            "QA-002",
            question="月嫂服務是否有試用期？（修訂版）",
            answer="目前平台無試用期制度。",
            category="合約規定",
            tag="試用相關",
            aliases=("試用期如何？",),
            enabled=True,
            notes="管理員已補齊回答",
            path=test_file,
        )
        assert updated.question == "月嫂服務是否有試用期？（修訂版）"
        assert updated.answer == "目前平台無試用期制度。"
        assert updated.status == "ready"

        # 4. 新增題目
        created = create_line_ai_qa_item(
            question="新題目測試？",
            answer="這是新答案。",
            category="測試分類",
            tag="測試",
            aliases=("別名一",),
            enabled=True,
            path=test_file,
        )
        assert created.id == "QA-003"
        reloaded = load_line_ai_qa_catalog(test_file)
        assert len(reloaded) == 3

        # 5. 移除題目
        delete_line_ai_qa_item("QA-001", path=test_file)
        reloaded = load_line_ai_qa_catalog(test_file)
        assert len(reloaded) == 2
        assert all(item.id != "QA-001" for item in reloaded)


def test_fastapi_qa_catalog_put_endpoint() -> None:
    from fastapi.testclient import TestClient
    from api.main import app
    from api.dependencies.admin_auth import require_line_configuration_reader
    from subsystems.access.authentication_session import AdminPrincipal

    def mock_auth():
        return AdminPrincipal(
            id=1,
            username="admin",
            display_name="Admin",
            role="system_admin",
            is_root=True,
        )

    app.dependency_overrides[require_line_configuration_reader] = mock_auth
    try:
        client = TestClient(app)
        res = client.put(
            "/api/v1/line/ai-events/qa-catalog/QA-001",
            json={
                "question": "如果和月嫂合作不適合，可以更換月嫂嗎？",
                "answer": "目前指派的人員都是符合工會標準後才會推薦給媽媽。如果後續實際服務遇到問題，且經協調仍無法解決，會再依相關規定辦理服務人員更換。",
                "category": "月嫂媒合",
                "tag": "更換月嫂",
                "aliases": ["可以換月嫂嗎？"],
                "enabled": True,
            },
        )
        assert res.status_code == 200, res.text
        assert res.json()["data"]["id"] == "QA-001"
    finally:
        app.dependency_overrides.clear()

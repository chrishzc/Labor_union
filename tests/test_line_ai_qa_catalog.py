from __future__ import annotations

from api.dependencies.line_ai_qa_catalog import (
    CATALOG_SOURCE_IDENTITY,
    load_line_ai_qa_catalog,
)


def test_curated_line_ai_qa_catalog_is_visible_and_status_preserving() -> None:
    items = load_line_ai_qa_catalog()

    assert CATALOG_SOURCE_IDENTITY == "document/line/AI客服QA題庫.jsonl"
    assert len(items) == 54
    assert items[0].id == "QA-001"
    assert items[-1].id == "QA-054"
    assert sum(item.status == "ready" for item in items) == 40
    assert any(item.status == "missing" for item in items)
    assert all(item.status in {"ready", "missing"} for item in items)
    assert items[0].aliases
    grocery_fee = next(item for item in items if item.id == "QA-021")
    assert grocery_fee.enabled is True
    assert "食材費由客戶負擔" in grocery_fee.answer
    assert "月嫂不負責代買或代墊" in grocery_fee.answer

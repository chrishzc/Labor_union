from __future__ import annotations

from api.dependencies.line_ai_qa_catalog import (
    CATALOG_SOURCE_IDENTITY,
    load_line_ai_qa_catalog,
)


def test_curated_line_ai_qa_catalog_is_visible_and_status_preserving() -> None:
    items = load_line_ai_qa_catalog()

    assert CATALOG_SOURCE_IDENTITY == "document/line/AI客服QA題庫.jsonl"
    assert len(items) == 29
    assert items[0].id == "QA-001"
    assert items[-1].id == "QA-029"
    assert sum(item.status == "ready" for item in items) == 17
    assert any(item.status == "missing" for item in items)
    assert any(item.status == "review_required" for item in items)
    assert any(item.status == "manual_only" for item in items)
    assert items[0].aliases

"""Read-only curated LINE AI customer-service QA catalog loader."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


CATALOG_SOURCE_IDENTITY = "document/line/AI客服QA題庫.jsonl"
_DEFAULT_CATALOG_PATH = Path(__file__).resolve().parents[2] / CATALOG_SOURCE_IDENTITY


@dataclass(frozen=True, slots=True)
class LineAiQaCatalogItem:
    id: str
    category: str
    tag: str
    question: str
    aliases: tuple[str, ...]
    answer: str
    enabled: bool
    source_ref: str
    notes: str | None = None

    @property
    def status(self) -> str:
        if self.enabled:
            return "ready"
        if not self.answer.strip():
            return "missing"
        if self.notes and "人工" in self.notes:
            return "manual_only"
        return "review_required"


def load_line_ai_qa_catalog(path: Path | None = None) -> tuple[LineAiQaCatalogItem, ...]:
    catalog_path = path or _DEFAULT_CATALOG_PATH
    items: list[LineAiQaCatalogItem] = []
    with catalog_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            aliases = payload.get("aliases", [])
            if not isinstance(aliases, list) or not all(isinstance(value, str) for value in aliases):
                raise ValueError(f"invalid_qa_aliases:{line_number}")
            enabled = payload.get("enabled")
            if not isinstance(enabled, bool):
                raise ValueError(f"invalid_qa_enabled:{line_number}")
            items.append(
                LineAiQaCatalogItem(
                    id=str(payload["id"]),
                    category=str(payload["category"]),
                    tag=str(payload["tag"]),
                    question=str(payload["question"]),
                    aliases=tuple(aliases),
                    answer=str(payload.get("answer", "")),
                    enabled=enabled,
                    source_ref=str(payload["source_ref"]),
                    notes=(str(payload["notes"]) if payload.get("notes") else None),
                )
            )
    return tuple(items)


def save_line_ai_qa_catalog(
    items: tuple[LineAiQaCatalogItem, ...] | list[LineAiQaCatalogItem],
    path: Path | None = None,
) -> None:
    catalog_path = path or _DEFAULT_CATALOG_PATH
    temp_path = catalog_path.with_suffix(".jsonl.tmp")
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    with temp_path.open("w", encoding="utf-8") as handle:
        for item in items:
            record: dict[str, object] = {
                "id": item.id,
                "category": item.category,
                "tag": item.tag,
                "question": item.question,
                "aliases": list(item.aliases),
                "answer": item.answer,
                "enabled": item.enabled,
                "source_ref": item.source_ref,
            }
            if item.notes:
                record["notes"] = item.notes
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    temp_path.replace(catalog_path)


def update_line_ai_qa_item(
    item_id: str,
    *,
    question: str,
    answer: str,
    category: str,
    tag: str,
    aliases: tuple[str, ...] | list[str],
    enabled: bool,
    notes: str | None = None,
    path: Path | None = None,
) -> LineAiQaCatalogItem:
    items = list(load_line_ai_qa_catalog(path))
    target_index = -1
    for index, item in enumerate(items):
        if item.id == item_id:
            target_index = index
            break
    if target_index == -1:
        raise KeyError(f"qa_item_not_found:{item_id}")

    old_item = items[target_index]
    updated_item = LineAiQaCatalogItem(
        id=item_id,
        category=category.strip(),
        tag=tag.strip(),
        question=question.strip(),
        aliases=tuple(alias.strip() for alias in aliases if alias.strip()),
        answer=answer.strip(),
        enabled=enabled,
        source_ref=old_item.source_ref or "custom_admin",
        notes=notes.strip() if notes and notes.strip() else None,
    )
    items[target_index] = updated_item
    save_line_ai_qa_catalog(items, path)
    return updated_item


def toggle_line_ai_qa_item(
    item_id: str,
    enabled: bool,
    path: Path | None = None,
) -> LineAiQaCatalogItem:
    items = list(load_line_ai_qa_catalog(path))
    target_index = -1
    for index, item in enumerate(items):
        if item.id == item_id:
            target_index = index
            break
    if target_index == -1:
        raise KeyError(f"qa_item_not_found:{item_id}")

    old = items[target_index]
    updated = LineAiQaCatalogItem(
        id=old.id,
        category=old.category,
        tag=old.tag,
        question=old.question,
        aliases=old.aliases,
        answer=old.answer,
        enabled=enabled,
        source_ref=old.source_ref,
        notes=old.notes,
    )
    items[target_index] = updated
    save_line_ai_qa_catalog(items, path)
    return updated


def delete_line_ai_qa_item(item_id: str, path: Path | None = None) -> None:
    items = list(load_line_ai_qa_catalog(path))
    remaining = [item for item in items if item.id != item_id]
    if len(remaining) == len(items):
        raise KeyError(f"qa_item_not_found:{item_id}")
    save_line_ai_qa_catalog(remaining, path)


def create_line_ai_qa_item(
    *,
    question: str,
    answer: str,
    category: str,
    tag: str,
    aliases: tuple[str, ...] | list[str],
    enabled: bool = True,
    notes: str | None = None,
    path: Path | None = None,
) -> LineAiQaCatalogItem:
    items = list(load_line_ai_qa_catalog(path))
    existing_numbers: list[int] = []
    for item in items:
        if item.id.startswith("QA-"):
            try:
                existing_numbers.append(int(item.id[3:]))
            except ValueError:
                pass
    next_number = (max(existing_numbers) + 1) if existing_numbers else 1
    new_id = f"QA-{next_number:03d}"

    new_item = LineAiQaCatalogItem(
        id=new_id,
        category=category.strip() or "一般諮詢",
        tag=tag.strip() or "常見問題",
        question=question.strip(),
        aliases=tuple(alias.strip() for alias in aliases if alias.strip()),
        answer=answer.strip(),
        enabled=enabled,
        source_ref="custom_admin",
        notes=notes.strip() if notes and notes.strip() else None,
    )
    items.append(new_item)
    save_line_ai_qa_catalog(items, path)
    return new_item


def enabled_line_ai_qa_catalog(path: Path | None = None) -> tuple[LineAiQaCatalogItem, ...]:
    """Return only QA rows explicitly enabled for automated matching."""
    return tuple(item for item in load_line_ai_qa_catalog(path) if item.enabled)


__all__ = [
    "CATALOG_SOURCE_IDENTITY",
    "LineAiQaCatalogItem",
    "create_line_ai_qa_item",
    "delete_line_ai_qa_item",
    "enabled_line_ai_qa_catalog",
    "load_line_ai_qa_catalog",
    "save_line_ai_qa_catalog",
    "toggle_line_ai_qa_item",
    "update_line_ai_qa_item",
]

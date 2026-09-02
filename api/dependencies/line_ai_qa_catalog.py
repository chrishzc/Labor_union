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


def enabled_line_ai_qa_catalog(path: Path | None = None) -> tuple[LineAiQaCatalogItem, ...]:
    """Return only QA rows explicitly enabled for automated matching."""
    return tuple(item for item in load_line_ai_qa_catalog(path) if item.enabled)


__all__ = [
    "CATALOG_SOURCE_IDENTITY",
    "LineAiQaCatalogItem",
    "enabled_line_ai_qa_catalog",
    "load_line_ai_qa_catalog",
]

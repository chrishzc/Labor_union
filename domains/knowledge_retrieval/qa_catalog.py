"""Canonical structured content for governed LINE common-QA knowledge."""

from __future__ import annotations

import json
from dataclasses import dataclass

from shared_kernel.validation import require_canonical_text

QA_CONTENT_SCHEMA = "line.common_qa.v1"
QA_SOURCE_PREFIX = "line-common-qa:"


@dataclass(frozen=True, slots=True)
class GovernedQaContent:
    qa_id: str
    category: str
    tag: str
    question: str
    aliases: tuple[str, ...]
    answer: str
    source_ref: str
    notes: str | None = None
    migration_status: str | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.qa_id, "qa_id", 80)
        require_canonical_text(self.category, "category", 100)
        require_canonical_text(self.tag, "tag", 100)
        require_canonical_text(self.question, "question", 500)
        require_canonical_text(self.source_ref, "source_ref", 1000)
        if any(not alias.strip() for alias in self.aliases):
            raise ValueError("knowledge_qa_alias_invalid")
        if self.notes is not None and not self.notes.strip():
            raise ValueError("knowledge_qa_notes_invalid")

    @property
    def source_identity(self) -> str:
        return f"{QA_SOURCE_PREFIX}{self.qa_id}"

    def require_publishable(self) -> None:
        if not self.answer.strip():
            raise ValueError("knowledge_qa_answer_required")


def encode_governed_qa(content: GovernedQaContent) -> str:
    payload: dict[str, object] = {
        "schema": QA_CONTENT_SCHEMA,
        "id": content.qa_id,
        "category": content.category,
        "tag": content.tag,
        "question": content.question,
        "aliases": list(content.aliases),
        "answer": content.answer,
        "source_ref": content.source_ref,
        "notes": content.notes,
        "migration_status": content.migration_status,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def decode_governed_qa(encoded: str) -> GovernedQaContent | None:
    try:
        payload = json.loads(encoded)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("schema") != QA_CONTENT_SCHEMA:
        return None
    aliases = payload.get("aliases")
    if not isinstance(aliases, list) or any(not isinstance(value, str) for value in aliases):
        raise ValueError("knowledge_qa_alias_invalid")
    if any(not isinstance(payload.get(key), str) for key in ("id", "category", "tag", "question", "answer", "source_ref")):
        raise ValueError("knowledge_qa_content_invalid")
    notes = payload.get("notes")
    migration_status = payload.get("migration_status")
    if notes is not None and not isinstance(notes, str):
        raise ValueError("knowledge_qa_notes_invalid")
    if migration_status is not None and not isinstance(migration_status, str):
        raise ValueError("knowledge_qa_migration_status_invalid")
    return GovernedQaContent(
        qa_id=payload["id"], category=payload["category"], tag=payload["tag"],
        question=payload["question"], aliases=tuple(value.strip() for value in aliases if value.strip()),
        answer=payload["answer"], source_ref=payload["source_ref"],
        notes=notes, migration_status=migration_status,
    )


__all__ = ["GovernedQaContent", "QA_CONTENT_SCHEMA", "QA_SOURCE_PREFIX", "decode_governed_qa", "encode_governed_qa"]

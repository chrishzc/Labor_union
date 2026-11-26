"""Published FAQ consumer port shared by LINE and the web."""

from __future__ import annotations

from dataclasses import dataclass

from domains.knowledge_retrieval.qa_catalog import decode_governed_qa, is_faq_id


class KnowledgeCatalogUnavailable(RuntimeError):
    """The published catalog could not be read or validated."""


@dataclass(frozen=True, slots=True)
class PublishedFaq:
    qa_id: str
    category: str
    category_id: str | None
    tag: str
    question: str
    answer: str
    aliases: tuple[str, ...]
    source_ref: str
    source_identity: str
    source_version: int
    source_uri: str


@dataclass(frozen=True, slots=True)
class PublishedFaqPage:
    items: tuple[PublishedFaq, ...]
    next_cursor: str | None


class PublishedFaqCatalog:
    def __init__(self, unit_of_work) -> None:
        self._unit_of_work = unit_of_work

    def get(self, qa_id: str) -> PublishedFaq | None:
        if not is_faq_id(qa_id):
            return None
        rows = self._read("published_faq_by_id", qa_id)
        return rows[0] if rows else None

    def page(self, cursor: str | None, limit: int = 50) -> PublishedFaqPage:
        if cursor is not None and not is_faq_id(cursor):
            raise ValueError("faq_cursor_invalid")
        if not 1 <= limit <= 100:
            raise ValueError("faq_limit_invalid")
        rows = self._read("published_faq_page", cursor, limit + 1)
        return PublishedFaqPage(rows[:limit], rows[limit - 1].qa_id if len(rows) > limit else None)

    def match_alias(self, text: str) -> tuple[PublishedFaq, ...]:
        text = text.strip()
        if not text or len(text) > 1000:
            return ()
        return self._read("published_faq_by_alias", text)

    def match_legacy_text(self, text: str) -> tuple[PublishedFaq, ...] | None:
        text = text.strip()
        if not text or len(text) > 1000:
            return None
        try:
            with self._unit_of_work() as unit:
                matched = unit.knowledge.faq_by_legacy_text(text)
                if not matched:
                    return None
                if len(matched) != 1 or matched[0]["source_version"] is None:
                    return ()
                return (_project(matched[0]),)
        except Exception as error:
            raise KnowledgeCatalogUnavailable("knowledge_catalog_unavailable") from error

    def _read(self, method: str, *args) -> tuple[PublishedFaq, ...]:
        try:
            with self._unit_of_work() as unit:
                return tuple(_project(row) for row in getattr(unit.knowledge, method)(*args))
        except Exception as error:
            raise KnowledgeCatalogUnavailable("knowledge_catalog_unavailable") from error


def _project(row: dict) -> PublishedFaq:
    qa = decode_governed_qa(row["content"])
    if qa is None or qa.source_identity != row["source_identity"]:
        raise ValueError("knowledge_qa_snapshot_invalid")
    qa.require_publishable()
    return PublishedFaq(
        qa_id=qa.qa_id,
        category=qa.category,
        category_id=qa.category_id or row.get("legacy_category_id"),
        tag=qa.tag,
        question=qa.question,
        answer=qa.answer,
        aliases=qa.aliases,
        source_ref=qa.source_ref,
        source_identity=qa.source_identity,
        source_version=int(row["source_version"]),
        source_uri=row["source_uri"] if row["source_uri"] is not None else qa.source_ref,
    )

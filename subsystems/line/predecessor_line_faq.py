"""Read-only service-help compatibility while a preserved database is being upgraded."""

from collections.abc import Callable

from domains.line.legacy_faq import LEGACY_FAQ_CATEGORIES, LEGACY_FAQ_GROUPS
from subsystems.knowledge_retrieval.faq_catalog import (
    KnowledgeCatalogUnavailable,
    PredecessorPublishedFaqCatalog,
    PublishedFaq,
)


class PredecessorLineFaq:
    def __init__(
        self,
        catalog: PredecessorPublishedFaqCatalog,
        load_seed: Callable[[], tuple[PublishedFaq, ...]],
    ) -> None:
        self._catalog = catalog
        self._load_seed = load_seed

    def _seed(self) -> tuple[PublishedFaq, ...]:
        try:
            return self._load_seed()
        except (OSError, ValueError, KeyError) as error:
            raise KnowledgeCatalogUnavailable("knowledge_catalog_unavailable") from error

    def match_text(self, text: str) -> tuple[PublishedFaq, ...] | None:
        try:
            seed = self._seed()
        except KnowledgeCatalogUnavailable:
            official = self._catalog.match_alias(text)
            if official:
                return official
            raise
        old = next((item for item in seed if text == item.question or text in item.aliases), None)
        if old is not None:
            official = self._catalog.get(old.qa_id)
            if official is not None:
                return (official,)
            return ()
        return self._catalog.match_alias(text) or None

    def card_questions(self, category_id: str) -> tuple[str, ...]:
        questions = tuple(dict.fromkeys(
            item.question for item in self._seed() if LEGACY_FAQ_GROUPS.get(item.category) == category_id
        ))[:4]
        return questions or LEGACY_FAQ_CATEGORIES[category_id][3]

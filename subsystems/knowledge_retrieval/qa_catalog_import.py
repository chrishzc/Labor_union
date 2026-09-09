"""One-way migration mapping from curated LINE QA input into Knowledge commands."""

from __future__ import annotations

import hashlib

from domains.knowledge_retrieval.qa_catalog import GovernedQaContent, encode_governed_qa
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.knowledge_retrieval.contracts import IngestKnowledgeSourceCommand


def build_qa_import_commands(items, actor: ActorContext, import_key: str, correlation_id: str) -> tuple[IngestKnowledgeSourceCommand, ...]:
    key_digest = hashlib.sha256(import_key.encode("utf-8")).hexdigest()[:24]
    return tuple(
        IngestKnowledgeSourceCommand(
            f"line-common-qa:{item.id}", "internal_policy", item.question,
            encode_governed_qa(GovernedQaContent(
                qa_id=item.id, category=item.category, tag=item.tag,
                question=item.question, aliases=item.aliases, answer=item.answer,
                source_ref=item.source_ref, notes=item.notes, migration_status=item.status,
            )),
            item.source_ref, actor,
            IdempotencyKey(f"qa-import:{key_digest}:{item.id}"),
            CorrelationId(correlation_id),
        )
        for item in items
    )


__all__ = ["build_qa_import_commands"]

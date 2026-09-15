"""Knowledge application construction and portable development catalog bootstrap."""

import hashlib
import os

from api.dependencies.line_ai_qa_catalog import load_line_ai_qa_catalog
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.knowledge_retrieval_unit_of_work import (
    open_knowledge_retrieval_unit_of_work,
)
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.knowledge_retrieval.application import KnowledgeApplication
from subsystems.knowledge_retrieval.contracts import PublishKnowledgeItemCommand
from subsystems.knowledge_retrieval.qa_catalog_import import build_qa_import_commands


def get_knowledge_application() -> KnowledgeApplication:
    return KnowledgeApplication(open_knowledge_retrieval_unit_of_work)


def import_builtin_knowledge_catalog(
    actor: ActorContext,
    import_key: str,
    correlation_id: str,
) -> dict[str, int | None]:
    """Add missing bundled QA and publish only pristine enabled v1 drafts."""
    IdempotencyKey(import_key)
    CorrelationId(correlation_id)
    import_digest = hashlib.sha256(import_key.encode("utf-8")).hexdigest()[:24]
    source_items = load_line_ai_qa_catalog()
    commands = build_qa_import_commands(
        source_items,
        actor,
        import_key,
        correlation_id,
    )
    application = get_knowledge_application()
    imported, skipped = application.import_missing(commands)

    enabled_identities = {
        f"line-common-qa:{item.id}" for item in source_items if item.enabled
    }
    commands_by_identity = {command.source_identity: command for command in commands}
    publish_commands = []
    for item in application.list_items(500):
        source_identity = str(item["source_identity"])
        source_command = commands_by_identity.get(source_identity)
        if (
            source_identity not in enabled_identities
            or source_command is None
            or item["lifecycle_status"] != "draft"
            or int(item["current_version"]) != 1
            or item["content"] != source_command.content
        ):
            continue
        key = f"builtin-publish:{import_digest}:{source_identity}:v1"
        publish_commands.append(
            PublishKnowledgeItemCommand(
                int(item["id"]),
                ExpectedVersion(1),
                actor,
                "restore enabled state from portable bundled QA catalog",
                IdempotencyKey(key),
                CorrelationId(correlation_id),
            )
        )
    published_versions, index_job_id = application.publish_many_and_request_index(
        publish_commands
    )
    return {
        "catalog_count": len(source_items),
        "imported_count": len(imported),
        "skipped_existing_count": len(skipped),
        "published_count": len(published_versions),
        "index_job_id": index_job_id,
    }


def ensure_builtin_knowledge_catalog() -> None:
    """Restore bundled QA content and initial enabled state without overwriting edits."""
    if os.getenv("APP_ENV", "").strip().lower() not in {"dev", "development", "local"}:
        return
    username = os.getenv("DEV_ROOT_USERNAME", "").strip().lower()
    if not username:
        return
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM admin_users WHERE username=%s", (username,))
            row = cursor.fetchone()
    finally:
        connection.close()
    if row is None:
        raise RuntimeError("knowledge_builtin_admin_missing")
    import_builtin_knowledge_catalog(
        ActorContext(str(row["id"])),
        "builtin-line-common-qa-v1",
        "builtin-line-common-qa-v1",
    )


__all__ = [
    "ensure_builtin_knowledge_catalog",
    "get_knowledge_application",
    "import_builtin_knowledge_catalog",
]

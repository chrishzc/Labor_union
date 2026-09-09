"""Knowledge application construction and built-in development catalog bootstrap."""

import os

from api.dependencies.line_ai_qa_catalog import load_line_ai_qa_catalog
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.knowledge_retrieval_unit_of_work import (
    open_knowledge_retrieval_unit_of_work,
)
from shared_kernel.identities import ActorContext
from subsystems.knowledge_retrieval.application import KnowledgeApplication
from subsystems.knowledge_retrieval.qa_catalog_import import build_qa_import_commands


def get_knowledge_application() -> KnowledgeApplication:
    return KnowledgeApplication(open_knowledge_retrieval_unit_of_work)


def ensure_builtin_knowledge_catalog() -> None:
    """Idempotently seed the bundled 29-row catalog for local development."""
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
    commands = build_qa_import_commands(
        load_line_ai_qa_catalog(),
        ActorContext(str(row["id"])),
        "builtin-line-common-qa-v1",
        "builtin-line-common-qa-v1",
    )
    get_knowledge_application().import_missing(commands)


__all__ = ["ensure_builtin_knowledge_catalog", "get_knowledge_application"]

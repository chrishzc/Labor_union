"""Compose a LINE-safe answer only from published cited knowledge."""

from typing import Any

from infrastructure.mysql.knowledge_retrieval_repository import query_published_knowledge


def answer_line_question(question: str) -> str | None:
    result = query_published_knowledge(question)
    if result is None:
        return None
    return _format_cited_answer(result)


def _format_cited_answer(result: dict[str, Any]) -> str:
    sources = "；".join(
        f"{citation['source_uri']}（v{citation['version']}）"
        for citation in result["citations"]
    )
    return f"{result['answer']}\n\n資料來源：{sources}\n此資訊僅供說明，請以行政專員確認為準。"

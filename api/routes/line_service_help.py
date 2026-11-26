"""
File: line_service_help.py
Description: 提供客服問答專屬 LIFF API 與頁面路由，支援常見問答檢索與 AI 智慧問答。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.knowledge_retrieval import published_index_source_versions
from api.dependencies.line_faq_layout import get_service_help_faq_readers
from api.dependencies.line_identity import get_liff_token_verifier
from api.dependencies.llm_configuration import (
    LlmConfigurationApplication,
    LlmSemanticTestResult,
    _qa_id_from_source,
    get_llm_configuration_application,
)
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from domains.knowledge_retrieval.knowledge import (
    KnowledgeAnswer,
    KnowledgeAnswerUnsupported,
    KnowledgeCitation,
)
from infrastructure.line.liff_token_verifier import (
    InvalidLiffTokenError,
    LiffVerificationUnavailableError,
)
from infrastructure.mysql.knowledge_retrieval_unit_of_work import (
    open_knowledge_retrieval_unit_of_work,
)
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.knowledge_retrieval.contracts import AskKnowledgeQuestionCommand
from subsystems.knowledge_retrieval.faq_catalog import (
    KnowledgeCatalogUnavailable,
    is_faq_id,
)
from subsystems.line.faq_chat_layout import FaqLayoutUnavailable
from subsystems.line.service_help_application import ServiceHelpFaqReaders

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SERVICE_HELP_PAGE = PROJECT_ROOT / "line" / "static" / "service_help.html"
_NO_CACHE_HEADERS = {"Cache-Control": "no-cache, no-store, must-revalidate"}

public_router = APIRouter(prefix="/api/v1/line/service-help", tags=["LINE Service Help"])
page_router = APIRouter(tags=["LINE Service Help"])


class FaqItem(BaseModel):
    qa_id: str
    category: str
    category_id: str | None = None
    tag: str
    question: str
    answer: str
    source_ref: str
    version: int


class FaqListResponse(BaseModel):
    items: list[FaqItem]
    categories: list[str]
    next_cursor: str | None = None


class ServiceHelpAskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=1000)
    interaction_id: str = Field(default="", max_length=160)
    line_id_token: str = Field(default="", max_length=4096)


class ServiceHelpAskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: str
    answer_text: str | None = None
    qa_id: str | None = None
    source_identity: str | None = None
    source_version: int | None = None
    index_version: int | None = None
    source_ref: str | None = None
    suggestion: str | None = None
    interaction_id: str | None = None
    answer_receipt_id: int | None = None
    feedback_request_id: int | None = None


@page_router.get("/line-service-help", include_in_schema=False)
def service_help_page():
    if not _SERVICE_HELP_PAGE.exists():
        raise HTTPException(status_code=404, detail="Service help page not found")
    return FileResponse(_SERVICE_HELP_PAGE, headers=_NO_CACHE_HEADERS)


@public_router.get("/faq", response_model=BaseResponse[FaqListResponse])
def get_published_faqs(
    select_readers: Annotated[Callable[[], ServiceHelpFaqReaders], Depends(get_service_help_faq_readers)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    qa_id: str | None = None,
) -> BaseResponse[FaqListResponse]:
    if qa_id is not None and (not is_faq_id(qa_id) or cursor is not None):
        raise _faq_validation_error("faq_query_invalid", "題目識別或查詢條件無效。")
    try:
        readers = select_readers()
        catalog, layout = readers.catalog, readers.layout
        if catalog is None:
            raise KnowledgeCatalogUnavailable("knowledge_catalog_unavailable")
        if qa_id is None:
            page = catalog.page(cursor, limit)
            questions, next_cursor = page.items, page.next_cursor
        else:
            question = catalog.get(qa_id)
            questions, next_cursor = ((question,) if question else ()), None
        category_names = layout.category_names() if layout is not None and questions else {}
    except ValueError as error:
        if str(error) != "faq_cursor_invalid":
            raise
        raise _faq_validation_error("faq_cursor_invalid", "常見問答的頁面游標無效。") from error
    except (KnowledgeCatalogUnavailable, FaqLayoutUnavailable) as error:
        code = (
            "faq_layout_unavailable"
            if isinstance(error, FaqLayoutUnavailable)
            else "knowledge_catalog_unavailable"
        )
        raise typed_http_error(
            503,
            "unavailable",
            code,
            "常見問答暫時無法讀取，請稍後再試。",
            "line-service-help:faq",
            retryable=True,
        ) from error

    items = [
        FaqItem(
            qa_id=item.qa_id,
            category=category_names.get(item.category_id, item.category),
            category_id=item.category_id,
            tag=item.tag,
            question=item.question,
            answer=item.answer,
            source_ref=item.source_ref,
            version=item.source_version,
        )
        for item in questions
    ]
    categories = list(dict.fromkeys(item.category for item in items))
    return BaseResponse(data=FaqListResponse(items=items, categories=categories, next_cursor=next_cursor))


def _faq_validation_error(code: str, message: str) -> HTTPException:
    return typed_http_error(422, "validation", code, message, "line-service-help:faq")


@public_router.post("/ask", response_model=BaseResponse[ServiceHelpAskResponse])
def ask_service_question(
    body: ServiceHelpAskRequest,
    application: LlmConfigurationApplication = Depends(get_llm_configuration_application),
    liff_verifier=Depends(get_liff_token_verifier),
) -> BaseResponse[ServiceHelpAskResponse]:
    clean_question = body.question.strip()
    interaction_id, actor_id = _verified_liff_interaction(body, liff_verifier)
    if interaction_id is not None and actor_id is not None:
        replay = _replay_liff_response(clean_question, interaction_id, actor_id)
        if replay is not None:
            return replay

    try:
        semantic_result = application.test_semantics(clean_question)
    except Exception as error:
        raise _liff_query_failed(clean_question, interaction_id, actor_id, "knowledge_query_unavailable") from error

    if semantic_result.outcome == "answered" and semantic_result.answer_text:
        answer_receipt_id = None
        if interaction_id is not None and actor_id is not None:
            try:
                answer_receipt_id = _persist_liff_answer(
                    clean_question,
                    interaction_id,
                    actor_id,
                    semantic_result,
                )
            except KnowledgeAnswerUnsupported:
                return _unsupported_answer(clean_question, interaction_id, actor_id)
        return BaseResponse(
            data=ServiceHelpAskResponse(
                outcome="answered",
                answer_text=semantic_result.answer_text,
                qa_id=semantic_result.qa_id,
                source_identity=semantic_result.source_identity,
                source_version=semantic_result.source_version,
                index_version=semantic_result.index_version,
                source_ref=semantic_result.source_identity,
                interaction_id=interaction_id,
                answer_receipt_id=answer_receipt_id,
            ),
            message="AI 助理已由知識庫為您找到解答",
        )

    if semantic_result.outcome == "unsupported":
        return _unsupported_answer(
            clean_question, interaction_id, actor_id, semantic_result.index_version,
        )

    code = "knowledge_query_unavailable"
    if semantic_result.outcome in {"index_unavailable", "provider_error"} and semantic_result.code:
        code = semantic_result.code
    raise _liff_query_failed(clean_question, interaction_id, actor_id, code)


def _unsupported_answer(
    question: str,
    interaction_id: str | None,
    actor_id: str | None,
    index_version: int | None = None,
) -> BaseResponse[ServiceHelpAskResponse]:
    feedback_request_id = (
        _persist_liff_outcome(question, interaction_id, actor_id, "unsupported")
        if interaction_id is not None and actor_id is not None
        else None
    )
    return BaseResponse(
        data=ServiceHelpAskResponse(
            outcome="unsupported",
            index_version=index_version,
            suggestion="抱歉，工會知識庫目前尚未收錄與您提問完全相符的標準解答。您可以直接在此 LINE 官方帳號聊天室中留言，工會真人客服專員將親自為您詳細解說！",
            interaction_id=interaction_id,
            feedback_request_id=feedback_request_id,
        ),
        message="未找到相符解答，已引導真人客服",
    )


def _verified_liff_interaction(
    body: ServiceHelpAskRequest,
    verifier,
) -> tuple[str | None, str | None]:
    token = body.line_id_token.strip()
    interaction_id = body.interaction_id.strip()
    if not token and not interaction_id:
        return None, None
    if not token or not interaction_id:
        raise typed_http_error(
            422,
            "validation",
            "liff_interaction_identity_incomplete",
            "LINE 問答身分資訊不完整，請重新從 LINE 開啟此頁。",
            "line-service-help:interaction",
        )
    try:
        identity = verifier.verify(token)
    except InvalidLiffTokenError as error:
        raise typed_http_error(
            401,
            "forbidden",
            "liff_token_invalid",
            "LINE 登入狀態已失效，請重新從 LINE 開啟此頁。",
            "line-service-help:liff-token-invalid",
        ) from error
    except LiffVerificationUnavailableError as error:
        raise typed_http_error(
            503,
            "unavailable",
            "liff_verification_unavailable",
            "LINE 身分驗證服務暫時無法使用，請稍後再試。",
            "line-service-help:liff-verification-unavailable",
            retryable=True,
        ) from error
    return interaction_id, identity.line_user_id.value


def _replay_liff_response(
    question: str,
    interaction_id: str,
    actor_id: str,
) -> BaseResponse[ServiceHelpAskResponse] | None:
    command = AskKnowledgeQuestionCommand(
        question,
        actor_id,
        IdempotencyKey(f"liff-knowledge-answer:{interaction_id}"),
        CorrelationId(f"liff-knowledge:{interaction_id}"),
    )
    try:
        with open_knowledge_retrieval_unit_of_work() as unit_of_work:
            previous = unit_of_work.read_inline_request(command)
    except Exception as error:
        if isinstance(error, RuntimeError) and str(error) == "knowledge_answer_idempotency_conflict":
            raise typed_http_error(
                409,
                "conflict",
                "knowledge_answer_idempotency_conflict",
                "此問答互動識別已被使用，請重新提出問題。",
                "line-service-help:interaction",
            ) from error
        raise _knowledge_query_unavailable("knowledge_answer_observation_unavailable") from error
    if previous is None:
        return None
    if previous["request_status"] == "unsupported":
        return BaseResponse(
            data=ServiceHelpAskResponse(
                outcome="unsupported",
                suggestion="抱歉，工會知識庫目前尚未收錄與您提問完全相符的標準解答。您可以直接在此 LINE 官方帳號聊天室中留言，工會真人客服專員將親自為您詳細解說！",
                interaction_id=interaction_id,
                feedback_request_id=int(previous["id"]),
            ),
            message="未找到相符解答，已引導真人客服",
        )
    if previous["request_status"] != "answered":
        # The existing failed request does not store the original provider code.
        request_id = int(previous["id"]) if previous["request_status"] == "failed" else None
        raise _knowledge_query_unavailable("knowledge_query_unavailable", request_id)
    if (
        previous["answer_receipt_id"] is None
        or not previous["answer_text"]
        or previous["index_version"] is None
        or not previous["citations"]
    ):
        raise _knowledge_query_unavailable("knowledge_answer_provenance_incomplete")
    faq_sources = {
        (citation["source_identity"], citation["source_version"])
        for citation in previous["citations"]
        if _qa_id_from_source(citation["source_identity"]) is not None
    }
    if faq_sources:
        try:
            current_sources = published_index_source_versions(
                tuple(sorted({source for source, _ in faq_sources}))
            )
        except Exception as error:
            raise _knowledge_query_unavailable("knowledge_catalog_unavailable") from error
        if not faq_sources <= current_sources:
            raise _knowledge_query_unavailable("knowledge_answer_source_changed")
    citation = previous["citations"][0]
    return BaseResponse(
        data=ServiceHelpAskResponse(
            outcome="answered",
            answer_text=previous["answer_text"],
            qa_id=_qa_id_from_source(citation["source_identity"]),
            source_identity=citation["source_identity"],
            source_version=citation["source_version"],
            index_version=previous["index_version"],
            source_ref=citation["source_identity"],
            interaction_id=interaction_id,
            answer_receipt_id=previous["answer_receipt_id"],
        ),
        message="AI 助理已由知識庫為您找到解答",
    )


def _persist_liff_answer(
    question: str,
    interaction_id: str,
    actor_id: str,
    semantic_result: LlmSemanticTestResult,
) -> int:
    if (
        semantic_result.source_identity is None
        or semantic_result.source_version is None
        or semantic_result.source_excerpt is None
        or semantic_result.index_version is None
        or semantic_result.answer_text is None
    ):
        raise _knowledge_query_unavailable("knowledge_answer_provenance_incomplete")
    answer = KnowledgeAnswer(
        answer=semantic_result.answer_text,
        citations=(
            KnowledgeCitation(
                semantic_result.source_identity,
                semantic_result.source_version,
                semantic_result.source_excerpt,
            ),
        ),
        index_version=semantic_result.index_version,
    )
    command = AskKnowledgeQuestionCommand(
        question,
        actor_id,
        IdempotencyKey(f"liff-knowledge-answer:{interaction_id}"),
        CorrelationId(f"liff-knowledge:{interaction_id}"),
    )
    try:
        with open_knowledge_retrieval_unit_of_work() as unit_of_work:
            receipt_id = unit_of_work.knowledge.record_inline_answer(command, answer)
            unit_of_work.commit()
    except (HTTPException, KnowledgeAnswerUnsupported):
        raise
    except Exception as error:
        raise _knowledge_query_unavailable("knowledge_answer_receipt_unavailable") from error
    return receipt_id


def _persist_liff_outcome(
    question: str,
    interaction_id: str,
    actor_id: str,
    request_status: str,
) -> int:
    command = AskKnowledgeQuestionCommand(
        question,
        actor_id,
        IdempotencyKey(f"liff-knowledge-answer:{interaction_id}"),
        CorrelationId(f"liff-knowledge:{interaction_id}"),
    )
    try:
        with open_knowledge_retrieval_unit_of_work() as unit_of_work:
            request_id = unit_of_work.record_inline_outcome(command, request_status)
            unit_of_work.commit()
    except HTTPException:
        raise
    except Exception as error:
        raise _knowledge_query_unavailable("knowledge_answer_observation_unavailable") from error
    return request_id


def _liff_query_failed(
    question: str, interaction_id: str | None, actor_id: str | None, code: str,
) -> HTTPException:
    request_id = None
    if interaction_id is not None and actor_id is not None:
        request_id = _persist_liff_outcome(question, interaction_id, actor_id, "failed")
    return _knowledge_query_unavailable(code, request_id)


def _knowledge_query_unavailable(code: str, feedback_request_id: int | None = None) -> HTTPException:
    error = typed_http_error(
        503,
        "unavailable",
        code,
        "AI 智慧問答服務暫時無法使用，請稍後再試。",
        "line-service-help:ask",
        retryable=True,
    )
    if feedback_request_id is not None:
        error.headers = {"X-LIFF-Feedback-Request-Id": str(feedback_request_id)}
    return error


__all__ = ["page_router", "public_router"]

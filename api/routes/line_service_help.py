"""
File: line_service_help.py
Description: 提供客服問答專屬 LIFF API 與頁面路由，支援常見問答檢索與 AI 智慧問答。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.llm_configuration import (
    LlmConfigurationApplication,
    get_llm_configuration_application,
)
from api.schemas.base import BaseResponse
from domains.knowledge_retrieval.qa_catalog import decode_governed_qa
from infrastructure.mysql.knowledge_retrieval_unit_of_work import (
    open_knowledge_retrieval_unit_of_work,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SERVICE_HELP_PAGE = PROJECT_ROOT / "line" / "static" / "service_help.html"
_NO_CACHE_HEADERS = {"Cache-Control": "no-cache, no-store, must-revalidate"}

public_router = APIRouter(prefix="/api/v1/line/service-help", tags=["LINE Service Help"])
page_router = APIRouter(tags=["LINE Service Help"])

_CANONICAL_FAQS = [
    {
        "qa_id": "service_hours_intro",
        "category": "服務內容與時數",
        "tag": "服務時數",
        "question": "月嫂每天的服務時數有哪些選擇？",
        "answer": "工會提供 4 小時、8 小時、9 小時、12 小時與 24 小時（全日住家）等多種彈性服務時數，可依據產婦家庭需求進行客製化媒合。",
        "source_ref": "工會服務規章第 3 條",
    },
    {
        "qa_id": "subsidy_intro",
        "category": "收費與政府補助",
        "tag": "政府補助",
        "question": "如何申請新竹市到宅月子產婦補助？",
        "answer": "凡符合新竹市到宅月子服務補助資格之產婦，可於市府平台提出申請。工會將依市府核定之補助時數進行費用扣抵，詳情可諮詢工會專員。",
        "source_ref": "新竹市到宅月子媒合服務實施要點",
    },
    {
        "qa_id": "cooking_diet_intro",
        "category": "服務內容與時數",
        "tag": "月子餐與下廚",
        "question": "月嫂服務包含煮月子餐與家務整理嗎？",
        "answer": "月嫂服務以產婦照護及新生兒照護為核心。下廚煮餐（月子餐料理、簡易家庭餐）可於訂單登記時選填約定；服務範圍不包含重度全戶大掃除。",
        "source_ref": "工會服務規章第 5 條",
    },
    {
        "qa_id": "caregiver_leave_intro",
        "category": "服務變更與請假",
        "tag": "月嫂請假代班",
        "question": "如果月嫂服務期間臨時請假或生病，工會如何處理？",
        "answer": "月嫂因病或突發事故請假時，工會將第一時間啟動代班機制，協調合格月嫂支援代班，或依產婦意願進行服務天數順延調整。",
        "source_ref": "工會服務代班規約",
    },
    {
        "qa_id": "human_contact_intro",
        "category": "客服與聯繫",
        "tag": "真人專員服務",
        "question": "如果想直接與工會專人聯繫，可以如何聯絡？",
        "answer": "您可以直接在目前這個 LINE 官方帳號聊天室中打字留言，留下您的姓名、電話與想諮詢的問題，工會真人客服專員將於服務時間內盡速親自回覆您！",
        "source_ref": "工會客服作業手冊",
    },
]


class FaqItem(BaseModel):
    qa_id: str
    category: str
    tag: str
    question: str
    answer: str
    source_ref: str


class FaqListResponse(BaseModel):
    items: list[FaqItem]
    categories: list[str]


class ServiceHelpAskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=1000)


class ServiceHelpAskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: str
    answer_text: str | None = None
    qa_id: str | None = None
    source_identity: str | None = None
    source_ref: str | None = None
    suggestion: str | None = None


@page_router.get("/line-service-help", include_in_schema=False)
def service_help_page():
    if not _SERVICE_HELP_PAGE.exists():
        raise HTTPException(status_code=404, detail="Service help page not found")
    return FileResponse(_SERVICE_HELP_PAGE, headers=_NO_CACHE_HEADERS)


@public_router.get("/faq", response_model=BaseResponse[FaqListResponse])
def get_published_faqs() -> BaseResponse[FaqListResponse]:
    items: list[FaqItem] = []
    seen_ids: set[str] = set()

    try:
        with open_knowledge_retrieval_unit_of_work() as unit_of_work:
            raw_items = unit_of_work.knowledge.list_items(100, "published")
            for raw in raw_items:
                decoded = decode_governed_qa(raw.get("content", ""))
                if decoded and decoded.qa_id not in seen_ids:
                    items.append(
                        FaqItem(
                            qa_id=decoded.qa_id,
                            category=decoded.category,
                            tag=decoded.tag,
                            question=decoded.question,
                            answer=decoded.answer,
                            source_ref=decoded.source_ref,
                        )
                    )
                    seen_ids.add(decoded.qa_id)
    except Exception:
        pass

    for fallback in _CANONICAL_FAQS:
        if fallback["qa_id"] not in seen_ids:
            items.append(FaqItem(**fallback))
            seen_ids.add(fallback["qa_id"])

    categories = list(dict.fromkeys(item.category for item in items))
    return BaseResponse(data=FaqListResponse(items=items, categories=categories))


@public_router.post("/ask", response_model=BaseResponse[ServiceHelpAskResponse])
def ask_service_question(
    body: ServiceHelpAskRequest,
    application: LlmConfigurationApplication = Depends(get_llm_configuration_application),
) -> BaseResponse[ServiceHelpAskResponse]:
    clean_question = body.question.strip()

    try:
        semantic_result = application.test_semantics(clean_question)
        if semantic_result.outcome == "answered" and semantic_result.answer_text:
            return BaseResponse(
                data=ServiceHelpAskResponse(
                    outcome="answered",
                    answer_text=semantic_result.answer_text,
                    qa_id=semantic_result.qa_id,
                    source_identity=semantic_result.source_identity,
                    source_ref=semantic_result.source_identity,
                ),
                message="AI 助理已由知識庫為您找到解答",
            )
    except Exception:
        pass

    lower_q = clean_question.lower()
    for item in _CANONICAL_FAQS:
        if any(keyword in lower_q for keyword in (item["tag"].lower(), item["question"].lower()[:6])):
            return BaseResponse(
                data=ServiceHelpAskResponse(
                    outcome="answered",
                    answer_text=item["answer"],
                    qa_id=item["qa_id"],
                    source_identity=f"line-common-qa:{item['qa_id']}",
                    source_ref=item["source_ref"],
                ),
                message="已由工會常見問答找到相符說明",
            )

    return BaseResponse(
        data=ServiceHelpAskResponse(
            outcome="unsupported",
            answer_text=None,
            suggestion="抱歉，工會知識庫目前尚未收錄與您提問完全相符的標準解答。您可以直接在此 LINE 官方帳號聊天室中留言，工會真人客服專員將親自為您詳細解說！",
        ),
        message="未找到相符解答，已引導真人客服",
    )


__all__ = ["page_router", "public_router"]

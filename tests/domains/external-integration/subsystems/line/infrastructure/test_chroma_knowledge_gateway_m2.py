"""Focused M2 tests for curated QA indexing, retrieval, and safe LLM selection."""

from __future__ import annotations

import json

import pytest

from domains.knowledge_retrieval.knowledge import KnowledgeAnswerUnsupported
from infrastructure.knowledge.chroma_gateway import ChromaKnowledgeGateway


class _Collection:
    def __init__(self, name: str) -> None:
        self.name = name
        self.ids: list[str] = []
        self.documents: list[str] = []
        self.metadatas: list[dict] = []

    def add(self, *, ids, documents, metadatas) -> None:
        self.ids = list(ids)
        self.documents = list(documents)
        self.metadatas = list(metadatas)

    def count(self) -> int:
        return len(self.ids)

    def query(self, *, query_texts, n_results):
        del query_texts
        return {
            "documents": [self.documents[:n_results]],
            "metadatas": [self.metadatas[:n_results]],
        }


class _Client:
    def __init__(self) -> None:
        self.collections: dict[str, _Collection] = {}

    def list_collections(self):
        return tuple(self.collections.values())

    def delete_collection(self, name: str) -> None:
        self.collections.pop(name, None)

    def create_collection(self, name: str) -> _Collection:
        collection = _Collection(name)
        self.collections[name] = collection
        return collection

    def get_collection(self, name: str) -> _Collection:
        return self.collections[name]


def _catalog(tmp_path):
    path = tmp_path / "qa.jsonl"
    records = (
        {
            "id": "QA-001",
            "category": "月嫂媒合",
            "tag": "更換月嫂",
            "question": "如果和月嫂合作不適合，可以更換月嫂嗎？",
            "aliases": ["可以換月嫂嗎？", "跟月嫂觀念不合可以換人嗎？"],
            "answer": "經協調仍無法解決時，會依相關規定辦理服務人員更換。",
            "status": "ready",
            "source_ref": "document/line/QA問答集.xlsx",
        },
        {
            "id": "QA-003",
            "category": "合約",
            "tag": "試用期",
            "question": "月嫂服務是否有試用期？",
            "aliases": ["有試用期嗎？"],
            "answer": "",
            "status": "missing",
            "source_ref": "document/line/QA問答集.xlsx",
        },
        {
            "id": "QA-007",
            "category": "月嫂資訊",
            "tag": "服務經驗",
            "question": "平台的月嫂有服務經驗嗎？",
            "aliases": ["月嫂有經驗嗎？"],
            "answer": "待人工確認的回答。",
            "status": "review_required",
            "source_ref": "document/line/QA問答集.xlsx",
        },
    )
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )
    return path


def _gateway(tmp_path, *, llm=None, min_confidence: float = 0.60):
    client = _Client()
    gateway = ChromaKnowledgeGateway(
        str(tmp_path / "chroma"),
        catalog_path=_catalog(tmp_path),
        llm=llm,
        min_confidence=min_confidence,
    )
    gateway._client = lambda: client
    return gateway, client


def test_rebuild_indexes_only_ready_catalog_with_labels_and_aliases(tmp_path) -> None:
    gateway, client = _gateway(tmp_path)

    indexed = gateway.rebuild(1, ())

    assert [item["catalog_id"] for item in indexed] == ["QA-001"]
    document = client.get_collection("union_knowledge_v1").documents[0]
    assert "月嫂媒合" in document
    assert "更換月嫂" in document
    assert "可以換月嫂嗎？" in document


def test_llm_can_only_select_candidate_and_answer_stays_verbatim(tmp_path) -> None:
    prompts: list[str] = []

    def llm(prompt: str) -> str:
        prompts.append(prompt)
        return "QA-001"

    gateway, _ = _gateway(tmp_path, llm=llm)
    gateway.rebuild(2, ())

    answer = gateway.answer("可以換月嫂嗎？", 2)

    expected = "經協調仍無法解決時，會依相關規定辦理服務人員更換。"
    assert answer.answer == expected
    assert answer.authoritative is False
    assert answer.citations[0].safe_excerpt == expected
    assert expected not in prompts[0]
    assert "只能回傳下列候選 ID" in prompts[0]


def test_no_model_or_low_confidence_fails_closed(tmp_path) -> None:
    gateway, _ = _gateway(tmp_path)
    gateway.rebuild(3, ())

    with pytest.raises(KnowledgeAnswerUnsupported, match="knowledge_answer_unsupported"):
        gateway.answer("可以換月嫂嗎？", 3)

    def unexpected_llm(_: str) -> str:
        raise AssertionError("low-confidence input must not reach the LLM")

    guarded_gateway, _ = _gateway(tmp_path, llm=unexpected_llm)
    guarded_gateway.rebuild(4, ())
    with pytest.raises(KnowledgeAnswerUnsupported, match="knowledge_answer_unsupported"):
        guarded_gateway.answer("火星基地的氧氣供應怎麼算？", 4)

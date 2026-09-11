"""Focused M2 tests for curated QA indexing, retrieval, and safe LLM selection."""

from __future__ import annotations

import pytest

from domains.knowledge_retrieval.knowledge import KnowledgeAnswerUnsupported
from domains.knowledge_retrieval.qa_catalog import GovernedQaContent, encode_governed_qa
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


def _published_qa():
    content = GovernedQaContent(
        qa_id="QA-001",
        category="月嫂媒合",
        tag="更換月嫂",
        question="如果和月嫂合作不適合，可以更換月嫂嗎？",
        aliases=("可以換月嫂嗎？", "跟月嫂觀念不合可以換人嗎？"),
        answer="經協調仍無法解決時，會依相關規定辦理服務人員更換。",
        source_ref="document/line/QA問答集.xlsx",
    )
    return {
        "source_identity": content.source_identity,
        "source_version": 3,
        "source_digest": "published-digest",
        "title": content.question,
        "content": encode_governed_qa(content),
        "source_uri": content.source_ref,
    }


def _published_subsidy_qa(
    *,
    qa_id: str,
    question: str,
    aliases: tuple[str, ...],
    answer: str,
):
    content = GovernedQaContent(
        qa_id=qa_id,
        category="補助",
        tag="補助時數",
        question=question,
        aliases=aliases,
        answer=answer,
        source_ref="formal-subsidy-policy",
    )
    return {
        "source_identity": content.source_identity,
        "source_version": 3,
        "source_digest": f"published-{qa_id}",
        "title": content.question,
        "content": encode_governed_qa(content),
        "source_uri": content.source_ref,
    }


def _published_food_qa(
    *,
    qa_id: str,
    tag: str,
    question: str,
    aliases: tuple[str, ...],
    answer: str,
):
    content = GovernedQaContent(
        qa_id=qa_id,
        category="餐飲服務",
        tag=tag,
        question=question,
        aliases=aliases,
        answer=answer,
        source_ref="formal-service-policy",
    )
    return {
        "source_identity": content.source_identity,
        "source_version": 3,
        "source_digest": f"published-{qa_id}",
        "title": content.question,
        "content": encode_governed_qa(content),
        "source_uri": content.source_ref,
    }


def _gateway(tmp_path, *, llm=None, min_confidence: float = 0.60):
    client = _Client()
    gateway = ChromaKnowledgeGateway(
        str(tmp_path / "chroma"),
        llm=llm,
        min_confidence=min_confidence,
    )
    gateway._client = lambda: client
    return gateway, client


def test_rebuild_indexes_only_supplied_published_knowledge_with_labels_and_aliases(tmp_path) -> None:
    gateway, client = _gateway(tmp_path)

    assert gateway.rebuild(1, ()) == ()
    indexed = gateway.rebuild(1, (_published_qa(),))

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
    gateway.rebuild(2, (_published_qa(),))

    answer = gateway.answer("可以更換月嫂嗎？", 2)

    expected = "經協調仍無法解決時，會依相關規定辦理服務人員更換。"
    assert answer.answer == expected
    assert answer.authoritative is False
    assert answer.citations[0].safe_excerpt == expected
    assert expected not in prompts[0]
    assert "只能回傳下列候選 ID" in prompts[0]


def test_no_model_or_low_confidence_fails_closed(tmp_path) -> None:
    gateway, _ = _gateway(tmp_path)
    gateway.rebuild(3, (_published_qa(),))

    with pytest.raises(KnowledgeAnswerUnsupported, match="knowledge_answer_unsupported"):
        gateway.answer("我能更換服務人員嗎？", 3)

    def unexpected_llm(_: str) -> str:
        raise AssertionError("low-confidence input must not reach the LLM")

    guarded_gateway, _ = _gateway(tmp_path, llm=unexpected_llm)
    guarded_gateway.rebuild(4, (_published_qa(),))
    with pytest.raises(KnowledgeAnswerUnsupported, match="knowledge_answer_unsupported"):
        guarded_gateway.answer("火星基地的氧氣供應怎麼算？", 4)


def test_exact_combined_alias_returns_published_answer_without_model(tmp_path) -> None:
    content = GovernedQaContent(
        qa_id="QA-019",
        category="餐飲服務",
        tag="食材準備",
        question="月嫂料理需要由家人先準備食材嗎？",
        aliases=("我要自己買菜嗎，買菜錢是我出嗎",),
        answer="食材由客戶自行購買並負擔費用，月嫂不代買或代墊。",
        source_ref="formal-service-policy",
    )
    item = {
        "source_identity": content.source_identity,
        "source_version": 2,
        "source_digest": "published-QA-019",
        "title": content.question,
        "content": encode_governed_qa(content),
        "source_uri": content.source_ref,
    }

    def unexpected_llm(_: str) -> str:
        raise AssertionError("an exact published alias must not require model selection")

    gateway, _ = _gateway(tmp_path, llm=unexpected_llm)
    gateway.rebuild(9, (item,))

    answer = gateway.answer("我要自己買菜嗎，買菜錢是我出嗎", 9)

    assert answer.answer == "食材由客戶自行購買並負擔費用，月嫂不代買或代墊。"


def test_natural_food_preparation_paraphrase_reaches_only_matching_candidate(tmp_path) -> None:
    prompts: list[str] = []

    def llm(prompt: str) -> str:
        prompts.append(prompt)
        return "QA-019"

    gateway, _ = _gateway(tmp_path, llm=llm)
    items = (
        _published_food_qa(
            qa_id="QA-019",
            tag="食材準備",
            question="月嫂料理需要由家人先準備食材嗎？",
            aliases=("我要自己買菜嗎",),
            answer="食材由客戶自行購買並負擔費用，月嫂不代買或代墊。",
        ),
        _published_food_qa(
            qa_id="QA-020",
            tag="食材採買",
            question="可以請月嫂在服務時間外出買菜嗎？",
            aliases=("月嫂會出去買菜嗎？",),
            answer="月嫂不負責利用服務時間外出採買。",
        ),
        _published_food_qa(
            qa_id="QA-021",
            tag="食材採買費用",
            question="料理食材費用由誰負擔？",
            aliases=("買菜錢是我出嗎",),
            answer="食材費由客戶負擔。",
        ),
    )
    gateway.rebuild(10, items)

    answer = gateway.answer("所有食材是不是都要我自己準備？", 10)

    assert answer.answer == "食材由客戶自行購買並負擔費用，月嫂不代買或代墊。"
    assert "QA-019" in prompts[0]
    assert "QA-020" not in prompts[0]
    assert "QA-021" not in prompts[0]


def test_social_welfare_question_cannot_select_general_citizen_subsidy(tmp_path) -> None:
    def unexpected_llm(_: str) -> str:
        raise AssertionError("scope-incompatible candidate must not reach the LLM")

    gateway, _ = _gateway(tmp_path, llm=unexpected_llm, min_confidence=0.0)
    gateway.rebuild(
        5,
        (
            _published_subsidy_qa(
                qa_id="QA-025",
                question="市府到府月子服務補助多少小時？",
                aliases=("政府補助幾小時？",),
                answer="市府補助 40 小時。",
            ),
        ),
    )

    with pytest.raises(KnowledgeAnswerUnsupported, match="knowledge_answer_unsupported"):
        gateway.answer("低收入戶社福補助多少？", 5)


def test_social_welfare_question_can_select_only_explicit_social_welfare_qa(tmp_path) -> None:
    gateway, _ = _gateway(tmp_path, llm=lambda _: "QA-026", min_confidence=0.0)
    gateway.rebuild(
        6,
        (
            _published_subsidy_qa(
                qa_id="QA-026",
                question="低收入戶的社福補助怎麼計算？",
                aliases=("社福補助多少？",),
                answer="低收入戶依補助市民政策，每小時 350 元，最多 120 小時。",
            ),
        ),
    )

    answer = gateway.answer("低收入戶社福補助多少？", 6)

    assert answer.answer == "低收入戶依補助市民政策，每小時 350 元，最多 120 小時。"


def test_short_social_welfare_alias_is_not_lost_beyond_initial_vector_results(tmp_path) -> None:
    gateway, _ = _gateway(tmp_path, llm=lambda _: "QA-026")
    distractors = tuple(
        _published_subsidy_qa(
            qa_id=f"QA-GENERAL-{index}",
            question=f"一般市民補助說明 {index}",
            aliases=(f"一般市民問題 {index}",),
            answer=f"一般市民答案 {index}",
        )
        for index in range(5)
    )
    social_welfare = _published_subsidy_qa(
        qa_id="QA-026",
        question="低收入戶或中低收入戶的社福補助怎麼計算？",
        aliases=("低收補助多少", "中低收補助多少"),
        answer="低收入戶依補助市民政策，每小時 350 元，最多 120 小時。",
    )
    gateway.rebuild(8, (*distractors, social_welfare))

    answer = gateway.answer("低收補助多少", 8)

    assert answer.answer == "低收入戶依補助市民政策，每小時 350 元，最多 120 小時。"


def test_unscoped_subsidy_amount_question_fails_closed_before_llm(tmp_path) -> None:
    def unexpected_llm(_: str) -> str:
        raise AssertionError("ambiguous subsidy scope must not reach the LLM")

    gateway, _ = _gateway(tmp_path, llm=unexpected_llm, min_confidence=0.0)
    gateway.rebuild(
        7,
        (
            _published_subsidy_qa(
                qa_id="QA-025",
                question="市府到府月子服務補助多少小時？",
                aliases=("政府補助幾小時？",),
                answer="市府補助 40 小時。",
            ),
        ),
    )

    with pytest.raises(KnowledgeAnswerUnsupported, match="knowledge_answer_unsupported"):
        gateway.answer("政府補助幾小時？", 7)

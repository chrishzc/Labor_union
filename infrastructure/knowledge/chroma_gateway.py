"""ChromaDB projection adapter for reviewed knowledge and the curated LINE QA catalog."""

from __future__ import annotations

import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable

from domains.knowledge_retrieval.knowledge import (
    KnowledgeAnswer,
    KnowledgeAnswerUnsupported,
    KnowledgeCitation,
    source_digest,
)


_DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parents[2] / "document" / "line" / "AI客服QA題庫.jsonl"
)
_READY_STATUS = "ready"


class ChromaKnowledgeGateway:
    def __init__(
        self,
        persistence_path: str,
        collection_prefix: str = "union_knowledge",
        *,
        catalog_path: str | Path | None = None,
        llm: Callable[[str], str] | None = None,
        min_confidence: float = 0.60,
    ) -> None:
        self._persistence_path = persistence_path
        self._collection_prefix = collection_prefix
        self._catalog_path = Path(catalog_path) if catalog_path is not None else _DEFAULT_CATALOG_PATH
        self._llm = llm
        self._min_confidence = min_confidence

    def rebuild(
        self, index_version: int, published_items: tuple[dict, ...]
    ) -> tuple[dict, ...]:
        indexed_items = tuple(published_items) + self._load_catalog_items()
        client = self._client()
        name = self._collection_name(index_version)
        existing_names = {
            getattr(collection, "name", str(collection))
            for collection in client.list_collections()
        }
        if name in existing_names:
            client.delete_collection(name)
        collection = client.create_collection(name)
        if not indexed_items:
            return ()
        collection.add(
            ids=[self._candidate_id(item) for item in indexed_items],
            documents=[self._retrieval_document(item) for item in indexed_items],
            metadatas=[self._metadata(item) for item in indexed_items],
        )
        return indexed_items

    def answer(self, question: str, index_version: int) -> KnowledgeAnswer:
        collection = self._client().get_collection(self._collection_name(index_version))
        count = int(collection.count())
        if count < 1:
            raise KnowledgeAnswerUnsupported("knowledge_answer_unsupported")
        result = collection.query(query_texts=[question], n_results=min(5, count))
        documents = tuple((result.get("documents") or [[]])[0])
        metadatas = tuple((result.get("metadatas") or [[]])[0])
        if not documents or not metadatas or len(documents) != len(metadatas):
            raise KnowledgeAnswerUnsupported("knowledge_answer_unsupported")

        candidates = tuple(
            metadata
            for document, metadata in zip(documents, metadatas, strict=True)
            if self._candidate_confidence(question, document, metadata)
            >= self._min_confidence
        )
        if not candidates or self._llm is None:
            raise KnowledgeAnswerUnsupported("knowledge_answer_unsupported")

        selected_id = str(self._llm(self._selection_prompt(question, candidates))).strip()
        if selected_id == "UNSUPPORTED":
            raise KnowledgeAnswerUnsupported("knowledge_answer_unsupported")
        selected = next(
            (
                candidate
                for candidate in candidates
                if str(candidate["candidate_id"]) == selected_id
            ),
            None,
        )
        if selected is None:
            raise KnowledgeAnswerUnsupported("knowledge_answer_unsupported")

        answer = str(selected["answer"]).strip()
        if not answer:
            raise KnowledgeAnswerUnsupported("knowledge_answer_unsupported")
        citation = KnowledgeCitation(
            str(selected["source_identity"]),
            int(selected["source_version"]),
            answer[:500],
        )
        return KnowledgeAnswer(answer[:5000], (citation,), index_version)

    def _load_catalog_items(self) -> tuple[dict, ...]:
        if not self._catalog_path.exists():
            return ()
        items: list[dict] = []
        seen_ids: set[str] = set()
        with self._catalog_path.open("r", encoding="utf-8") as source:
            for line_number, raw_line in enumerate(source, start=1):
                if not raw_line.strip():
                    continue
                try:
                    record = json.loads(raw_line)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"knowledge_catalog_invalid:{line_number}"
                    ) from error
                if str(record.get("status", "")).strip().lower() != _READY_STATUS:
                    continue
                catalog_id = str(record.get("id", "")).strip()
                category = str(record.get("category", "")).strip()
                tag = str(record.get("tag", "")).strip()
                question = str(record.get("question", "")).strip()
                answer = str(record.get("answer", "")).strip()
                aliases = record.get("aliases", [])
                if (
                    not catalog_id
                    or not category
                    or not tag
                    or not question
                    or not answer
                    or not isinstance(aliases, list)
                    or any(not isinstance(alias, str) for alias in aliases)
                    or catalog_id in seen_ids
                ):
                    raise ValueError(f"knowledge_catalog_invalid:{line_number}")
                seen_ids.add(catalog_id)
                canonical_record = {
                    "id": catalog_id,
                    "category": category,
                    "tag": tag,
                    "question": question,
                    "aliases": [alias.strip() for alias in aliases if alias.strip()],
                    "answer": answer,
                    "status": _READY_STATUS,
                    "source_ref": str(record.get("source_ref", "")).strip(),
                }
                encoded = json.dumps(
                    canonical_record,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                items.append(
                    {
                        "source_identity": f"{self._catalog_path.as_posix()}#{catalog_id}",
                        "source_version": 1,
                        "source_digest": source_digest(encoded),
                        "title": f"{category} / {tag}",
                        "content": answer,
                        "catalog_id": catalog_id,
                        "category": category,
                        "tag": tag,
                        "question": question,
                        "aliases": tuple(canonical_record["aliases"]),
                        "source_ref": canonical_record["source_ref"],
                    }
                )
        return tuple(items)

    def _metadata(self, item: dict) -> dict:
        aliases = item.get("aliases") or ()
        return {
            "candidate_id": self._candidate_id(item),
            "source_identity": str(item["source_identity"]),
            "source_version": int(item["source_version"]),
            "title": str(item.get("title", "")),
            "answer": str(item["content"]),
            "question": str(item.get("question", "")),
            "category": str(item.get("category", "")),
            "tag": str(item.get("tag", "")),
            "aliases": json.dumps(tuple(aliases), ensure_ascii=False),
        }

    def _retrieval_document(self, item: dict) -> str:
        aliases = item.get("aliases") or ()
        parts = (
            str(item.get("question", "")),
            *(str(alias) for alias in aliases),
            str(item.get("category", "")),
            str(item.get("tag", "")),
            str(item.get("title", "")),
            str(item.get("content", "")),
        )
        return "\n".join(part for part in parts if part.strip())

    def _candidate_confidence(self, question: str, document: str, metadata: dict) -> float:
        aliases = self._aliases(metadata)
        terms = (
            str(metadata.get("question", "")),
            *aliases,
            str(metadata.get("tag", "")),
            str(metadata.get("category", "")),
            str(metadata.get("title", "")),
            document,
        )
        return max((self._similarity(question, term) for term in terms), default=0.0)

    @staticmethod
    def _similarity(left: str, right: str) -> float:
        normalized_left = _normalize(left)
        normalized_right = _normalize(right)
        if not normalized_left or not normalized_right:
            return 0.0
        if normalized_left == normalized_right:
            return 1.0
        if normalized_left in normalized_right or normalized_right in normalized_left:
            length_ratio = min(len(normalized_left), len(normalized_right)) / max(
                len(normalized_left), len(normalized_right)
            )
            return 0.75 + (0.25 * length_ratio)
        return SequenceMatcher(None, normalized_left, normalized_right).ratio()

    def _selection_prompt(self, question: str, candidates: tuple[dict, ...]) -> str:
        rows = []
        for candidate in candidates:
            aliases = "、".join(self._aliases(candidate))
            rows.append(
                " | ".join(
                    (
                        str(candidate["candidate_id"]),
                        str(candidate.get("category", "")),
                        str(candidate.get("tag", "")),
                        str(candidate.get("question", "")),
                        aliases,
                    )
                )
            )
        candidate_text = "\n".join(rows)
        return (
            "你是客服題庫候選選擇器。只能回傳下列候選 ID 其中之一，"
            "若沒有足夠符合的候選只能回傳 UNSUPPORTED。不要回答問題、不要輸出其他文字。\n"
            f"使用者問題：{question}\n"
            f"候選：\n{candidate_text}"
        )

    @staticmethod
    def _aliases(metadata: dict) -> tuple[str, ...]:
        raw = metadata.get("aliases", "[]")
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return ()
            if isinstance(parsed, list):
                return tuple(str(item) for item in parsed)
            return ()
        if isinstance(raw, (list, tuple)):
            return tuple(str(item) for item in raw)
        return ()

    @staticmethod
    def _candidate_id(item: dict) -> str:
        catalog_id = str(item.get("catalog_id", "")).strip()
        if catalog_id:
            return catalog_id
        return f"{item['source_identity']}:{item['source_version']}"

    def _client(self):
        import chromadb

        return chromadb.PersistentClient(path=self._persistence_path)

    def _collection_name(self, index_version: int) -> str:
        return f"{self._collection_prefix}_v{index_version}"


def _normalize(value: str) -> str:
    return "".join(character.casefold() for character in value if character.isalnum())


__all__ = ["ChromaKnowledgeGateway"]

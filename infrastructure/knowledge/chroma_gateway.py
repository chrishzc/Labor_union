"""ChromaDB projection adapter for published, governed knowledge only."""

from __future__ import annotations

import json
from pathlib import Path
import re
from pathlib import Path
import re
from difflib import SequenceMatcher
from typing import Callable

from domains.knowledge_retrieval.knowledge import (
    KnowledgeAnswer,
    KnowledgeAnswerUnsupported,
    KnowledgeCitation,
)
from domains.knowledge_retrieval.qa_catalog import decode_governed_qa


class ChromaKnowledgeGateway:
    def __init__(
        self,
        persistence_path: str,
        collection_prefix: str = "union_knowledge",
        *,
        llm: Callable[[str], str] | None = None,
        min_confidence: float = 0.60,
    ) -> None:
        self._persistence_path = persistence_path
        self._collection_prefix = collection_prefix
        self._llm = llm
        self._min_confidence = min_confidence

    def rebuild(
        self, index_version: int, published_items: tuple[dict, ...]
    ) -> tuple[dict, ...]:
        indexed_items = tuple(self._project_published_item(item) for item in published_items)
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

    def answer(
        self,
        question: str,
        index_version: int,
        history: tuple[dict[str, str], ...] = (),
    ) -> KnowledgeAnswer:
        collection = self._client().get_collection(self._collection_name(index_version))
        count = int(collection.count())
        if count < 1:
            raise KnowledgeAnswerUnsupported("knowledge_answer_unsupported")
        query_texts = [question]
        if history:
            query_texts.append(f"{history[-1]['question']} {question}")
        result = collection.query(query_texts=query_texts, n_results=min(5, count))
        raw_docs = result.get("documents") or []
        raw_metas = result.get("metadatas") or []
        documents_list: list[str] = []
        metadatas_list: list[dict] = []
        seen_ids = set()
        for d_list, m_list in zip(raw_docs, raw_metas, strict=False):
            for doc, meta in zip(d_list, m_list, strict=True):
                cid = meta.get("candidate_id")
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    documents_list.append(doc)
                    metadatas_list.append(meta)
        documents = tuple(documents_list)
        metadatas = tuple(metadatas_list)
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

        selected_id = str(
            self._llm(self._selection_prompt(question, candidates, history=history))
        ).strip()
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

    def list_index_versions(self) -> tuple[int, ...]:
        """Return only collections owned by this gateway."""
        pattern = re.compile(rf"^{re.escape(self._collection_prefix)}_v([0-9]+)$")
        versions = []
        for collection in self._client().list_collections():
            name = str(getattr(collection, "name", collection))
            match = pattern.fullmatch(name)
            if match:
                versions.append(int(match.group(1)))
        return tuple(sorted(versions))

    def estimate_index_bytes(self, index_version: int) -> int:
        """Estimate logical payload bytes without exposing stored content."""
        collection = self._client().get_collection(self._collection_name(index_version))
        payload = collection.get(include=["documents", "metadatas"])
        return len(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
        )

    def delete_index(self, index_version: int) -> bool:
        """Delete one exact versioned collection; missing is an idempotent no-op."""
        name = self._collection_name(index_version)
        existing = {
            str(getattr(collection, "name", collection))
            for collection in self._client().list_collections()
        }
        if name not in existing:
            return False
        self._client().delete_collection(name)
        return True

    def persistence_bytes(self) -> int:
        root = Path(self._persistence_path)
        if not root.exists() or not root.is_dir():
            return 0
        resolved_root = root.resolve()
        total = 0
        for path in resolved_root.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                resolved = path.resolve(strict=True)
                resolved.relative_to(resolved_root)
                total += resolved.stat().st_size
            except (FileNotFoundError, OSError, ValueError):
                continue
        return total

    @staticmethod
    def _project_published_item(item: dict) -> dict:
        governed_qa = decode_governed_qa(str(item["content"]))
        if governed_qa is None:
            return dict(item)
        governed_qa.require_publishable()
        return {
            **item,
            "content": governed_qa.answer,
            "catalog_id": governed_qa.qa_id,
            "category": governed_qa.category,
            "tag": governed_qa.tag,
            "question": governed_qa.question,
            "aliases": governed_qa.aliases,
            "source_ref": governed_qa.source_ref,
        }

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

    @staticmethod
    def _selection_prompt(
        question: str,
        candidates: tuple[dict, ...],
        history: tuple[dict[str, str], ...] = (),
    ) -> str:
        rows = []
        for candidate in candidates:
            aliases = "、".join(ChromaKnowledgeGateway._aliases(candidate))
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
        history_text = ""
        if history:
            h_lines = []
            for item in history:
                h_lines.append(f"用戶：{item['question']}")
                h_lines.append(f"客服：{item['answer']}")
            history_text = "最近對話紀錄（供理解語意與指代關係）：\n" + "\n".join(h_lines) + "\n\n"
        return (
            "你是客服題庫候選選擇器。請參考對話紀錄並根據當前使用者問題，挑選最符合的候選 ID。\n"
            "只能回傳下列候選 ID 其中之一，若沒有足夠符合的候選只能回傳 UNSUPPORTED。不要回答問題、不要輸出其他文字。\n\n"
            f"{history_text}當前使用者問題：{question}\n"
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

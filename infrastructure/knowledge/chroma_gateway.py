"""ChromaDB projection adapter; MySQL knowledge versions remain the SSOT."""

from __future__ import annotations

import os

from domains.knowledge_retrieval.knowledge import KnowledgeAnswer, KnowledgeCitation


class ChromaKnowledgeGateway:
    def __init__(self, persistence_path: str, collection_prefix: str = "union_knowledge") -> None:
        self._persistence_path = persistence_path
        self._collection_prefix = collection_prefix

    def rebuild(self, index_version: int, published_items: tuple[dict, ...]) -> None:
        client = self._client()
        name = self._collection_name(index_version)
        existing_names = {
            getattr(collection, "name", str(collection))
            for collection in client.list_collections()
        }
        if name in existing_names:
            client.delete_collection(name)
        collection = client.create_collection(name)
        if not published_items:
            return
        collection.add(
            ids=[f"{item['source_identity']}:{item['source_version']}" for item in published_items],
            documents=[str(item["content"]) for item in published_items],
            metadatas=[{
                "source_identity": str(item["source_identity"]),
                "source_version": int(item["source_version"]),
                "title": str(item["title"]),
            } for item in published_items],
        )

    def answer(self, question: str, index_version: int) -> KnowledgeAnswer:
        collection = self._client().get_collection(self._collection_name(index_version))
        result = collection.query(query_texts=[question], n_results=3)
        documents = tuple((result.get("documents") or [[]])[0])
        metadatas = tuple((result.get("metadatas") or [[]])[0])
        if not documents or not metadatas:
            raise ValueError("knowledge_answer_unsupported")
        citations = tuple(
            KnowledgeCitation(
                str(metadata["source_identity"]),
                int(metadata["source_version"]),
                str(document)[:500],
            )
            for document, metadata in zip(documents, metadatas, strict=True)
        )
        answer = str(documents[0])[:5000]
        return KnowledgeAnswer(answer, citations, index_version)

    def _client(self):
        import chromadb

        return chromadb.PersistentClient(path=self._persistence_path)

    def _collection_name(self, index_version: int) -> str:
        return f"{self._collection_prefix}_v{index_version}"


__all__ = ["ChromaKnowledgeGateway"]

"""Focused contract tests for the multilingual Gemini embedding adapter."""

from __future__ import annotations

from infrastructure.knowledge.gemini_embedding import GeminiKnowledgeEmbedder


class _Store:
    def read_for_runtime(self) -> str:
        return "private-test-key"


class _Response:
    status_code = 200

    def __init__(self, count: int, dimension: int) -> None:
        self._count = count
        self._dimension = dimension

    def json(self):
        return {
            "embeddings": [
                {"values": [1.0] + [0.0] * (self._dimension - 1)}
                for _ in range(self._count)
            ]
        }


def test_documents_and_queries_use_named_model_dimension_and_distinct_qa_formats() -> None:
    calls: list[dict] = []

    def post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        requests = kwargs["json"]["requests"]
        return _Response(len(requests), 768)

    embedder = GeminiKnowledgeEmbedder(store=_Store(), post=post)

    document_vectors = embedder.embed_documents(("更換月嫂規定",))
    query_vectors = embedder.embed_queries(("我可以換月嫂嗎？",))

    assert embedder.model == "gemini-embedding-2"
    assert embedder.dimension == 768
    assert embedder.space_id == "gemini:gemini-embedding-2:768:qa-v1"
    assert len(document_vectors[0]) == len(query_vectors[0]) == 768
    assert calls[0]["url"].endswith("gemini-embedding-2:batchEmbedContents")
    document_request = calls[0]["json"]["requests"][0]
    query_request = calls[1]["json"]["requests"][0]
    assert document_request["model"] == query_request["model"] == "models/gemini-embedding-2"
    assert document_request["outputDimensionality"] == 768
    assert query_request["outputDimensionality"] == 768
    assert document_request["content"]["parts"][0]["text"].startswith(
        "title: none | text:"
    )
    assert query_request["content"]["parts"][0]["text"].startswith(
        "task: question answering | query:"
    )

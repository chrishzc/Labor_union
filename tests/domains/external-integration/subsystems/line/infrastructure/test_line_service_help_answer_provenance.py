from __future__ import annotations

import unittest

from fastapi import HTTPException

from api.dependencies.llm_configuration import LlmConfigurationApplication
from api.routes.line_service_help import ServiceHelpAskRequest, ask_service_question
from domains.knowledge_retrieval.knowledge import KnowledgeAnswer, KnowledgeCitation


class _Store:
    pass


class _Selector:
    model = "test-model"

    def __call__(self, prompt: str) -> str:
        return "UNUSED"


class _Gateway:
    def answer(self, question: str, index_version: int) -> KnowledgeAnswer:
        return KnowledgeAnswer(
            answer="核准回答",
            citations=(
                KnowledgeCitation(
                    source_identity="line-common-qa:service-flow",
                    source_version=4,
                    safe_excerpt="核准來源摘要",
                ),
            ),
            index_version=index_version,
        )


class _Verifier:
    def __init__(self) -> None:
        self.tokens: list[str] = []

    def verify(self, token: str):
        self.tokens.append(token)
        return object()


class LineServiceHelpAnswerProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.application = LlmConfigurationApplication(
            store=_Store(),
            selector=_Selector(),
            ready_index_version=lambda: 7,
            gateway_factory=lambda selector: _Gateway(),
        )

    def test_semantic_result_preserves_governed_source_version(self) -> None:
        result = self.application.test_semantics("服務流程")

        self.assertEqual(result.outcome, "answered")
        self.assertEqual(result.qa_id, "service-flow")
        self.assertEqual(result.source_identity, "line-common-qa:service-flow")
        self.assertEqual(result.source_version, 4)
        self.assertEqual(result.index_version, 7)

    def test_liff_response_exposes_source_and_index_versions(self) -> None:
        response = ask_service_question(
            ServiceHelpAskRequest(question="服務流程"),
            application=self.application,
        )

        self.assertEqual(response.data.outcome, "answered")
        self.assertEqual(response.data.source_identity, "line-common-qa:service-flow")
        self.assertEqual(response.data.source_version, 4)
        self.assertEqual(response.data.index_version, 7)
        self.assertIsNone(response.data.interaction_id)

    def test_verified_liff_interaction_identity_is_preserved_for_persistence_boundary(self) -> None:
        verifier = _Verifier()

        response = ask_service_question(
            ServiceHelpAskRequest(
                question="服務流程",
                interaction_id="interaction-307-1",
                line_id_token="verified-token-placeholder",
            ),
            application=self.application,
            liff_verifier=verifier,
        )

        self.assertEqual(verifier.tokens, ["verified-token-placeholder"])
        self.assertEqual(response.data.interaction_id, "interaction-307-1")
        self.assertEqual(response.data.source_identity, "line-common-qa:service-flow")
        self.assertEqual(response.data.source_version, 4)
        self.assertEqual(response.data.index_version, 7)

    def test_partial_liff_interaction_identity_fails_before_answering(self) -> None:
        verifier = _Verifier()

        with self.assertRaises(HTTPException) as caught:
            ask_service_question(
                ServiceHelpAskRequest(
                    question="服務流程",
                    interaction_id="interaction-307-2",
                ),
                application=self.application,
                liff_verifier=verifier,
            )

        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(
            caught.exception.detail["error"]["code"],
            "liff_interaction_identity_incomplete",
        )
        self.assertEqual(verifier.tokens, [])


if __name__ == "__main__":
    unittest.main()

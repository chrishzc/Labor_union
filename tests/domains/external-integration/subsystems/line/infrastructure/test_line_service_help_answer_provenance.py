from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from api.dependencies.llm_configuration import LlmConfigurationApplication, LlmSemanticTestResult
from api.routes import llm_configuration as admin_llm
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
        return SimpleNamespace(
            line_user_id=SimpleNamespace(value="U-line-307")
        )


class LineServiceHelpAnswerProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        # These existing cases test first-time provenance/persistence calls.
        # Actual stored replay is exercised in test_line_inline_knowledge_replay.
        lookup = patch("api.routes.line_service_help._replay_liff_response", return_value=None)
        lookup.start()
        self.addCleanup(lookup.stop)
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
        self.assertEqual(result.source_excerpt, "核准來源摘要")
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
        self.assertIsNone(response.data.answer_receipt_id)

    def test_verified_liff_interaction_is_bound_to_persisted_answer_receipt(self) -> None:
        verifier = _Verifier()

        with patch(
            "api.routes.line_service_help._persist_liff_answer",
            return_value=41,
        ) as persist:
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
        self.assertEqual(response.data.answer_receipt_id, 41)
        self.assertEqual(response.data.source_identity, "line-common-qa:service-flow")
        self.assertEqual(response.data.source_version, 4)
        self.assertEqual(response.data.index_version, 7)
        persist.assert_called_once()
        self.assertEqual(persist.call_args.args[0], "服務流程")
        self.assertEqual(persist.call_args.args[1], "interaction-307-1")
        self.assertEqual(persist.call_args.args[2], "U-line-307")
        self.assertEqual(
            persist.call_args.args[3].source_excerpt,
            "核准來源摘要",
        )

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

    def test_verified_unsupported_interaction_is_persisted_for_admin_observation(self) -> None:
        verifier = _Verifier()
        application = SimpleNamespace(
            test_semantics=lambda _question: SimpleNamespace(
                outcome="unsupported",
                answer_text=None,
                index_version=7,
                code="knowledge_answer_unsupported",
            )
        )

        with patch(
            "api.routes.line_service_help._persist_liff_outcome",
            return_value=51,
        ) as persist:
            response = ask_service_question(
                ServiceHelpAskRequest(
                    question="題庫沒有這一題",
                    interaction_id="interaction-307-unsupported",
                    line_id_token="verified-token-placeholder",
                ),
                application=application,
                liff_verifier=verifier,
            )

        self.assertEqual(response.data.outcome, "unsupported")
        persist.assert_called_once_with(
            "題庫沒有這一題",
            "interaction-307-unsupported",
            "U-line-307",
            "unsupported",
        )

    def test_verified_runtime_failure_is_persisted_before_typed_503(self) -> None:
        verifier = _Verifier()
        application = SimpleNamespace(
            test_semantics=lambda _question: SimpleNamespace(
                outcome="provider_error",
                answer_text=None,
                code="timeout",
            )
        )

        with patch(
            "api.routes.line_service_help._persist_liff_outcome",
            return_value=52,
        ) as persist:
            with self.assertRaises(HTTPException) as caught:
                ask_service_question(
                    ServiceHelpAskRequest(
                        question="服務問題",
                        interaction_id="interaction-307-failed",
                        line_id_token="verified-token-placeholder",
                    ),
                    application=application,
                    liff_verifier=verifier,
                )

        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(caught.exception.detail["error"]["code"], "timeout")
        persist.assert_called_once_with(
            "服務問題",
            "interaction-307-failed",
            "U-line-307",
            "failed",
        )

    def test_verified_unexpected_failure_is_persisted_before_generic_503(self) -> None:
        verifier = _Verifier()

        def fail(_question: str):
            raise RuntimeError("provider detail")

        application = SimpleNamespace(test_semantics=fail)

        with patch(
            "api.routes.line_service_help._persist_liff_outcome",
            return_value=53,
        ) as persist:
            with self.assertRaises(HTTPException) as caught:
                ask_service_question(
                    ServiceHelpAskRequest(
                        question="服務問題",
                        interaction_id="interaction-307-exception",
                        line_id_token="verified-token-placeholder",
                    ),
                    application=application,
                    liff_verifier=verifier,
                )

        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(
            caught.exception.detail["error"]["code"],
            "knowledge_query_unavailable",
        )
        persist.assert_called_once_with(
            "服務問題",
            "interaction-307-exception",
            "U-line-307",
            "failed",
        )


class AdminSemanticResponseRegressionTests(unittest.TestCase):
    def test_all_semantic_outcomes_preserve_the_admin_response_contract(self) -> None:
        for outcome in ("answered", "unsupported", "index_unavailable", "provider_error"):
            with self.subTest(outcome=outcome):
                answered = outcome == "answered"
                result = LlmSemanticTestResult(
                    outcome=outcome, provider="test-provider", model="test-model",
                    index_version=7 if answered else None,
                    qa_id="service-flow" if answered else None,
                    source_identity="line-common-qa:service-flow" if answered else None,
                    source_version=4 if answered else None,
                    source_excerpt="核准來源摘要" if answered else None,
                    answer_text="核准回答" if answered else None,
                    code=None if answered else "test-code",
                )
                request = SimpleNamespace(state=SimpleNamespace())
                response = admin_llm.test_llm_semantics(
                    admin_llm.LlmSemanticTestRequest(question="服務流程"),
                    request, _=None,
                    application=SimpleNamespace(test_semantics=lambda _: result),
                )
                self.assertEqual(response.data.outcome, outcome)
                self.assertEqual(response.data.model_dump(), {
                    name: getattr(result, name) for name in (
                        "outcome", "provider", "model", "index_version", "qa_id",
                        "source_identity", "answer_text", "code",
                    )
                })
                self.assertEqual(request.state.audit_details["outcome"], outcome)
                self.assertNotIn("source_excerpt", request.state.audit_details)

    def test_admin_model_still_rejects_undeclared_fields(self) -> None:
        with self.assertRaises(ValidationError):
            admin_llm.LlmSemanticTestView(
                outcome="unsupported", provider="test-provider", model="test-model",
                index_version=None, qa_id=None, source_identity=None,
                answer_text=None, code="test-code", source_excerpt="not-public",
            )


if __name__ == "__main__":
    unittest.main()

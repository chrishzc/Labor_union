# Module: publishable QA catalog

## Responsibility

將 LINE QA migration input 投影為 stable-identity Knowledge items；所有編修產生 draft revision，publish／retire 決定可用性，只有 published items 可進 READY index。同一 owner read model 提供已去除 LINE identity 的實際問句、回答結果與 unsupported 知識缺口觀測。

## Implementation

- `domains/knowledge_retrieval/qa_catalog.py`
- `subsystems/knowledge_retrieval/qa_catalog_import.py`
- `subsystems/knowledge_retrieval/application.py`
- `api/dependencies/knowledge_retrieval.py`
- `scripts/import_builtin_knowledge_catalog.py`
- `api/main.py`
- `domains/knowledge_retrieval/publication.py`
- `infrastructure/mysql/knowledge_retrieval_repository.py`
- `infrastructure/mysql/knowledge_retrieval_unit_of_work.py`
- `infrastructure/knowledge/chroma_gateway.py`
- `api/routes/knowledge_retrieval.py`
- `api/routes/line_service_help.py`
- `api/routes/llm_configuration.py`
- `api/dependencies/llm_configuration.py`
- `ui_react/src/pages/line_management/CommonQaCatalogPanel.tsx`
- `ui_react/src/pages/line_management/RealLlmSemanticTestPanel.tsx`
- `ui_react/src/pages/line_management/KnowledgeFeedbackPanel.tsx`

## Dependencies

- migration input: `document/line/AI客服QA題庫.jsonl` — input/evidence only；不得由 retrieval runtime 直接查詢。
- runtime packaging: `.dockerignore` 只放行 bundled QA JSONL，不納入其餘 `document/` tree。
- operator runbook: `document/line/LINE_AI客服題庫Production匯入操作手冊.md`
- consumer: LINE AI customer-service studio and knowledge answer worker.

## Verification

- layout_status: `custom_current`
- test_root: `tests/domains/knowledge-retrieval/subsystems/knowledge-retrieval/modules/reviewable-qa-catalog/`
- test_root: `tests/test_line_ai_qa_catalog.py`
- integration_root: `tests/test_line_service_help.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_service_help_governed_catalog.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_service_help_error_contracts.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_service_help_answer_provenance.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_inline_knowledge_outcomes.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_inline_knowledge_replay.py`
- integration_root: `ui_react/src/tests/domains/knowledge-retrieval/subsystems/knowledge-retrieval/integration/`
- required claims: 54-row non-overwriting portable import, initial enabled-state restoration, direct draft publishability gate, publish/retire plus atomic index-job request, bounded lexical re-ranking that cannot lose a known short Chinese alias outside the first vector results, published-only metadata projection, unsupported-to-common-FAQ navigation, feedback-derived answer outcome, UI lifecycle/index workflow.

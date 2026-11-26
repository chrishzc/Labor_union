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
- `infrastructure/knowledge/gemini_embedding.py`
- `api/routes/knowledge_retrieval.py`
- `api/routes/line_service_help.py`
- `api/routes/llm_configuration.py`
- `api/dependencies/llm_configuration.py`
- `ui_react/src/pages/line_management/AiCustomerServiceStudioPage.tsx`
- `ui_react/src/pages/line_management/LlmConfigurationPage.tsx`
- `ui_react/src/pages/line_management/CommonQaCatalogPanel.tsx`
- `ui_react/src/pages/line_management/RealLlmSemanticTestPanel.tsx`
- `ui_react/src/pages/line_management/KnowledgeFeedbackPanel.tsx`

## Dependencies

- migration input: `document/line/AI客服QA題庫.jsonl` — input/evidence only；不得由 retrieval runtime 直接查詢。
- runtime packaging: `.dockerignore` 只放行 bundled QA JSONL，不納入其餘 `document/` tree。
- operator runbook: `document/line/LINE_AI客服題庫Production匯入操作手冊.md`
- consumer: LINE AI customer-service studio and knowledge answer worker.

## 共用 FAQ 讀取契約（待實作）

- [需求書 #29 §4.1](../../../../../requirements/29_LINE服務說明、客服互動與選單角色正式規格.md#41-共用問答與聊天室版面)；LINE 呈現與分類卡片生命週期見 [聊天室版面模組](../../../../external-integration/subsystems/line/modules/faq-chat-layout.md)。
- Knowledge Retrieval 擁有正式問答內容及發布版本。沿用 `knowledge_items` 與目前已發布的 `knowledge_item_versions`，以穩定題目 ID 與正式版本讀取問題、答案、分類識別及別名；草稿另存，不取代正式可讀版本。索引是衍生資料，不是 FAQ 的權威，索引延遲不應讓兩邊出現不同版本的正式答案。
- 提供依穩定 ID、正式別名或分頁列舉的共用唯讀契約；明確區分不存在／已停用與來源暫時不可用。網頁使用既有 FAQ HTTP 入口，完整清單走明確分頁，穩定排序且不得默默只回前 100 題。聊天室只消費同一契約，不自行讀資料表或解析 JSONL。
- 現況：網頁路由已接治理題庫；聊天室分類和精確回覆仍有 JSONL 路徑。實作應移除該 runtime 讀取，保留播種用途；遷移既有 ID／分類引用需可重跑且不得覆蓋已發布的人工修訂。

### 草稿與正式版本不能共用同一個指標

- 實作候選：在既有 Knowledge root 增加可空的正式版本指標，不另建 FAQ 題庫。現有 `version` 繼續用於編輯與併發檢查；公開題目／別名／分頁按已發布版本關聯不可變版本內容。需確認發布當時的摘要、來源及分類同樣來自該正式版本，不能混入 root 的草稿欄位。
- migration 先為現行已發布項目回填其正式版本，已停用不回填；舊案如存在未發布修訂，僅在有完整正式發佈／停用事件鏈時回填可確認的最後正式版，不用草稿補。舊版本標題、引用來源或分類若無一致證據，列為遷移差異，人工確認後才切換。
- 儲存修訂只前移編輯版本；正式發布才原子更新正式指標，停用清除可見性且保留歷史。精確 FAQ 讀取不等索引重建；索引讀取仍不得回傳已停用或未發布版本。以隔離 CI 驗「發布 A → 儲存 B → 兩通路仍是 A → 發布 B → 兩通路是 B → 停用 → 舊按鈕也不回傳」。

## Verification

- layout_status: `custom_current`
- test_root: `tests/domains/knowledge-retrieval/subsystems/knowledge-retrieval/modules/reviewable-qa-catalog/`
- test_root: `tests/test_line_ai_qa_catalog.py`
- integration_root: `tests/test_line_service_help.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_service_help_governed_catalog.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_service_help_error_contracts.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_service_help_answer_provenance.py` — 既有合成案例核對答覆保留原始知識來源識別、來源版本及索引版本。
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_inline_knowledge_outcomes.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_inline_knowledge_replay.py`
- integration_root: `ui_react/src/tests/domains/knowledge-retrieval/subsystems/knowledge-retrieval/integration/`
- required claims: 54-row non-overwriting portable import, initial enabled-state restoration, direct draft publishability gate, publish/retire plus atomic index-job request, bounded lexical re-ranking that cannot lose a known short Chinese alias outside the first vector results, published-only metadata projection, unsupported-to-common-FAQ navigation, feedback-derived answer outcome, UI lifecycle/index workflow.

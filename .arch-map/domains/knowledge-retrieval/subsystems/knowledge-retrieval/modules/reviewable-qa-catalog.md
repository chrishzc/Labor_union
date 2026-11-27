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
- `ui_react/src/pages/line_management/AiCustomerServiceStudioPage.tsx`
- `ui_react/src/pages/line_management/LlmConfigurationPage.tsx`
- `ui_react/src/pages/line_management/CommonQaCatalogPanel.tsx`
- `ui_react/src/pages/line_management/RealLlmSemanticTestPanel.tsx`
- `ui_react/src/pages/line_management/KnowledgeFeedbackPanel.tsx`

## Dependencies

- migration input: `document/line/AI客服QA題庫.jsonl` — input/evidence only；不得由 retrieval runtime 直接查詢。
- runtime packaging: `.dockerignore` 只放行 bundled QA JSONL，不納入其餘 `document/` tree。
- operator runbook: `document/line/LINE_AI客服題庫Production匯入操作手冊.md`
- consumer: LINE 常見問答管理、聊天室 Reply；保留其他 Knowledge 同源消費者.

## 共用 FAQ 讀取契約（待實作）

- [需求書 #29 §4.1](../../../../../requirements/29_LINE服務說明、客服互動與選單角色正式規格.md#41-共用問答與聊天室版面)；LINE 呈現與分類卡片生命週期見 [聊天室版面模組](../../../../external-integration/subsystems/line/modules/faq-chat-layout.md)。
- Knowledge Retrieval 擁有正式問答內容及發布版本。沿用 `knowledge_items` 與目前已發布的 `knowledge_item_versions`，以穩定題目 ID 與正式版本讀取問題、答案、分類識別及別名；草稿另存，不取代正式可讀版本。索引是衍生資料，不是 FAQ 的權威，索引延遲不應讓管理端正式題庫與 LINE Reply 讀到不同版本的正式答案。
- 本功能對外只由 LINE 聊天室 Reply 讀正式版。管理端以受權限保護的正式題庫讀取作分頁與發布後核對；不提供公開 FAQ 網頁、AI 模型問答或回饋分析。
- 切換管理 Query 與聊天室 Reply 前驗證既有正式版本和舊入口映射。JSONL 用於種子、遷移及切換前的舊題目辨識；聊天室回覆一律取正式版本。

### 草稿與正式版本不能共用同一個指標

- 現行資料契約：`knowledge_items.published_version` 是可空的正式版本指標，不另建 FAQ 題庫。`version` 用於編輯與併發檢查。管理端正式題庫的分頁，以及 LINE Reply 的題目／別名查詢，均以正式指標關聯 `knowledge_item_versions` 的 `published` 快照。正式摘要、來源及分類不得混入 root 的草稿欄位。編輯清單讀回的 root 摘要不是正式 FAQ 內容。
- migration 先為現行已發布項目回填其正式版本，已停用不回填；舊案如存在未發布修訂，僅在有完整正式發佈／停用事件鏈時回填可確認的最後正式版，不用草稿補。舊版本標題、引用來源或分類若無一致證據，列為遷移差異，人工確認後才切換。
- 儲存修訂只前移編輯版本；正式發布才原子更新正式指標，停用清除可見性且保留歷史。正式版是否可停用按正式指標判定；對仍有正式版但正在修改草稿的題目，不能只依 root 的 `draft` 拒絕。既有非 FAQ 狀態轉移與權限不因此放寬。精確 FAQ 讀取不等索引重建；索引讀取仍不得回傳已停用或未發布版本。以隔離 CI 驗「發布 A → 儲存 B → 管理端正式題庫與 LINE Reply 都讀 A → 發布 B → 兩個入口都讀 B → 停用 → 正式題庫不列該題，LINE 舊按鈕也不回原答案」。

## 匯入、發布與索引

- 維運依 [正式匯入手冊](../../../../../../document/line/LINE_AI客服題庫Production匯入操作手冊.md) 核對計畫與目標。空庫首次匯入例為 54 題、40 題初始發布候選；已有人工修改時不覆寫、不自動發布。Apply 的 `committed` 是匯入／發布回執，不代表索引已可用；索引失敗不回滾已匯入的題目。
- Knowledge owner 在個別 publish／retire 的同一交易送出索引工作（`application.py::_transition_and_request_index`）。`KnowledgeWorker._build_index` 取已發布資料重建，成功才完成目標索引。交接時以回執的 `index_job_id` 追該次工作及其目標版本，不拿舊的 `READY` 當本次已通過；重建失敗先查工作結果，不直接刪題庫或版本。
- 聊天室 FAQ 讀回與回覆格式依 [需求書 #29 §4.1](../../../../../requirements/29_LINE服務說明、客服互動與選單角色正式規格.md#41-共用問答與聊天室版面)。舊 AI 問答 LIFF 依同份規格 §3.2 提供退役指引。

### 題庫永久刪除

- `POST /api/v1/knowledge/items/{item_id}/delete-faq` 使用題庫管理權限，接受 `expected_version`、`reason` 與既有冪等及關聯標頭。成功回傳 `item_id`。只處理 LINE FAQ。刪除前鎖定目標並核對編輯版本及正式版本，涵蓋切換前仍會對 LINE 生效的舊發布記錄。有正式答案或版本衝突回 409，題目不存在回 404。
- 同一交易移除題目、內容版本及隸屬題目的事件列，保留既有操作回執及不含答案的刪除記錄。重送相同操作鍵可讀回原結果。該題識別保留最小刪除標記，避免原 ID 被再次用於建題或內建目錄匯入。先前送出的 LINE 訊息及既存回覆收據仍屬原 owner。
- 資料庫版本刪除觸發器只接受同一連線、同一題目的交易中刪除標記，並重新核對 FAQ 身分及發布指標。應用程式先鎖住題目並核對相容發布歷程，才寫入交易中標記。提交後只保留避免復原的識別記錄。

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

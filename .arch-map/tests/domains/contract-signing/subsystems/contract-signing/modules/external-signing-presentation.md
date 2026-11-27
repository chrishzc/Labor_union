module: external-signing-presentation
parent_subsystem: contract-signing
architecture: ../../../../../../domains/contract-signing/subsystems/contract-signing/modules/external-signing-presentation.md
layout_status: custom_current
test_root: ui_react/src/tests/domains/contract-signing/subsystems/contract-signing/modules/external-signing-presentation/

# Owned verification
- `ui_react/src/tests/domains/contract-signing/subsystems/contract-signing/modules/external-signing-presentation/contract_external_signing_actions.test.tsx` — closed states、歷史簽回 lineage、Preview invalidation、handoff／unsigned-PDF unknown original-command recovery、receipt readback-only 與 final PDF readback。
- `ui_react/src/tests/domains/contract-signing/subsystems/contract-signing/modules/external-signing-presentation/contract_external_signing_client.test.ts` — typed React transport 與 schema decode。
- `tests/domains/contract-signing/subsystems/contract-signing/integration/test_contract_completion_workflow.py` — final PDF Apply 與 Orders completion／deposit obligation outer-UoW 邊界。
- `tests/domains/contract-signing/subsystems/contract-signing/integration/test_full_contract_preview.py` — exact target、typed owner mappings、conditional applicability 與零寫入 Preview。
- `tests/domains/contract-signing/subsystems/contract-signing/integration/test_contract_external_signing_api.py` — preparation／session Query closed union、零寫入文件準備投影、文件回讀及既有命令門檻。
- `tests/domains/contract-signing/subsystems/contract-signing/integration/test_contract_external_signing_api.py` — authenticated API contract。
- `tests/domains/contract-signing/subsystems/contract-signing/integration/test_client_unsigned_preparation.py` — accepted-plan source gate、fresh lock and client source replay archive boundary。

## 直接歸檔：從驗收情境找到測試

來源：[需求 #21 §3.4](../../../../../../requirements/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md#34-分開文件回收手工證明與本機測試跳過)。本節只驗不依賴送交紀錄的已簽 PDF 歸檔，不用較早的準備／會話案例替代。

| 層 | 直接入口 | 已有自動測試能確認的事 |
| --- | --- | --- |
| 前端 | `contract_external_signing_actions.test.tsx` 的 `archives directly with no session, handoff, unsigned version, or ready scheduling` 及原操作恢復案例 | 檔案齊備才送；原操作恢復以 case/key 綁定的回執顯示成功，miss／查核失敗保持未明；重開與查核不重送 POST。正式 CI 案例結果見當次 PR，不以此對照表宣稱已執行。 |
| API | `test_contract_external_signing_api.py::test_signed_archive_multipart_does_not_require_unsigned_version_or_signing_session` | 直接 POST 使用 multipart，接線不要求未簽版本或簽署 session。 |
| 應用 | `test_final_document_workflow.py::test_signed_archive_requires_only_the_existing_case_and_selected_pdf_files`、`::test_archive_storage_failure_rolls_back_without_recording_completion` | 成功、必要檔案缺漏、同鍵重送與異指紋拒絕；失敗用假交易在首份檔案寫入時攔下，不證明三類 MySQL 寫入後一起回滾。 |
| DB | [架構書的資料庫查核落點](../../../../../../domains/contract-signing/subsystems/contract-signing/modules/external-signing-presentation.md#已簽-pdf-歸檔資料庫查核落點) | 需另用隔離 DB 及新連線查正式檔案、完約與歸檔回執；這個範圍未實跑。 |

## 原操作恢復驗證邊界

[需求 #21 的 CONTRACT-ARCHIVE-RECOVERY-01／02](../../../../../../requirements/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md#4-驗收標準) 由上述前端 component／client 入口、`test_final_document_workflow.py` 的精確回執查核及 `test_contract_external_signing_api.py` 的 result GET 契約覆蓋。此 Query 不變更 SQL 或正式寫入；fake port 測試只驗查核無寫入，不能充當 MySQL 三類寫後回滾證據。既有 GitHub Actions 的 Candidate pool frontend 保留 Vitest 與 pytest JUnit artifact，案例是否實跑以該次 artifact／job logs 為準。

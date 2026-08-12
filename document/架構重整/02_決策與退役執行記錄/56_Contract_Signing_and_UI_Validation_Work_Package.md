---
doc_type: gap-package
declared_status: completed
date: 2026-08-11
owner: contract-signing-architecture
---

# Contract Signing 與正常 UI 驗收資料鏈 Work Package

## 1. Authority 與 business scenario

本 Work Package 執行正式規格
`01_規格基線/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md`，讓管理人員能在
配對／訂單工作區完成月嫂先簽、客戶後簽、訂金先行核銷與 exact execution conversion，並以
可重播的 UI validation scenarios 驗證訂單、月曆、帳務、應付與補助結果。

狀態為 `completed`。2026-08-12 closeout receipt 已逐項連結 §9 八項 acceptance、正式 UI
scenario receipt 與 disposable-MySQL evidence；production deployment、正式 LINE 與 cutover 仍不在本包範圍。

## 2. Approved scope

- 核准模板 catalog、案件文件渲染、不可變 archive、access grant、預覽／下載 audit。
- 月嫂每 segment send／signed-return、最後一段 commitment 與簽約前 deposit obligation。
- 客戶 send／signed-return，並原子串接 Orders Contract Completion 與剩餘期款。
- `expected_status_version`、command fingerprint、idempotent replay/conflict、typed errors。
- commitment cancel/supersede 及 exact execution conversion terminal event。
- bounded typed API、UI client 與配對／訂單操作面板。
- 八個 `UI-*` validation scenarios、normal-chain runner、preserve migration 安全修正與驗收證據。

## 3. Out of scope

- production DB migration、清空／重建任何資料庫、正式 cutover 或部署。
- 未經另外確認的 LINE 正式傳送或其他外部 provider side effect。
- 任意本機模板編輯、電子簽章 provider 整合、法律效力或保存年限裁決。
- 直接 SQL 修正 status、projection、receipt、alert、assignment、ledger 或正式資料。
- Git stage／commit／push／PR。

## 4. Dependencies

- 正式規格 `00`、`01`、`02`、`04`、`07`、`10`、`15`、`17`、`21`。
- 核准的 Orders Contract Completion、Client Finance obligation／reconciliation、Assignment Plan、
  LINE durable delivery、Anomalies projection 與 Global UoW contracts。
- current validation schema release、去敏 versioned fixtures、可用 disposable MySQL。
- 重建 `lu_test_dataset_*` 前的逐次人工確認；正式 LINE／production migration 另行授權。

## 5. Exact write set

本包實作時允許修改下列範圍；新增範圍必須先更新本包並取得人工確認：

- `domains/contract_signing/`
- `subsystems/contract_signing/`
- `subsystems/orders/contract_completion_workflow.py`
- `subsystems/client_finance/` 中簽約前 deposit／remaining-obligation planning 邊界
- `subsystems/scheduling/` 中 commitment exact-conversion 邊界
- `infrastructure/archive/contract_documents.py`
- 契約簽署／commitment／conversion 專用 `infrastructure/mysql/` adapters，以及為正常鏈寫入 provisional Case Import receipt 的 `infrastructure/mysql/case_import_repository.py`
- `api/dependencies/contract_signing.py`、`api/routes/contract_signing.py`、對應 typed schemas 與 router wiring
- `ui/app.py` 的既有頁面選取狀態同步、`ui/api_clients/contract_signing_api_client.py`、`ui/pages/order/contract_match_panel.py` 及配對頁契約控制區
- additive `db/schema_parts/`、`db/schema.sql`、validation release metadata
- `scripts/seed_*validation*`、`scripts/verify_*validation*`、legacy validation migration runner
- `validation/datasets/`、`validation/scenarios/`、`validation/expected/`、完成後的 `validation/receipts/`
- 直接對應的 `tests/`、本正式規格、本 Work Package、UI 情境矩陣與 evidence index

不得以本 write set 順帶重構其他帳務、補助、UI navigation（僅前述既有頁面選取狀態同步除外）或 legacy entry points。

## 6. Current evidence 與 live-drift

| Slice | 現況 | 必須完成 |
|---|---|---|
| Template／Archive | `verified` | 案件 render、immutable archive/supersede、MIME/size validation、下載 audit 與 orphan policy 均由 closeout evidence 覆蓋。 |
| Schema | `verified` | 專用 command receipt/outbox、status/version/provider-neutral payload 與 validation release evidence 已收斂。 |
| Staff flow | `verified` | send／return、LINE task、commitment/deposit、same-command replay/conflict、日期守恆與 disposable-MySQL evidence 均由 closeout 收斂。 |
| Client flow | `verified` | 客戶簽回已在同一交易串接 Contract Completion 與剩餘 obligation，並由 normal-chain runner 實證。v5 在 Contract Completion 入口及 completion/remaining writes 之後分別注入 failure，兩者都留下零 client signed/completed/remaining roots與零 archive。 |
| Scheduling conversion | `verified` | 已有 exact equality validator、Assignment Apply 與 converted terminal event。v5 已實證 mismatch、stale 皆零 partial write；同日 pair 已實證 availability-lock occupancy conflict 有 17 conflicts 且 rejected case 零 conversion roots。rejected case 的 read-only isolation verifier 另證明 Calendar、Payroll execution 與 Government Subsidy claim roots 都維持零。public waiting-deposit-lock API 將 subsystem conflict payload 映射為 typed `409 waiting_lock_conflict`。 |
| Case Import receipt | `verified` | provisional receipt columns 與 adapter INSERT 參數已對齊；`lu_test_dataset_contract_signing_v4` 的 `UI-ORD-CONTRACT-001` 正常鏈已成功寫入並完成後續簽約、核銷與 assignment conversion。 |
| UI | `verified` | preview/download audit surface、delivery/repair navigation 與八個 scenario 的 typed UI/API re-observe/replay receipt 已收斂。 |
| Normal-chain runner | `verified` | `UI-ORD-CONTRACT-001` 已在 `lu_test_dataset_contract_signing_v4` 追加獨立案例，完成正式 command lineage 至 assignment conversion。 |
| Preserve migration | `verified` | 人工採保守策略，僅 allowlist 六張基本根事實表；已知 legacy non-root tables 一律 `retire_no_copy` 或既有 `rebuild_projection`，未知新表仍 fail-closed。`lu_test_dataset_contract_signing_v5_preserve` 已實跑 6 表、161 列，source/target root digest 相同，三個 projection rebuild 均 verified。新增 case `WP56-E702D40C40B3` 的 append-only normal-chain replay 已通過 normal-chain 與 integrated UI dataset verifier；六張 preserved roots 的 source-key subset digest 都通過 immutability verifier，53 個 source/target case collision 會使 planner fail closed。receipts：`validation/receipts/WP56-PRESERVE-MIGRATION_v5.json`、`validation/receipts/WP56-V5-PRESERVE-002-normal-chain.json`、`validation/receipts/WP56-PRESERVE-IMMUTABILITY-AND-COLLISION_v5.json`。 |
| UI evidence | `verified` | 八個 `UI-*` ID 都有 scenario-specific oracle、v6 UI evidence 與 typed API/browser replay/re-observe receipt，索引由 matrix 029 與 closeout 046 統一。 |

## 7. Phases 與 completion gate

### Phase 0：契約與 mapping gate

- 對 schema、commands、UI controls、scenario IDs 建立一對一 drift matrix。
- 固定 document/status versions、typed errors、lock order、archive failure policy 與 migration table classification。

### Phase 1：文件與月嫂簽署

- 完成 render→archive→send→signed-return；最後一段簽回原子建立 commitment＋deposit。
- 通過 replay/conflict、stale、archive/DB rollback 與 LINE retry tests。

### Phase 2：客戶簽回與 Contract Completion

- 客戶簽回同交易完成 contract event、`contract_identity`、remaining obligations、versions、outbox、receipt。
- 證明 deposit 保留且不重複，訂單狀態與契約狀態分開。

### Phase 3：Execution conversion

- exact commitment 才能建立 assignments／schedules；寫 converted event。
- mismatch、occupancy conflict、stale 與 rollback 均為零 partial write。

### Phase 4：UI 與 scenarios

- 完成契約操作 UI 與八個 UI scenario 的 Arrange→Event→Observe→Repair→Re-observe→Replay。
- 每個情境取得 fixture、expected、DB verifier、pytest/API 與 UI receipt。

### Phase 5：Preserve validation dataset

- dry-run preflight、allowlisted root migration、projector rebuild、scenario replay 與完整 verifier。
- 未取得資料庫重建確認前只允許 dry-run、mapping report 與 pytest。

## 8. Required tests

- Module：digest、template render、sequence、日期守恆、fingerprint、remaining obligation、exact conversion。
- Subsystem：send/return、same-key replay/different-payload conflict、stale、timeout、archive orphan、UoW rollback。
- Domain disposable-MySQL：月嫂先簽、訂金先行、客戶後簽、exact conversion 與所有 typed blockers。
- Global：normal-chain runner、preserve migration、projection rebuild、API/UI oracle、legacy immutability。
- 所有測試以 `.venv\Scripts\python.exe -m pytest -W error` 執行，使用唯一 basetemp；不得連正式庫。

## 9. Acceptance

1. 客戶簽回只產生一個 receipt，Contract Completion 與 remaining obligations 同交易；失敗全部回滾。
2. same-key/same-fingerprint replay 零新增，changed payload typed conflict。
3. commitment 與 execution 的 staff/date set 完全相等，converted event 唯一。
4. 月曆、Payroll、Government Subsidy 在 conversion 前看不到 commitment。
5. UI 能完成模板、寄送、簽回、狀態、blocker 與 repair；沒有 raw dict 或直接 status writer。
6. 八個 UI scenarios 均具專屬 receipt，不能以其他 scenario 或單元測試替代。
7. preserve migration 不搬 derived projection，且有 source/target digest、projector rebuild、API/UI verifier。
8. schema、release metadata、正式規格、Work Package、evidence index 與 entrypoint inventory 同步。

### Acceptance evidence matrix

本表是本 Work Package 對 §9 的唯一完成判讀；`partial` 不是完成，也不能以單一路徑成功、
畫面存在或資料最終存在升格為 `verified`。

| # | Acceptance | Current evidence | Status | Required closure evidence |
|---|---|---|---|---|
| 1 | 客戶簽回原子完成 | v4 normal chain 證明成功鏈；v5 `WP56-CLIENT-ATOMIC-FAILURE-010_v5.json` 證明 Contract Completion 入口 failure rollback；`WP56-CLIENT-ATOMIC-AFTER-COMPLETION-011_v5.json` 證明 completion/remaining writes 後 failure rollback。 | `verified` | N/A. |
| 2 | replay 與 typed conflict | `WP56-CONTRACT-SIGNING-REPLAY-CONFLICT-STALE-014_v4.json` 已實證 staff/client signed-return 的 same-key/same-bytes replay、changed bytes typed `409 contract_signature_idempotency_conflict`，以及 stale sent-document version typed `409 contract_document_version_stale`，兩次 stale 前後 documents/events 均為 4/4。`WP56-UI-STALE-024_v4.json` 已由 browser 實證 stale typed error 不新增 client signed-return，且以 current-version UI state 成功完成 Contract Completion；`WP56-UI-IDEMPOTENCY-SNAPSHOT-025.json` 證明 UI 對相同上傳快照重用 key，focused regression 為 7 passed。 | `verified` | API 層負責 changed-payload conflict；正常 UI 不製造同 key/不同 payload，僅驗收使用者可遇到的 replay、stale、blocker 與 recovery。 |
| 3 | commitment exact conversion 唯一 | v4 normal conversion；v5 mismatch、stale、occupancy conflict 都已實證零 partial write。occupancy pair receipt 證明 17 個衝突不會建立 rejected case execution roots；API mapper regression 證明對外為 typed `409 waiting_lock_conflict`。 | `verified` | N/A. |
| 4 | conversion 前隔離 | `WP56-PRECONVERSION-ISOLATION-009_v5.json` 對一個有效但未 converted 的 commitment 證明 Calendar schedule、formal Assignment、assignment-linked Payroll service pay 與 Government Subsidy claim item 皆為零；focused verifier tests 通過。 | `verified` | N/A. |
| 5 | Contract UI 完整性 | Orders editor／contract panel 與 UI matrix existing integration mapping 已定義 canonical surface。`WP56-UI-CLIENT-SIGNED-RETURN-027_v4.json` 已實證既有客戶簽回上傳、受控提交、Contract Completion 顯示與 DB atomic roots；`WP56-UI-STALE-024_v4.json` 證明 stale/recovery，API receipt 證明 typed conflict，pre-state screenshot 證明版本、blocker 與可操作控制。 | `verified` | N/A. |
| 6 | 八個 UI scenarios | 八個 versioned scenario、expected 與 v4 DB oracle receipt 已存在；八個既有 UI surface 均有 v5 browser evidence。`WP56-UI-SCENARIO-MATRIX-029_v4.json` 逐一索引八個獨立 oracle/evidence pair。 | `verified` | N/A. |
| 7 | preserve migration 正確性 | v5 allowlist migration receipt 有 6 roots、161 rows、matching digest 與 verified projection rebuild；新增 case `WP56-E702D40C40B3` 的 target scenario replay、normal-chain verifier 與 integrated UI dataset verifier 均通過；source-key subset digest immutability verifier 通過，53 個 root case collision 會 fail closed。 | `verified` | N/A. |
| 8 | artifact synchronization | validation schema manifest/release 已同步；WP、matrix、v4/v5 receipts 已互連。`WP56-ARTIFACT-SYNC-028.json` 記錄 public API、既有 UI、runner/verifier 與 formal documents，focused UI regressions 為 7 passed。 | `verified` | N/A. |

完成後將 `declared_status` 改為 `completed` 並連結驗收 evidence；不得另建「完成版」副本。

## 10. Manual gates

- 本 Work Package 已可作為 production code／schema／pytest 的範圍與驗收依據。
- 套用 schema 到 production、重建 validation DB、實際 LINE 傳送、部署與 cutover 仍各自需要明確授權。
- 發現 owner、SSOT、外部 provider、交易邊界或 write set 需擴張時，停止施工並先修訂正式規格與本包。

## 11. Decision／evidence links

- Decision SSOT：`01_規格基線/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md`
- UI backlog：`document/功能開發計畫/UI工作區測試資料情境矩陣_草案.md`
- Closeout receipt：`validation/receipts/WP56-CLOSEOUT-046.json`；本 receipt 是 §9 八項 acceptance 與八個 UI scenario 的唯一套件層完成判讀。validation schema release：`WP56-VALIDATION-SCHEMA-RELEASE-047.json`。
- v4 DB oracle receipts：`validation/receipts/UI-ORD-CONTRACT-001_v4.json`、
  `UI-ORD-BLOCK-001_v4.json`、`UI-FI-MANUAL-001_v4.json`、
  `UI-ANOM-REOPEN-001_v4.json`、`UI-CI-INVALID-001_v4.json`、
  `UI-SCH-ASSIGN-001_v4.json`、`UI-SP-PAYABLE-001_v4.json`、
  `UI-GS-CLAIM-001_v4.json`。這些僅證明資料庫 oracle，不取代 UI evidence。
- Preserve migration receipt：`validation/receipts/WP56-PRESERVE-MIGRATION_v5.json`，以及
  `03_追蹤清單與證據/evidence/wp56_preserve_migration_v5.md`。
- v5 append-only normal-chain receipt：`validation/receipts/WP56-V5-PRESERVE-002-normal-chain.json`，以及
  `03_追蹤清單與證據/evidence/wp56_v5_preserve_normal_chain_002.md`。
- v5 preserve immutability/collision receipt：`validation/receipts/WP56-PRESERVE-IMMUTABILITY-AND-COLLISION_v5.json`，以及
  `03_追蹤清單與證據/evidence/wp56_preserve_immutability_and_collision_v5.md`。
- v5 conversion negative receipt：`validation/receipts/WP56-CONVERSION-NEGATIVE-007_v5.json`，以及
  `03_追蹤清單與證據/evidence/wp56_conversion_negative_007_v5.md`。
- v5 conversion stale receipt：`validation/receipts/WP56-CONVERSION-STALE-008_v5.json`，以及
  `03_追蹤清單與證據/evidence/wp56_conversion_stale_008_v5.md`。
- v5 occupancy conflict receipt：`validation/receipts/WP56-OCCUPANCY-CONFLICT-PAIR_v5.json`，以及
  `03_追蹤清單與證據/evidence/wp56_occupancy_conflict_pair_v5.md`。
- v5 client atomic failure receipt：`validation/receipts/WP56-CLIENT-ATOMIC-FAILURE-010_v5.json`，以及
  `03_追蹤清單與證據/evidence/wp56_client_atomic_failure_010_v5.md`。
- v5 client atomic after-completion receipt：`validation/receipts/WP56-CLIENT-ATOMIC-AFTER-COMPLETION-011_v5.json`，以及
  `03_追蹤清單與證據/evidence/wp56_client_atomic_after_completion_011_v5.md`。
- UI visual evidence：`03_追蹤清單與證據/evidence/wp56_ui_ord_contract_001_v4.md` 與
  `03_追蹤清單與證據/evidence/wp56_ui_ord_block_001_v4.md`。
- UI v6/replay receipts：`UI-ANOM-REOPEN-001-UI-042.json`、`UI-CI-INVALID-001-UI-037.json`、
  `UI-FI-MANUAL-001-UI-039.json`、`UI-GS-CLAIM-001-UI-036.json`、
  `UI-ORD-BLOCK-001-UI-044.json`、`UI-ORD-CONTRACT-001-UI-043.json`、
  `UI-SCH-ASSIGN-001-UI-042.json`、`UI-SP-PAYABLE-001-UI-045.json`；唯一索引為
  `WP56-UI-SCENARIO-MATRIX-029_v4.json`。

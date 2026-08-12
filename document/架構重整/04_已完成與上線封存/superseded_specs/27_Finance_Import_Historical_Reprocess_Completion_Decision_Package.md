---
doc_type: decision-package
declared_status: partial
---

# Finance Import Historical Reprocess Completion Decision Package

## 1. 現況裁決

狀態為 `partial`。舊 reprocess 已正確 fail-closed，這是 legacy writer 退役成果，
舊 reprocess 仍不是正式 Apply；但 canonical Historical Reprocess Preview／Apply 已完成
application、repository、additive schema contract 與 authenticated API 的第一個可驗證版本。

`subsystems/finance_import/reprocessing.py` 的唯一可執行命令只會鎖定並讀取
eligible rows、計算 plan，最後永遠 rollback；`dry_run=False` 固定拋出
`legacy_finance_import_reprocess_apply_retired`。CLI 也在取得資料庫連線前拒絕
`--apply`。因此沒有現行 production writer 可誤寫舊 ledger，但正式規格所需的
classification event、owning Domain dispatch、reprocess receipt 和 outbox 已由正式 workflow
建立；Finance Import panel 已提供 typed Preview／Apply 操作入口，但 Historical Reprocess
本身仍尚未完成真實格式 Excel 與 isolated MySQL 的端到端驗證。

既有 `db/schema_parts/61_finance_import_reprocessing.sql` 的 append-only run/event
tables 是可重用的稽核基礎；它們不能被當成已完成的 application workflow。

## 2. 正式目標

對唯一 completed batch 的 eligible `non_business_review` rows，Preview 與 Apply 必須
使用同一 candidate builder。Apply 在一個 outer Unit of Work 中完成：

1. row、occurrence、batch 與 expected-version lock；
2. append-only classification decision event 與相容 current projection；
3. 每列唯一 owning Domain 的 typed dispatch；
4. owning Domain 的 ledger／allocation／lifecycle result；
5. reprocess run、changed-row event、idempotency receipt；
6. post-commit Finance Import／Anomalies outbox intent。

任一 row 沒有唯一 owner、已產生正式交易、fingerprint stale、版本衝突、dispatch
失敗或違反 Domain invariant 時，整批 rollback。Anomalies projection 失敗不回滾已
提交的 root facts，但必須可由 source outbox retry。

## 3. 必要 data-contract 補齊

- 將 classification 由 current columns 提升為 append-only decision event；舊 columns
  只作 current projection。
- 為每個 reprocess dispatch 保存 canonical source identity、command identity、owner、
  receipt reference 與 failure-safe outbox reference。
- 現有 run/event tables 可保留，但要由正式 repository 在 outer UoW 寫入，並補足
  replay/idempotency/expected-version trace。
- `client_refund` 僅可在 Client Refund 完整 lifecycle contract 完成後列為可 dispatch
  owner；在此之前須 fail closed 轉人工，不得把銀行 row 直接寫入 refund ledger。

## 4. 已完成邊界與後續順序

已完成：

1. `historical_reprocess_workflow.py` 以同一 candidate builder 執行 Preview／Apply，並鎖定
   expected batch version、preview fingerprint、idempotency 與 actor。
2. `historical_reprocess_repository.py` 在 outer UoW 內寫入 classification event、run、
   receipt、outbox 與 batch version；Government Subsidy 仍強制要求唯一 target，不猜測。
3. `139_finance_import_historical_reprocess.sql` 以 additive tables／enum contract 保存 receipt
   與 `historical_reprocess_completed` outbox intent。
4. `/api/v1/finance-import/historical-reprocess/preview` 與 `/apply` 已掛入 Finance Import
   typed API，Apply 維持同步 transaction boundary，避免將 request-scoped DB connection 交給
   background task。
5. 2026-08-04 已驗證 canonical Apply 在同一 outer UoW 內先追加 classification decision
   event，再進行 owning Domain dispatch；若 dispatch 非 final，classification 與後續
   reprocess facts 均 rollback。此為 workflow/repository/API/schema/real-format parser 的
   23 個聚焦測試證據。
6. 2026-08-04 已在完全隔離的 `lu_test_refund_e2e_20260804` MySQL database 完成真實格式
   台新 Excel 的 intake → root fact → manual-review／correction → owning Domain
   ledger/allocation → Anomalies outbox E2E。驗證包含未解析 owner 的 fail-closed、退款與
   退款退回、七個 persistence seam 的 outer-UoW rollback、projector retry，以及補助代墊、
   政府入帳回收與部分入帳人工覆核；全數通過。此證據不表示可跳過第 7 節的歷史 owner
   selection contract，也不以 mock 或 `union_db` 取代。

後續順序：

1. 建立 Finance Reprocess application contract、Preview／Apply typed request/result，及
   candidate builder、eligibility/replay policies。
2. 以 additive preserve-data migration 補齊 event、dispatch identity、receipt/outbox
   reference；先在 disposable database 驗證，再有明確 switch/rollback plan。
3. 將 Client Finance、Government Subsidy、Staff Payables 的既有 typed dispatch adapters
   接到同一 outer UoW；不允許 adapter hidden commit。
4. 在 API／thin CLI 接同一 application；CLI Apply 需 actor、idempotency key、
   fingerprint。Streamlit 僅顯示 typed results。
5. 讓 canonical Anomalies projector 消費 post-commit source outbox，不讓 reprocess
   command 直接寫 alert projection。
6. 在真實格式 Excel 與完全隔離 MySQL 驗證 ingestion → Preview → Apply → owner →
   Anomalies；不得使用 `union_db` 或 mock 取代。

## 5. 驗收與 rollback

Module：classification、eligibility、fingerprint、idempotency、typed errors。

Subsystem：整批 rollback、lock race、stale preview、exact replay、owner dispatch、
outbox retry。

Domain／Global：一筆真實格式 Excel 的 reprocess 結果與同步 owner command 一致；
投影失敗後可恢復且不重複 ledger。

Migration 必須 additive、可 journal、可切回舊 readonly diagnostic；rollback 不得
刪除 append-only decision、receipt、ledger 或 outbox facts。

## 6. 未完成且未授權事項

本文件不自行授權執行真實資料庫 migration、真實 Excel 連線、部署或 release manifest。
目前 schema 僅是 additive contract；實際資料庫升級必須另有 preserve-data rehearsal 與
rollback evidence。

## 7. 2026-08-04 live blocker：historical client refund owner resolution

以真實台新格式 Excel 驗證時，來源可提供唯一的 `counterparty_account`，因此 Historical
Reprocess 可以重新將列分類為 `client_refund`；但台新 normalized `bank_references` 沒有
case number。正式 Client Refund dispatch 為避免跨案件猜測，仍要求該 immutable 銀行根事實
含唯一 `case_no` reference 後，才可從 client identity 解析 payable obligation。

不可接受的繞法是事後更新 `finance_import_rows.bank_references` 補 case number：這會改寫
已保存的銀行根事實，違反 Finance Import 的 append-only／根事實規格。故現行 canonical
Historical Reprocess 對此類 row 必須維持 typed fail-closed；完整 Apply E2E 不能靠測試直接
寫資料庫偽造 case reference。

解除此 blocker 需要新增一個經人工確認的、append-only 的「historical owner selection／case
evidence」contract，並指定其 actor、evidence、fingerprint、idempotency、outer UoW 與 rollback
語意；在此 contract 未存在前，不得標記 Historical Reprocess 的 Client Refund owner dispatch
為完成。

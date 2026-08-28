# Finance recovery anomaly MySQL receipt

- Work package：`PROV-20260826-finance-recovery-anomaly-closure-work-packages.md`。
- Codes：`GOVSUB-006`、`client_over_refund_recovery_open`、`staff_overpayment_recovery_open`。
- Environment：`APP_ENV=development`；所有資料庫均符合 `lu_test_*` allowlist。
- Boundary：未操作 `union_db`、production、provider、replacement、`--switch` 或 deployment。
- Current conclusion：`DB_CHANGE_NOT_READY`；真 MySQL lifecycle、fresh bootstrap、preserve-data candidate 與
  local-bypass Browser Query/detail 已 PASS，developer local replacement 與 enabled-human Browser Apply 仍未執行。

## Rulebook-complete resolution result

自動解除不得以 receipt、outbox delivered、通知成功、追蹤狀態或管理員宣告代替 owner 業務完成。
`tests/test_finance_recovery_anomaly_disposable_mysql_e2e.py` 在 final schema 的
`lu_test_task96_fin_recovery_r4b` 驗證：

1. Government 溢領建立後 alert active；只有 owner offset disposition Apply／replay 完成並 fresh readback
   status 不再是 `pending_review` 後，`GOVSUB-006` 才 inactive 且不再出現在 active list。
2. Client 超額退款由 500 部分收回至 remaining 200 時仍 active；owner root 進入 `recovered` 且 remaining=0
   後才 inactive。
3. Staff 溢撥由 600 部分收回至 remaining 250 時仍 active；owner root 進入 `recovered` 且 remaining=0
   後才 inactive。授權調整的 full-only 規則由既有 owner contract focused tests 保護。

結果：`3 passed in 7.61s`。同一 final candidate 的 projector／owner query／evidence／dead-letter focused
regression 為 `80 passed in 2.04s`；另有 Government owner offset durable replay `1 passed in 7.82s`。

2026-08-27 final source candidate 另以全新 `lu_test_task96_fin_rules_r4_20260827` 重新 fresh bootstrap 並重跑
同一三碼 lifecycle，結果 `3 passed in 8.05s`。Client partial remaining=200 與 Staff partial remaining=250
均保持 active；只有 owner terminal root 且 remaining=0 才 inactive。這次重跑沒有重用 Browser seed DB。

## Browser Query／detail 與權限負向驗證

- Runtime：本輪獨立 FastAPI `127.0.0.1:8001`、Vite `127.0.0.1:5174`，只連
  `lu_test_task96_fin_browser_r3_20260827`；未干擾使用者既有 8000／5173 服務。
- 三碼 active list 與 detail 均可見。Client 顯示 remaining=500、status=open 與
  `remaining=0 && status in {recovered, adjusted}` 完成條件；Government 顯示 pending_review、remaining=500、
  合法 offset target 與 recipient-account blocker；Staff 顯示 remaining=600，並明示 adjustment 必須一次精確
  結清 fresh remaining。
- Public detail 與 recovery context 均回 200；只暴露具完整 owner identities／versions 的 action。Client root
  未有 matching bindings 時只提供 matching 與 adjustment，不錯誤暴露 collection。
- `local_bypass` 可以 Query，但 Client adjustment Preview 實測回 403「目前身分無權執行此操作」。未建立、
  注入或繞過 persisted privileged account；因此這是安全負向 PASS，不是 enabled-human 正向 Apply。

瀏覽器驗證暴露並修正兩個 live-drift：current alert 的 `source_domain` 曾被 repository 固定寫成
`finance_import`；detail／recovery 對 recovery bindings 的公開去敏與 action binding 不一致。修正後 focused
source contract 為 `63 passed, 3 skipped`；另以明確 MySQL 環境執行的三個 skipped lifecycle 為上述
`3 passed in 8.05s`。

## Preserve-data candidate

- Source：`lu_test_task96_finrec_source_1006`，fresh bootstrap 只到 schema part 1006。
- Candidate：`lu_test_task96_finrec_candidate_1008`，初始不存在。
- Release order：`1007_finance_recovery_evidence.sql` →
  `1008_historical_order_adoption_noop_constraint.sql`。
- Source dump：1,122,037 bytes，SHA-256
  `e97a1e1634a5d5c07cff096b6243312ba11d606ecc28cd11c136e4da7e0dfa71`。
- Operation：dump → new candidate restore → ordered apply → verify；operation receipt status=`verified`，
  view mismatches=0，candidate schema SHA-256
  `54fa5a30706a25570371a024e252c9d57a47808884407faba9393e12769d90e2`。
- Owned objects：1007=`exact`；1008=`exact`。
- Representative old rows：client event、client matching、staff event、staff matching 各 1；migration verifier
  證明 pre-additive columns 與 rows fingerprint 全部保留。升級後四筆 `evidence_reference` 都是 NULL，符合
  schema-only migration；系統沒有把 reason、銀行流水或其他資料推測成人工證據。

可重現的 ignored raw receipts 位於 `scratch/task96-finance-recovery-r4/`；本文件只保存最小去敏 final
evidence，不保存 DB password 或 raw 個資。

## DB change gates

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | approved finance recovery package、正式 `06`／`14`／`16` owner rulebook 與 `lu_test_*` Authority 覆蓋。 |
| Change inventory | PASS | 1007／1008 均為 `schema-only`；system-seed、business-row-backfill、destructive 均無。 |
| Static release | PASS | canonical chain 包含 1007 後接 1008；manifest／descriptor hash focused regression PASS。 |
| Descriptor | PASS | source 1007／1008=`absent`；candidate 兩者=`exact`；partial／drift fail closed。 |
| Read-only plan | PASS | `scratch/task96-finance-recovery-r4/preserve-plan.json` 列出 1007→1008 且 candidate 不存在；developer plan 另正確回報 `qualification_missing`，零寫入。 |
| Engine verification | PASS | final fresh bootstrap＋三碼 lifecycle PASS；1006 representative source → 1008 candidate restore/apply/verify PASS，舊資料保留。 |
| Developer acceptance | NOT_RUN | 未建立 canonical local qualification receipt，未執行 replacement launcher 或 `--switch`。 |

## DDH dynamic operation log

1. 前一 phase 的三條 42-code rulebook reconciliation lanes 均為 `gpt-5.6-luna`／`high`，只讀且已 terminal。
2. 本 phase 原計畫再以三條 Luna High 唯讀 lane 分別核對 Government／Client／Staff MySQL readiness；Host
   的已結束 agent threads 仍占滿 thread quota，spawn 在建立任何新 agent 前即失敗。
3. 這是 material capability delta；DDH 只重投影剩餘工作，由 E4 隔離並行改為主代理單寫者的序列
   MySQL verification。沒有競爭寫入，也沒有把未啟動 lane 計為子代理成果。
4. 規則書再收斂時，三條既有唯讀 lane 分別稽核 finance/staff/government、LINE/access/service 與
   scheduling/orders；三者均為 `gpt-5.6-luna`／`high`，write set 為空且已 terminal。這次 E4 符合隔離收益。
5. 進入共享 FastAPI／Vite／MySQL Browser integration 後，環境、DB 與 UI state 不再可安全隔離，DDH 只重投影
   剩餘工作並改為 E2 主代理單一 runtime writer，避免互相重啟服務或改動同一資料列。
6. Browser 發現 source-domain 與 action-binding contract drift 後，verification profile 由既有 focused／MySQL
   擴張為 public detail、recovery context、DOM 與 auth-negative；計畫改變但 owner 規則、Authority 與完成條件
   未改變。

## Remaining acceptance

- `NOT_RUN`：canonical local additive qualification／developer replacement acceptance。
- `PASS`：local-bypass 真 FastAPI＋Vite Browser 三碼 Query/detail、exact action routing 與 403 權限負向。
- `NOT_RUN`：enabled persisted human Session 的三碼正向 Apply、partial、stale 與 owner typed-error Browser
  驗收。
- `in-progress`：projector dead-letter supersede 與真 queue-progress integration；其他 anomaly codes 的
  owner action／manual completion／Browser closure。

Cleanup：未被 final receipt 引用的失敗重跑 DB `lu_test_task96_fin_recovery_r4` 與單項 offset DB
`lu_test_task96_gov_offset_r4` 已精確刪除；保留 final lifecycle、pre-1007 source 與 verified candidate 供後續
Browser／developer acceptance 對讀。刪除的兩個 DB 無備份且不可復原，內容僅為本輪可重建測試資料。

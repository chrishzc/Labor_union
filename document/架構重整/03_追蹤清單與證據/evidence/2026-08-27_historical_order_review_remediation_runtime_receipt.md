# Historical order review remediation runtime receipt

- Work package: `CUR-P0-HISTORICAL-ORDER-REMEDIATION-01`
- Scenario identity: `historical-order-review:9a019b5a-2527-4da6-919d-977aea733224`
- Environment: `APP_ENV=development`; source/candidate/fresh database 均為 `lu_test_*`。
- Boundary: 未操作 `union_db`、production、provider、replacement、`--switch` 或 deployment。
- Current conclusion: `DB_CHANGE_NOT_READY`；candidate runtime 已驗證，但工作包要求的 enabled-human Browser 與 developer replacement 仍未執行。

## Rulebook and behavior result

Orders 規則允許更正來源通過完整檢核後，採納結果與現行 status/date/assignment 相同。
這是合法 no-op adoption：必須建立可稽核 remediation disposition，但不得製造 lifecycle event。
實機初次 Apply 因舊 `chk_historical_order_adoption_shape` 拒絕此形狀；1008 successor 將 constraint
收斂為：真實狀態轉換必須有 event 且 version +1，no-op 必須無 event 且 version 不變。

Runtime Preview 結果為 `corrected_source_adopted`、`remaining_issues=[]`。Apply 建立唯一 receipt
`historical-order-remediation-receipt:6501733e78ad97b032a935f702916e629883da4e91d8d1b40a40b248f888e6b7`；
正式 consumer 投遞 1 筆且失敗 0 筆。投影後 prior alert 為 `predicate_active=0` / `resolved`，
`GET /api/v1/anomalies?active_only=true` 回傳空清單。相同 idempotency key 重送回傳同一 receipt 且
`replayed=true`，沒有第二筆 event/receipt/outbox。

MySQL readback：訂單 status 仍為「洽談中」（UTF-8 hex `E6B4BDE8AB87E4B8AD`）、
`lifecycle_version=0`、`order_lifecycle_state_events=0`；remediation event/receipt/outbox 各 1，
outbox 已 published、attempts 為 0。immutable prior review 保留，僅 current predicate 解除。

## DB change gates

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | Orders 正式規格、approved work package 與 `lu_test_*` authority 明確覆蓋。 |
| Change inventory | PASS | 1008 僅 `schema-only` check constraint successor；system-seed、business-row-backfill、destructive 均無。 |
| Static release | PASS | release `labor-union-historical-order-adoption-noop-2026-08-27-v1`、assembly v14、generated validation SQL 與 manifest check 一致。 |
| Descriptor | PASS | source 舊 exact shape 解析為 `absent`；candidate 1008 為 `exact`；missing/unknown 皆 fail closed 為 `drift`。 |
| Read-only plan | PASS | `scratch/task96-ddh-e4-r2/runtime-1008-plan.json`，僅列 1008，source state `absent`。 |
| Engine verification | PASS | fresh DB `lu_test_historical_fresh_1008_20260827` 完整 bootstrap PASS；preserve-data candidate `lu_test_historical_runtime_candidate_1008_20260827` restore/apply/verify PASS，1008 exact 且舊資料指紋保留。 |
| Developer acceptance | NOT_RUN | 未執行 local replacement launcher 或 `--switch`；未擴張為既有資料庫替換授權。 |

## Verification

- Python focused：57 passed（historical remediation/repository/API/workflow/schema/plan contract）。
- Static manifest/build：`python -m scripts.verify_validation_schema_manifest` 與
  `python -m scripts.build_validation_schema_release --check` passed。
- React focused：49 passed；production build passed（先前同一 final source candidate）。
- `git diff --check` on scoped paths: passed。
- Browser positive：`NOT_RUN`。候選 API 使用 local bypass 只能作 runtime 證據，不可取代
  enabled persisted human Session。

## 2026-08-28 active readback correction addendum

Task 96 priority correction後重新以fresh Luna/high驗證本slice，發現Apply response在prior alert仍active時把
`readback.remaining_issues`固定回空陣列，會形成「異常未解除但沒有剩餘問題」的假成功。修正版固定遵循：

- `prior_alert_active=true`：回傳prior owner context的完整typed conflicts，React明確顯示並提供重新檢核；
- explicit inactive row：`remaining_issues=[]`；
- anomaly projection row缺失：視為readback unavailable，consumer rollback／mark failed並保持fail closed；
- successor與same-receipt replay語意不變。

修正版focused Python `25 passed`、React `4 passed`、build與`git diff --check` PASS；第二位fresh
`gpt-5.6-luna`／`high`獨立判定source-level P0=PASS。真MySQL／Browser仍`NOT_RUN`，將由後續
H/R/C/A versioned scenario package提供合法active lineage後驗收；本addendum不得冒充跨層完成。

## DDH dynamic operation log

1. 初始使用 E4 分離的 anomaly completeness、LIFF readiness 與 runtime acceptance 唯讀 audit；
   三條均為 `gpt-5.6-luna` / `high`。
2. 真實 Apply 發現 constraint 與規則書衝突後，material phase 改變，動態重投影為 E3
   單一 exact proposal；該子代理亦為 `gpt-5.6-luna` / `high`、唯讀且已 terminal。
3. 1008 整合後，剩餘工作是可機械驗證的序列，改回 E0 deterministic validation，
   沒有再增加不必要的 writer。

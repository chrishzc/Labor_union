# PAYOUT-001 逾期月嫂應付款人工核銷 source completion receipt

- Result：`passed`
- Runtime：`passed`（canonical no-auth MySQL／API／Browser）
- Scope：`PAYOUT-001` exact owner action、React人工核銷與fresh business-oracle readback。
- Non-goals：發動銀行匯款、修改銀行raw fact、PAYOUT-002/003、schema/provider/production。

## Delivered behavior

- Detail精確顯示逾期義務的staff、identity、due date、amount與balance，並從current snapshot綁定owner action。
- 人員只能選擇已存在的canonical outgoing Finance Import rows；Preview驗證exact-only payout，零寫入。
- Apply只enqueue `staff_payout_apply` durable job；HTTP 202、queued/running、receipt或job succeeded本身都不解除異常。
- terminal succeeded必須指向同一 `staff_payout:<staff_id>`，再fresh Query原義務；只有balance=0且completed才refresh anomaly list。
- stale會fresh Query並要求重新Preview；network/timeout未知結果保留同一idempotency key安全重試；failed/cancelled、wrong result、readback未結清都保留異常且提供後續入口。
- generic manual resolve維持禁止；無任何銀行/provider transfer。
- React StrictMode effect replay 不再使 owner Query 永久停在 loading。
- `bank_facts_version` 限制在 JavaScript safe integer 範圍；避免 JSON round trip 把 60-bit token 改值後永久 stale。
- PAYOUT-001 以正 `current balance` 為欠款根事實；`amount_due_ntd=0`、`settled` 或 `completed` 標籤不得
  遮蔽正餘額，balance=0、未到期或 cancelled 則維持 inactive。

## Verification

| Gate | 結果 | Evidence |
|---|---|---|
| Backend binding/QPA regression | `passed` | parent final related suite `71 passed`；E3 final backend sampling `48 passed`。 |
| React strict client/workbench/dispatcher/detail | `passed` | lifecycle/dispatcher final focused `22 passed`；先前 relevant suite `34 passed`。 |
| React production build | `passed` | `tsc -b && vite build` PASS；只有既有bundle-size warning。 |
| Compile/diff/UTF-8 | `passed` | compileall、`git diff --check`、strict UTF-8 PASS。 |
| E3 independent verifier | `passed` | runtime 後 fresh Luna/high 抓到 detector P1；最小修正後另一位 fresh `gpt-5.6-luna`／`high` 以 broader suite `76 passed`、predicate matrix、P0=0/P1=0 獨立通過。 |
| Repository safe-version regression | `passed` | Staff payout repository/workflow/job/action focused `26 passed`；version 固定不超過 `2^53-1`。 |
| Real MySQL/API/Browser | `passed` | `lu_test_task96_scenarios_20260827`；8016/5183 no-auth 真 Browser完成 detail 200/recovery 404、owner Query、Preview、Apply、typed DurableJobWorker與fresh readback。 |
| Terminal owner oracle | `passed` | job `4faae803-3319-4231-8329-640720c48b0a` terminal succeeded；Staff #2 version 1，case `115960411` obligation balance 0/completed。 |
| Anomaly recheck | `passed` | scenario `PAYOUT-001-EXACT-001 --phase verify`：fingerprint `223179fc…416c8` predicate false、workflow resolved；Browser active count 6→5。 |

## DDH dynamic adjustment evidence

1. 三條Luna High/high唯讀候選稽核比較PAYOUT、GOVSUB、LINE；因後兩者仍需Authority，material重投影至PAYOUT-001。
2. write set隔離後以E4 backend與React writers平行，parent保留shared dispatcher，零競寫。
3. 第一輪E3抓到工作台不可達P0與stale循環P1，立即由E4切回單一integration writer。
4. 第二輪E3抓到空recovery actions蓋掉detail metadata P1；保持單一writer做最小修正。
5. 第三輪E3 PASS後進入runtime；真 Browser 額外發現 StrictMode永久loading與60-bit bank version精度漂移，
   依同一PACKAGE_READY的no-dead-UI／fresh-lock oracle做最小修正。
6. final runtime只使用canonical scenario rows；兩筆精度修正前command均以typed stale terminal failed保留異常，
   修正後新Preview／command由正式DurableJobWorker成功，未重送terminal command或直接改帳務root。

## DB gate inventory

本包diff沒有table/column/constraint/index/trigger/view/seed/backfill變更。

| Gate | 結果 | Evidence |
|---|---|---|
| Scope | `PASS` | controlling SPEC/WP只reuse現有Staff Payables Q/P/A。 |
| Change inventory | `PASS` | schema-only/system-seed/business-row-backfill/destructive均`none`。 |
| Static release | `NOT_RUN` | 無DB change，非必要gate。 |
| Descriptor | `NOT_RUN` | 無DB change，非必要gate。 |
| Read-only migration plan | `NOT_RUN` | 無DB change，非必要gate。 |
| Engine migration verification | `NOT_RUN` | 無DB change，非必要gate。 |
| Developer DB acceptance | `NOT_RUN` | 無DB change，非必要gate。 |

DB summary：`NO_DB_CHANGE`。migration gates 不適用；runtime MySQL acceptance 已依上方獨立 runtime gate 通過。

## Remaining truth

`PAYOUT-001` 的 source、canonical MySQL、API、React、正式command runtime、fresh owner readback與真 Browser
閉環已完成。這只證明此一 code/scenario；`PAYOUT-002`仍缺 late-event disposition／delta branches／completion
predicate裁決，`PAYOUT-003`仍缺 bank-master mutation owner／branch policy／closure oracle裁決，兩者維持
`AUTHORITY_REQUIRED`。本收據不得用來宣稱33個active anomaly皆已完成人工修復驗收。

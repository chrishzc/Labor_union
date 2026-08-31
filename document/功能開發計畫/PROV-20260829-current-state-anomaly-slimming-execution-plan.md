---
doc_type: execution-plan
declared_status: approved
date: 2026-08-31
owner: anomalies / architecture-governance / owning-domains
task_level: T3
execution_authority: specification-and-plan-alignment-only
---

# Current-state 異常機制瘦身執行計劃

> 2026-08-31 最新人工裁決取代本計劃較早的 `15 current issues + 25 owner work items + 3 retire/merge` denominator。
> 本次只授權規格與計劃同步；不因本文件更新自動授權 production source、schema、DB、API、React、provider、deployment、entry switch 或 destructive cleanup。

## 1. Objective

Anomalies 只保留「實際可發生，而且發生後需要人處理」的業務異常。

純系統公式、deterministic aggregate／projection、transaction invariant、migration integrity、正常來源先後、normal retry／replay、owner readback temporary failure，不建立 runtime recovery product。

Canonical current issue exact set：

```text
LINE-006
```

因此 runtime Anomalies exact set = `{LINE-006}`。

`GOVSUB-007` 退出 runtime Anomalies，改由 Government Subsidy 正常 accounting／review／correction flow 承接；`BECLASS-001` 改為 Case Import／Client owner follow-up。其餘原 15-code target 中 13 碼退出 runtime anomaly。

正式產品語意以 `document/架構重整/01_規格基線/06_Anomalies_Domain.md` 的 2026-08-31 amendment 為準。

## 2. Disposition

| Code | Target | 理由／承接 |
|---|---|---|
| `GOVSUB-007` | retire from anomaly | 政府退款超額處置屬 Government Subsidy 正常 owner flow，不形成 Anomalies current issue；保留正常 owner accounting／review／correction與必要 validation |
| `LINE-006` | current issue | 外部 recipient／binding／configuration／provider delivery 在 bounded retry 後可能仍需要人工處理 |
| `BECLASS-001` | owner work item | HCM／Client BeClass 是合法獨立 intake；缺 counterpart 是正常先後，必要時由 owner follow-up |
| `PAYOUT-002` | retire from anomaly | late obligation scenario 不屬目前實際業務；薪資以正式服務天數為根 |
| `GOVSUB-001` | retire from anomaly | 季別／批次 reconciliation 是 deterministic owner behavior或 Finance review |
| `GOVSUB-002` | retire from anomaly | allocation ambiguity若存在走 owner Preview／manual allocation，不需要第二個 anomaly lifecycle |
| `GOVSUB-003` | retire from anomaly | ledger／allocation／projection 不一致是 correctness／migration failure |
| `GOVSUB-004` | retire from anomaly | reversal validity由正式 Preview／Apply阻止非法結果 |
| `GOVSUB-005` | retire from anomaly | 合法 drift走正常 revision；非法 drift是 correctness failure |
| `IMPORT-003` | retire from anomaly | BeClass／HCM可合法先後到達；不存在 HCM 補件 anomaly workflow |
| `IMPORT-006` | retire from anomaly | import/parser/aggregate integrity由 deterministic tests與Apply validation負責 |
| `SCHEDULE-002` | retire from anomaly | replacement／substitution正式 transaction 本來就必須原子保存完整 lineage |
| `SCHEDULE-003` | retire from anomaly | occupancy conflict應在 Scheduling Preview／Apply前被阻止 |
| `SCHEDULE-006` | retire from anomaly | coverage／hours／dates／ownership都是 canonical Apply invariant |
| `LINE-004` | retire from anomaly | same-type conflict已有normal replacement rule；customer＋staff雙角色合法 |

退役只表示退出 runtime anomaly product；owner events、receipts、tests、migration provenance不因此刪除。

## 3. `LINE-006` target behavior

不得因下列狀態單獨建立新的 `LINE-006`：

- `pending`／`processing`；
- retryable failure仍在 bounded retry；
- manual replay正常執行中；
- owner readback incomplete／temporarily unavailable；
- maintenance scan incomplete。

只有 automatic path已無法繼續且需要人工時才 active：

1. exact recipient／binding／configuration缺失或失效，需要人修正；
2. bounded automatic retry耗盡並 terminal failed，需要人工 replay／處置；
3. provider outcome經 bounded reconciliation仍無法確定並正式進入人工處理邊界。

readback unavailable若已有真實 business issue，可以 fail closed保留舊 row；不得以 incomplete本身合成新 issue。

## 4. `GOVSUB-007` runtime exit

`GOVSUB-007` 不再是 runtime Anomalies current issue，也不再由 Anomalies detector、public definition、React mapping 或 current projection 表達。政府退款超額若需處理，仍由 Government Subsidy 正常 accounting／review／correction flow 承接。

Government Subsidy 的正常 claim、receipt、allocation、reversal、review與必要 owner correction保留；Anomalies不修改 payable、allocation或ledger，也不建立 anomaly-owned recovery framework。


## 5. LINE identity target behavior

- customer＋staff雙角色合法，不產生 anomaly。
- customer binding綁 Client root，不綁案件編號；同一 Client新增年度案件不更換 LINE identity。
- legacy資料真的形成兩個 customer roots且同一 LINE user時，依人工裁決用 normal same-type replacement讓目前／新 Client root取代舊 root，清除舊 owner projection；staff role保持不變。
- 無法唯一確認 current Client root時留在 LINE Identity owner review，不建立 Anomalies lifecycle。

## 6. Execution packages

### ANM-PRUNE-00 — Specification alignment

Write set：`06_Anomalies_Domain.md`、Task 96 current register、本計劃與 current parallel refresh。

Acceptance：所有 current planning文件使用 exact one-code denominator `{LINE-006}`；不再要求為`GOVSUB-007`、其餘12個 retired codes或`BECLASS-001`建立manual recovery Q/P/A。

### ANM-PRUNE-01 — Registry／typed contract shrink

未由本次文件更新自動授權執行。

未來取得 source edit Authority 後：

- runtime registry exact set改為 `{LINE-006}`；
- public details／subject union只保留 `LINE-006`；
- `GOVSUB-007`與其餘12碼 definition／producer／consumer／React mapping逐項移除或改為 owner-validation/migration-only evidence；
- `BECLASS-001`改接 owner follow-up query。

不為 retired code建立 adapter、fallback、replacement remediation framework。

### ANM-PRUNE-02 — `LINE-006` predicate shrink

- owner readback分清 automatic/transient 與 manual-required；
- pending／processing／retryable／readback-only不產生新 issue；
- terminal manual-required才產生；
- owner修正後仍需fresh validation＋delivery success或source no longer applicable才刪除。

### ANM-PRUNE-03 — `GOVSUB-007` runtime exit

- 移除 runtime producer與public current definition；
- Government Subsidy正常 accounting／review／correction flow保留，必要 owner validation與migration readback不受影響；
- 不重建 GOVSUB anomaly family或generic government recovery framework。

### ANM-PRUNE-04 — API／React alignment

- `#anomalies`只顯示 `LINE-006`；
- owner work item不重新聚合進Anomalies；
-無claim／resolve／history／tracking UI；
- retired code的舊頁面、fixtures、KPI若只服務舊語意則刪除，不保留compatibility shell。

### ANM-PRUNE-05 — Runtime／migration cleanup

只有取得 exact source／DB／entry Authority後才執行。

- fresh current projection只由 `LINE-006` owner facts重建；
- 舊 schema artifact若是immutable migration provenance可保留檔案，但current runtime零引用；
- destructive table drop、entry retirement、configured DB Apply仍需各自Authority；
- 不因 anomaly pruning刪除 owner Domain正式business history。

### ANM-PRUNE-06 — Final proof

最低充分 oracle：

1. registry exact one-code set `{LINE-006}`；
2. `BECLASS-001` owner follow-up可達且不在 `#anomalies`；
3. `GOVSUB-007`與其餘12 retired codes零runtime producer／public definition／React current mapping；
4. `LINE-006` automatic in-progress/retry/readback-only negative cases不產生issue；manual-required positive case產生；
5. customer＋staff dual-role、多案件same Client與normal same-type replacement不產生`LINE-004`；
6. predicate false＋authoritative complete時row實際delete；
7. focused tests、strict UTF-8、governance/reference scan、`git diff --check` PASS。

## 7. Explicit non-goals

本計劃不再要求：

- 15-code owner action matrix；
- PAYOUT-002 late-event disposition framework；
- GOVSUB-001～005 recovery workbench；
- IMPORT-006 deterministic-rebuild／corrected-source雙 recovery surface；
- IMPORT-003 original-review→HCM successor anomaly lineage；
- Scheduling invariant repair UI；
- LINE-004 duplicate-root anomaly recovery；
- 因readback incomplete而生成業務issue。

這些較早計畫內容全部由2026-08-31人工reachability裁決 supersede。

## 8. Completion definition

本計劃只有在產品與runtime都符合下列條件才可標 `completed`：

- current anomaly product exact one code `LINE-006`；
-所有被剃除情境仍由其真正owner validation／test／normal workflow或operations保護，沒有功能斷線；
-沒有為理論上「程式自己算錯」的情境留下人工 recovery surface；
- `LINE-006`具current detection、owner action boundary與fresh removal oracle；
-未越權執行 production／`union_db`／provider／deployment／entry switch／destructive DB cleanup。

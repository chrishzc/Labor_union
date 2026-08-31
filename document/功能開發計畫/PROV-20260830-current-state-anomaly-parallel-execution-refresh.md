---
doc_type: execution-ssot-refresh
declared_status: superseded
date: 2026-08-31
task_id: CUR-ANOMALY-SLIMMING-01
owner: anomalies / owning-domains
superseded_by: PROV-20260829-current-state-anomaly-slimming-execution-plan.md
supersession_reason: 2026-08-31 business-reachability pruning
---

# Current-state Anomalies：parallel execution refresh（superseded）

2026-08-31 最新人工裁決已取代本檔原本的 15-code repository-local execution denominator。

Current product rule：Anomalies 只保留「實際可發生且發生後需要人處理」的業務異常；純系統公式、deterministic projection／aggregate、transaction invariant、migration integrity、正常來源先後、automatic retry／replay 與 temporary readback failure 不建立 runtime recovery product。

目前唯一 current execution plan：

`PROV-20260829-current-state-anomaly-slimming-execution-plan.md`

正式產品規格：

`document/架構重整/01_規格基線/06_Anomalies_Domain.md`

## Supersession result

原本 15 current definitions 不再是 current target。

Current runtime issue exact set = `{LINE-006}`：

- `LINE-006`，且只有 automatic path 已無法繼續、確實需要人工處理時才 active。

`GOVSUB-007` 已退出 runtime Anomalies；政府退款超額若需處理，回到 Government Subsidy 正常 accounting／review／correction flow，不保留 anomaly producer或public current mapping。

移出 Anomalies：

- `BECLASS-001` → Case Import／Client owner follow-up；
- `PAYOUT-002`；
- `GOVSUB-001`～`GOVSUB-005`；
- `IMPORT-003`；
- `IMPORT-006`；
- `SCHEDULE-002`；
- `SCHEDULE-003`；
- `SCHEDULE-006`；
- `LINE-004`。

其中退役碼仍可有 owner validation、focused tests、migration readback 或正常 owner operation；只是不得再以「如果程式自己寫壞」為理由建立 manual recovery framework。

## Preserved evidence

本檔較早記錄的 repository-local source、tests、typed readback、same-UoW recheck、PR integration與Task 97 closeout結果只保留為 implementation evidence。它們不得反向要求：

- 保留 15-code registry；
- 補齊 13-code owner Q/P/A；
- 建立 IMPORT-003 pairing lineage；
- 建立 IMPORT-006 recovery branches；
- 建立 Scheduling invariant repair UI；
- 把 LINE retry in-progress 或 readback incomplete 顯示成業務異常。

## Current boundary

本次文件同步不授權 production source、schema／migration、configured DB、public API、React、provider、deployment、entry switch或destructive cleanup。後續若取得 source implementation Authority，只依 current plan 的 `ANM-PRUNE-*` packages施工。

本檔不再接受 execution status 更新；後續任何 current anomaly工作只更新 canonical plan、Task 96 current register與真正 owning spec。

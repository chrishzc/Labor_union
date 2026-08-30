# 功能開發計畫索引

本目錄只保留尚在規劃、blocked 或 deferred，且尚未由正式規格完整承接的 initiative。
功能計畫不是 production mutation 授權；正式 owner 與業務語意以
[`15_正式規格索引與裁決總表.md`](../架構重整/01_規格基線/15_正式規格索引與裁決總表.md)
及其 Domain／Global 規格為準。跨功能 current 執行清單只看
[`96_Current_剩餘代辦任務總表.md`](../架構重整/02_決策與退役執行記錄/96_Current_剩餘代辦任務總表.md)。

## Active／deferred 計畫

| 文件 | 狀態 | 下一個 gate |
|---|---|---|
| [Current-state 異常機制瘦身完整執行計劃](PROV-20260829-current-state-anomaly-slimming-execution-plan.md)（[Task 97 Authority reconciliation](PROV-20260830-current-state-anomaly-task97-authority-reconciliation.md)；[parallel execution SSOT](PROV-20260830-current-state-anomaly-parallel-execution-refresh.md)） | `ANOMALIES_REPOSITORY_LOCAL_PARTIAL / integrated in PR #63`；destructive cutover `NOT_AUTHORIZED` | Task 96 Stage 4才續作：先等Stage 1 DB、Stage 2 LINE與Stage 3其他13碼owner backend terminal，再只消費owner Q／P／A／readback完成detector、descriptor、fresh recheck與15-code matrix。 |
| [LINE 後端瘦身執行計畫](LINE_BACKEND_SLIMMING_PLAN.md)（[historical/current-head pre-refresh amendment](LINE_BACKEND_SLIMMING_POST_PREP_AMENDMENT.md)；[parallel execution SSOT](LINE_BACKEND_SLIMMING_PARALLEL_EXECUTION_REFRESH.md)） | `LINE_BACKEND_SLIMMING_REPOSITORY_LOCAL_PARTIAL / integrated in PR #63` | PR adoption後先完成Task 96 Stage 1 DB baseline，再進Stage 2：M1 dual-role persistence、M2真正缺口、M3 recipient／snapshot／token／delivery、M4 terminal source及`LINE-006` owner Query／readback。 |
| [NAS 檔案庫與資料中心管理介面正式規範](NAS_檔案庫與資料中心管理介面正式規範.md) | `approved` | 雙欄檔案總管版型、結構化命名、Freeze-Before-Send 與刪除防呆已核准；進行 UI 實作與資料中心分頁切換。 |
| [Cloud Run＋單一 Cloud VPN 雲端部署測試計畫](Cloud_Run_單一Cloud_VPN_部署測試計畫.md) | `proposed` | 指定隔離 cloud project／NAS DB、operator、預算與故障注入範圍後，另立 exact Work Package。 |
| [Cloud Run Durable Job Worker Supervision](Durable_Job_Worker_Supervision_延後開發計畫.md) | `proposed`／`deferred` | 指定隔離 cloud test project／NAS DB、OIDC、operator、故障注入與雲端測試 gate。 |
| [LINE QA 客服知識契約收斂](LINE_QA客服知識契約收斂計畫.md) | `blocked` | loader runtime 可用，且 owner／category／source／approved answer 完成人工 review 後另立 Work Package。 |

### Anomalies／LINE 平行整合結果（2026-08-30）

兩支bounded branch已依`LINE → Anomalies → LINE-004 consumer → shared governance`順序收斂於PR #63。
Integration Writer只新增LINE-004 typed current-fact consumer／adapter與必要shared projections；沒有重開Task 97、
沒有新增schema／migration，也沒有替LINE-006或其他13個owner gap發明契約。完整結果與deferred boundary見
[`PROV-20260830-line-anomalies-slimming-integration-receipt.md`](../架構重整/03_追蹤清單與證據/evidence/PROV-20260830-line-anomalies-slimming-integration-receipt.md)。

上述計畫不是 production、Cloud、provider、deployment、entry switch 或外部副作用的自動授權；涉及這些效果時仍須符合各計畫的 current Authority 與人工 gate。

## 2026-08-25 歷史收斂

下列舊 umbrella／設計計畫已由正式規格與 current task register 完整承接，並自目前工作樹移除：

- UI 真實業務流程測試資料與驗收主計畫
- Part 00 全域測試資料治理與 Scenario 契約
- React 管理端遷移與 UI 真實業務流程驗收計畫
- LINE 運營與智能管理中心視覺化工作台規範
- LINE LIFF 工會手機管理中心規範
- LINE LIFF 身分先行與服務登記導流規劃
- LINE LIFF 舊客快速身分綁定與防冒領規範

這些文件的 UI／UX 設計意圖仍可在 exact 任務中作低頻參考，但不得覆蓋正式規格；其舊 phase、
`approved` 自稱、route、writer 或待辦不再參與 current 完成度判斷；需要原文時從 Git 歷史精準取回。

2026-08-25 使用者提供的 Eraser M1～M4 與全系統總覽原圖需求，已另由
`../架構重整/01_規格基線/26_LINE四大模組Eraser流程圖轉錄與驗收基線.md` 保存。該文件承接
後續逐節點驗收與原圖缺口登記；缺口在 96 完成前固定 `deferred-after-96`，
不重新啟用上述 archived 計畫。

`completed` 或 `superseded` 文件不得留在 active 表。只有 current successor 已承接業務不變量、
remaining task 與人工 recovery，且 inbound links 已更新後，才能從工作樹移除。

# 功能開發計畫索引

本目錄只保留尚在規劃、blocked 或 deferred，且尚未由正式規格完整承接的 initiative。
功能計畫不是 production mutation 授權；正式 owner 與業務語意以
[`15_正式規格索引與裁決總表.md`](../架構重整/01_規格基線/15_正式規格索引與裁決總表.md)
及其 Domain／Global 規格為準。跨功能 current 執行清單只看
[`96_Current_剩餘代辦任務總表.md`](../架構重整/02_決策與退役執行記錄/96_Current_剩餘代辦任務總表.md)。

## Active／deferred 計畫

| 文件 | 狀態 | 下一個 gate |
|---|---|---|
| [Cloud Run＋單一 Cloud VPN 雲端部署測試計畫](Cloud_Run_單一Cloud_VPN_部署測試計畫.md) | `proposed` | 指定隔離 cloud project／NAS DB、operator、預算與故障注入範圍後，另立 exact Work Package。 |
| [Cloud Run Durable Job Worker Supervision](Durable_Job_Worker_Supervision_延後開發計畫.md) | `proposed`／`deferred` | 指定隔離 cloud test project／NAS DB、OIDC、operator、故障注入與雲端測試 gate。 |
| [LINE QA 客服知識契約收斂](LINE_QA客服知識契約收斂計畫.md) | `blocked` | loader runtime 可用，且 owner／category／source／approved answer 完成人工 review 後另立 Work Package。 |

上述三項不是目前程式施工授權。Cloud、production、provider、deployment、entry switch 與外部副作用
仍須新的人工確認。

## 2026-08-25 封存收斂

下列舊 umbrella／設計計畫已由正式規格與 current task register 完整承接，移至
`04_已完成與上線封存/superseded_specs/`：

- UI 真實業務流程測試資料與驗收主計畫
- Part 00 全域測試資料治理與 Scenario 契約
- React 管理端遷移與 UI 真實業務流程驗收計畫
- LINE 運營與智能管理中心視覺化工作台規範
- LINE LIFF 工會手機管理中心規範
- LINE LIFF 身分先行與服務登記導流規劃
- LINE LIFF 舊客快速身分綁定與防冒領規範

這些文件的 UI／UX 設計意圖仍可在 exact 任務中作低頻參考，但不得覆蓋正式規格；其舊 phase、
`approved` 自稱、route、writer 或待辦不再參與 current 完成度判斷。精確 archive path、digest、successor
與 restore trigger 只由 `archive_manifest.json` 路由。

`completed` 或 `superseded` 文件不得留在 active 表。只有 current successor 已承接業務不變量、
remaining task 與人工 recovery，且 inbound links／manifest 已更新後，才能封存。

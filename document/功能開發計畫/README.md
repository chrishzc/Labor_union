# 功能開發計畫（已收斂）

狀態：`current-operational-manual-plus-historical-routing`  
收斂日期：2026-09-02

本目錄不再保存平行的 current 產品規格、施工計畫或外部操作 gate，但保留無法由正式規格取代、仍供實際執行的操作／測試手冊。Current owner 與業務語意仍只由 `document/架構重整/01_規格基線/` 的正式規格擁有；舊計畫需要稽核時，從清理前 commit `b1679e737e50d0d3a064f380df8584e202dd8df4` 精確取回。

## Current 操作手冊

- [LINE 四大模組詳細測試手冊與 Agent 前置條件規範](LINE_四大模組_詳細測試手冊與前置條件.md)：保留 M0～M4 的 Agent 前置、手機 E2E 操作、readback、驗收層級與 cleanup 步驟。它是 current 可執行測試手冊，不是 owner／SSOT；route、schema、owner 或正式驗收契約變更時必須同步更新，且不得覆蓋 `17`、`20`、`23`、`26`、`29`。

## 已收斂路由

| 舊主題 | Current owner／處置 |
|---|---|
| Cloud Run＋單一 Cloud VPN 部署測試 | 特定 cloud topology、project、VPN、預算與 rollout 皆未成為 current requirement；部署不變量由 `18_Global_Deployment與治理正式規格.md` 擁有。需要實際 cloud target 時重新依當時官方能力與明確 Authority 立案。 |
| Durable Job Worker Supervision 延後計畫 | Durable job、worker、heartbeat、lease、retry 與 runtime supervision 由 `07`、`18` 及 current source 擁有；舊 Cloud Run Worker Pool proposal 不再保留 current copy。 |
| NAS 檔案庫與資料中心介面 | Controlled-file、NAS、authenticated download 與媒體 owner boundary 由 `00`、`18`、`20` 擁有；資料中心三分頁的 latest human decision 已在 `15`。舊硬編路徑、命名、容量門檻與刪除 UI 不形成 current contract。 |
| LINE QA、Service Help 與 Rich Menu 規格 | 由 `17`、`20`、`23`、`26` 與 `29_LINE服務說明、客服互動與選單角色正式規格.md` 承接。 |

## 邊界

- 舊計畫中的 priority、write set、host、port、provider、schema、credential、付款、deployment 或 production 名稱不構成執行授權。
- Current 操作手冊可保留具體操作順序、裝置需求、測試資料前置與結果回報格式，但不得自行建立 owner、業務規則、外部副作用或 production Authority。
- 新需求優先修改既有 owning formal spec；只有實際執行步驟改變時才同步修改操作手冊，不新增平行規格或第二套 owner。

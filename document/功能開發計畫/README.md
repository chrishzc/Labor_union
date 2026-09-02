# 功能開發計畫（已收斂）

狀態：`historical-routing-only`  
收斂日期：2026-09-02

本目錄不再保存 current 產品規格、施工計畫或外部操作 gate。Current owner 與語意只由 `document/架構重整/01_規格基線/` 的正式規格擁有；舊計畫需要稽核時，從清理前 commit `b1679e737e50d0d3a064f380df8584e202dd8df4` 精確取回。

## 已收斂路由

| 舊主題 | Current owner／處置 |
|---|---|
| Cloud Run＋單一 Cloud VPN 部署測試 | 特定 cloud topology、project、VPN、預算與 rollout 皆未成為 current requirement；部署不變量由 `18_Global_Deployment與治理正式規格.md` 擁有。需要實際 cloud target 時重新依當時官方能力與明確 Authority 立案。 |
| Durable Job Worker Supervision 延後計畫 | Durable job、worker、heartbeat、lease、retry 與 runtime supervision 由 `07`、`18` 及 current source 擁有；舊 Cloud Run Worker Pool proposal 不再保留 current copy。 |
| NAS 檔案庫與資料中心介面 | Controlled-file、NAS、authenticated download 與媒體 owner boundary 由 `00`、`18`、`20` 擁有；資料中心三分頁的 latest human decision 已在 `15`。舊硬編路徑、命名、容量門檻與刪除 UI 不形成 current contract。 |
| LINE QA、Service Help、Rich Menu 與手機驗收 | 由 `17`、`20`、`23`、`26` 與 `29_LINE服務說明、客服互動與選單角色正式規格.md` 承接。 |

## 邊界

- 舊計畫中的 priority、write set、host、port、provider、schema、credential、付款、deployment 或 production 名稱不構成執行授權。
- 新需求優先修改既有 owning formal spec；不得因本目錄存在而新增平行 plan、adapter、fallback 或第二套 owner。
- 本檔只維持歷史路由，不提供 current acceptance、implementation status 或外部操作指令。

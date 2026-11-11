# Global Deployment 與治理正式規格

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Global Deployment / Runtime Governance
- 單一負責範圍：正式部署拓樸（工會 Windows 主機應用端＋區網 NAS MySQL 端）、React 靜態產物與本機 runtime 邊界、Windows 遠端入口與獨立換版、Release orchestration、Runtime supervision 與 30 天營運技術資料保留治理。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Global Migration 與 Cutover](10_Global_保留資料Migration與Cutover_Subsystem.md)、[External Integration / Access Control](17_External_Integration_LINE_Access正式規格.md)、[Global Entry Point Governance](19_Global_Entry_Point_Governance.md)

本文件定義部署、發布與維運契約，不構成任何特定 production target、credential、schema mutation、provider publication 或外部寫入的執行授權。

## 2. Deployment 不變量

1. MySQL 位於 private data zone，不公開 Port 3306。
2. Public edge 只暴露必要 HTTPS endpoint；管理端預設限制於 LAN、VPN 或受控 access。
3. TLS 由受管理 edge／reverse proxy 終止，edge 到 application 的信任邊界明確。
4. 管理端唯一正式前端產物為 React（`ui_react/`）。
5. FastAPI 是唯一正式 HTTP business／integration boundary。
6. Worker 與 monitor 不持有 DB credential，只透過 authenticated Private Operations API 執行已定義 operation。
7. Production secret 不進 Git、文件、log、process argument、browser bundle 或 receipt。
8. Schema 變更必須使用 preserve-data release manifest、backup、candidate、validation、switch 與 recovery receipt。
9. Release 未通過 post-start readback 不得標示完成。
10. 部署位置變更不得改變 Domain ownership、typed API contract、transaction 或資料語意。
11. NAS production Private Operations caller 使用各 Worker 獨立機器憑證與私人 HTTPS；local shared key 不得 fallback 到 production。
12. 外部副作用只由已提交的 outbox、inbox 或 durable job 執行。
13. 技術 log 與營運觀測資料以正向 allowlist 管理，最長保留 30 天；所有業務根事實、事件與稽核證據不受本政策刪除。

## 3. 正式部署拓樸

系統採「工會電腦應用端＋區網 NAS 資料庫端」分離架構：

- **工會電腦（Windows 應用端）**：以根目錄 `Windows管理.bat`（`scripts/launchers/manage_windows.ps1` → `supervise_local_runtime.ps1`）與根目錄 `docker-compose.yml`（本機 Redis）啟動並監督 FastAPI、React 靜態產物、背景 Workers、LINE Webhook 與 Cloudflare Tunnel（詳見 `scripts/launchers/WINDOWS-REMOTE.md`）。主機間程式交付使用 `scripts/package_windows_runtime.py` 產生排除秘密與 runtime 資料的來源雜湊部署包。
- **NAS（Synology 資料庫端）**：僅透過 `deployment/nas/compose.yaml`、同目錄 `.env` 與 `mysql-client.cnf` 部署區網隔離的 MySQL 8.0 資料庫（`db` 服務與 `mysql-data` 資料卷，密碼以 `/run/mysql-secrets/root-password` 與 `app-password` 唯讀檔案掛載）。日常維護由 `deployment/nas/README.md` 承接。
- **NAS 每日線上 SQL 備份**：DSM 每日 03:00 以獨立 root 腳本 `deployment/nas/backup-database.sh` 將 `db` 容器內的非空 InnoDB 資料庫匯出至未掛入容器的 NAS 管理者專用資料夾，永久保存、不自動清理；不停止服務或變更 Compose／`.env`／DB GRANT。檢查來源歸屬、權限／路徑、串流／壓縮／檢查碼與完成標記，失敗非零通知 DSM 並保留備份；詳細操作見 `deployment/nas/SQL-BACKUPS.md`。
- **NAS 保留資料升級**：Schema 升級使用 `deployment/nas/upgrade-database.sh` 與 `scripts/update_nas_database.py` 針對冷備份副本驗證後切換，詳見 `deployment/nas/DATABASE-UPGRADE.md`。
- **API 隔離組成與機器憑證邊界**：`api/main.py`（含 `api/routes/admin_setup.py` 首次 root 建帳）、`api/nas_apps.py` 與 `api/routes/nas_line_operations.py` 維持管理與公開 LINE 分離組成及私人入口 `/internal/v1/line-operations`（限 `line-operations-proxy` 獨立機器憑證呼叫）。

### 3.1 Public edge、Application zone 與 Data zone

- **Public edge**：只允許 LINE webhook（`/webhook/line`）、LIFF callback／必要 public read、最小非敏感 health 與受控 React 管理端 HTTPS origin；禁止公開 MySQL、未驗證 admin mutation、debug 檢視或以 local bypass／shared key 當 production contract。
- **Application zone**：FastAPI 負責 HTTP Q/P/A、Webhook 與 Private Operations；React 為靜態 Presentation Adapter；Worker 執行 committed outbox／LINE／durable／inbox／retention tasks；Monitor 觀測並回報 Private Operations API；Migration runner 僅於維護窗獨立執行。FastAPI lifespan 不內嵌 worker。
- **Data / Archive zone**：Production DB credential 只交給 FastAPI composition 與 migration runner；React／worker／monitor／browser 不持有 DB credential；Backup 必須通過 restore rehearsal。

## 4. React 靜態產物與標準本機 Runtime

### 4.1 React production artifact

Current source 位於 `ui_react/`。Production artifact 必須具備：immutable artifact identity 與 digest、完整檔案 manifest、`index.html` current React root marker、被 current registry 接受的 API compatibility revision，以及 health readback 證明。

### 4.2 標準本機 Runtime

標準本機 topology：FastAPI `127.0.0.1:8000`、React/Vite `127.0.0.1:5173/admin/`、runtime monitor、durable job worker、incident worker 及依設定啟用的 LINE／knowledge workers。統一採 `local_auth` profile。

Windows 開發環境可使用主機 npm 或 Docker Vite；無主機 npm 時，`supervise_local_runtime.ps1` 將 Docker Vite 發布於動態 `127.0.0.1` port 並啟動 `scripts.launchers.local_react_gateway` 轉送 `/api`、`/line-`、`/webhook` 與 Vite WebSocket。`--dry-run` 只檢查 dependencies；`--smoke-test` 建立 owned process 執行 GET-only readiness 後清理。

## 5. Windows 遠端入口、獨立換版與統一管理

### 5.1 遠端登入與 LINE Webhook 入口

- **遠端管理路徑**：`https://chrishzc.com/test/` 使用專用 Windows Tunnel 與受 Cloudflare Access 指定信箱 Email PIN 保護的 origin；Worker 僅轉送 `/test` 路徑，不外傳原網站 session／cookies，保留 Bearer、版本、下載與 typed status；上游維持 `Cache-Control: no-store`（僅具 manifest 驗證與版本雜湊之純 JS／CSS 靜態檔可回 `private, max-age=31536000, immutable` 並剝除內部認證標頭）。本機同時保留 `http://localhost:5173/admin/`（公開 host 拒絕 `/admin/`）。
- **Access 與本機設定隔離**：`start_windows_remote.bat --connect` 啟動與本機一致的背景工作／推播與唯讀 DB schema gate；tunnel token 只存於 ACL 限制的 ignored token-file，不進 `.env`、命令列、映像或 log；Agent 不讀取或修改 `.env`。
- **LINE Webhook 公開入口**：`https://line.chrishzc.com/webhook/line` 經同一 Windows Tunnel 獨立 hostname 精確路徑轉送至 `127.0.0.1:8000`，不套人員 Email Access、保留 LINE 簽章／inbox／去重契約，catch-all 拒絕該 hostname 下所有非 `/webhook/line` 路徑。

### 5.2 前端獨立換版（`--update-frontend`）

- `start_windows_remote.bat --update-frontend` 先於隔離目錄建置並通過 manifest validator 後，透過 run-bound 本機控制檔提交重啟請求，不觸發 DB gate、Redis 或 Worker 重啟，不讀寫 `.env`。
- Supervisor 嚴格核對 `role`、PID 與 native start time；建置或新版 static manifest 回讀失敗時保留／回復原 artifact，不連帶影響 API、Workers 或 Tunnel。

### 5.3 統一管理與多機切換

- `Windows管理.bat` → `scripts/launchers/manage_windows.ps1` 提供整組啟停／更新、前端更新、狀態查詢、來源部署包與依賴安裝；停止時採 run-bound 控制通道與 native PID／start-time 核對後清理，關閉選單不停止背景服務。
- 完整更新先建置成功再停啟，保留既有設定啟用的所有背景 worker；部署包排除 `.env*`、credential、runtime data 及 ignored 檔案（managed Vite build 關閉 envDir discovery）。
- 共用網址且多台主機資料獨立時，人工確認舊機整組停止且 connector 離線後才啟新機，不同步業務資料。

## 6. Release orchestration 與觀測

### 6.1 Release 狀態流與 Preflight

```text
prepared → preflight_passed → execution_approved → backup_verified
→ candidate_validated → release_approved → switched → restart_verified → released
```

任一步驟失敗轉 `failed`；`switched` 後失敗轉 `recovery_required → recovered | escalated`。Release manifest 須記錄 release version、Git ref、artifact digest、schema release identity／digest、source／candidate DB identity、backup／restore evidence、operator、window、correlation identity、required secret 名稱（不含值）與 rollback contract。

Preflight 強制檢核 target identity、secret、DB principal、schema drift／pending migration、backup／restore tool、FastAPI/React/worker/schema compatibility 與 approval 效期；Switch 必須原子並保留 before／after readback。

### 6.2 Runtime supervision

分別觀測 FastAPI、React `/admin/`、Worker heartbeat／queue lag／dead letter、inbox oldest pending、MySQL connectivity／pool、public edge／TLS／signature、controlled storage 可用性與容量、backup／restore rehearsal age。Private Operations client 僅依 typed `retryable` 有上限重試；Logs 須含 correlation identity、service、release version 與 error code，嚴禁洩漏敏感內容。

## 7. Operational retention 與容量治理（30 天政策）

本節由 Global `runtime-governance / operational-retention` 擁有。

- `RET-001 — 分類登記`：所有可清理來源須登記於 versioned retention registry（含 owner、store、age 欄位、刪除順序、30 天規則、容量估算與驗證）。未分類來源標為 `blocked-unclassified`，嚴禁清理。
- `RET-002 — 30 天上限`：allowlist 來源以 UTC terminal time（無 terminal lifecycle 時採 creation time）滿 30 天進入到期候選，由 maintenance worker 分批回收；仍在合法 lease／active runtime 使用中物件先完成終態再候選。
- `RET-003 — 容量壓力`：部署 target 須設定 `0 < low-water < high-water`。超過 high-water 時依 oldest-first 回收 allowlist 至 low-water；候選不足回報 `retention_capacity_unrelieved` 並告警，絕不跨入 denylist。
- `RET-004 — 初始 allowlist`：(a) application／worker active 與 rotated log segments；(b) Knowledge terminal `knowledge_answer_requests`、`knowledge_jobs`、`knowledge_answer_receipts`、`knowledge_answer_sources`；(c) terminal Knowledge index-build job、failed／stale／已被較新 READY 取代之 index metadata 與 vector artifact（active READY index 與 published catalog 不可清理）。
- `RET-005 — 永久 denylist`：member／client／staff、order／schedule／case、finance／payment／payroll、contract、客服案件、業務 event／receipt、inbox／outbox／delivery task、admin／security audit 及 archive、controlled-file object／business artifact／cleanup or reconciliation evidence、schema migration、release、backup／restore 與 incident evidence 一律永久保留。
- `RET-006 — 自動清理與對帳`：獨立 maintenance worker 每日至少執行一次，按來源分批、單一 outer UoW 與 idempotent command identity；DB 與 filesystem 無法同 transaction 時須保存可重跑 reconciliation state。
- `RET-007 — 檔案輪替與路徑安全`：active log segment 達上限先 rotate，僅操作 registry 內 canonicalized owned roots；symlink／junction、root escape、active writer 與受控業務檔案 fail closed。
- `RET-008 — 後端執行與管理端邊界`：保留 30 天自動排程清理（`run_automatic_retention_cycle`）與既有 API；管理端側欄不呈現獨立「儲存空間管理」維護頁（依 [Entry Point Governance](19_Global_Entry_Point_Governance.md) 邊界執行）。
- `RET-009 — Manual Preview／Apply`：觸發人工清理操作時限 root 管理員權限，須先以 zero-write Preview 凍結 policy revision、source、cutoff、candidate upper bounds 與 digest，Apply 帶入 multi-root preview fingerprint，任何候選或 policy 改變皆回 typed stale conflict。
- `RET-010 — Aggregate Audit`：每次清理保留非敏感 aggregate audit evidence（actor/worker、mode、policy revision、source、cutoff、counts、logical bytes、時間、outcome、correlation identity），不受 30 天政策刪除。

## 8. 人工授權邊界與驗收標準

### 8.1 高風險操作授權邊界

production deployment、schema／data migration、backup restore／target switch、provider publication、credential 操作、付費資源異動與實際 destructive cleanup，均須取得針對精確 target 的最新人工明確授權；本機測試或 rehearsal 通過不構成執行授權。

### 8.2 驗收標準

- Allowlist 來源滿 30 天可由 worker 分批刪除，第 29 天與 active runtime state 零誤刪；高水位壓力模擬時 oldest-first 降至 low-water 或回報 `retention_capacity_unrelieved`，denylist 零變更。
- Knowledge 回饋清理依 `source → receipt → terminal job → request` 順序執行，published catalog 與 READY index 保持不變。
- Log 達上限先 rotate；path escape、active writer 與未登記 root 均 fail closed；部分失敗可重跑對帳且 aggregate evidence 不含敏感資料。
- Windows 遠端與換版驗證：無權限／anonymous 請求正確 401/拒絕、`/test` 不外傳原網站 cookie、建置失敗保留原 5173 服務與 non-frontend PIDs、部署包零 `.env*` 與秘密洩漏。

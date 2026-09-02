# Global Deployment 與治理正式規格

## 1. Status

- 狀態：`approved-architecture-baseline`
- Current UI amendment：`approved-by-user-2026-09-02`
- 管理端唯一 current UI：React
- 舊 Streamlit、ngrok supervisor 與三映像 compat deployment：`removed`

本文件定義 deployment、release、runtime supervision 與 secret 邊界。它不授權任何特定 production project、host、credential、付款、schema mutation 或 provider write；外部執行仍需精確 target 與明確授權。

## 2. Deployment invariants

1. MySQL 位於 private data zone，不公開 Port 3306。
2. Public edge 只暴露必要 HTTPS endpoint；管理端預設限制於 LAN、VPN 或受控 access。
3. TLS 由受管理 edge／reverse proxy 終止，edge 到 application 的信任邊界必須明確。
4. Current 管理端只有 React artifact；不得部署或監控 Streamlit。
5. FastAPI 是唯一正式 HTTP business／integration boundary。
6. Worker 與 monitor 不持有 DB credential，只透過 authenticated Private Operations API 執行已定義 operation。
7. Production secret 不進 Git、文件、log、process argument、browser bundle 或 receipt。
8. Schema 變更必須使用 preserve-data release manifest、backup、candidate、validation、switch 與 recovery receipt。
9. Release 未通過 post-start readback 不得標示完成。
10. 部署位置變更不得改變 Domain ownership、typed API contract、transaction 或資料語意。
11. Production Private Operations caller 使用 Google-signed OIDC ID token；local shared key 不得 fallback 到 production。
12. 外部副作用只由已提交的 outbox、inbox 或 durable job 執行。

## 3. Logical topology

```text
External Platform / React Admin
               │ HTTPS
        Managed Edge / VPN
               │
     ┌─────────┴─────────┐
     │ Application Zone  │
     │ FastAPI + Workers │
     │ React artifact    │
     └─────────┬─────────┘
               │ private authenticated DB connection
     ┌─────────┴─────────┐
     │ Data / Archive    │
     │ MySQL / NAS /     │
     │ Backup            │
     └───────────────────┘
```

### 3.1 Public edge

允許：

- LINE webhook；
- LIFF callback 與必要 public read endpoint；
- 最小非敏感 health endpoint；
- 經核准的 React 管理端 HTTPS origin。

禁止：

- 公開 MySQL；
- 未驗證的 administrator mutation；
- debug、dev tunnel inspection、raw backup 或 archive；
- 把本機 bypass、shared key 或 temporary origin 當 production contract。

Edge 應提供 TLS、request size limit、timeout、rate limit、signature validation 與 correlation identity。

### 3.2 Application zone

- FastAPI：HTTP Query／Preview／Apply、Webhook 與 Private Operations owner。
- React artifact：靜態 Presentation Adapter，只透過 typed API 讀寫。
- Worker：執行 committed outbox、LINE task、durable job、inbox 與 bounded maintenance operation。
- Monitor：觀測 API、React、public edge 與 LIFF transport，再把 typed observation 寫回 Private Operations API。
- Migration runner：只在 maintenance window、專用 principal 與明確 target 下執行。

FastAPI lifespan 不得內嵌啟動 background worker。每個 process 可獨立 restart；worker failure 不得被 API health 200 掩蓋。

### 3.3 Data and archive zone

- Runtime production DB credential 只提供給 FastAPI application composition 與獲准 migration runner。
- React、worker、monitor 與 browser 不取得 DB credential。
- Controlled file、NAS、XLSX archive、evidence archive 與 DB backup 保存 digest 及必要 retention metadata。
- Backup 必須通過 restore rehearsal；檔案存在不等於可復原。
- Public metadata 不暴露 host path、UNC path、credential 或 private network detail。

## 4. React deployment

Current source 位於 `ui_react/`。Local development 由 Vite 提供 `/admin/`，並以 relative `/api` proxy 呼叫 FastAPI。

Production artifact 必須：

- 有 immutable artifact identity 與 digest；
- manifest 列出全部檔案及 digest；
- `index.html` 含 current React root marker；
- API compatibility revision 已被 current registry 接受；
- 不含 `ui/`、`.streamlit/`、Streamlit dependency 或 rollback deep link；
- health readback 能證明 active artifact identity。

Current 與 previous React artifact 可供 React artifact rollback；這不等於保留第二套 UI framework。

## 5. Standard local runtime

標準本機 topology：

1. FastAPI `127.0.0.1:8000`
2. React/Vite `127.0.0.1:5173/admin/`
3. runtime monitor
4. durable job worker
5. incident worker
6. 依 current configuration 啟用的 LINE／knowledge workers

`scripts/launchers/start_local_development.bat` 與 `.sh` 不得啟動 Streamlit、查詢 8501 或引用 `ui/app.py`。

`--dry-run` 只檢查 current dependency；`--smoke-test` 只建立 owned FastAPI＋React process，執行 GET-only readiness 後清理。

## 6. Release orchestration

最低狀態流：

```text
prepared
→ preflight_passed
→ execution_approved
→ backup_verified
→ candidate_validated
→ release_approved
→ switched
→ restart_verified
→ released

任一步驟 → failed
switched 後失敗 → recovery_required → recovered | escalated
```

Release manifest 至少包含：

- release version、Git ref 與 artifact digest；
- schema release identity 與 digest；
- source／candidate database identity；
- backup／restore evidence；
- operator、maintenance window、correlation identity；
- required secret 名稱，不含值；
- execution approval 與 release approval；
- health、smoke 與 rollback command contract。

Preflight fail closed 檢查：

- environment 與 target identity；
- secret、DB principal、schema drift 與 pending migration；
- backup target 與 restore tool；
- FastAPI、React artifact、worker 與 schema compatibility；
- uncommitted／unversioned artifact；
- approval scope、digest 與有效期。

Switch 必須原子並留下 before／after readback。Rollback 只切回已驗證 immutable identity；不得原地修補正式 artifact 或 source DB。

## 7. Runtime supervision and observability

必須分別觀測：

- FastAPI readiness／liveness；
- React `/admin/` readiness 與 active artifact identity；
- Worker heartbeat、queue lag、retry 與 dead letter；
- durable inbox oldest pending；
- MySQL connectivity、transaction latency 與 pool saturation；
- public edge、TLS、signature failure；
- controlled storage availability、capacity、digest mismatch 與 orphan；
- backup age 與 restore rehearsal age。

Monitor 只觀測它真正可見的 transport。MySQL、Redis、queue 與 storage readiness 由持有該 runtime configuration 的 FastAPI composition 提供，不由外部 monitor 猜測 localhost 或 mount path。

Private Operations client 只依 typed `retryable` 決定重試；transient retry 有上限、backoff 與 jitter。認證、schema、configuration 或 contract failure 不得無限重試。

Logs 必須含 correlation identity、service、release version、operation 與 typed error code；不得記錄 token、internal key、銀行帳號、webhook secret 或完整個資 payload。

## 8. Human approval boundary

下列操作各自需要精確授權，不互相推定：

- production deployment；
- schema／data migration；
- backup restore 或 target switch；
- provider publication；
- credential 建立、連接或 rotation；
- 付費資源建立或變更；
- destructive cleanup。

Repository 內的計畫、rehearsal、dry run 或測試通過，不構成上述外部操作授權。

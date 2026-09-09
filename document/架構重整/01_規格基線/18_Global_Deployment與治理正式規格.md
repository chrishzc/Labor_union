# Global Deployment 與治理正式規格

## 1. Status

- 狀態：`approved-architecture-baseline`
- Current UI amendment：`approved-by-user-2026-09-02`
- Operational retention amendment：`approved-by-user-2026-09-09`
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
13. 技術 log、技術紀錄與營運觀測資料以正向 allowlist 管理，最長保留 30 天；會員、訂單、排班、款項、合約、客服案件、正式業務事件、投遞證據、稽核證據、migration／release／backup 證據與受控業務檔案不得因本政策刪除。

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

### 7.1 Operational retention 與容量治理

本節由 Global `runtime-governance / operational-retention` 擁有。以下 requirement ID 為本政策的唯一 current 語意；各資料 owner 只能登記其資料是否符合，不得自行放寬 denylist。

- `RET-001 — 分類登記`：所有可清理來源必須先登記於 versioned retention registry，包含 owner、實體 store、terminal／age 欄位、依賴刪除順序、30 天到期規則、容量估算方式與直接驗證。未登記或無法證明為純技術／營運觀測的來源一律不可刪除。
- `RET-002 — 30 天上限`：allowlist 來源以 UTC terminal time 為主、無 terminal lifecycle 時才以 UTC creation time 為準；資料到第 30 天即進入到期候選，清理 worker 必須以 bounded batch 持續回收。尚在合法 lease／active runtime 使用中的物件先走該來源已定義的 terminal／rotation／reconciliation，再進候選，不得以 active 標記無限延長歷史紀錄。
- `RET-003 — 容量壓力`：每個部署 target 必須明確設定 DB 與受管 log／技術 artifact root 的 `high-water`、`low-water`，且 `0 < low-water < high-water`。超過 high-water 時，系統按 oldest-first 提早回收 allowlist 候選直到 low-water；若候選不足，回報 typed `retention_capacity_unrelieved` 並告警，絕不擴大到 denylist。
- `RET-004 — 初始 allowlist`：至少涵蓋 (a) application／worker 的 active 與 rotated log segments；(b) Knowledge 實際問句觀測 graph：terminal `knowledge_answer_requests`、其 `knowledge_jobs`、`knowledge_answer_receipts` 與 `knowledge_answer_sources`；(c) terminal Knowledge index-build job、failed／stale 或已被較新 READY version 取代的 index metadata 與 vector artifact。active READY index、Knowledge catalog／item／version／publication receipt 不屬歷史觀測，不可清理。
- `RET-005 — 永久 denylist`：member／client／staff、order／schedule／case、finance／payment／payroll、contract、customer-service ticket lifecycle、業務 event／receipt、inbox／outbox／delivery task、admin／security audit 及 archive、controlled-file object／business artifact／cleanup or reconciliation evidence、schema migration、release、backup／restore 與 incident evidence均不受 30 天政策影響。加入 allowlist 前若碰到其中任何類型，必須回 owning spec 取得新的人工 Authority。
- `RET-006 — 自動清理`：獨立 maintenance worker 每日至少執行一次到期清理，並在容量觀測超過 high-water 時觸發壓力清理。每次按來源分批、具單一 outer commit owner 與 idempotent command identity；DB 與 filesystem 無法同 transaction 時必須留下可重跑 reconciliation state，不得把部分完成顯示為成功。
- `RET-007 — 檔案輪替`：active log segment 達到來源設定的單檔上限時先 rotate，再按 age／capacity 政策刪除 closed segments；只可操作 registry 中的 canonicalized owned roots，symlink／junction、root escape、未完成寫入與受控業務檔案一律 fail closed。
- `RET-008 — 管理頁`：React 管理端新增獨立入口「稽核與系統 → 儲存空間管理」，顯示各 registered source 的 current logical usage、oldest eligible time、30 天內／已到期筆數或檔案數、estimated reclaimable bytes、last run、last outcome 與 capacity status。DB 刪除只可宣稱釋放可重用 logical space，不得宣稱已縮小實體 DB 檔案。
- `RET-009 — Manual Preview／Apply`：具 storage-maintenance permission 的管理員可選來源與清理原因取得 zero-write Preview，再以明確確認 Apply；current release 將此 permission 收斂為 root 管理員。Preview 必須凍結 policy revision、source、cutoff、candidate upper bounds、file identity／digest 與估算量；因跨 DB table 與 filesystem 且沒有單一 aggregate version，Apply 使用該 multi-root preview fingerprint，任何候選狀態、範圍或 policy 改變皆回 typed stale conflict，不得擴刪新候選或 blind retry。
- `RET-010 — Readback 與證據`：automatic／manual run 都保留非敏感 aggregate audit evidence：actor／worker、mode、policy revision、source、cutoff、candidate／deleted／failed counts、logical bytes、started／finished time、typed outcome 與 correlation identity；不得保存 raw question、answer、log payload、host path 或 secret。這份 evidence 屬正式稽核證據，不受 30 天清理。

Retention registry 的初始盤點必須涵蓋 current DB schemas、configured log roots 與 Knowledge vector root；盤點中未分類的候選來源視為 `blocked-unclassified`，頁面可顯示但 cleanup 不得觸碰。30 天政策不代表資料庫實體檔案會立即縮小；physical compaction／table rebuild 不在本規格範圍，若需要必須另取得 migration／maintenance Authority。

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

本次人工指示已核准產品層的 30 天到期／容量壓力清理語意及管理端入口；它不等同於對任一 production target 啟用 worker、執行一次手動 Apply、進行 schema mutation 或 physical DB compaction 的執行授權。

## 9. Operational retention 驗收

- `RET-AC-01`：registry allowlist 的 terminal／closed observation 到第 30 天可由 automatic worker 分批刪除；第 29 天資料與 active runtime state 不會被錯刪。
- `RET-AC-02`：以測試設定的 high／low water 模擬容量壓力時，只會 oldest-first 回收 allowlist 並降至 low-water；候選不足時得到 `retention_capacity_unrelieved`，denylist 零變更。
- `RET-AC-03`：Knowledge 回饋清理依 source → receipt → terminal job → request 的依賴順序完成；published catalog、current READY index、LINE delivery／客服案件證據保持不變。
- `RET-AC-04`：log 達單檔上限先 rotate；path escape、active writer、未登記 root 與 business artifact 均 fail closed。
- `RET-AC-05`：「儲存空間管理」頁的 usage、eligible、estimated reclaimable、last outcome 與 typed failure 均由正式 Query readback；Preview 零寫入，Apply 只刪 preview 凍結集合，stale fingerprint 不產生刪除。
- `RET-AC-06`：自動與手動的部分失敗可 reconciliation／重跑且不重複刪除，UI 不顯示假成功；aggregate cleanup evidence 不含 raw payload 或敏感資料且不受 30 天政策清理。
- `RET-AC-07`：對永久 denylist 做完整 before／after fixture 比對，會員、訂單、排班、財務、合約、客服、business event／receipt、inbox／outbox、admin audit、controlled files、migration／release／backup／incident evidence 全部零變更。

```yaml
convergence:
  status: READY
  blockers: []
  canonical_revision: 18-retention-amendment-2026-09-09
  authority: user-2026-09-09-log-technical-operational-only
```

## 10. Living Work Package：`WP-GOV-RETENTION-001`

### 10.1 Entry baseline 與邊界

- Objective：落實 `RET-001..010` 與 `RET-AC-01..07`，提供 30 天／容量壓力自動清理及「稽核與系統 → 儲存空間管理」Manual Preview／Apply。
- Authority digest：使用者 2026-09-09 指示「30 天只適用於 log、技術與營運紀錄」，並要求容量過大自動清理及手動入口；canonical revision 為 `18-retention-amendment-2026-09-09`。
- In scope：Global runtime governance、Knowledge observation adapter、owned log／Knowledge artifact adapter、typed Query／Preview／Apply API、React page、bounded worker、aggregate audit readback 與直接測試。
- Exclusions：`RET-005` 全部 denylist、physical DB compaction、production enablement、既有 audit archive policy、未經授權 schema／migration、部署與外部 provider effect。
- Effect ceiling：repository code／test／map 修改及測試 fixture 內的 eligible deletion；production／shared DB 或真實檔案刪除均需另行精確 target Authority。
- Safe stop：registry 有未分類來源、任一候選跨入 denylist、preview stale、root canonicalization 失敗、active writer／lease 未能安全 terminal、reconciliation 未完成或容量仍無法降至 low-water 時停止該來源並回 typed outcome，不擴大刪除。

### 10.2 Ordered execution

1. `S1 — Registry 與 owner adapters`：建立 versioned positive registry，完成 current schema／configured roots 盤點；每個來源提供 eligibility、age、dependency order、usage／reclaim estimate 與 denylist oracle。未分類來源只讀顯示。
2. `S2 — Retention application boundary`：在 Global runtime-governance 實作 Query、zero-write Preview、fingerprinted Apply、自動 age／pressure command、bounded per-source UoW、typed stale／capacity／partial outcomes與 reconciliation；Knowledge 與 log／artifact 只作 typed adapter，不各自成為 cleanup owner。
3. `S3 — Runtime scheduling 與檔案安全`：接入獨立 maintenance worker 的 daily／high-water trigger、log rotation、canonical owned-root guard、idempotency、bounded retry 與 last-run aggregate evidence；不得在 FastAPI lifespan 內嵌 worker。
4. `S4 — API 與 React surface`：提供 authenticated typed Query／Preview／Apply／run-readback API，並新增「稽核與系統 → 儲存空間管理」頁；操作必須呈現 estimated logical reclaim、二次確認、stale／partial／unrelieved failure 及 reconciliation 狀態。
5. `S5 — Focused closure`：驗證 29／30-day boundary、pressure oldest-first、Knowledge dependency order、Preview zero-write／stale zero-delete、path escape／active writer、partial reconciliation、denylist before／after 零變更、API auth／typed mapping、React navigation／empty／failure states；再執行受影響 build、`git diff --check` 與 architecture closure。

### 10.3 Permission atoms 與 handoff

- `S1..S5` 的 repository 修改與 isolated fixture test 由 current feature Authority 涵蓋。
- 若實作證明需要新 table／index／column，先停在 additive migration proposal；依 `10_Global_保留資料Migration與Cutover_Subsystem.md` 另取 schema／target Authority，不得在本 package 推定。
- production／shared DB enablement、production log root 綁定、首次 automatic run 與每次 manual Apply 都是獨立 destructive execution permission；程式完成不代表已授權執行。
- Handoff evidence 只保留 registry revision、direct test oracles、typed failure/readback 與必要 aggregate result；raw DB rows、問題／回答、log payload、private path 與 secret 不得進 package 或 receipt。

### 10.4 Bidirectional coverage

| Requirement／Acceptance | Source／Authority | Step | Direct oracle |
|---|---|---|---|
| `RET-001`, `RET-004`, `RET-005`, `RET-AC-07` | user scope + current schema／spec denylist | `S1`, `S5` | registry completeness + denylist fixture before／after |
| `RET-002`, `RET-006`, `RET-AC-01`, `RET-AC-03` | 30-day Authority + Knowledge FK graph | `S2`, `S3`, `S5` | 29／30-day boundary + FK-order integration |
| `RET-003`, `RET-AC-02` | user capacity requirement; target-configured limits | `S2`, `S3`, `S5` | high／low-water simulation + unrelieved typed outcome |
| `RET-007`, `RET-AC-04` | owned-root／active-writer safety invariant | `S3`, `S5` | rotate + traversal／writer negative tests |
| `RET-008`, `RET-009`, `RET-AC-05` | user manual page requirement | `S2`, `S4`, `S5` | API/component tests proving Query readback, zero-write Preview and stale zero-delete |
| `RET-010`, `RET-AC-06` | audit/privacy invariant | `S2`, `S3`, `S4`, `S5` | partial reconciliation/idempotency + evidence redaction oracle |

```yaml
package:
  status: PACKAGE_READY
  id: WP-GOV-RETENTION-001
  specification_revision: 18-retention-amendment-2026-09-09
  requirements: [RET-001, RET-002, RET-003, RET-004, RET-005, RET-006, RET-007, RET-008, RET-009, RET-010]
  acceptance: [RET-AC-01, RET-AC-02, RET-AC-03, RET-AC-04, RET-AC-05, RET-AC-06, RET-AC-07]
  execution_authority: repository-only
```

### 10.5 Repository execution status（2026-09-09）

- `PASS — repository implementation`：`S1..S4` 已具 positive registry、typed Query／Preview／Apply、
  Knowledge／managed-log adapters、daily opt-in worker 與「稽核與系統 → 儲存空間管理」介面。
- `PASS — focused verification`：`S5` 的 29／30-day、oldest-first／capacity-unrelieved、stale
  zero-delete、idempotency／reconciliation、root-auth API、React readback／confirmation 與視覺驗證通過。
- `NOT_RUN — target operations`：未啟用 production worker、未綁定 production log roots、未執行
  shared／production DB 或檔案 Apply、未進行 physical compaction；仍須依 §8 取得精確 target Authority。

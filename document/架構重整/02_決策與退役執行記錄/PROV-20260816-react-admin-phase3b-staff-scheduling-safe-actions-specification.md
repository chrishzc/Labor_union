---
doc_type: implementation-specification
declared_status: approved
identity: PROV-20260816-react-admin-phase3b-staff-scheduling-safe-actions
date: 2026-08-16
owner: Scheduling Staff Matching Profile / Staff Lifecycle / Assignments Scheduling / React Integration
domain: Scheduling / Staff
subsystem: Preferences / Availability / Lifecycle / Leave Substitution / React Presentation
authority: human-approved-exact-package-2026-08-16
---

# React 管理端 Phase 3B：Staff／Scheduling 安全 action 規格

## 0. 目的與切片

保留 `StaffPage`、`SchedulingPage` 的既有版面，只啟用四個已有正式 owner、typed Query／Preview／Apply
與後端測試的 bounded flows：

1. 月嫂 matching preference profile Query／Preview／Apply；
2. 不可服務期間 Query／Create Preview／Apply／Cancel Preview／Apply；
3. Staff retirement／reactivation Query／Preview／Apply；
4. 服務中請假代班／順延 Query／Preview／Apply／receipt。

本波不得把四條 workflow 合成一個 generic staff client、generic save endpoint 或單一「成功」狀態。

## 1. Business scenarios 與 owner

| Flow | Operator scenario | Root owner | 不得推導 |
|---|---|---|---|
| Preferences | 維護可承接天數、每日服務時數及已核准 definition values | Scheduling Staff Matching Profile | React 不依中文名稱決定比較規則 |
| Availability | 建立／取消 long_leave 或 paused_service | Scheduling | 不可服務期間不等於 assignment leave/buffer |
| Lifecycle | 退役或復職月嫂 | Staff lifecycle | 不改 staff master，不自動取消 assignment／恢復舊媒合 |
| Leave/Substitution | 對既有 assignment 多日請假作代班或順延 | Assignments/Scheduling | 不由 request/local calendar 推算正式 outcome |

## 2. 不變量

1. Query 唯讀、Preview 零寫入、Apply fresh-read、lock、versions、fingerprint、idempotency、單一 UoW。
2. 每條 flow 使用自己的 bounded client；共用 auth 只能由既有 transport composition 注入。
3. preference Apply 不寫 Orders、assignment 或 availability。
4. availability create 先鎖 staff occupancy mutex，重驗 assignment、waiting lock、buffer；overlap fail closed。
5. availability cancel 只追加 event，不刪除／改寫 root period。
6. retirement 保留 Staff、BeClass、Orders、Payroll、歷史配對與已確認未來 assignment；新 matching 固定排除。
7. reactivation 不恢復過期 availability、偏好、邀請或候選。
8. leave/substitution 是一個 batch fingerprint 與 transaction；header、daily outcomes、assignment/schedule、
   Orders/Payroll/Client Finance impacts、outbox、receipt 原子提交。
9. substitute 只換同日 owner；extension 才移動服務日期；服務量守恆由 server candidate證明。
10. React 不計算完工日、七日 buffer、薪資、工時、衝突或 eligibility。

## 3. HTTP allowlist

### 3.1 Preferences bounded client

- `GET /api/v1/scheduling/staff-matching-preferences/definitions`
- `GET /api/v1/scheduling/staff-matching-preferences/staff/{staff_id}`
- `POST /api/v1/scheduling/staff-matching-preferences/staff/{staff_id}/preview`
- `POST /api/v1/scheduling/staff-matching-preferences/staff/{staff_id}/apply`

Definition create/update endpoints不屬目前 visible Staff UI，本波禁止。

### 3.2 Availability bounded client

- `GET /api/v1/scheduling/staff/{staff_id}/availability-blocks`
- `POST /api/v1/scheduling/staff/{staff_id}/availability-blocks/preview`
- `POST /api/v1/scheduling/staff/{staff_id}/availability-blocks/apply`

Create/cancel intent 必須由 Pydantic discriminator／enum 決定；不得用 DELETE 或 local array splice。

### 3.3 Staff lifecycle bounded client

- `GET /api/v1/staff/{staff_id}/lifecycle`
- `POST /api/v1/staff/{staff_id}/{retirement|reactivation}/preview`
- `POST /api/v1/staff/{staff_id}/{retirement|reactivation}/apply`

action 必須來自 allowlist；不得拼接其他 path。UI 是否顯示退役或復職只依 server lifecycle view。

### 3.4 Leave/Substitution bounded client

- `GET /api/v1/orders/{case_no}/leave-substitution/assignments`
- `POST /api/v1/orders/{case_no}/leave-substitution/preview`
- `POST /api/v1/orders/{case_no}/leave-substitution/apply`

精確 GET path、body、header 與 response 由 G1 live route/Pydantic matrix 凍結；若 route 與此描述不同，
以正式 route identity更新 proposed 文件後重新人工確認，不得由 writer猜 path。

## 4. Presentation state machine

四條 flow 各自使用：

```text
idle → query_loading → query_ready → editing → preview_loading → preview_ready
     → apply_pending → receipt_received → requery_loading → observed
                         └ timeout/503 → outcome_unknown → same-key retry
```

- edit 後立即作廢舊 preview/fingerprint。
- stale/version conflict後只允許 re-query＋新 Preview。
- apply_pending/outcome_unknown期間禁止 close、切換 staff/case、重送或更改欄位。
- receipt received 但 re-query失敗顯示 `observation_failed`，不得改稱 Apply 失敗。
- 每個新 intent 產生新 idempotency key；只有 outcome_unknown retry沿用原 key/payload。
- 202/durable job若 live route回 job identity，使用既有 Jobs query；不得前端輪詢不存在 endpoint或當成完成。

## 5. UI preservation 與 stable controls

至少固定：

- `staff.page`、`staff.tab.roster`、`staff.tab.preferences`、`staff.tab.unavailability`
- `staff.preferences.preview`、`staff.preferences.apply`
- `staff.availability.create.preview`、`staff.availability.create.apply`
- `staff.availability.cancel.preview`、`staff.availability.cancel.apply`
- `staff.lifecycle.retirement.preview`、`staff.lifecycle.retirement.apply`
- `staff.lifecycle.reactivation.preview`、`staff.lifecycle.reactivation.apply`
- `scheduling.page`、`scheduling.tab.leave-substitution`
- `scheduling.leave-substitution.preview`、`scheduling.leave-substitution.apply`

現行 Staff Drawer save、新增 staff、附件 upload、Scheduling holiday/custom-rest、quick lock、ghost projection
Apply、leave inbox acceptance/reject 全部 locked。不得刪除既有 tab／Drawer／cards或以 hidden CSS逃避驗收。

## 6. Contract and safety requirements

- 每個 endpoint逐欄凍結 Pydantic → Zod mapping、privacy與error/status matrix。
- Zod必須`.strict()`；server required不得optional/default；nullable與optional精確對齊。
- 禁止`z.any`、`z.unknown`、`z.record`、`.passthrough()`、`.catch()`、`.default()`、`.coerce()`、
  `.preprocess()`、`.transform()`及`as any`／`unknown as`。
- 每個DTO至少測missing required、wrong primitive、unknown key、null violation、enum drift、invalid range。
- 每次request即時取得current memory session token；不得module-load快取或寫入browser storage。
- 每個 Apply 測 Preview zero-write、same-key replay、same-key/different-payload conflict、stale、rollback。
- Leave/Substitution 額外測 batch corruption、cross-domain version conflict、full service conservation、outbox原子性。
- Availability 額外測 overlap、waiting lock、buffer、occupancy conflict與append-only cancel。
- Retirement額外測 matching consumer guards及已確認未來 assignment preservation。
- component tests以兩組不同 server sentinel證明 DOM 隨 payload變化，禁止把 fixture literal搬進 production。

## 7. Out of scope

- Staff master create/edit、bank／certificate mutation、attachment upload；
- preference definition management UI；
- holiday/raw dict routes、custom rest dates、retired single-day CRUD；
- quick waiting lock、ghost projection Apply、assignment plan、new staff scheduling；
- LINE leave intake acceptance/rejection；
- DB schema/migration/seed/backfill、真人 LINE、Streamlit cutover；
- App/Auth/shared transport/package/lockfile及其他頁面。

## 8. Completion semantics

四條 flow 各自有 independent gate status。任一 flow缺 typed contract、controlled data或真 browser證據時，
該 flow固定 blocked；不得以另外三條完成宣稱整包 victory。整包只有 G0–G8 全 PASS 才能
`completed-local-validated`。

---
doc_type: work-package
declared_status: completed
date: 2026-08-14
approved_at: 2026-08-15
owner: Staff / Matching / Scheduling
priority: P1
---

# 91 Staff 退役 Work Package

## 裁決狀態

2026-08-15 人工確認採用本文件全部建議裁決。本文件現為 `declared_status: approved`；後續實作仍須
先完成 live inventory、整體架構確認、exact write set 與適用的資料庫變更執行門，不因核准而自動取得
production data、deployment、cutover 或外部通知授權。

## 已採用裁決

### 狀態與生效時間

- Staff 採 `active -> retired` 的顯式狀態轉移；退役不是刪除、匿名化或歷史資料搬移。
- command 必須帶 `effective_at`、typed reason、actor、expected version 與 idempotency key；不得以
  自由文字或直接改欄位旁路狀態機。
- 生效後停止建立新的 Matching candidate、邀請、媒合或新 assignment；既有歷史查詢仍可讀。

### 未來工作切割點

- 已確認的未來服務／assignment 不因 Staff 退役自動取消；需要變更時，沿用 Scheduling owner 的
  替代、取消或改派 command，保留原交易與通知邊界。
- 尚未確認的 candidate、offer、邀請或暫存媒合在生效時失去資格，不得被後續 Apply 採用，並以
  deterministic reason 留下 receipt。
- 退役不得改寫既有 Orders、Payroll、BeClass、Staff relation 或其他歷史根事實。

### Consumer 行為

- Matching：所有新候選與重算排除已於 business time 生效的 retired Staff。
- Scheduling／Orders：保留既有已確認義務；不得把退役當成隱式取消命令。
- Payroll、reporting、audit 與 history：維持可查詢及既有識別關係，不得因退役失聯。
- LINE／UI：不得再提供建立新 Matching 的操作；歷史與既有義務入口依各 bounded owner 權限顯示。

### 交易、重播與外部副作用

- Staff owner 是狀態根事實與 command owner；Apply 必須 fresh-read、鎖定並驗證 version，整個
  mutation 只有一個 outer Unit of Work 與 commit owner。
- 成功後保存 immutable retirement event／receipt；跨 Domain 通知或清除未確認 offer 必須由
  committed outbox／durable job 處理，不得在 transaction 內直接執行外部副作用。
- 相同 idempotency key 與相同 payload replay 原結果；不同 payload、stale version 或已退役狀態
  回傳 typed conflict／no-op，不得重複發送副作用。

### 復職

- 允許獨立的 typed `ReactivateStaff` 管理命令，不以修改退役紀錄或重跑退役命令復職。
- 復職不自動恢復已過期 availability、偏好、邀請或 candidate；重新通過當下資格與必要資料驗證後，
  才可重新進入 Matching。

### 通知與 migration

- 第一階段不新增 Staff 或 Client 外部通知；若要通知，另立 external side-effect contract、模板、
  recipient、retry 與 partial-failure 裁決。
- 既有資料若需要 backfill retirement state，必須先完成 live inventory，並依 schema-only、
  system-seed、business-row-backfill、destructive 四類盤點與資料庫變更執行門；不得把 row migration
  藏在 schema part。

## 人工裁決結果（2026-08-15）

- 採用「已確認未來服務保留、未確認媒合失效」的切割點。
- 採用獨立 `ReactivateStaff` command，復職不恢復過期媒合資料。
- 第一階段不新增外部通知。
- typed retirement reason 的 canonical 枚舉與可見權限由 live consumer／資料欄位盤點後定稿；這是
  實作細化，不重新開啟上述業務政策。

## Live inventory（2026-08-15）

- `staff.status` 已存在，型別為 `VARCHAR(20)`，目前 fresh schema 註解只描述 `active/inactive`；沒有
  retirement version、effective time、typed reason、event 或 idempotent receipt，且取消與檔期功能共用此語意。
- `infrastructure/mysql/matching_recommendation_repository.py` 已以 `status='active'` 篩選候選；本包改以獨立
  lifecycle state 補足 retired 排除，不讓既有 status consumer 語意漂移。
- `infrastructure/mysql/segmented_availability_repository.py` 與取消案月嫂查詢同樣只列 active Staff。
- `AssignmentPlanWorkflow` 是可直接建立正式 assignment 的另一入口，且採整代重建；若全面拒絕 retired
  Staff，會錯誤阻擋「保留既有已確認服務」。因此 Preview／Apply 必須區分 exact preservation 與新增／擴張。
- 現況沒有 Staff retirement Domain aggregate、typed Query／Preview／Apply、event、receipt、API 或測試。
- 已寄出的 Matching invitation／schedule confirmation interaction 目前只驗證 plan、token 與 recipient，
  未 fresh-check Staff eligibility；退役後仍可能寫入 response／confirmation event，必須納入本包。
- `customer_service_repository` 目前只排除 legacy `inactive`。本包不把 Staff 自助查詢等同 Matching；只要
  該入口沒有建立新 Matching／assignment 的能力，第一階段保留歷史與既有義務查詢。

## 已確認架構的待施工細化

### Global

- Query 唯讀；Preview 零寫入；Apply 使用 actor、reason code、effective time、expected version、preview
  fingerprint、idempotency key 與 correlation id。
- 每個 transition 只有一個 MySQL outer Unit of Work。lifecycle state projection、immutable event、command
  claim 與 receipt 同 transaction；repository 不 hidden commit。
- 第一階段沒有外部通知，也不主動修改既有 candidate／offer row，因此不新增 outbox。所有新 Matching
  與 assignment Apply 由 fresh-read eligibility fail closed；未來若新增通知或批次清除，另立 side-effect WP。

### Staff Domain

- current root projection 使用新增 `staff_lifecycle_states`；合法 current transition 僅 `active -> retired`
  與 `retired -> active`。既有 `staff.status` 不變，legacy `inactive` 仍由既有 consumers 排除，且不自動
  轉義為 retired。
- lifecycle state row 的 aggregate version 從 0 起；immutable event 保存每次 resulting version。既有 Staff
  沒有 lifecycle row 時視為 lifecycle active，無 business-row backfill。
- 第一階段只接受 `effective_at <= BusinessClock.now()` 的立即生效命令；未來生效固定回
  `staff_retirement_future_effective_at_unsupported`，避免在沒有 durable scheduler 時提早或漏掉排除。
- canonical reason codes 第一版限定 `left_union | no_longer_available | qualification_changed | returned_to_service`；
  retirement 不接受 `returned_to_service`，reactivation 只接受 `returned_to_service`。
- exact replay 回原 receipt；同 key 不同 payload 回 `idempotency_mismatch`；stale version 回 `stale_version`；
  對已在目標狀態的新 key 回 typed no-op receipt，不重複 event。

### Staff Retirement Subsystem

- `QueryStaffLifecycle(staff_id)` 回 current status、version、latest effective time 與 masked reason code。
- `PreviewRetireStaff`／`PreviewReactivateStaff` 回 before、after、version、effective time、保留的 confirmed
  assignment count、失效的 unconfirmed matching count、blockers 與 preview fingerprint，且零寫入。
- `ApplyRetireStaff`／`ApplyReactivateStaff` 在 outer UoW 內鎖定 Staff row 與 command claim，fresh-read latest
  event／相關計數，重建 Preview，驗證 version／fingerprint 後原子保存 projection、event 與 receipt。

### Scheduling consumers

- Matching candidate Query、segmented availability、notification dispatch、LINE response 與 schedule confirmation
  同時消費 legacy `staff.status='active'` 與 lifecycle active，且不自行修改 Staff root。
- Assignment Plan Preview 讀取 intent 涉及 Staff 的 current status；retired Staff 的 proposed segment 必須
  與一筆 current effective assignment 在 staff、區間、official service dates 完全相同。
- Assignment Plan Apply 於現有 deterministic lock sequence 中鎖定相同 Staff rows，exact replay 先返回；
  fresh Apply 再做相同 eligibility 判定。新增、延長、移動或增加 retired Staff service day 回
  `staff_retired_new_assignment_forbidden`，且零 assignment／generation mutation。

### API／Module

- `GET /api/v1/staff/{staff_id}/lifecycle`
- `POST /api/v1/staff/{staff_id}/retirement/preview`
- `POST /api/v1/staff/{staff_id}/retirement/apply`
- `POST /api/v1/staff/{staff_id}/reactivation/preview`
- `POST /api/v1/staff/{staff_id}/reactivation/apply`
- 所有 endpoint 僅供 authenticated admin；Pydantic schema 驗證 typed request／result，stable errors 映射
  404／409／422／500，UI 不直接寫 DB。本包不新增 Streamlit 畫面，先交付正式 API 契約。

## 核准最大 write set（施工前基線）

- `domains/staff/__init__.py`
- `domains/staff/retirement.py`
- `subsystems/staff/__init__.py`
- `subsystems/staff/retirement_workflow.py`
- `infrastructure/mysql/staff_retirement_repository.py`
- `infrastructure/mysql/assignment_plan_repository.py`
- `infrastructure/mysql/matching_notification_repository.py`
- `infrastructure/mysql/matching_schedule_confirmation_repository.py`
- `infrastructure/mysql/segmented_availability_repository.py`
- `subsystems/scheduling/assignment_plan_workflow.py`
- `api/dependencies/staff_retirement.py`
- `api/schemas/staff_retirement.py`
- `api/routes/staff_retirement.py`
- `api/main.py`
- `db/schema_parts/1000_staff_retirement.sql`
- `db/schema.sql`
- `db/schema_assembly/labor_union_fresh_schema_v1.json`
- `db/cutover_releases/labor_union_validation_schema_v1.json`
- `db/releases/labor_union_validation_schema_v1.sql`
- `db/migration_releases/labor_union_2026_08_15_staff_retirement_v1.json`
- `db/migration_releases/labor_union_2026_08_15_staff_retirement_v1.descriptors.json`
- `scripts/migrate_preserved_database_additive_schema.py`
- `tests/test_staff_retirement.py`
- `tests/test_staff_retirement_routes.py`
- `tests/test_assignment_plan_workflow.py`
- `tests/test_assignment_plan_durable_mysql_e2e.py`
- `tests/test_matching_recommendation_query.py`
- `tests/test_matching_notification_repository.py`
- `tests/test_matching_schedule_confirmation.py`
- `tests/test_segmented_availability_query_port.py`
- `tests/test_schema_assembly.py`
- `tests/test_staff_retirement_migration_release.py`
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- `document/架構重整/01_規格基線/24_Staff_Matching_Preferences與不可服務期間正式規格.md`
- `document/架構重整/02_決策與退役執行記錄/91_Staff_Retirement_Work_Package.md`
- `document/架構重整/02_決策與退役執行記錄/README.md`
- `document/架構重整/03_追蹤清單與證據/README.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260815-staff-retirement-closeout.md`

現有 release chain 以 `999_v_order_details_view.sql` 結束，依 runner ordinal 排序規則，本包 canonical
successor 固定為 `1000_staff_retirement.sql`；現有 release 名稱含 `wp91_hcm_partial_formal_case`，屬
migration release namespace 的舊 identity，不得改名、覆寫或誤認為本 Work Package 的 retirement release。

2026-08-15 late-bind inventory 補充：fresh bootstrap catalog 會機械檢查所有 schema parts 與
`db/schema.sql` digest，preserve-data runner 則只解析固定 `DEFAULT_RELEASE_MANIFESTS`。因此上述 schema
assembly catalog、runner release chain 與兩份 focused metadata tests 是不可省略的 shared hot spots；
它們不改變業務政策，但在人工確認 write-set expansion 前不得施工。

## Schema／migration change inventory

| 類型 | source artifact | target／資料效果 | replay／rollback／unresolved policy |
|---|---|---|---|
| schema-only | `1000_staff_retirement.sql` | 新增 lifecycle state、append-only events 與 idempotent receipts；不改 `staff` parent columns | exact object replay；code rollback 保留歷史表；partial／drift fail closed |
| system-seed | none | 無 seed | not applicable |
| business-row-backfill | none | 現有 Staff 維持既有 `active/inactive`；首次 version 為 0 | 禁止隱式轉換 `inactive` |
| destructive | none | 不刪表、不刪欄、不改歷史資料 | not applicable |

## 初始 DB change gate（2026-08-15）

| gate | status | evidence／blocked reason |
|---|---|---|
| Scope gate | `PASS` | 2026-08-15 人工採用獨立 lifecycle state 修正版，包含 schema assembly catalog、runner release chain、invitation／confirmation guards 與 focused tests |
| Change inventory | `PASS` | 上表已區分 schema-only、system-seed、business-row-backfill、destructive |
| Static release gate | `PASS` | `1000_staff_retirement.sql`、fresh assembly catalog、`labor_union_2026_08_15_staff_retirement_v1.json` 與 `DEFAULT_RELEASE_MANIFESTS` 已互相引用；focused schema test 通過 |
| Descriptor gate | `PASS` | `labor_union_2026_08_15_staff_retirement_v1.descriptors.json` 列出三張 owned tables 的完整 column contract |
| Read-only plan gate | `PASS` | `.venv\Scripts\python.exe -m scripts.update_local_database` 回傳 latest `labor-union-staff-retirement-2026-08-15-v1`，唯一待套 `1000_staff_retirement.sql` |
| Engine verification gate | `PASS` | Docker `mysql_db`：preserve-data candidate `lu_test_dataset_contract_signing_v4_wp91_r2` 為 `verified`、`1000_staff_retirement.sql=exact` 且 source/candidate data evidence 相同；fresh `lu_test_wp91_fresh_r2` manifest postcheck 無錯 |
| Developer acceptance gate | `PASS` | 已授權執行 `.venv\\Scripts\\python.exe -m scripts.update_local_database --apply --mysql-container mysql_db --candidate-database lu_test_dataset_contract_signing_v4_wp91_accept --confirm-database lu_test_dataset_contract_signing_v4`；candidate 驗證後完成來源替換，未操作 `union_db` |

總結：所有 WP91 DB change gates 均為 `PASS`。本結論僅涵蓋 developer-local acceptance，不構成 production deployment、cutover 或 production-data authorization。

## 施工與 focused evidence（2026-08-15）

- 已交付 Staff lifecycle Domain、Query／Preview／Apply workflow、MySQL repository 與管理 API；合法退役／復職原因、BusinessClock future effective time、version、preview fingerprint、global command claim、no-op receipt 與 same-key replay 均由 workflow 保護。
- 已交付 `1000_staff_retirement.sql`、fresh assembly digest、release manifest 與 owned-object descriptor；本 release 為 `schema_only`，不含 seed、backfill 或 destructive mutation。
- Matching recommendation、segmented availability、notification／interaction、schedule confirmation 皆 fresh-check lifecycle active；Assignment Plan 僅允許 retired Staff 完整保留現存有效 assignment。
- focused command：`.venv\Scripts\python.exe -m pytest tests/test_staff_retirement_workflow.py tests/test_staff_retirement_consumer_guards.py tests/test_init_db_schema_parts.py tests/test_bootstrap_disposable_mysql_schema.py -q`，結果 `24 passed`；validation manifest 與 generated release static check 亦通過。pytest cache 權限警告未影響結果。
- 完整去敏 command/result 與 DB gate 狀態見 `document/架構重整/04_已完成與上線封存/receipts/2026-08-15_wp91_staff_retirement_closeout_receipt.md`。

## 收尾與封存門

- focused Module／Subsystem／Domain／Global tests、API contract、assignment exact-preservation regression、
  fresh bootstrap 與 preserve-data candidate upgrade 全部 PASS。
- 保存 schema release identity、descriptor exactness、read-only plan、rollback、replay 與去敏 closeout receipt。
- 更新本文件為 `completed`、同步 active index 與 evidence index；只有 successor、inbound links、digest、
  restore trigger 與 archive manifest 全部完成後才移入 `04_已完成與上線封存/`。

## 已確認 business scenario

月嫂停止參與公會後，必須保留其既有 Staff、BeClass、訂單、薪資與歷史配對資料；但不再加入新的
Matching 等後續系統流程。

## 範圍

- 建立 Staff 退役能力的正式代辦與後續裁決入口。
- 實作前必須明定 state machine、既有與未來指派的處理、Matching／Scheduling／LINE 等各 consumer 的
  排除邊界、typed command、交易／outbox、replay、migration 與驗收。

## 非範圍

- 本包目前不授權 schema、API、UI、資料 mutation、既有 Staff 狀態變更或任何排班取消。
- 不預先裁決退役原因、日期、未來已確認服務、再啟用或通知行為。

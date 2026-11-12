# Module: historical-adoption

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
將受控、單一月嫂 historical order workbook 的可採納來源值套用到既有 Orders root。每次匯入重新檢查整份工作簿，檔內採納與檔外取消共用同一 outer UoW。採納保留原帳務，歷史服務完成時委派 Payroll 同步月嫂應付，匯入收據另列略過原因，並依正式方案委派 Client Finance 同步客戶補助退款。

## Implementation
- primary:
  - `domains/orders/historical_adoption.py`
  - `subsystems/orders/historical_adoption_workflow.py`
  - `subsystems/orders/historical_order_workbook.py`
  - `subsystems/orders/historical_order_workbook_import.py`
  - `subsystems/orders/historical_order_adoption_outbox_consumer.py`
  - `subsystems/orders/historical_actual_start_rebuild.py`
  - `infrastructure/mysql/historical_order_adoption_repository.py`
  - `infrastructure/mysql/historical_order_workbook_import_repository.py`
  - `infrastructure/mysql/historical_order_adoption_cancellation_decorator.py`
  - `infrastructure/mysql/historical_actual_start_date_planner.py`
- entrypoints:
  - `api/exception_handlers/historical_order_database.py` — 建連與執行期間共用 MySQL errno 去敏分類、typed HTTP 503 與安全診斷日誌。
  - `api/routes/historical_order_adoption.py`
  - `api/exception_handlers/historical_order_database.py` — 歷史工作簿連線與執行期的封閉資料庫錯誤轉譯；回傳代碼及追蹤編號，不輸出原始資料庫訊息。
  - `api/dependencies/historical_order_adoption.py`
  - `api/dependencies/historical_order_review_remediation.py`
  - `api/schemas/historical_order_adoption.py`
  - `scripts/imports/adopt_historical_orders.py` — operational use remains subject to entry-point governance.
- migrations:
  - `db/schema_parts/243_historical_order_reused_pairing_check.sql` — fresh CHECK successor，candidate／reused 均要求 staff 與 assignment，其餘不得帶 assignment。
  - `db/schema_parts/1065_historical_order_reused_pairing_check.sql` — 保留資料 CHECK successor；原紀錄、enum、FK 與 immutable guards 不變。
  - `db/migration_releases/labor_union_2026_11_03_historical_order_reused_pairing_check_v1.json` — 與 descriptor／canonical chain 綁定。
  - `db/schema_parts/1008_historical_order_adoption_noop_constraint.sql`
  - `db/schema_parts/214_historical_order_pairing_resolution_reused.sql`
  - `db/schema_parts/1027_historical_order_pairing_resolution_reused.sql` — preserve-data successor.
  - `db/migration_releases/labor_union_2026_08_27_historical_order_adoption_noop_v1.json`
  - `db/migration_releases/labor_union_2026_09_01_historical_order_pairing_resolution_reused_v1.json`

## Dependencies
- outbound: `scheduling/matching-coordination` — discussion＋開始日空白＋唯一月嫂來源透過 typed borrowed-transaction port 建立正式 proposed Matching plan；其他來源不得製造 Matching root。
- outbound: `anomalies/anomalies` — committed review evidence由 `subsystems/orders/historical_order_adoption_outbox_consumer.py`確認投遞；歷史服務日曆未確認維持 owner review，不建立推測帳務。
- outbound: `payroll/historical-service-accounting` — 已完成歷史案件在採納與同檔重匯時同步正式月嫂應付。
- outbound: `orders/service-date-confirmation` — 只有歷史未服務／服務中案件明確重啟後，才由正常流程建立正式服務日；歷史完成訂單的天數修正留在 `orders/historical-service-accounting`。
- inbound: Case Import / operator import entry — only through typed source/workflow boundary.

## Contracts
- Preview／Apply 依工作簿日期、月嫂與每日時段區分實際重疊與缺少證據。標準六欄的時段按案號取自 Orders 完整起訖與跨日標記，既有附時段來源沿用明示時段。當次 `row_issues` 顯示雙方 Excel 列號與案件。檔內排除列保留案號，避免被列為檔外取消。
- Workbook Apply 只回傳當次結果。同檔重匯依目前版本重新判定，業務資料已一致的列避免重複寫入。整份結果快照與整批 claim 已停止讀寫。
- 現行逐筆採納資料仍承載可採納時段、指派及帳務的正式引用。`27` §12.1 定義搬遷至 owner 資料及轉接查詢與外鍵後的清除條件。
- MySQL 3819 沿 `historical_order_database_check_<constraint>` 保留 bounded、去 schema 的規則識別，不辨識時回 `check_rejected`；不以規則失敗直接推定 migration 或來源修正。
- 歷史工作簿資料庫錯誤以 `historical_order_database_*` 區分連線、權限、結構、資料鎖及指令／資料限制，保留數字與 correlation，不回傳或記錄 raw SQL／provider message；資料鎖與死結不觸發自動重送。
- `document/架構重整/01_規格基線/01_Orders_Domain.md` — historical adoption semantics and Orders ownership.
- `document/架構重整/01_規格基線/19_Global_Entry_Point_Governance.md` — script/API entry lifecycle.

## Verification
- static:
  - `db/schema_parts/1008_historical_order_adoption_noop_constraint.sql`
  - `db/schema_parts/214_historical_order_pairing_resolution_reused.sql`
- test_root: `tests/domains/orders/subsystems/orders/modules/historical-adoption/`

## Provenance
- Orders ownership and historical adoption contract — `architecture_declared` — `01_Orders_Domain.md`.
- API/repository/migration paths — `source_observed` — current repository.
- Owner-local test routing — `source_observed` — module-owned unit/contract/regression roots.

## Change triggers
Reconcile when historical workbook contract, Orders owner, API/script entry, persistence schema, receipt/replay semantics or test roots move.

# Module: historical-adoption

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
將受控、單一月嫂 historical order workbook 的可採納來源值套用到既有 Orders root。每次匯入重新檢查整份工作簿，檔內採納與檔外取消共用同一 outer UoW。採納保留原帳務，歷史服務完成時委派 Payroll 同步月嫂應付，匯入收據另列略過原因，並依正式方案委派 Client Finance 同步客戶補助退款。

<a id="historical-unserved-design"></a>

## 歷史零服務更正的實作邊界 ^historical-unserved-design

- 更正語意見 [歷史訂單 §6.2.1](../../../../../requirements/27_歷史訂單生命週期與服務天數帳務正式規格.md#historical-unserved-correction)。目標設計由 Domain 表達人員明確確認曾成立及未服務，原因與證據來源選填；缺失、矛盾、服務痕跡及舊款項待查核列非阻擋提示。實作是否符合此設計待驗，不把既有 `historical_unserved` 當作已終止狀態。
- 更正能力歸 Orders application boundary，經既有 cancellation Query／Preview／Apply 的 `historical_unserved_correction` typed 輸入及面板模式接線。API 要求零服務確認，沒有任意 target status；`historical_unserved_correction_read_model.py` 提供採納、事件、原結算與既有指派證據，共用原 cancellation workflow 的 fresh-lock／版本／冪等契約。
- Query 組成正式成立證據、現行服務事實及各 owner 帳務摘要；Preview 純計算更正影響；Apply 在單一 outer UoW 驗 current versions，委派 Orders、Client Finance、Payroll／Staff Payables 原 ports 保存結果與可追溯事件。帳務已正確的取消案件只補正分類，不重新執行退款。
- Repository adapters 保存本次人員確認，原採納關聯存在時保留，不假造採納收據；原歷史 assignment writer 退役原日班關聯指派，保留原列與 pairing 證據。Workbook import／adoption 對「成立後未服務」保留更正結果，衝突來源交查核，不以原日期恢復服務量；原收付及不可變事件保留。
- `build_historical_unserved_payroll_impact` 將零服務配置交 Payroll 原 impact builder。帳務已正確且官方服務量為零的原取消採分類更正分支，沿用原 cancellation control，不再次建立退款或替換班表。
- 驗收對應 `HIST-UNSERVED-01/02/03/04`，沿本 module 既有測試根及被借用的帳務 owner 入口，核對未付更正、已付追償／查核、同命令重播與重匯；真實 DB 執行結果與 source mapping 分開判定。
- Orders Subsystem 負責跨模組整合驗證。[WP80 測試](../../../../../../tests/domains/orders/subsystems/orders/modules/historical-adoption/integration/test_wp80_disposable_mysql_e2e.py)涵蓋歷史採納、零服務更正後重匯與週報、看板回讀。

```yaml archmap-impact
- kind: implements_requirement
  source: historical-unserved-design
  target: '.arch-map/requirements/27_歷史訂單生命週期與服務天數帳務正式規格.md#^historical-unserved-correction'
```

## Implementation
- primary:
  - `domains/orders/historical_adoption.py` — 採納候選只有在案件狀態改變或日期有修正時才推進 Orders lifecycle version；這是候選結果，不代表已寫入。
  - `domains/orders/historical_unserved_correction.py` — 更正意圖與人員確認；非阻擋核對提示及符合新規格的行為待驗。
  - `subsystems/orders/historical_unserved_correction.py` — 沿 Payroll owner 組成歷史零服務應付更正。
  - `infrastructure/mysql/historical_unserved_correction_read_model.py` — typed 歷史更正證據讀取。
  - `infrastructure/mysql/order_establishment_read_model.py` — 共用正式成立證據。
  - `infrastructure/mysql/historical_assignment_writer.py` — 原交易內退役已核對的歷史 standalone 指派，保留 pairing 與事件。
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
  - `api/routes/order_cancellation.py` — 沿原 cancellation Query／Preview／Apply 承接受限歷史零服務更正。
  - `api/schemas/historical_unserved_correction.py` — 選填原因、來源及明確零服務確認的目標 transport 契約，待驗。
  - `ui_react/src/components/OrderCancellationPanel.tsx` — 由案件抽屜提供受限歷史更正模式。
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
- [01A §4.1](../../../../../requirements/01A_訂單看板與事前日期及歷史採納規格.md#41-六欄來源與同檔重匯檔外取消hist-import-0104) 定義當次匯入結果：`import_counts` 區分成功寫入、資料已一致、未匯入；檔外取消另計。不要將 `adopted_count` 當成此次新增寫入數。同檔重匯依目前版本重新判定，不持久化整份結果快照或整批 claim。
- 正式逐筆採納證據不是當次工作簿暫存。既有正式引用及舊資料清除依 [27 §10.2](../../../../../requirements/27_歷史訂單生命週期與服務天數帳務正式規格.md#102-資料遷移與舊匯入清除邊界)：先轉接 owner 讀寫來源並核對搬遷；若仍有未轉接的外鍵、查詢或未對應事件，不清除。
- MySQL 3819 沿 `historical_order_database_check_<constraint>` 保留 bounded、去 schema 的規則識別，不辨識時回 `check_rejected`；不以規則失敗直接推定 migration 或來源修正。
- 歷史工作簿資料庫錯誤以 `historical_order_database_*` 區分連線、權限、結構、資料鎖及指令／資料限制，保留數字與 correlation，不回傳或記錄 raw SQL／provider message；資料鎖與死結不觸發自動重送。
- `.arch-map/requirements/01_Orders_Domain.md` — historical adoption semantics and Orders ownership.
- `.arch-map/requirements/19_Global_Entry_Point_Governance.md` — script/API entry lifecycle.

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

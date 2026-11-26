# Module: historical-service-accounting

## Parent
- domain: `payroll`
- subsystem: `payroll`

## Responsibility
以每位歷史 assignment 的服務天數、每日時數、`assignment_payroll_rate_snapshots` 費率快照與既有 Payroll adjustments 計算服務薪資應付，樓層費按最大餘數法分配。天數更正只保存比較金額；需入帳的差異由 Payroll／Staff Payables 正式更正處理，保留既有應付及付款證據。
歷史服務完成的基準應付依各已採納指派的可證實服務量與正式費率建立，借用既有 Payroll rebuild 事件、投影與收據 writer。歷史服務結束日及付款來源用於確認預計付款日與資金分期，不作為已具計薪依據者建帳的前置條件。採納、到期推進和既有同步入口共用同一流程。

## Implementation
- `domains/payroll/historical_calculation.py` — 候選要求服務事實與費率快照逐筆對應，快照缺漏、重複或多出時拒絕。
- `subsystems/payroll/historical_baseline_obligation_sync.py` — historical source synchronization in the caller's transaction；拆開正式應付建立與資金分期／預計付款日形成（`HistoricalFundingSchedule`）。單人與多人歷史完工案按已採納指派逐筆評估：可證實服務量與費率且無衝突者先建立正式應付（`due_date` 與分期未確認時保留 `None` 及具體原因，不填假日期、不預設補助為零），資料不足或已有原帳／衝突者保留待查或原狀；後續補齊付款日時由 `infrastructure/mysql/payroll_rebuild_repository.py::_set_historical_missing_due_date` 沿既有應付識別與版本更新日期，不改寫應付金額。
- `api/routes/accounting_differences.py`：管理員在應付清冊「查未列入原因」→「查核歷史月嫂款」選擇案件後，若處理面板提供「同步月嫂應付」，由 `POST /api/v1/orders/{case_no}/payroll/sync-historical-baseline-obligations` 觸發正式建帳；打開帳務頁或查核結果不寫入。既有維運入口為 `scripts/sync_historical_staff_obligations.py`。
  - `created` 是首次建立；`updated` 是已存在且可更新；`skipped` 要看原因，不能當成已入帳。若已有正式服務歸屬更正，基準同步只讀回該更正應付與待核對，不從早期採納資料另外建帳；若歷史帳務完成卻沒有原應付，也不由基準同步補造。
  - 「已有計薪來源，正式應付尚未建立」是唯讀判定，不表示正式同步已執行。缺付款日或補助資金分期時，按實際建帳回執區分「尚未建立」與「已建立、付款安排待確認」。
  - **接線契約**：查核使用 `GET /api/v1/finance-reports/accounts-payable/historical-lookup`，傳 `keyword`、`target_month`，同案核對案號與月嫂；參考 [應付清冊查核](../../../../staff-payables/subsystems/staff-payables/modules/accounts-payable-export.md)。同步的 `POST` 由管理員提交，案號在路徑，不需要 request body。寫入範圍是該案，不是畫面上單一月嫂；按該案已採納指派逐筆查核。
  - **正式讀回**：同步回應的 `data.details` 可能為空；以相同 `case_no` 找到案件結果。多人時看 `items` 的各筆結果、理由與付款安排，不把摘要的 `created`／`updated` 當成全員成功。空結果、請求失敗或回應案號不符都不能判建帳成功。重新查核同案同人，讀正式應付和金額；原已存在或付款安排未定要分開判讀。清冊未列入不等於無正式應付，不在結果未知時直接重送。
- `infrastructure/mysql/historical_service_accounting_repository.py` — reads calculation inputs and persists the Orders comparison snapshot.
- `infrastructure/mysql/case_staff_accounting_repository.py::query_case_staff_accounting_availability` — 逐人唯讀查核正式應付、原日期與歷史計薪來源（含已採納指派與 `staff_schedule` 出席日數），分開呈現已建帳缺日期、來源齊全尚未建立及具體缺項。既有應付不因他人缺件消失，無逐日班表不構成單人歷史計薪缺項；查詢不呼叫同步 writer。
  - 預計付款日須有適用該應付的唯一、可證實服務結束日及資金來源。採納或服務量投影的指派來源缺失／歧義時，不以整案結束日補推日期；保留正式金額、原到期日與原已保存付款日期，並按人回傳具體缺項。唯一來源的正例僅補原缺席的唯讀預計日，不改已形成日期。

### 同步接線：現行契約與缺口

- 查核只用日期與身分做定位。讀回 `case_no`、可空的 `staff_id`／`obligation_identity`／`current_event_id`、`amount_due_ntd`／`balance_ntd`、日期、`source`／`disposition`／`reason`。只有同案同人的 `source=formal_obligation` 與正式義務身分能證明建帳；`historical_projection`、`order_facts` 不證明已建帳。同人的多筆不能直接合為一筆。前端解析入口為 `accounts_payable_query_schemas.ts`。
- 目前同步回應由 `subsystems/payroll/historical_baseline_obligation_sync.py` 組裝，`data` 包含 `scanned_orders`、`created_count`、`updated_count`、`skipped_count` 與 `details`。計數按案，不是按人。多人 `items` 可帶 `assignment_id`、`staff_id`、`obligation_identity`，以及 `action`、`amount_ntd`、可空 `due_date`、`reason` 或 `pending_reason`；不得要求缺證項目補齊這些欄位。單人結果不要求 `items` 或 `obligation_identity`，正式識別從查核讀回。
- 這支 POST 未接收呼叫端重送鍵，也沒有公開依命令鍵查回執的入口。系統先鎖該案 Orders、核對既有應付，再依該案 Payroll aggregate version 產生內部 `historical-payroll:{case_no}:{version}` 寫入鍵。結果未知先唯讀查同案同人；不能把同案第二次按同步說成同鍵回放。現行路由未發布專用錯誤碼對照，不借用其他帳務端點的錯誤契約。
- 新建服務應付以 `staff-obligation:assignment:{assignment_id}` 為識別；可承接的既有義務保留原識別。`db/schema_parts/112_payroll_obligations.sql` 約束 `staff_obligations(case_no, obligation_identity)` 唯一、`current_event_id` 連到不可變事件，事件與投影的 `due_date` 都允許 SQL NULL。未形成分期不建子列。建立事件、正式投影、Payroll 內部套用收據和本次適用的分期共用呼叫方交易；GET 不寫入，不用 HTTP 回應取代提交後新連線回讀。
- **現行畫面缺口**：`HistoricalPayableReview.tsx` 與 query client 目前以同案摘要和日期／付款安排提示呈現，尚未消費多人 `items`。目標呈現需分別標示哪些已建帳、哪些待核對；結果未知時只給「重新查核」而不自動重送。這是前端／API 接線待修，不是已驗證畫面。

## Contracts
- `.arch-map/requirements/27_歷史訂單生命週期與服務天數帳務正式規格.md`
- `.arch-map/requirements/03_Payroll_Domain.md` §2.2、§3.2

## Verification
- test_root: `tests/domains/payroll/subsystems/payroll/modules/historical-service-accounting/`

## Change triggers
Reconcile when the single-pay rule, rate snapshot, floor-fee allocation or comparison inputs change.

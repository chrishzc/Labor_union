# Module: historical-service-accounting

## Parent
- domain: `payroll`
- subsystem: `payroll`

## Responsibility
以每位歷史 assignment 的服務天數、每日時數、`assignment_payroll_rate_snapshots` 費率快照與既有 Payroll adjustments 計算服務薪資應付，樓層費按最大餘數法分配。天數更正只保存比較金額；需入帳的差異由 Payroll／Staff Payables 正式更正處理，保留既有應付及付款證據。
歷史服務完成的基準應付讀取 HCM 登記天數／每日時數、已採納唯一指派、歷史結束日、正式費率及付款來源，借用既有 Payroll rebuild 事件、投影與收據 writer。採納、到期推進和既有同步入口共用同一流程。

## Implementation
- `domains/payroll/historical_calculation.py` — 候選要求服務事實與費率快照逐筆對應，快照缺漏、重複或多出時拒絕。
- `subsystems/payroll/historical_baseline_obligation_sync.py` — historical source synchronization in the caller's transaction；拆開正式應付建立與資金分期／預計付款日形成（`HistoricalFundingSchedule`）。單人與多人歷史完工案按已採納指派逐筆評估：可證實服務量與費率且無衝突者先建立正式應付（`due_date` 與分期未確認時保留 `None` 及具體原因，不填假日期、不預設補助為零），資料不足或已有原帳／衝突者保留待查或原狀；後續補齊付款日時由 `infrastructure/mysql/payroll_rebuild_repository.py::_set_historical_missing_due_date` 沿既有應付識別與版本更新日期，不改寫應付金額。
- `api/routes/accounting_differences.py`、`scripts/sync_historical_staff_obligations.py` — existing historical synchronization entry points.
- `infrastructure/mysql/historical_service_accounting_repository.py` — reads calculation inputs and persists the Orders comparison snapshot.
- `infrastructure/mysql/case_staff_accounting_repository.py::query_case_staff_accounting_availability` — 逐人唯讀查核正式應付、原日期與歷史計薪來源（含已採納指派與 `staff_schedule` 出席日數），分開呈現已建帳缺日期、來源齊全尚未建立及具體缺項。既有應付不因他人缺件消失，無逐日班表不構成單人歷史計薪缺項；查詢不呼叫同步 writer。
  - 預計付款日須有適用該應付的唯一、可證實服務結束日及資金來源。採納或服務量投影的指派來源缺失／歧義時，不以整案結束日補推日期；保留正式金額、原到期日與原已保存付款日期，並按人回傳具體缺項。唯一來源的正例僅補原缺席的唯讀預計日，不改已形成日期。

## Contracts
- `.arch-map/requirements/27_歷史訂單生命週期與服務天數帳務正式規格.md`
- `.arch-map/requirements/03_Payroll_Domain.md` §2.2、§3.2

## Verification
- test_root: `tests/domains/payroll/subsystems/payroll/modules/historical-service-accounting/`

## Change triggers
Reconcile when the single-pay rule, rate snapshot, floor-fee allocation or comparison inputs change.

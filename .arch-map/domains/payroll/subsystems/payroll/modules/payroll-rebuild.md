# Module: payroll-rebuild

## Parent
- domain: `payroll`
- subsystem: `payroll`

## Responsibility
依正式 Scheduling assignment 與 Orders terms 重建 Payroll projection；不得反向改寫來源排班或條款。
既有正式排班缺漏應付日時，以正式 actual_end_date、Client Finance 衍生客戶應付與補助資格套用既有付款日政策；保留已形成日期，建立 obligation 時保存 candidate 日期。

服務完成可在 Orders 既有 UoW 呼叫 `synchronize_in_unit_of_work`，應付動作全部未變時不寫入重建結果；使用分段計價時仍同步分期。不建立新人工步驟，交易由呼叫方持有。

除需求書定義的假日加成外，純日期合併、分裂及復原使用 Scheduling 的原財務日期讀取投影，保留原受款人、時數、費率及樓層費分配。current generation 完整原列優先；僅純 Actual Start 的同月嫂 lineage 可承接最近完整基準，真正財務更正沿自身 current effective 口徑。
neutral 重排承接原財務指派身分作樓層費同餘數排序，計算結果仍使用 current assignment；此身分只存在於計算輸入，不新增資料庫或畫面欄位。

## Implementation
- primary:
  - `subsystems/payroll/rebuild_workflow.py`
  - `infrastructure/mysql/payroll_rebuild_repository.py`
  - `api/schemas/payroll_rebuild.py`

## Dependencies
- inbound: `scheduling/scheduling` — 正式 assignment 與服務時數。
- inbound: `infrastructure/mysql/service_date_adjustment_repository.py::load_payroll_service_dates` — 純日期調整與 neutral Actual Start 的原財務日期投影。
- inbound: `orders/orders` — current order terms。
- inbound: `case-import/case-import/pairing-current-facts` — 服務前正式 BeClass 胎數 correction 的 effective rate override。

## Verification
- integration_root: `tests/domains/payroll/subsystems/payroll/integration/test_payroll_rebuild_workflow.py`

## Provenance
- Rebuild repository、HTTP schema 與既有整合測試 — `source_observed` — current repository。

## Change triggers
Reconcile when rebuild input facts、projection contract or verification root changes.

## 國定假日計價接線 ^payroll-rebuild-holiday-pricing

```yaml archmap-impact
- kind: implements_requirement
  source: payroll-rebuild-holiday-pricing
  target: ".arch-map/requirements/03_Payroll_Domain.md#^payroll-service-pricing"
```
- 假日計價接線接線由下列 owner 實作，驗證見既有測試入口。`payroll_rebuild_repository.py` 分開讀 Scheduling 實際有效日時數及原財務基準，`rebuild_workflow.py` 使用 assignment 凍結費率算月嫂服務薪資。一般與歷史入口分流，兩方收付 facts 經同一 caller UoW 重讀後才交 Payroll writer；不可單獨改未付款一邊。

- 22A 全額免自備差額負擔未定時，初排 Terms impact 與完成 Rebuild 均保留原服務薪資基數，假日加成暫不入帳；Scheduling 日期、時數與付款日仍沿原流程。服務費候選由 Client Finance Query 呈現，不以政府補助補平。

# Module: schedule-generation

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
純日期合併、分裂及復原在原交易透過 Orders writer 同步最後正式服務日及 Orders version；首排承接協調日期時亦同步，完工時點由 [Orders owner](../../../../orders/subsystems/orders/modules/lifecycle-authoritative-facts.md) 判斷，不以帳務天數限制實際日期筆數。
從 current Scheduling generation facts 產生版本化 assignment／buffer candidate。Orders Terms caller 必須先比對 candidate 與 current effective assignment 的 identity／人員／日期／區間形狀；形狀未變時 candidate 只供 Finance／Payroll 計算與真實 assignment identity mapping，不得持久化新 generation。尚無 assignment／buffer 時，開始日／服務天數 candidate 不虛構 segment；已有服務日期或排班事實時仍 fail closed，分別要求替換日期或正式重新分配。

服務中 Orders Terms 使用每個既有指派的明確服務日，Scheduling 核對其合計恰為完整正式日期，再產生同一 generation candidate。

## Implementation
- primary:
  - `db/schema_parts/1068_scheduling_shift_occupancy_indexes.sql` — 保留排班、檔期鎖、有效占用及請假血緣資料，允許同人同日多筆；正式寫入仍依月嫂 mutex 與時段重疊規則驗證。
  - `domains/scheduling/generation.py`
  - `domains/scheduling/service_date_adjustment.py` — 4＋4 合併、8 分裂及來源配對精確復原。
  - `subsystems/scheduling/service_date_adjustment.py` — 純日期版本命令與單一 outer Unit of Work。
  - `infrastructure/mysql/service_date_adjustment_repository.py` — 逐日保存、配對回執與正式首排承接。
  - `domains/scheduling/service_date_adjustment.py` — 4＋4 合併、8 分裂及來源配對精確復原。
  - `subsystems/scheduling/service_date_adjustment.py` — 純日期版本命令與單一 outer Unit of Work。
  - `infrastructure/mysql/service_date_adjustment_repository.py` — 逐日保存、配對回執與正式首排承接。
  - `domains/scheduling/assignment_plan.py`
  - `domains/scheduling/bootstrap.py`
  - `api/schemas/assignment_plan.py`

## Dependencies
- inbound: `payroll/payroll` — `load_payroll_service_dates` 唯讀提供純日期調整的原財務日期與指派身分；neutral Actual Start 同人 lineage 承接原基準，供 Payroll 保留原受款人及樓層費分配，不改實際班次或帳務 writer。
- inbound: `global/reporting/staff-performance` — `resolve_opening_primary_staff` reads ordered segment identity, same-person rebuild lineage and exact daily substitution outcomes. Pre-service replacement changes principal; later handover/substitution does not duplicate opening credit. No root/writer change.
- 七日 buffer 是獨立提醒 facts，不參與 assignment interval 的 hard occupancy claim；實際服務占用仍唯一。
- inbound: `orders/order-terms` — Orders Terms workflow 只透過 typed generation candidate 交付排班影響。
- inbound: Scheduling workflows — 使用 current generation facts 建立正式重建 candidate。

## Contracts
### 純日期服務量調整 ^service-date-adjustment-generation

- `source_observed`：專用版本命令，業務契約見 [合併與分裂服務日期](../../../../../requirements/02_Assignments_Scheduling_Domain.md#service-date-merge-split)。正常 generation replacement 流程維持，純日期重組則保留 effective generation、assignment identity、費率快照及帳務來源。
- Apply 由 `subsystems/scheduling/service_date_adjustment.py` 的單一 outer UoW 鎖定並核對 Orders、Scheduling、相關月嫂與日班，經 `infrastructure/mysql/service_date_adjustment_repository.py` 保存受影響班次、必要 occupancy 投影、操作紀錄與 Scheduling aggregate version。停用來源日班而非刪除，保留其他 owner 的日班參照；不呼叫 Payroll／Finance writer。
- `staff_schedule.service_hours_override` 為 nullable 逐日時數。NULL 沿用原訂時數與時段；明確值代表自行協調日期，不新增時段模式。重排及首排的 typed daily facts 必須承接覆寫值，不能又乘回原訂每日時數。
- additive schema part 為 `db/schema_parts/1082_service_date_adjustments.sql`，同步 fresh assembly 與同名 preserve-data release／descriptors。除逐日時數及事前人員欄位外，以一張本功能操作紀錄承接復原；同代同日唯一鍵包含 `effective_marker`，保留歷史非生效日班且保證目前同案同日只有一個 owner。
- 復原是明確命令，不是遇到相同 request 就反覆切換；版本及來源衝突回 typed conflict，整筆 rollback。正式世代未改不等於忽略版本，Scheduling aggregate version 每次實際成功異動均增加。

- `.arch-map/requirements/02_Assignments_Scheduling_Domain.md` — generation、assignment 與 occupancy ownership。

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/scheduling/subsystems/scheduling/modules/schedule-generation/`
- default_boundary: Module
- cross-owner behavior is verified by the Orders Terms owner at its declared focused test root.

## Provenance
- Scheduling generation ownership — `architecture_declared` — Scheduling formal spec.
- Candidate builders and cross-owner preassignment behavior — `source_observed` — current source and focused Orders integration test.

## Change triggers
Reconcile when generation versioning, assignment／buffer candidate, preassignment fail-closed rules, or callers change.

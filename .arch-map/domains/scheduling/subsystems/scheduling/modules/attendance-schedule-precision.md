# Module: attendance-schedule-precision

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
依 Orders 提供的 canonical 服務方式、國定假日、個別排休與人工服務日，產生逐日出勤與完工日精算投影；固定單日週休必須保留休周六與休周日的差異。

## Implementation
- primary:
  - `subsystems/scheduling/attendance_schedule_query.py`
  - `infrastructure/mysql/mysql_adapter.py`
- entrypoints:
  - `api/schemas/orders.py`
  - `ui_react/src/api/scheduling/schedule_precision_client.ts`

## Dependencies
- inbound: `orders/orders` — 接收案件實際開始日、服務天數與 canonical 服務方式。
- outbound: Scheduling holiday facts — 讀取國定假日並套用明確的人工休假／服務日覆蓋。

## Contracts
- `POST /api/v1/orders/calculate-schedule` — bounded 出勤精算 request／response。
- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md` — Scheduling 服務日精算語意。

## Verification
- higher_boundary:
  - `tests/domains/scheduling/subsystems/scheduling/integration/test_service_end_date_calculation_correctness.py`

## Provenance
- Scheduling owns attendance-date calculation — `architecture_declared` — current Scheduling formal spec。
- implementation、API schema、frontend client 與 cross-calculator oracle — `source_observed` — current repository。

## Change triggers
Reconcile when canonical 服務方式、固定週休、holiday／leave／manual-work precedence、precision API 或計算 adapter 改變。

# Module: service-day-log

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
月嫂服務日日誌 typed options／直接 Apply、requires_cooking 門禁、服務結束 checkpoint／outbox，以及受控寶寶／餐食照片在同一 Scheduling UoW 的登錄與 fresh readback。畫面點送出即保存，無日誌預覽或確認；既有 Preview 只供媒體及 API consumer 驗證。允許提前填寫、提交後不可修改；`missing_runs` 只讀 current generation，輸出 LINE 人工提醒使用的連續缺漏區間。餐食照片僅在需要料理時適用，寶寶照片可在不需料理的服務日使用；需要料理時仍必須有餐食照片。

## Implementation
- primary:
  - `domains/scheduling/service_day_log.py`
  - `subsystems/scheduling/service_day_log_workflow.py`
  - `subsystems/scheduling/service_day_checkpoint_workflow.py`
  - `infrastructure/mysql/service_day_log_repository.py`
  - `infrastructure/mysql/service_day_checkpoint_repository.py`
  - `infrastructure/mysql/service_day_checkpoint_worker.py`
  - `db/schema_parts/204_scheduling_service_day_logs.sql`
  - `db/schema_parts/205_scheduling_service_day_checkpoints.sql`
  - `db/schema_parts/213_scheduling_service_day_attachment_kind.sql`
- entrypoints:
  - `api/routes/staff_service_day_logs.py`
  - `api/dependencies/service_day_logs.py`
  - `api/schemas/line_staff_self_service.py`

## Verification
- integration: `tests/domains/scheduling/subsystems/scheduling/integration/test_service_day_log_controlled_media.py` — controlled meal/baby attachment gates and schema kind contract
- legacy focused: `tests/test_service_day_log_workflow.py`
- routing: `.arch-map/domains/scheduling/subsystems/scheduling/index.md`

## Provenance
- Scheduling ownership and requires_cooking/media contract — `architecture_declared` — current self-service specification.
- implementation and test paths — `source_observed` — current repository.

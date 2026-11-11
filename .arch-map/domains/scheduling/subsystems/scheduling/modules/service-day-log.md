# Module: service-day-log

> **Status: Retired / Compatibility Mode (2026-11-10)**
> 依據高齡友善決策，月嫂寶寶日誌與餐食照片改維持於 LINE 案件群組相簿，免除網頁表單操作；日誌不再作為排班卡控或催繳依據，公開 API 端點退役回傳 HTTP 410 GONE。歷史日誌與檔案關聯於資料庫完整保留。

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
[RETIRED / HISTORICAL] 原月嫂服務日日誌 typed options／直接 Apply、requires_cooking 門禁、服務結束 checkpoint／outbox，以及受控寶寶／餐食照片在同一 Scheduling UoW 的登錄與 fresh readback。現行流程下，寶寶日誌與餐食照片回歸 LINE 案件群組相簿由月嫂自行拍照上傳，系統不強制料理日餐食照片驗證，公開 API 端點退役回傳 410。資料庫保留歷史日誌記錄。

## Implementation
- primary:
  - `domains/scheduling/service_day_log.py` (放寬日誌卡控)
  - `subsystems/scheduling/service_day_log_workflow.py`
  - `subsystems/scheduling/service_day_checkpoint_workflow.py`
  - `infrastructure/mysql/service_day_log_repository.py`
  - `infrastructure/mysql/service_day_checkpoint_repository.py`
  - `infrastructure/mysql/service_day_checkpoint_worker.py`
  - `db/schema_parts/204_scheduling_service_day_logs.sql`
  - `db/schema_parts/205_scheduling_service_day_checkpoints.sql`
  - `db/schema_parts/213_scheduling_service_day_attachment_kind.sql`
- entrypoints:
  - `api/routes/staff_service_day_logs.py` (HTTP 410 GONE: `service_day_log_retired`)
  - `api/dependencies/service_day_logs.py`
  - `api/schemas/line_staff_self_service.py`

## Verification
- test_root: `tests/domains/scheduling/subsystems/scheduling/modules/service-day-log/`
- integration: `tests/domains/scheduling/subsystems/scheduling/integration/test_service_day_log_controlled_media.py`
- legacy focused: `tests/test_service_day_log_workflow.py`
- api test: `tests/domains/scheduling/subsystems/scheduling/modules/service-day-log/test_staff_service_day_log_api.py` (驗證 410 GONE)
- routing: `.arch-map/domains/scheduling/subsystems/scheduling/index.md`

## Provenance
- retirement decision (2026-11-10) — `architecture_declared` — `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md` §19, `20_LINE客服與月嫂自助服務正式規格.md` §5.4。

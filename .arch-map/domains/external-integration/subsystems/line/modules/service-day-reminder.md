# Module: service-day-reminder

> **Status: Retired (2026-11-10)**
> 依據 2026-11-10 最新人工裁決，月嫂寶寶日誌與餐食照片改為直接於 LINE 案件群組相簿新增，系統端基於日誌資料庫記錄之「連續缺漏提醒」機制全數退役。工會端案件群組工作區（`LineOrderGroupWorkbench.tsx`）與手機審核中心（`mobile_admin.html`）已移除「日誌連續缺漏」待辦與催繳發送功能；後端 `/log-reminders` 與 `/log-reminders/send` API 端點依規格 19 退役回傳 HTTP 410 GONE。

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
[RETIRED] 原以 Scheduling current 正式服務日及日誌投影連續缺漏至少四日的工會內部清單，供人員點發送提醒。退役後群組相簿照片由工會人員巡群直接關懷，不再以機器人催繳。

## Implementation
- primary (retired to 410):
  - `api/routes/line_order_groups.py` — `/log-reminders` 與 `/log-reminders/send`（HTTP 410 GONE）。
  - `api/routes/line_mobile_admin.py` — `/log-reminders` 與 `/log-reminders/send`（HTTP 410 GONE）。
  - `line/static/mobile_admin.html` — 已移除日誌連續缺漏工作流按鈕與載入邏輯。
  - `ui_react/src/components/LineOrderGroupWorkbench.tsx` — 已移除缺漏標籤與發送提醒介面。
- retained history/cancellation:
  - `subsystems/line/service_day_log_reminders.py` — 自動及人工的殘留提醒在呼叫 LINE 前取消。
  - 歷史通知任務與資料庫既有 outbox/checkpoint 記錄完整保留存查。
  - `subsystems/line/scheduling_checkpoint_notification_source.py`
  - `subsystems/line/service_day_log_notification_stop.py`
  - `subsystems/line/scheduling_rebuild_notification_invalidation.py`
  - `infrastructure/mysql/scheduling_checkpoint_notification_source_repository.py`
  - `infrastructure/mysql/scheduling_checkpoint_notification_source_worker.py`
  - `infrastructure/mysql/service_day_log_notification_stop_repository.py`
  - `infrastructure/mysql/service_day_log_notification_stop_worker.py`
  - `infrastructure/mysql/scheduling_rebuild_notification_invalidation_repository.py`
  - `infrastructure/mysql/scheduling_rebuild_notification_invalidation_worker.py`
- notification persistence:
  - `infrastructure/mysql/line_notification_repository.py`

## Dependencies
- inbound: 既有完成及 rebuild outbox — 沿既有取消及歷史處理。
- outbound: LINE delivery task owner — committed task 與 provider 前 fresh cancellation gate。

## Contracts
- [LINE 客服與月嫂自助服務 §4.3](../../../../../document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md) — 缺漏催繳退役。

## Verification
- layout_status: `custom_current`
- layout_basis: Python 使用 owner-local module root，React 使用專案 Vitest 的 `ui_react/src/tests/` 相同 Domain／Subsystem／Module 鏡像；既有 outbox 歷史與取消 regression 沿原 declared roots 保留。
- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_scheduling_checkpoint_notification_source.py`
- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_scheduling_rebuild_notification_invalidation.py`
- test_root: `tests/domains/external-integration/subsystems/line/modules/service-day-reminder/`
  - `test_service_day_log_reminders.py` — 人工決定、唯讀、退役自動提醒與寄送前門禁。
  - `test_service_day_log_reminder_mysql.py` — current generation、連續日、補填及 fake provider 整合。
- ui_test_root: `ui_react/src/tests/domains/external-integration/subsystems/line/modules/service-day-reminder/`
- test_root: `tests/domains/external-integration/subsystems/line/modules/service-day-reminder/test_line_service_day_reminder_acceptance.py`
- integration: `tests/domains/external-integration/subsystems/line/integration/test_service_day_reminder_disposable_mysql.py`

## Provenance
- owner、implementation 與 verification paths — `source_observed` — issue #325 current executable flow and Native MySQL acceptance.

# Module: service-day-reminder

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
以 Scheduling current 正式服務日及日誌投影連續缺漏至少四日的工會內部清單；人員點發送提醒才建立原案件群組 durable task。Query 零寫入，發送前複核缺漏區間及群組版本。舊每日自動私訊規則與 provider 發送停用，保留既有完成／重建 outbox 取消處理及歷史查閱。

## Implementation
- primary:
  - `subsystems/line/service_day_log_reminders.py`
  - `infrastructure/mysql/service_day_log_reminder_repository.py`
  - `api/dependencies/service_day_log_reminders.py`
  - `api/routes/line_order_groups.py` — `/log-reminders` Query 及 `/log-reminders/send` 工會人工寄送。
  - `ui_react/src/components/ServiceDayLogReminderWorkbench.tsx`
  - `ui_react/src/api/line_order_groups/service_day_log_reminder_client.ts`
  - `ui_react/src/pages/LineManagementPage.tsx` — 案件群組頁內部提醒。
- retained history/cancellation:
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
- inbound: `scheduling/service-day-log` — current generation 正式服務日、已結束時段及日誌缺漏 typed Query；完成／rebuild outbox 僅沿用既有取消與歷史處理。
- outbound: LINE delivery task owner — committed task 與 provider 前 fresh cancellation gate。

## Contracts
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` §5.5 — 日曆連續至少四個已結束且未填的正式服務日、工會逐次決定、原案件群組及群組版本複核；Scheduling 保留事實 owner。
- Query 不 commit；人工命令只由 application 的 outer UoW 提交 durable task，HTTP 不直接呼叫 provider。公版預覽共用 `reminder_text`，不建立工作且沒有獨立啟用設定。
- 提醒文案沿規格 17 LINE-COPY 維護；repository 的 `message` reader 借用原 connection，供待辦 Query 及依賴組裝注入的寄送 copy reader 共用。仍由原 `MySqlUnitOfWork` 唯一提交，不為文字設定建立新交易。
- 通知事項 Query 以同一 `reminder_text` 及目前月嫂名稱提供實際提醒文案；仍以原送前 fresh read 決定收件群組及最終內容，不因預覽建立工作。

## Verification
- layout_status: `custom_current`
- layout_basis: Python 使用 owner-local module root，React 使用專案 Vitest 的 `ui_react/src/tests/` 相同 Domain／Subsystem／Module 鏡像；既有 outbox 歷史與取消 regression 沿原 declared roots 保留。
- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_scheduling_checkpoint_notification_source.py`
- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_scheduling_rebuild_notification_invalidation.py`
- test_root: `tests/domains/external-integration/subsystems/line/modules/service-day-reminder/`
  - `test_service_day_log_reminders.py` — 人工決定、唯讀、退役自動提醒與寄送前門禁。
  - `test_service_day_log_reminder_mysql.py` — current generation、連續日、補填及 fake provider 整合。
- ui_test_root: `ui_react/src/tests/domains/external-integration/subsystems/line/modules/service-day-reminder/`
- dependency: `infrastructure/mysql/service_day_log_repository.py::missing_runs` — Scheduling typed 缺漏區間，非服務日及已填日切斷區間。
- test_root: `tests/domains/external-integration/subsystems/line/modules/service-day-reminder/test_line_service_day_reminder_acceptance.py`
- integration: `tests/domains/external-integration/subsystems/line/integration/test_service_day_reminder_disposable_mysql.py`

## Provenance
- owner、implementation 與 verification paths — `source_observed` — issue #325 current executable flow and Native MySQL acceptance.

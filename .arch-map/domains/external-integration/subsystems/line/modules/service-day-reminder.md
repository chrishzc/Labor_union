# Module: service-day-reminder

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
將已提交的 Scheduling 服務日 checkpoint outbox 投影為 versioned LINE notification source／decision／intent／delivery task，並在服務日誌完成或排班重建後，於 provider delivery 前精確取消受影響提醒。

## Implementation
- primary:
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
- inbound: `scheduling/service-day-log` — immutable checkpoint、日誌完成與 rebuild outbox facts。
- outbound: LINE delivery task owner — committed task 與 provider 前 fresh cancellation gate。

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_scheduling_checkpoint_notification_source.py`
- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_scheduling_rebuild_notification_invalidation.py`
- test_root: `tests/domains/external-integration/subsystems/line/modules/service-day-reminder/`
- integration: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_service_day_reminder_acceptance.py`
- integration: `tests/domains/external-integration/subsystems/line/integration/test_service_day_reminder_disposable_mysql.py`

## Provenance
- owner、implementation 與 verification paths — `source_observed` — issue #325 current executable flow and Native MySQL acceptance.

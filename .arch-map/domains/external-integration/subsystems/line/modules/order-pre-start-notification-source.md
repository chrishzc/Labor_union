# Module: order-pre-start-notification-source

## Parent
- subsystem: `external-integration/line`

## Responsibility
Owns the read-only scan and immutable LINE notification source-event projection
for formal start-day group caregiver-status inquiries. Committed second-payment settlement notices now require the explicit human receipt command in payment-overdue-reminders; this scanner does not project them. Financial reminder text is excluded from the group inquiry; initial/due payment reminders now use the private payment schedule worker. The
worker also projects explicitly marked committed normal service completions into one original-case-group survey invitation. The
worker owns its outer unit of work only when new source events are persisted;
it does not mutate Orders or Client Finance facts and does not call the LINE
provider directly. Verified group postbacks record replies in existing LINE receipts
and create Customer Service service-progress todos only when assistance is requested.

## Implementation
- `subsystems/line/order_pre_start_notification_source.py`
- `subsystems/line/service_start_day.py`
- `infrastructure/mysql/service_start_day_repository.py`
- `subsystems/line/service_completion_notifications.py` — typed completion evidence and fresh delivery guard.
- `infrastructure/mysql/service_completion_notification_repository.py` — committed normal-completion marker, original group, attempts and no historical backfill.
- `subsystems/line/second_payment_notifications.py`
- `infrastructure/mysql/second_payment_notification_repository.py`
- `subsystems/line/notification_source_adapters.py`
- `infrastructure/mysql/order_pre_start_notification_source_repository.py`
- `infrastructure/mysql/order_pre_start_notification_source_worker.py`

## Dependencies
- inbound: `orders` and `client-finance` typed persisted facts, read only
- Finance reader: `SecondPaymentQueryPort` — required stage／remaining balance／valid settlement are Finance-owned facts, no LINE ledger reducer
- second-payment success source: marked `projection_refresh` Finance outbox; no historical backfill or status consumption
- missing original group: existing LINE-006 recipient-unavailable staff todo; no private fallback
- outbound: existing LINE notification source registry and committed delivery intent
- outbound: Customer Service `create_or_append`, caller-owned webhook transaction
- ingress: `api/dependencies/line_worker_operation.py` routes verified `start-day:` group postbacks
- provider guard: `subsystems/line/delivery_worker.py` cancels stale day/group/assignment/payment snapshots and retired private reminders

## Contracts
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md`
- `document/架構重整/01_規格基線/29_LINE服務說明、客服互動與選單角色正式規格.md`

## Verification routing
layout_status: `custom_current`

- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_line_notification_source_adapters.py`
- test_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_notification_recipient_resolution.py`
- test_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_order_pre_start_notification_source_repository.py`
- test_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_order_reminder_worker_wiring.py`
- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_order_pre_start_notification_policy.py`
- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_order_pre_start_notification_source.py`

- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_service_start_day_postback.py`
- test_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_service_start_day_mysql.py`

- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_second_payment_notifications.py`
- test_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_second_payment_notifications_mysql.py`

- test_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_service_completion_notifications_mysql.py`

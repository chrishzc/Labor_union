# Module: order-pre-start-notification-source

## Parent
- subsystem: `external-integration/line`

## Responsibility
Owns the read-only scan and immutable LINE notification source-event projection
for first-payment pre-start reminders and second-payment due reminders. The
worker owns its outer unit of work only when new source events are persisted;
it does not mutate Orders or Client Finance facts and does not call the LINE
provider directly.

## Implementation
- `subsystems/line/order_pre_start_notification_source.py`
- `subsystems/line/notification_source_adapters.py`
- `infrastructure/mysql/order_pre_start_notification_source_repository.py`
- `infrastructure/mysql/order_pre_start_notification_source_worker.py`

## Dependencies
- inbound: `orders` and `client-finance` typed persisted facts, read only
- outbound: existing LINE notification source registry and committed delivery intent

## Contracts
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md`
- `document/架構重整/01_規格基線/29_LINE服務說明、客服互動與選單角色正式規格.md`

## Verification routing
layout_status: `custom_current`

- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_line_notification_source_adapters.py`
- test_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_notification_recipient_resolution.py`
- test_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_order_pre_start_notification_source_repository.py`
- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_order_pre_start_notification_policy.py`
- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_order_pre_start_notification_source.py`

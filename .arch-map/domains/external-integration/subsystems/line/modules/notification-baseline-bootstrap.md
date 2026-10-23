# Module: notification-baseline-bootstrap

## Parent
- subsystem: `external-integration/line`

## Responsibility
Owns the Task96 M1–M4 notification baseline identities, development-only
`lu_test_*` source-event fixture producer, and typed projection into the
existing LINE notification repository. It does not own business decisions,
assignments, profiles, payroll obligations, or provider calls.

## Implementation
- `subsystems/line/notification_baseline.py`
- `domains/line/notification_rules.py`
- `infrastructure/mysql/line_notification_repository.py`
- `subsystems/line/configuration_application.py`
- `api/schemas/line_notification_rules.py`
- `api/schemas/line_config.py` — shared management template projection preserves current formal template IDs and bounded notification categories／usages; does not rename owner identities.
- `config/notification_rules.json`
- `config/message_templates.json`

## Consumers
- existing LINE notification Query / Preview / Apply routes and typed views

## Verification
- canonical test root: `tests/domains/external-integration/subsystems/line/modules/notification-baseline-bootstrap/`
- acceptance: exact 26 §1.3 identities, fixture target/actor gate, source digest,
  idempotent source identity, and no provider invocation

2026-10-22：零候選固定通知從有效 rules／templates 與 fixture 移除，new candidate validation 拒絕恢復；historical grammar readback 仍可解析舊定義，專用刪除 writer 可取消其 intent／task，歷史不重寫。

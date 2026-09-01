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
- `scripts/bootstrap_line_configuration.py`
- `config/notification_rules.json`
- `config/message_templates.json`

## Consumers
- existing LINE notification Query / Preview / Apply routes and typed views

## Verification
- canonical test root: `tests/domains/external-integration/subsystems/line/modules/notification-baseline-bootstrap/`
- acceptance: exact 26 §1.3 identities, fixture target/actor gate, source digest,
  idempotent source identity, and no provider invocation

# WP56 UI idempotency snapshot evidence 025

- Receipt: `validation/receipts/WP56-UI-IDEMPOTENCY-SNAPSHOT-025.json`
- Scope: existing contract match panel signed-return controls only.

The panel stores both the sent document version and command idempotency key with
the selected upload signature. Repeated submission of that unchanged snapshot
uses the same key and therefore reaches the server replay contract. A changed
file, or a stale-version response that clears the snapshot, produces a new key
and requires the current document version.

Focused regression passed: `7 passed`.

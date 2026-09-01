# Module: safe-review-link

## Parent

- domain: `external-integration`
- subsystem: `line`

## Responsibility

Own the short-lived, one-time safe review-link transport root, its masked
readback, receipts, audit events, and committed local outbox intent. Runtime
alert targets remain the source of target identity/version; LINE never writes
those roots or performs provider delivery.

## Implementation

- `subsystems/line/safe_review_link_contracts.py`
- `subsystems/line/safe_review_link_application.py`
- `db/schema_parts/1023_task96_line_safe_review_link_matching_outbox_v1.sql`
- `infrastructure/mysql/line_safe_review_link_repository.py`
- `api/routes/runtime_health.py`
- `api/schemas/runtime_health.py`
- `ui_react/src/api/line_safe_review_link/`
- `ui_react/src/components/SafeReviewLinkWorkbench.tsx`

## Persistence

- `db/schema_parts/1023_task96_line_safe_review_link_matching_outbox_v1.sql`
- additive release manifest and descriptor under `db/migration_releases/`

## Safety boundary

Only token digests are persisted. Redeem rechecks actor, capability, target,
version, and expiry under row lock; replay, expiry, revocation, wrong actor,
and stale target are closed typed failures. Provider send is outside this
module's effect ceiling.

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/external-integration/subsystems/line/modules/safe-review-link/`
- test_root: `ui_react/src/tests/safe_review_link_workbench.test.tsx`

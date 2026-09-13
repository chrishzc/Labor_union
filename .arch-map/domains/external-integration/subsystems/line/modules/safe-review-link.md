# Module: safe-review-link

## Parent

- domain: `external-integration`
- subsystem: `line`

## Responsibility

Own the short-lived, one-time safe review-link transport root, its masked
readback, receipts, audit events, and committed local outbox intent. Runtime
alert targets remain the source of alert-target identity/version; this module
reads those roots but never changes them or performs provider delivery.
Business review facts and approval remain with their owning Domain.

## Implementation

- `subsystems/line/safe_review_link_contracts.py`
- `subsystems/line/safe_review_link_application.py`
- `db/schema_parts/1023_task96_line_safe_review_link_matching_outbox_v1.sql`
- `infrastructure/mysql/line_safe_review_link_repository.py`
- `subsystems/line/runtime_alert_target_application.py::_target_view` — existing runtime owner version interpretation.
- `api/routes/runtime_health.py`
- `api/schemas/runtime_health.py`
- `ui_react/src/api/line_safe_review_link/`
- `ui_react/src/components/SafeReviewLinkWorkbench.tsx`

## Persistence

- `db/schema_parts/1023_task96_line_safe_review_link_matching_outbox_v1.sql`
- additive release manifest and descriptor under `db/migration_releases/`
- The PR #299 correction uses the existing immutable `issued` event payload:
  `runtime_alert_target.target_id` and `runtime_alert_target.current_version`.
  It adds no table or public request field. `get_issued_runtime_target()` reads
  that evidence back from `line_safe_review_link_events`.

## Safety boundary

Only token digests are persisted. A fresh Issue reads and locks the unique
active runtime alert group in the same UoW as the link, event, receipt, and
outbox. A first Redeem locks the link and rechecks token, actor, capability,
path, expiry, and the freshly read runtime group id/opaque version against
its immutable issuance evidence. The public numeric `target_version` /
`current_target_version` fields are still compared, but are not a substitute
for the runtime owner's opaque version or for a business owner's version check.

A changed group, disabled group, or changed version after same-group
reactivation rejects the old link. A pre-correction link without issuance
owner evidence must be reissued; do not invent or backfill that evidence.
An exact command replay returns its existing receipt, not a new redemption.
Provider send is outside this module's effect ceiling.

The ordinary `/line-mobile-admin?target=customer_service` URL now included in
Customer Service alerts is authenticated navigation, not an issued one-time
Safe Review Link. Its presence does not prove the alert-to-one-time-link
acceptance in specification 26 §9 / §9.1. That end-to-end flow and the business
review's Preview/Apply/readback must be verified separately.

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/external-integration/subsystems/line/modules/safe-review-link/`
- test_root: `ui_react/src/tests/safe_review_link_workbench.test.tsx`
- shared regression: `tests/domains/external-integration/subsystems/line/subsystems/test_line_m4_continuation_regressions.py` — actual owner version drift, disabled/reactivated group, missing issuance evidence, and unchanged-target redemption.
- evidence: PR #299 code baseline `4eb58e07e94660308ba8afd05d39931f0301fdf1`; shared regression run `34733277249` / job `103659935152`. The 29 M4 regressions are part of the recorded 53-test run, not 53 tests of this module. Owner/UoW substitutes and SQLite adapter checks do not establish MySQL locking, mobile, provider, or full one-time-link flow acceptance; those remain `NOT_RUN` for this correction.

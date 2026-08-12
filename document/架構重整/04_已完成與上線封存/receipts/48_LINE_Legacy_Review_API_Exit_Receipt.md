---
doc_type: legacy-exit-receipt
date: 2026-08-09
status: implemented-and-verified
scope: LINE legacy review APIs only
---

# LINE Legacy Review API Exit Receipt

## Closed routes

The following unauthenticated/internal-key legacy routes in `line/line_bot.py`
now return HTTP 410 with `line_review_api_retired` and the replacement path:

- `GET /api/line/rebind_requests`
- `POST /api/line/rebind_requests/approve`
- `POST /api/line/rebind_requests/reject`
- `GET /api/line/staff/review-requests`
- `POST /api/line/staff/review-requests/{request_type}/{request_id}/approve`
- `POST /api/line/staff/review-requests/{request_type}/{request_id}/reject`

Their single replacement is the authenticated typed router
`/api/v1/line/review-requests` in `api/routes/line_reviews.py`. It applies
role authorization, typed decision request validation, audit data, and the
`subsystems.line.identity_review_workflow` transaction.

## Evidence

- `tests/test_line_legacy_review_routes_retired.py` asserts every closed route
  returns HTTP 410 and points to the typed replacement.
- Existing Streamlit LINE review management uses `LineAdminApiClient` typed
  review methods, not any closed path.
- Focused LINE tests passed on 2026-08-09: `13 passed`.

## Explicitly not closed

These direct writers remain reachable and must not be labelled exited yet:

- `line_register`: creates `clients` and `beclass_records`; it needs a typed
  Case Import / Client onboarding Apply replacement.
- `set_line_user_role`: writes `line_users`; it needs a typed identity-admin
  Apply replacement with authorization and audit ownership.
- Webhook follow/unfollow/onboarding: still owns direct transport and identity
  writes; it requires separate typed ingress/identity workflows.

This receipt does not claim the whole `line_bot.py` writer inventory has
exited. It only proves the duplicate review mutation entrypoints are no longer
callable.

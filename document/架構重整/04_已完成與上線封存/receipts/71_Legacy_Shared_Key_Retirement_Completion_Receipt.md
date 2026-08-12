---
doc_type: completion-receipt
archive_id: ARCH-20260812-052
date: 2026-08-12
owner: Global / Access Control
work_package: document/架構重整/04_已完成與上線封存/work_packages/71_INTERNAL_API_KEY_Retirement_Work_Package.md
status: completed
---

# WP71 Legacy Shared Key Retirement Completion Receipt

## Scope completed

The active runtime, callers, configuration examples, tests, and current documentation no longer read, require, generate, send, or validate the retired shared-secret mechanism. Existing Admin Session, capability, development bypass, and LINE signature boundaries remain the controlling mechanisms.

## Evidence

- Focused regression: 44 passed.
- Direct regression: 14 passed.
- OpenAPI route regression: 1 passed.
- Retired shared-secret marker scan: 0 active-content matches.
- Chrome UI smoke: Orders, Finance, Anomaly Center, Data Browser, System Status, Operations, Calendar, Forms/Resume, and LINE Management rendered without browser console errors or API error displays.
- The Forms/Resume and LINE Management pages were retested after a 10-second settle window. The previously observed stale calendar content did not remain, indicating a Streamlit rerun/component-cache timing observation rather than a reproducible page failure.

## Full-suite result and residual risk

The full suite completed with 1785 passed, 88 skipped, and 37 failed. The failures were pre-existing or outside this work package: unavailable MySQL test environment, stale entrypoint/validation/receipt baselines, retired-route expectations, missing operator script, stale UI/helper test assumptions, and incomplete fakes. They do not exercise the retired shared-secret flow and were not modified to avoid scope expansion.

## Limits

UI testing covered read and preview-safe rendering only. Data-changing actions, including apply, send, create, reconcile, publish, and delete, were intentionally not invoked because they require explicit mutation approval and controlled data.

## Release and restore

- Deployed at: not applicable; no production secret-store mutation or deployment was performed.
- Release identity: not applicable; source retirement and local regression evidence only.
- Successor: `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md` and the existing Admin Session/capability contract.
- Restore triggers: discovery of a deployed machine caller that only has the retired secret boundary; regression in Admin Session/capability access; regression in LINE signature validation.

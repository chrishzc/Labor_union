---
doc_type: verification-receipt
declared_status: completed
date: 2026-08-12
work_package: 66_Scheduling_Leave_Substitution_Calendar_Preview_Work_Package
---

# WP66 Scheduling Leave Preview Receipt

- Focused regression: `16 passed` for Calendar filtering, leave workflow and API contract smoke tests.
- API: case `115000008`, assignment `232`, schedule `10569`, date `2026-07-21` returned HTTP 200 with 36 Calendar day cells.
- Readiness: `blocked` with `client_finance_bootstrap_required`; Preview batch count remained `0 -> 0`.
- UI: Chrome selected the case and assignment, added the leave item, generated Preview, rendered the blocker, and observed disabled Apply.
- Safety: no Apply request was sent and no leave-substitution batch was persisted.

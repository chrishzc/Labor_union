# WP68 Matching Schedule Confirmation Focused Receipt

- Date: `2026-08-12`
- Scope: confirmed service dates, current schedule snapshot, recipient confirmations, and the
  formal assignment gate.
- Environment: local test database; `LINE_CHANNEL_ACCESS_TOKEN` was not invoked and no provider
  delivery worker was run.

## Executed evidence

1. Chrome opened local Order Management, selected case `115000002`, rendered 25 editable service
   dates, generated the Sunday-to-Saturday Preview, and applied it. The API query afterwards
   returned `current_version=3` and `current_date_count=25`.
2. Test case `WP56-7B82E214D8E8`, active matching plan `18`, confirmed date version `2`, had a
   LINE binding for its customer and its single caregiver. Explicit Send created current snapshot
   `2`, customer recipient `3`, caregiver recipient `4`, and both delivery statuses `queued`.
3. Manual confirmation of recipient `3` left `gate_passed=false`; confirmation of recipient `4`
   changed it to `gate_passed=true`.
4. After manually revoking customer recipient `3`, direct formal Assignment Plan Preview returned
   typed `matching_schedule_two_party_confirmation_required` (HTTP 422). Reconfirming recipient
   `3` restored `gate_passed=true`.
5. Focused regression command:

```powershell
.venv\Scripts\python.exe -m pytest -W error `
  tests/test_service_date_confirmation.py `
  tests/test_matching_schedule_confirmation.py `
  tests/test_matching_schedule_confirmation_api_client.py `
  tests/test_matching_center_no_bootstrap.py `
  tests/test_segmented_availability_coverage.py `
  tests/test_assignment_plan_workflow.py `
  tests/line/subsystems/test_line_matching_postback_stage7.py `
  tests/line/subsystems/test_line_runtime_stage3.py -q
```

Result: `26 passed`.

6. The schedule-confirmation UI uses `MatchingScheduleConfirmationApiClient` and Pydantic views;
   it no longer passes raw transport dictionaries into its renderer. A fresh Streamlit rerun reloads
   the active matching plan from the server rather than relying only on session state.
7. Current snapshot `6` created recipient-level canonical delivery tasks `90` and `91`. After
   controlled local task-state simulation, the schedule-confirmation API returned one recipient as
   `failed` and the other as `sent`, proving the UI view projects the canonical worker-owned task
   status rather than retaining a stale recipient status.
8. Schedule-confirmation Query now exposes the latest confirmation event's source, UTC time, and
   rejection reason. The typed UI client rejects malformed data and renders the reason for manual
   follow-up; its focused regression is recorded with the next WP68 focused run.
9. In-app Browser opened Matching Center case `115000015`. The default single-caregiver flow
   rendered caregiver `#531` with backend coverage `2026-12-06` through `2026-12-20 (15/15)`;
   it had no multi-segment controls or traceback. The UI created a one-segment matching plan and
   rendered the contact/date-table workspace. Before Orders confirmed the dates, the date-table
   panel remained fail-closed with `confirmed_service_dates_required`; its typed client maps this
   to the operator message that service dates must first be confirmed in Order Management.
10. The Browser test did not press `發送目前服務日期表`: that command creates delivery tasks that
    may later cause an external LINE send. Existing local receipt evidence covers snapshot,
    recipient confirmation and assignment-gate behavior without invoking a provider worker.

11. After the in-app Browser fixes, the WP68 focused command was rerun with the matching-center
    actor and typed coverage contract tests included. Result: `30 passed` under `-W error`.

12. A continuation attempt used Order Management UI for case `115000015` to confirm dates for the
    newly created matching plan. That test case has no formal roots. Its operator bootstrap control
    accepted the required reason but produced neither a receipt nor an error and remained
    `not ready`; no direct database bypass was used. This is an existing Order bootstrap live-drift
    outside WP68's Matching UI write set, so it blocks only the same-case end-to-end UI continuation.

## Remaining evidence required before WP68 archive

- Chrome validation of the matching-center schedule-confirmation panel, including Send status and
  staff manual override controls. The Chrome connector session was able to validate Order
  Management but could not navigate a newly-created blank tab to the local Streamlit URL.
- Broader repository regression failures outside WP68 must be separately reconciled before a full
  `pytest -W error` closeout can be claimed; the focused WP68 command above is green.
- Archive-gate manifest update after those remaining evidence items are closed.

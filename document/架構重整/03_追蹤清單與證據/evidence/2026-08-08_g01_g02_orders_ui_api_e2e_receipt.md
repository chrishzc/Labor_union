# G01/G02 Orders UI/API/MySQL E2E Receipt

- Observed: 2026-08-08
- Isolation: randomly named disposable local MySQL database; dropped in the runner `finally` block.
- Tests: `test_g01_terms_panel_uses_real_http_preview_and_apply` and `test_g02_actual_start_panel_uses_real_http_preview_and_apply`.
- Result: the two new UI/API cases plus their shared G03/G04 regression cases passed: `4 passed`.

## G01 trace

1. The actual Orders Terms panel changes daily service hours from 8 to 9.
2. Its API client submits typed HTTP Preview and Apply with the server-issued versions and fingerprint.
3. Orders, Scheduling, Client Finance and Payroll each persist one canonical change and source outbox event.

Decision recorded: Terms Apply does not directly create an anomaly. If the rebuilt schedule has a real coverage risk, the existing Scheduling coverage scan owns creation of the alert. This direct Terms UI/API trace therefore completes G01.

## G02 trace

1. The actual Actual Start panel changes the confirmed start date by one day.
2. Its API client sends typed HTTP Preview and Apply using request-scoped application dependencies and the server-issued versions and fingerprint.
3. Orders, Scheduling, Client Finance, Payroll and Lifecycle each advance once; each source outbox is persisted once.

The fixture records the client as `一般市民`, a valid Client Finance identity root, so the real API validates the same subsidy-coverage contract as production.

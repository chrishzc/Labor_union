# WP56 UI Anomaly Reopen 001 v6

- Date: 2026-08-12
- UI: `http://127.0.0.1:8501`
- Scenario: `UI-ANOM-REOPEN-001`
- Case: `WP56-7E8BEB213973`
- Receipt: `validation/receipts/UI-ANOM-REOPEN-001-UI-042.json`

Chrome re-observed the open service-staff alert, its `SCHEDULE-006` mismatch
classification, and the `前往正式人力配置` repair route. The scenario-specific
verifier confirmed the durable timeline `claim`, `resolve`, `reopen`,
`auto_resolve`, `reopen` and retained open status.

The repair route's formal Assignment Plan outcome is recorded separately in
`UI-SCH-ASSIGN-001-UI-042.json`: one durable job completed at generation `1`
and replayed the same command without a second assignment.

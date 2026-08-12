# WP56 UI SCH Assign 001 v6

- Date: 2026-08-12
- UI: `http://127.0.0.1:8501`
- Scenario: `UI-SCH-ASSIGN-001`
- Case: `WP56-7E8BEB213973`
- Replay receipt: `validation/receipts/UI-SCH-ASSIGN-001-UI-042.json`

Chrome opened the `SCHEDULE-006` service-staff alert and used its formal
staffing repair action. The Case Staffing surface selected the same case, then
submitted a one-segment Assignment Plan for staff `8892` from `2031-10-13`
through `2031-10-17`.

The controlled UI accepted job `dfcdd774-510f-4ecb-8f25-21e7f365ce76`. After
the durable worker completed it, the UI re-observed generation `1` and the
single created assignment key `WP56-7E8BEB213973:g1:a1`. The terminal UI then
rendered `重送相同 Apply 請求`; invoking it retained the same job and receipt,
with no second assignment.

The scenario's DB oracle passed all normal-chain checks: four archived digests,
staff/client signing, commitment conversion, settled deposit, one assignment,
and five schedule days. The older v5 evidence remains a historical
fail-closed observation; this v6 document is the successful repair chain.

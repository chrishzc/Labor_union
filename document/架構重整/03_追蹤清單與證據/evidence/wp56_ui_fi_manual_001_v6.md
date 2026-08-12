# WP56 UI FI Manual 001 v6

- Date: 2026-08-12
- UI: `http://127.0.0.1:8501`
- API: `http://127.0.0.1:8000`
- Dataset: `lu_test_dataset_contract_signing_v4`
- Scenario: `UI-FI-MANUAL-001`
- Result: verified

The scenario used a fresh canonical ingestion seed, batch
`finance-import-batch:33` / row `finance-import-row:87`. Its initial
classification was `non_business_review` / `manual_review`, with a 16000 NTD
incoming bank fact and an active manual-review anomaly.

Chrome selected that anomaly and opened the anomaly-owned manual correction
form. The UI Preview allocated exactly 16000 NTD to
`client-obligation:WP56-20DF22A30D53:deposit`, retained the immutable bank row,
and required two ordered operator evidence references. Chrome Apply submitted
job `c35a1a2e-2ade-4751-b0a9-a5b3b0caaf39`; the official durable worker completed
it once.

Chrome then used the terminal same-command replay control without altering
Preview, fields, reason, or command identity. The UI returned the same job id.
Database re-observation found one formal correction event, one ledger/reconciliation
receipt chain, one correction receipt, and one durable job; the manual-review
alert was resolved. Replay added none of those records.

- Replay/re-observe screenshot:
  `wp56_ui_fi_manual_replay_reobserve_039.png`
- Machine-readable receipt:
  `validation/receipts/UI-FI-MANUAL-001-UI-039.json`
- Previous DB oracle: `validation/receipts/UI-FI-MANUAL-001_v4.json`

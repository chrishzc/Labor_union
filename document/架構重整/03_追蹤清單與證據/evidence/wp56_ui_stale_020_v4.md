# WP56 UI Stale 020 v4

- Date: 2026-08-11
- Database: `lu_test_dataset_contract_signing_v4`
- Case: `WP56-FD32A3DB20D6`
- UI: `http://127.0.0.1:8511`

The scenario created a replacement client template document after the UI had
loaded the prior version. The browser automation reached a final timeout, so it
does not prove that the stale typed code was visible before refresh.

Database roots after the browser flow show three sent events, two signed-return
events, and a populated `contract_identity`. This proves the repaired client
signing completed but is not a substitute for the missing browser stale
assertion.

Receipt: `validation/receipts/WP56-UI-STALE-020_v4.json`.

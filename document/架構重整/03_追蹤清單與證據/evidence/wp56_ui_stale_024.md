# WP56 UI stale-version recovery evidence 024

- Receipt: `validation/receipts/WP56-UI-STALE-024_v4.json`
- Dataset: `lu_test_dataset_contract_signing_v4`
- Case: `WP56-EFE834105638`
- Browser: existing Streamlit UI on `http://127.0.0.1:8512`

The browser first selected and uploaded a client signed-return file while document version 54 was current. A controlled application-path send created replacement version 55 before the UI submission. The UI displayed typed error `contract_document_version_stale`; the database still contained only the staff signed-return event and no contract identity.

The same file was then submitted from a fresh current-version UI state. The UI displayed contract completion, the database contained two signed-return events, and `orders.contract_identity` was populated. This proves the stale rejection is non-mutating and the user can recover using the current document version.

Screenshots:

- `wp56_ui_stale_024_stale.png`
- `wp56_ui_stale_024_repaired.png`

# WP56 UI client signed-return evidence 027

- Receipt: `validation/receipts/WP56-UI-CLIENT-SIGNED-RETURN-027_v4.json`
- Case: `WP56-7C9CF2503A5B`
- Dataset: `lu_test_dataset_contract_signing_v4`

The operator submitted a client signed-return through the existing Orders
contract panel. The UI reported document version 60, signing event 57, and
completed Contract Completion. The database oracle then confirmed two signed
returns, four document versions, a populated contract identity, and one client
obligation. The order lifecycle remains `洽談中` because deposit settlement is
an independent fact and is not created by client signing.

Screenshot: `wp56_ui_client_signed_return_027.png`.

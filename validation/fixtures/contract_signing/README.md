# Contract signing fixtures

This directory contains the minimal, versioned spreadsheet inputs for WP56 contract-signing tests.

| File | Use |
| --- | --- |
| `staff_contract_upload.xlsx` | Staff contract send, signed-return, MIME/size allowlist, and replay tests. |
| `client_contract_upload.xlsx` | Client contract send, signed-return, MIME/size allowlist, and replay tests. |

Do not add generated contract documents, stale-version variants, browser downloads, or operator diagnostics here. Those are runtime artifacts and belong under the ignored `runtime_data/` directory.

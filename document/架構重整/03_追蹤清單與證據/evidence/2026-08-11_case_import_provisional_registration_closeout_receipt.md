---
doc_type: validation-receipt
declared_status: completed
date: 2026-08-11
owner: case-import
work_package: 49
---

# Case Import provisional registration closeout receipt

## Scope

Case Import consumes a selected submitted LINE provisional registration in its owning outer Unit of Work. It upgrades the existing client, creates the formal Order/bootstrap roots, binds the existing BeClass record, appends one issuance event and stores a replayable receipt.

## Command and result

```text
.venv\Scripts\python.exe -m pytest tests/test_case_import_workflow.py tests/test_provisional_line_registration.py tests/test_case_import_disposable_mysql_e2e.py -q
16 passed in 1.44s
```

The disposable MySQL suite used the locally configured `lu_test_*` database and verified:

- existing Case Import roots and replay remain valid;
- selected registration transitions `submitted` to `case_issued`, clears active LINE identity, upgrades the existing client and binds BeClass `query_no`;
- same idempotency key replays one receipt and one issuance event;
- injected failure rolls back Client, Order, BeClass, registration and issuance-event writes;
- two different idempotency keys competing for one registration produce exactly one success and one typed conflict.

## Source digests

| Path | SHA-256 |
|---|---|
| `domains/case_import/case_import.py` | `7bcef83ecf84e64c18d640cc1f94a324e14368c8b9928f49e1a363e5a569475f` |
| `subsystems/case_import/case_import_workflow.py` | `f23df774b58df6c20cae0ed84cca813667cab68d50786d91de5c64aba5c3eeaf` |
| `infrastructure/mysql/case_import_repository.py` | `5e8c6560fd2a3d01c5d760659f007d6bfadad895c59b061de96fe6ddcaf59ea6` |
| `db/schema_parts/165_provisional_registration_case_issue.sql` | `517c43e8ae428a3cf44c861e857dfaf3dd2812b14db40ef5af61737fb254f6ca` |
| `tests/test_case_import_workflow.py` | `89da714c423b192a3470aad561eb31223d0c5fa173873461e3b1b58b10200871` |
| `tests/test_case_import_disposable_mysql_e2e.py` | `a2031ca38ff8f7a8428cc2440e07b52819d8a06805eb27701e1821a80d32cdd9` |

## Boundary

This receipt does not authorize production deployment, production schema application, data migration or any external LINE delivery.

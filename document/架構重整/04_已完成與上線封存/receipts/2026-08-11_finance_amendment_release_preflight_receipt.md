# Finance Amendment release preflight receipt

- Date: 2026-08-11T14:27:53+08:00
- Scope: Work Package `55` and release-readiness `57` only.
- Result: local artifact preflight passed; the approved additive schema was applied to the existing isolated test database; no production execution occurred.

## Verified local artifacts

| Artifact | SHA-256 |
|---|---|
| `db/schema.sql` | `bc00526f7f7af488a080503afe71b0348a58c68551024d5a94d86bca983593b0` |
| `db/cutover_releases/labor_union_validation_schema_v1.json` | `d2a2384e7e17feeda99777046c82b317f1a191581e4102e921f343f3cf4690a3` |
| `db/releases/labor_union_validation_schema_v1.sql` | `e6c0980cdae01af1e107674b934d40565d2587029c432d3b2bc4508e3c5f4c6a` |

The manifest reports 95 ordered schema parts and its own ordered digest
`e9a6f4103f06cc4762f04eea385dc163325193a6c35b5782346fb3ab317172d4`.

## Commands run

```text
.venv\Scripts\python.exe scripts\verify_validation_schema_manifest.py
# {"valid": true, "errors": []}

.venv\Scripts\python.exe scripts\build_validation_schema_release.py --check
# exit 0
```

## Execution boundary

The reviewed manifest declares its purpose as rebuilding an isolated `lu_test_*` schema and
rejects non-`lu_test_*` database names. It is therefore validation evidence only, not a
production schema-release artifact.

## Existing test-database execution

- Target database: `lu_test_dataset_contract_signing_v4`
- Server: MySQL `8.0.46`
- Target classification: isolated test schema; not a production target.
- Apply set: `167_client_finance_overage_dispositions.sql` through
  `178_government_subsidy_overpayment_apply_receipts.sql`, in numeric order.
- Apply result: all 12 additive parts succeeded; the three Finance Amendment root tables are
  present and trigger count became `246`.

Postcheck against that database passed:

```json
{
  "valid": true,
  "contract_identity_present": true,
  "trigger_count": 246,
  "v_order_details_row_count": 55,
  "errors": []
}
```

With the same explicitly selected test-database environment, the WP 55 core focused suite passed:

```text
56 passed in 6.11s
```

The suite covered client refund underpayment/overage/recovery, staff payout difference and
overpayment recovery, government subsidy overpayment and workflow, recovery-context assembly, and
the typed finance-anomaly UI boundary. It did not perform a payment transfer.

No production target environment, production database identity, operator, planned window,
backup/restore owner, or immutable production candidate revision was supplied or inferred. No
production deployment, production database connection, switch, restart, smoke, or accountant
transfer was performed.

The current repository worktree is dirty, so its `HEAD` (`1f93a5459dc80e7ab4341b21abc0535dbdcecd02`)
cannot by itself identify a releasable production artifact. A future execution record must bind an
explicit immutable candidate revision and a production-safe additive schema manifest before the
approved cutover is intentionally started.

## Browser UI validation on an isolated test schema

- Target database: `lu_test_finance_ui_20260811` (fresh isolated `lu_test_*` schema).
- Scenario: projected active `GOVSUB-006` for test overpayment identity
  `government-overpayment-e2e:browser-ui` with amount `500` NTD.
- Operator path: Streamlit **異常警示中心** → **帳務異常** → **政府補助溢撥待處置** →
  **處置政府補助溢撥** → **建立政府退款應付**.
- Preview result displayed by the UI: `本次處置 500 元，處置後剩餘 500 元。`
- Apply result displayed by the UI: `已完成處置；剩餘 500 元。`

The post-Apply read-only database check found the overpayment in `return_payable` status with
`remaining_amount_ntd = 500`, `projection_version = 2`, and exactly one test
`government_overpayment_return_payables` row. This creates a test refund-payable detail only; it
does not create or execute a bank transfer.

## UI-test closeout

The 57 test closeout was rerun against the existing isolated test schema
`lu_test_dataset_contract_signing_v4` after the browser validation. The focused Finance Amendment
suite completed with `56 passed in 4.86s`. It covers client refund underpayment/overage/recovery,
staff payout difference and recovery, government overpayment workflows, root-fact recovery context,
and the typed finance-anomaly UI boundary. Together with the interactive `GOVSUB-006` browser
Preview/Apply above, this closes the approved test-environment acceptance scope; it does not
constitute a production deployment or a bank transfer.

# WP24 MySQL Adapter Mutation Exit — Fresh Reconciliation Receipt

Date: `2026-08-12`

## Scope

This is a source and regression reconciliation for Work Package 24. The later reviewed-disposition
reconciliation changes evidence only; it does not authorize schema, production-data, deployment,
external-provider, or writer removal.

## Adapter exit evidence

| Check | Result |
| --- | --- |
| `infrastructure/mysql/mysql_adapter.py` SHA-256 | `1397a020a127635d7307cf17b7142002271dfb20efee2e2a6964b354c808b062` |
| Writer Inventory v3 candidate findings for `mysql_adapter.py` | `0` |
| Static `INSERT` / `UPDATE` / `DELETE` / `REPLACE` / DDL mutation tokens in adapter | `0` |
| Static `.commit()` calls in adapter | `0` |
| Callers of retired adapter mutation symbols | `0` |
| Replacement regression | `5 passed` |

The caller scan covered the original WP24 mutation symbols:
`create_order`, `save_order_rest_dates`, `add_or_update_holiday`,
`delete_holiday`, `update_order_full_details`, `update_table_row`,
`mark_resume_sent`, `mark_resume_sent_for_case`, `reply_matching_inquiry`, and
`update_matching_info_sent`.

The focused regression command was:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_admin_command_workflows.py tests/test_data_browser_admin_route.py tests/test_order_full_details_entry_retirement.py --basetemp .pytest_tmp/wp24-closeout -q
```

Result: `5 passed in 0.46s`.

## Global inventory reconciliation

The fresh candidate generation and candidate validator ran successfully:

```powershell
.venv\Scripts\python.exe scripts/generate_writer_inventory_v3_candidate.py
.venv\Scripts\python.exe scripts/validate_writer_inventory_v3_candidate.py
```

Fresh candidate: `1,047` findings, `1,028` unique identities, `209` unresolved.
The previous reviewed disposition had `660` identities and was stale.

The first disposition reconciliation command failed closed:

```powershell
.venv\Scripts\python.exe scripts/reconcile_writer_inventory_v3_dispositions.py
```

Failure: `KeyError: 'api/dependencies/line_runtime.py'`. The script has no
approved review metadata for this merge-introduced writer path. Classifying it
or the other `368` unmatched identities requires a separate global inventory
reconciliation scope; WP24 must not infer their owners or replacement evidence.

The reconciler was then made fail-closed for unknown paths: each candidate without existing reviewed metadata
becomes `owner_review_required` plus `needs_decision`, never a guessed owner or removal candidate. It was
rerun successfully and produced 1,028 reviewed records: 474 `retain_canonical`, 207 `retain_restricted`,
and 347 `needs_decision`. The `needs_decision` queue is now exclusively tracked by WP63.

```powershell
.venv\Scripts\python.exe scripts\reconcile_writer_inventory_v3_dispositions.py
.venv\Scripts\python.exe scripts\validate_writer_inventory_v3_dispositions.py
.venv\Scripts\python.exe -m pytest tests/test_writer_inventory_v3_dispositions.py -q --basetemp .pytest_tmp/wp24-reconcile
```

Result: validator passed; `3 passed`.

## Outcome

WP24's adapter-specific production exit is proven and the inventory coverage gate is current. The unresolved
global owner review is separately active in WP63; it is not a WP24 blocker. WP24 is eligible for completion
and archival.

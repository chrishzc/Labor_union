---
doc_type: decision-package
declared_status: completed
---

# MySQL Adapter Mutation Exit Decision Package

## Scope and evidence

- Status: `completed`.
- Source: `infrastructure/mysql/mysql_adapter.py`
- Fresh SHA-256: `1397a020a127635d7307cf17b7142002271dfb20efee2e2a6964b354c808b062`
- 2026-08-12 fresh static scan: zero `mysql_adapter.py` mutation findings, zero mutation-SQL tokens, zero `.commit()` calls, and zero callers for every retired adapter mutation symbol.
- Focused replacement regressions pass (`5 passed`); see [WP24 fresh reconciliation receipt](../receipts/2026-08-12_wp24_mysql_adapter_mutation_exit_reconciliation_receipt.md).
- Inventory v3 reconciliation is current: the fresh candidate has 1,047 findings / 1,028 identities and
  the reviewed disposition has all 1,028 identities. 347 merge-introduced or unclassified identities are
  explicitly `needs_decision`; they have no inferred owner and no removal authority.
- The adapter remains a live query/connection dependency. This package covers only its mutation functions.

## Completed outcome and separated follow-up

The adapter-specific exit is proven and the global reviewed-disposition layer is reconciled against the fresh
candidate set. The 347 `needs_decision` records are carried by
`63_Global_Writer_Inventory_v3_Owner_Review_Work_Package.md`; they are an explicit global owner-review queue,
not a hidden blocker or an adapter-mutation removal authorization. No removal authority is created by this
package.

## Caller disposition

| Mutation group | Live caller | Decision | Required replacement / exit condition |
|---|---|---|---|
| Matching communication and reply writers | Legacy API routes are 410; no live writer caller | `remove-candidate` | Re-scan caller=0 and delete exact functions with their direct tests only. |
| `create_order` and client-payment due-date backfill | No live writer caller; public backfill route is 410 | `remove-candidate` | Re-scan caller=0; retain no generic write compatibility path. |
| `save_order_rest_dates` | `scripts/generate_fake_data.py` only | `migrate-then-remove` | Fake-data must seed through the canonical Scheduling fixture/workflow in a disposable DB. |
| `add_or_update_holiday`, `delete_holiday` | `api/routes/holidays.py` | `migrate-then-remove` | Typed Scheduling Holiday Preview/Apply command with actor, capability, idempotency, audit and cache invalidation. |
| `update_order_full_details` | `api/routes/orders.py` | `migrate-then-remove` | Typed Orders details command with field authority, version/conflict and lifecycle guard. |
| `update_table_row` | `subsystems/access/data_browser_maintenance.py` | `migrate-then-remove` | Per-table typed Access maintenance commands; generic cross-table writer must not survive. |

## Dependency-cut order

1. Remove caller-zero matching, order-create and due-date functions after a source-hash and caller recheck.
2. Migrate fake-data rest-date seeding to the Scheduling-owned test fixture path.
3. Migrate Holidays to Scheduling typed command/API/UI.
4. Migrate Orders full-details to an Orders typed command/API/UI.
5. Split Data Browser generic table patch into explicit Access maintenance operations.
6. Re-scan Inventory v3; remove the exact adapter mutation functions only when all external callers are zero.

## Non-negotiable verification

- No direct `mysql_adapter` mutation call remains outside its migration slice.
- Every migrated command has one outer UoW owner, actor/capability, idempotency and typed error path.
- Fresh source, focused replacement tests, disposition validator and inventory pytest pass; Inventory v3 may
  only lose the approved exact findings.
- No schema/data/deployment mutation belongs to this decision package.

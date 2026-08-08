---
doc_type: decision-package
declared_status: "decision-ready; no code removal in this package"
---

# MySQL Adapter Mutation Exit Decision Package

## Scope and evidence

- Status: `decision-ready; no code removal in this package`.
- Source: `infrastructure/mysql/mysql_adapter.py`
- Fresh SHA-256: `159865EA0FD3A246A0387FBB57C8CE4E78C6F950BF5AE48733C671617CD9E76F`
- Inventory v3: 29 mutation findings, all `blocked` and `migrate_then_remove_candidate`.
- The adapter remains a live query/connection dependency. This package covers only its mutation functions.

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
- New source, focused tests and full pytest pass; Inventory v3 may only lose the approved exact findings.
- No schema/data/deployment mutation belongs to this decision package.

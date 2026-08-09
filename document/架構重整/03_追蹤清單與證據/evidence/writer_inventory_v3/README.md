# Writer Inventory v3 Disposition Contract

`writer_inventory_v3_candidate.*` is machine-generated discovery evidence. It
always remains `blocked` and cannot authorize a writer removal.

`writer_inventory_v3_disposition.*` is the reviewed layer. Every record must
reference an unchanged candidate identity and fingerprint. A candidate scan
hash change makes the reviewed layer stale until it is revalidated.

The allowed final dispositions are `retain_canonical`, `retain_restricted`,
`migrate_then_remove`, `gone`, and `needs_decision`. Only `gone` may set
`approved_to_remove` to true, and it requires a non-empty replacement receipt.

The current reviewed slice resolves all 17 findings whose path could not
determine an owner, all 20 current migrate-then-remove candidates, and 50
unreachable findings in the frozen fake-data fixture (47 unique identities),
and 30 Government Subsidy canonical repository identities, plus 65 Client
Finance repository/workflow identities. It has 614 disposition records, including 78 Orders lifecycle/terms identities:
48 canonical persistence or transaction-boundary operations and 30 restricted root-fact queries, plus 30 Payroll rebuild/adjustment/terms unique identities:
24 canonical persistence or transaction-boundary operations and 6 restricted root-fact or reconciliation queries. The legacy Holiday, client-name, and Data Browser
generic adapter writers were removed after their typed replacement was
implemented; absent candidates are intentionally not retained as disposition
records because the validator requires every record to reference a current
candidate identity. The remaining 90 candidate findings stay blocked.

# Writer Inventory v3 Disposition Contract

`writer_inventory_v3_candidate.*` is machine-generated discovery evidence. It
always remains `blocked` and cannot authorize a writer removal.

`writer_inventory_v3_disposition.*` is the reviewed layer. Every record must
reference an unchanged candidate identity and fingerprint. A candidate scan
hash change makes the reviewed layer stale until it is revalidated.

The allowed final dispositions are `retain_canonical`, `retain_restricted`,
`migrate_then_remove`, `gone`, and `needs_decision`. Only `gone` may set
`approved_to_remove` to true, and it requires a non-empty replacement receipt.

The current reviewed layer has 1,027 disposition records for all 1,027 unique identities in the fresh
candidate. WP63 resolved the complete owner-review queue: 745 are `retain_canonical`, 278 are
`retain_restricted`, 4 are `migrate_then_remove`, and 0 remain `needs_decision`. No record is approved to
remove. The four migration candidates are the legacy client identity direct-update boundary and the
unmounted staff-leave review direct transaction; each requires its own approved retirement package before
code changes. The legacy Holiday, client-name, and Data Browser generic adapter writers were removed after
their typed replacement was implemented; absent candidates are intentionally not retained as disposition
records because the validator requires every record to reference a current candidate identity.

# Writer Inventory v3 Disposition Contract

`writer_inventory_v3_candidate.*` is machine-generated discovery evidence. It
always remains `blocked` and cannot authorize a writer removal.

`writer_inventory_v3_disposition.*` is the reviewed layer. Every record must
reference an unchanged candidate identity and fingerprint. A candidate scan
hash change makes the reviewed layer stale until it is revalidated.

The allowed final dispositions are `retain_canonical`, `retain_restricted`,
`migrate_then_remove`, `gone`, and `needs_decision`. Only `gone` may set
`approved_to_remove` to true, and it requires a non-empty replacement receipt.

The current reviewed layer has 1,028 disposition records for all 1,028 unique identities in the fresh
candidate. 474 are `retain_canonical`, 207 are `retain_restricted`, and 347 are explicit
`needs_decision` records with no inferred owner. The latter are carried only by
`63_Global_Writer_Inventory_v3_Owner_Review_Work_Package.md`; they neither authorize removal nor make a
writer canonical. The legacy Holiday, client-name, and Data Browser generic adapter writers were removed after
their typed replacement was implemented; absent candidates are intentionally not retained as disposition
records because the validator requires every record to reference a current candidate identity.

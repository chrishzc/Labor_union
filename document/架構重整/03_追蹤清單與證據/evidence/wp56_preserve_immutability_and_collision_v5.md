# WP56 Preserve Immutability and Collision v5

- Date: 2026-08-11
- Source: `union_db_candidate_20260803_v5`
- Target: `lu_test_dataset_contract_signing_v5_preserve`
- Mode: read-only verification

## Collision fail-closed

The legacy integration planner found 53 overlapping source/target case numbers.
It returned both `target contains data and must be explicitly rebuilt` and
`source and target case numbers collide`; preservation migration was not
permitted. The migration preflight independently returned `target_not_empty`.

## Immutability

`scripts/verify_legacy_ui_preservation.py` compared every source preserved-root
row to the target row with the same primary key. All six root tables passed with
matching subset digests. Target-only rows from append-only scenario execution
were excluded from the source-key comparison and did not alter legacy rows.

Machine-readable receipt:
`validation/receipts/WP56-PRESERVE-IMMUTABILITY-AND-COLLISION_v5.json`.

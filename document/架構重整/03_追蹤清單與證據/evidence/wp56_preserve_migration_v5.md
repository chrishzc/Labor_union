# WP56 conservative preserve migration v5

- Date: 2026-08-11
- Source: `union_db_candidate_20260803_v5`
- Target: `lu_test_dataset_contract_signing_v5_preserve`
- Strategy: conservative preserved roots only
- Copied tables: 6
- Copied rows: 161
- Root digest: `8d51d22cdb53200b6e940f6b926b66d63a27718027738a516a9994f1168c2691`

## Preserved roots

`clients`, `staff`, `media_assets`, `orders`, `caregiver_matching_plans`, and
`caregiver_matching_plan_segments` were copied. The source and target root
digests match.

## Projection rebuild

`anomaly_current_alerts`, `client_deposit_settlement_projection`, and
`scheduling_effective_occupancy` were zero before and after rebuild. The
rebuild verified `preserved_roots_only` with digest
`020730ac24021407c498dbb3af5f19fffb2c0f37664f4e9103494fa27d1bf469`.

Financial, contract-signing, scheduling, job, and other derived records were
not copied by the approved conservative policy.

Canonical machine-readable receipt:
`validation/receipts/WP56-PRESERVE-MIGRATION_v5.json`.

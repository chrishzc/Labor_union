# WP56 preserve migration preflight v4

- Captured at: 2026-08-11
- Command: `scripts/migrate_legacy_ui_dataset.py --dry-run`
- Source database: `union_db_candidate_20260803_v5`
- Target database: `lu_test_dataset_contract_signing_v4`
- Target mutation: none; the command returned the intentional nonzero blocked result.

## Initial fail-closed result

- `source_root_digest`: `8d51d22cdb53200b6e940f6b926b66d63a27718027738a516a9994f1168c2691`
- allowlisted root tables: 6 (`clients`, `staff`, `media_assets`, `orders`,
  `caregiver_matching_plans`, `caregiver_matching_plan_segments`)
- `target_is_empty`: `false`
- `migration_permitted`: `false`
- initial blocker: `unclassified_source_tables`
- initially populated unclassified source tables: 67

## Conservative-policy rerun

The user selected the conservative policy: only the six listed root tables are copied; every
known non-root legacy table is explicitly `retire_no_copy` or `rebuild_projection`. The rerun
produced the same source digest and changed the only blocker to `target_not_empty`.

The runner emits this structured read-only report and exits nonzero when blocked. It will not
copy roots or rebuild projections until an independently created empty target dataset is
explicitly authorized.

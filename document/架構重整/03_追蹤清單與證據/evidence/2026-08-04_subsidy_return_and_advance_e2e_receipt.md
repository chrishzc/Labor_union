# Client Subsidy Return / Union Advance E2E Receipt

- Date: 2026-08-04
- Execution boundary: disposable MySQL 8.4 only (`lu_test_subsidy_recovery_20260804` and
  `lu_test_subsidy_mismatch_20260804`); `union_db` was not used.
- Test source: `tests/test_finance_import_disposable_mysql_e2e.py`
- Test source SHA-256: `7ef62507ef96d67b79ee3c16486dd1a8783aade9a7a001382775c70adcb37474`
- Result: exact recovery cases `2 passed in 20.50s`; partial-allocation safety case
  `1 passed in 8.90s`.
- Isolation guard: the test now forces the static legacy adapter configuration to the
  declared disposable database, so bootstrap, ingestion, seed, and consumer cannot
  fall back to a `.env` candidate database.

## Proven rules

1. A first-month claim-quarter completion with no matching government receipt allocation at the fixed due date creates one `subsidy_advance` obligation/ledger entry.
2. A later exact government receipt allocation creates an immutable recovery against that existing advance. It does not create a second client payout.
3. A partial government allocation creates the `subsidy_advance_settlement_ambiguous` review route and does not auto-net, recover, or create another payout.

## Boundary retained

`client_payments.subsidy_refund_*` remains a legacy projection and is not a fact source for this workflow. General client refunds and subsidy return/advance use separate obligation and ledger semantics.

## Related current architecture evidence

- `formal_baseline_v1.json`: current live validation: 683 writers and 0 legacy projection runtime callers.
- `writer_inventory_v3/writer_inventory_v3_candidate.manifest.json`: current live validation: 683 findings, 9 unresolved; every inventory disposition remains blocked and no removal approval is implied.

This receipt is supplementary evidence for the Client Finance and Government Subsidy completion matrix. It does not upgrade the remaining UI task-queue, loading-trace, historical-reprocess, or preserve-data release gaps to proven.

## 2026-08-04 isolated rerun

- New disposable schema: `lu_test_subsidy_advance_e2e_20260804`; `union_db` was not used.
- `test_real_taishin_subsidy_payout_advances_then_recovers_after_government_allocation`: `1 passed in 14.62s`.
- The same source SHA-256 above was used. This rerun confirms the real-format workbook path still creates one advance and performs only the later Government Subsidy recovery.

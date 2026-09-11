module: reconciliation-register-query
parent_subsystem: government-subsidy
architecture: ../../../../../../../domains/government-subsidy/subsystems/government-subsidy/modules/reconciliation-register-query.md
layout_status: canonical
test_root: tests/domains/government-subsidy/subsystems/government-subsidy/modules/reconciliation-register-query/
# Owned verification
- formal claim submission period uses `subsidy_claim_batches.submitted_at`, includes both boundaries, uses frozen claim-item values, and does not substitute service completion year。
- quarterly/annual query contracts use established-order effective service end, owner-calculated subsidy values, and XLSX-aligned fields without requiring a claim batch。
- operations-report annual candidate includes normal／historical deposit-established statuses, derives reconciliation year／quarter from effective service end, and remains independent of claim batch state。

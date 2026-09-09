module: reconciliation-register-query
parent_subsystem: government-subsidy
architecture: ../../../../../../../domains/government-subsidy/subsystems/government-subsidy/modules/reconciliation-register-query.md
layout_status: canonical
test_root: tests/domains/government-subsidy/subsystems/government-subsidy/modules/reconciliation-register-query/
# Owned verification
- formal claim submission period uses `subsidy_claim_batches.submitted_at`, includes both boundaries, uses frozen claim-item values, and does not substitute service completion year。
- quarterly/annual query and UI contracts use formal batch year/quarter, item-owned staff, and XLSX-aligned fields。

module: historical-payment-settlement
parent_subsystem: staff-payables
architecture: ../../../../../../domains/staff-payables/subsystems/staff-payables/modules/historical-payment-settlement.md
test_root: tests/domains/staff-payables/subsystems/staff-payables/modules/historical-payment-settlement/

# Owned verification
- `contract/test_historical_staff_payout_schema_contract.py` — Staff-owned immutable event, exact obligation link, projection, source outbox, release descriptor and terminal assembly contract.
- `contract/test_historical_staff_payout_workflow.py` — Staff owner Query／Preview／Apply, bank-first blocker, exact staff/case, replay and later reopen.
- `contract/test_historical_staff_payout_mysql_repository.py` — Staff fresh-lock order and owner-only event/link/overlay/outbox/existing-receipt persistence without hidden commit.
- `contract/test_historical_staff_payout_api.py` — authenticated bounded Query／Preview／Apply／fresh readback owner transport and strict views.

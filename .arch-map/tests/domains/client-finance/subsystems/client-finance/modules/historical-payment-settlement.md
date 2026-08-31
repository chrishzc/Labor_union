module: historical-payment-settlement
parent_subsystem: client-finance
architecture: ../../../../../../domains/client-finance/subsystems/client-finance/modules/historical-payment-settlement.md
test_root: tests/domains/client-finance/subsystems/client-finance/modules/historical-payment-settlement/

# Owned verification
- `contract/test_historical_client_payment_schema_contract.py` — Client-owned immutable event, exact obligation link, projection, source outbox, release descriptor and terminal assembly contract.
- `contract/test_historical_client_payment_workflow.py` — Client owner Query／Preview／Apply, bank-first blocker, direction exactness, replay and later reopen.
- `contract/test_historical_client_payment_mysql_repository.py` — Client fresh-lock order and owner-only event/link/overlay/outbox/existing-receipt persistence without hidden commit.
- `contract/test_historical_client_payment_api.py` — authenticated bounded Query／Preview／Apply／fresh readback owner transport and strict views.

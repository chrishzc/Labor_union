module: historical-completion
parent_subsystem: orders
architecture: ../../../../../../domains/orders/subsystems/orders/modules/historical-completion.md
test_root: tests/domains/orders/subsystems/orders/modules/historical-completion/
integration_root: ui_react/src/tests/historical_completion.test.tsx

# Owned verification
- `historical_completion.test.tsx` — 保護HOB-E strict decode、Step 11不假完成、closed owner referral與預設收合的技術證據。
- `test_historical_completion_apply.py` — 保護 fresh oracle admission、版本/source vector stale、same-key replay、其他狀態 fail closed及單一UoW。
- `test_historical_completion_writer.py` — 保護 canonical Orders lifecycle event/outbox/projection writer重用。
- `test_historical_completion_api.py` — 保護 authenticated Query／Preview／Apply strict HTTP contract。

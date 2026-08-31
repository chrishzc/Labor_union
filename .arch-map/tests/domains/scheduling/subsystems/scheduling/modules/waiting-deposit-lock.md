module: waiting-deposit-lock
parent_subsystem: scheduling
architecture: ../../../../../../domains/scheduling/subsystems/scheduling/modules/waiting-deposit-lock.md
test_root: tests/domains/scheduling/subsystems/scheduling/modules/waiting-deposit-lock/

# Owned verification
- `regression/test_order_cancellation_proposed_lock.py` — 保護服務前取消能原子解除 legacy proposed plan 上仍有效的 waiting-deposit lock 與逐日占用。

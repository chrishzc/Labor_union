module: line-notification-current-issue
parent_subsystem: anomalies
architecture: ../../../../../../domains/anomalies/subsystems/anomalies/modules/line-notification-current-issue.md
test_root: tests/domains/anomalies/subsystems/anomalies/modules/line-notification-current-issue/

# Owned verification
- `contract/test_consumer.py` — public identity、active／inactive projection與incomplete readback fail-closed。

# Boundary
LINE owner evaluator與mutation recheck由LINE Module test root擁有；本Module不驗證或重算LINE private facts。

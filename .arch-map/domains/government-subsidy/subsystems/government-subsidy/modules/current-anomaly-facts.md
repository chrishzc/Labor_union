# Module: current-anomaly-facts

## Parent
- subsystem: `government-subsidy`

## Responsibility
提供 `GOVSUB-001`、`GOVSUB-002`、`GOVSUB-004` 的 owner-typed、zero-write current-fact predicate與bounded recheck request；金額與allocation只依Government Subsidy ledger／claim roots判定。外層MySQL composition才轉成既有Anomalies intent。

## Implementation
- `subsystems/government_subsidy/current_anomaly_facts.py`
- `infrastructure/mysql/government_subsidy_current_issue_adapter.py`
- `infrastructure/mysql/government_subsidy_anomaly_recheck_sink.py`

## Consumers
- `subsystems/anomalies/government_subsidy_current_issue_consumer.py`

## Verification
- test_root: `tests/domains/government-subsidy/subsystems/government-subsidy/modules/current-anomaly-facts/`

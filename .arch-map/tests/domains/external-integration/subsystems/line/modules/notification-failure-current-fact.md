module: notification-failure-current-fact
parent_subsystem: line
architecture: ../../../../../../domains/external-integration/subsystems/line/modules/notification-failure-current-fact.md
test_root: tests/domains/external-integration/subsystems/line/modules/notification-failure-current-fact/

# Owned verification
- `contract/test_current_fact.py` — logical group、applicability、exact replay lineage與closed terminal reasons。
- `contract/test_mutation_recheck.py` — manual replay／delivery owner mutation在既有UoW內排bounded recheck。

# Boundary
Anomalies projection consumer位於Anomalies canonical module root；provider實送、schema與deployment不在本Module驗收內。

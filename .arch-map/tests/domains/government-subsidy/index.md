domain: government-subsidy
architecture: ../../../domains/government-subsidy/index.md
test_root: tests/domains/government-subsidy/
integration_root: tests/domains/government-subsidy/subsystems/government-subsidy/integration/
fixtures_root: tests/fixtures/
subsystems:
  government-subsidy:
    index: subsystems/government-subsidy/index.md

# Routing notes
Government Subsidy owner query/lifecycle coverage belongs here. Tests whose subject under test is `subsystems.anomalies` remain with the Anomalies owner even when their source facts originate from Government Subsidy.

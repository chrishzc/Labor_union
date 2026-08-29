domain: payroll
architecture: ../../../domains/payroll/index.md
test_root: tests/domains/payroll/
integration_root: tests/domains/payroll/subsystems/payroll/integration/
fixtures_root: tests/fixtures/
subsystems:
  payroll:
    index: subsystems/payroll/index.md

# Routing notes
Payroll focused subsystem coverage now lives under the canonical Domain-owned tree. Cross-domain acceptance, disposable-MySQL and Task 97 oracles remain at their higher boundary rather than being moved solely for layout symmetry.

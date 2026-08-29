subsystem: payroll
parent_domain: payroll
architecture: ../../../../../domains/payroll/subsystems/payroll/index.md
test_root: tests/domains/payroll/subsystems/payroll/
integration_root: tests/domains/payroll/subsystems/payroll/integration/
fixtures_root: tests/fixtures/

# Routing notes
Owner-local Payroll rebuild and terms-impact verification lives here. Tests may consume canonical Orders/Scheduling source facts while still being Payroll-owned when the subject under test is `domains.payroll` or `subsystems.payroll`. Keep true cross-domain acceptance, disposable-MySQL and Task 97 oracles at their higher boundary.

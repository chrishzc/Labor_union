subsystem: payroll
parent_domain: payroll
architecture: ../../../../../domains/payroll/subsystems/payroll/index.md
test_root: tests/domains/payroll/subsystems/payroll/
integration_root: tests/domains/payroll/subsystems/payroll/integration/
fixtures_root: tests/fixtures/

# Routing notes
Owner-local Payroll rebuild, adjustment, terms-impact, staff-payment due-date/state and Payroll-specific persistence-invariant verification lives here. Tests may consume canonical Orders/Scheduling source facts while still being Payroll-owned when the subject under test is `domains.payroll`, `subsystems.payroll`, or a Payroll-specific infrastructure adapter invariant. Keep cross-boundary API/Access/Jobs durable-command acceptance, disposable-MySQL and Task 97 oracles at their higher boundary.

# Flat-test audit
The current flat-test audit found no additional high-confidence Payroll owner-local tests outside the documented cross-boundary API/Access/Jobs, durable-command, disposable-MySQL/E2E, Task97, or true cross-owner boundaries. Admit future cases by direct SUT/current ownership rather than filename alone.

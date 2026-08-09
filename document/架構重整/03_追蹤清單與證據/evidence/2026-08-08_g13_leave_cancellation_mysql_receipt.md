# G13 Leave versus Cancellation Isolated MySQL Receipt

- Observed date: `2026-08-08`
- Test node: `tests/test_g13_leave_cancellation_disposable_mysql_e2e.py::test_g13_leave_and_cancellation_serialize_shared_occupancy_write`
- Result: `1 passed`
- Isolation: a generated `lu_test_g13_*` database was used; the runner set both `LABOR_UNION_TEST_MYSQL_*` and application `DB_*` variables to that database.
- Cleanup: the runner executed `DROP DATABASE IF EXISTS` in a PowerShell `finally` block after pytest.
- Forbidden databases: neither `union_db` nor the configured candidate database were used.

The test starts a real Leave/Substitution Apply and a real Orders Cancellation Apply from separate Previews against one two-caregiver in-service order. It requires exactly one successful Apply, one typed workflow error, no live worker threads after the timeout, one effective scheduling generation, and no duplicate `(staff_id, occupancy_date)` row in `scheduling_effective_occupancy`.

Pytest emitted an unrelated existing `.pytest_cache` `WinError 183` warning. It did not affect the test result.

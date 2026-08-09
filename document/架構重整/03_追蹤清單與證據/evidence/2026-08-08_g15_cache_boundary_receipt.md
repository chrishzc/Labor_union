# G15 Cache Boundary and Stale Preview Receipt

- Observed date: `2026-08-08`
- Contract test: `tests/test_g15_cache_boundary_contract.py`
- Contract result: `2 passed`
- Isolated MySQL test: `tests/test_order_auto_completion_disposable_mysql_e2e.py::test_auto_completion_first_rejects_the_real_stale_leave_apply_without_writes`
- MySQL result: `1 passed`
- Isolation: generated `lu_test_g15_*` database with `DROP DATABASE IF EXISTS` in the runner `finally` block.

The cache-boundary test confirms that formal workflow modules do not import `QueryCachePort` or `TtlProjectionCache`. The only TTL cache is `holiday_query_cache`, a read-only holiday projection with no transaction control. The isolated MySQL trace proves an old Leave Preview returns typed `stale_version` after a concurrent AutoComplete and leaves all captured command writes unchanged.

The MySQL pytest run emitted an unrelated existing `.pytest_cache` `WinError 183` warning. It did not affect the result.

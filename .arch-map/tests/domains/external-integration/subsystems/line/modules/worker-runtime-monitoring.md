module: worker-runtime-monitoring
parent_subsystem: line
architecture: ../../../../../../domains/external-integration/subsystems/line/modules/worker-runtime-monitoring.md
test_root: tests/domains/external-integration/subsystems/line/modules/worker-runtime-monitoring/

# Owned verification
- Contract coverage proves a failed worker cycle persists a typed failure heartbeat before propagating the error.
- Runtime monitoring coverage distinguishes a fresh failed cycle from an absent or stale worker and uses the shared 90-second default freshness window.

- `contract/test_runtime_status_query.py` verifies closed authenticated LIFF query, sanitized aggregate counts, freshness/unknown/error states and zero alert projection.

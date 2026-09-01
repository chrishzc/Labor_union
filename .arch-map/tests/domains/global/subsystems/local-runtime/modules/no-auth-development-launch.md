module: no-auth-development-launch
parent_subsystem: local-runtime
architecture: ../../../../../../../domains/global/subsystems/local-runtime/modules/no-auth-development-launch.md
test_root: tests/domains/global/subsystems/local-runtime/modules/no-auth-development-launch/

# Owned verification
- `test_no_auth_source_runtime.py` — proves the wrapper cannot inherit an incomplete immutable artifact binding into local no-auth startup, and injects an ephemeral anomaly cursor key without persistence or override of an explicit value.

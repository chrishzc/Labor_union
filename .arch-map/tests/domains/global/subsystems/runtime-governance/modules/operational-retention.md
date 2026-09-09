module: operational-retention
parent_subsystem: runtime-governance
domain: global
architecture: ../../../../../../../domains/global/subsystems/runtime-governance/modules/operational-retention.md
layout_status: custom_current
test_root: tests/domains/global/subsystems/runtime-governance/

# Owned verification

- `test_operational_retention.py` — 29／30-day boundary、capacity oldest-first／unrelieved、zero-write
  Preview、stale zero-delete、idempotent replay、DB reconciliation conflict and managed-log root safety.
- `test_operational_retention_api.py` — root-authenticated typed Query／Preview／Apply composition.
- `storage_management_page.test.tsx` — Audit & System capacity readback、zero-write Preview、
  explicit confirmation and terminal receipt presentation.

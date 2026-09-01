module: finalize-runtime
parent_subsystem: controlled-files
domain: global
architecture: ../../../../../../../domains/global/subsystems/controlled-files/modules/finalize-runtime.md
layout_status: custom_current
test_root: tests/domains/global/subsystems/controlled-files/integration/

# Owned verification

- `test_controlled_file_finalize_runner.py` — bounded finalize claim, local storage
  integrity outcome, and reconciliation CAS behavior.

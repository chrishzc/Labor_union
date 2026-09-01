module: api-composition
parent_subsystem: controlled-files
domain: global
architecture: ../../../../../../../domains/global/subsystems/controlled-files/modules/api-composition.md
layout_status: custom_current
test_root: tests/domains/global/subsystems/controlled-files/

# Owned verification

- `test_controlled_file_api.py` — authenticated seven-route composition, typed Preview/Apply/readback,
  safe projections and no locator leakage.

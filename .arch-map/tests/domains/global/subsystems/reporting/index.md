subsystem: reporting
parent_domain: global
architecture: ../../../../../domains/global/subsystems/reporting/index.md
layout_status: custom_current
integration_root: tests/test_weekly_operations_report_contract.py
modules:
  weekly-operations-report:
    layout_status: custom_current
    test_root: tests/test_weekly_operations_report_contract.py

# Routing notes
The Python contract remains at its path-sensitive cross-domain root because the current entrypoint review generator consumes that exact path. React presentation/client oracles remain under `ui_react/src/tests/`.

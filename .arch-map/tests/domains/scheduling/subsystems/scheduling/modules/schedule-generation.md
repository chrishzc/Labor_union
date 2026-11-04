module: schedule-generation
parent_subsystem: scheduling
architecture: ../../../../../../../domains/scheduling/subsystems/scheduling/modules/schedule-generation.md
layout_status: custom_current
test_root: tests/domains/scheduling/subsystems/scheduling/modules/schedule-generation/

# Owned verification
- `test_opening_primary_staff.py` — before-service replacement, first-day/repeated substitution, date rebuild, later handover and incomplete/cyclic lineage.

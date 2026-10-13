module: staff-qualification-master
parent_subsystem: staff
architecture: ../../../../../../domains/staff/subsystems/staff/modules/staff-qualification-master.md
layout_status: custom_current
test_root: tests/test_staff_qualification_master.py
test_root: ui_react/src/tests/domains/staff/subsystems/staff/modules/staff-qualification-master/

# Owned verification
- `tests/test_staff_qualification_master.py` covers typed sections, Staff certifications, bounded SQL and authenticated API projection.
- Manual qualification tests cover preview zero writes, stale conflicts, atomic receipt/replay, cancellation and readback.

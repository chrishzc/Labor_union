module: staff-retirement
parent_subsystem: staff
architecture: ../../../../../../domains/staff/subsystems/staff/modules/staff-retirement.md
test_root: tests/domains/staff/subsystems/staff/modules/staff-retirement/

# Owned verification
- `contract/test_staff_retirement_line_effect.py` — exact Staff transition, shared outer UoW, role-scoped LINE revocation and idempotent request identity.

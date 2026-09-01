module: profile-change
parent_subsystem: client-profile
architecture: ../../../../../../domains/clients/subsystems/client-profile/modules/profile-change.md
layout_status: canonical
test_root: tests/domains/clients/subsystems/client-profile/modules/profile-change/

# Owned verification
- `contract/test_application.py` — Client profile applicant／reviewer workflow, version conflict, idempotent replay and owner readback.
- `contract/test_client_binding_port.py` — verified binding evidence and role scope boundary.

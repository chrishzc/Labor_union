subsystem: client-profile
parent_domain: clients
architecture: ../../../../../domains/clients/subsystems/client-profile/index.md
test_root: tests/domains/clients/subsystems/client-profile/
modules:
  profile-change:
    layout_status: canonical
    test_root: tests/domains/clients/subsystems/client-profile/modules/profile-change/

# Routing notes
Client profile Query／Preview／Apply／approval and binding-port contract tests are owned by the profile-change module.

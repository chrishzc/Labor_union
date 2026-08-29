domain: external-integration
architecture: ../../../domains/external-integration/index.md
test_root: tests/domains/external-integration/
integration_root: tests/domains/external-integration/
fixtures_root: tests/fixtures/
subsystems:
  access:
    index: subsystems/access/index.md
  line:
    index: subsystems/line/index.md

# Routing notes
LINE and migrated Access-focused tests now use canonical subsystem roots. Remaining flat Access tests are bounded `layout_gap` candidates and must move only when semantic ownership is directly proven; legacy Streamlit rollback coverage remains deferred to Streamlit retirement.

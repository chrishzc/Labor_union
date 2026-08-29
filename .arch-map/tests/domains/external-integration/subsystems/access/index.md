subsystem: access
parent_domain: external-integration
architecture: ../../../../../domains/external-integration/subsystems/access/index.md
test_root: tests/domains/external-integration/subsystems/access/
integration_root: tests/domains/external-integration/subsystems/access/integration/
fixtures_root: tests/fixtures/

# Routing notes
Account-center, command-safety, audit-query and disposable-MySQL Access tests now live under the canonical Access subsystem root. Remaining flat Access tests should be migrated only when their current semantic owner is directly proven. `tests/test_access_control_ui_app_test.py` remains outside this root because it protects the legacy Streamlit rollback surface and is deferred to Streamlit retirement.

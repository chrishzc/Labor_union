subsystem: access
parent_domain: external-integration
architecture: ../../../../../domains/external-integration/subsystems/access/index.md
test_root: tests/domains/external-integration/subsystems/access/
integration_root: tests/domains/external-integration/subsystems/access/integration/
fixtures_root: tests/fixtures/

# Routing notes
Focused Access account-center, command-safety, audit-query, security-alert-outbox and TOTP coverage lives under the canonical Access subsystem root. Existing owner-local disposable-MySQL coverage already placed under this root remains there.

# Higher-boundary / deferred coverage
- `tests/test_access_knowledge_disposable_mysql_e2e.py` — explicit disposable-MySQL business-flow oracle; keep at the higher boundary until a dedicated knowledge owner/root is proven.
- `tests/test_access_control_ui_app_test.py` — protects the legacy Streamlit rollback surface; defer to Streamlit retirement.
- `tests/test_admin_auth_security.py` — path-sensitive repo-wide security contract and Streamlit compatibility coverage; keep at the higher boundary.

# Flat-test audit
The current flat-test audit found no additional high-confidence Access owner-local tests outside the documented Knowledge disposable-MySQL, legacy Streamlit, path-sensitive repo-wide security, or true cross-owner boundaries. Admit future cases by direct SUT/current ownership rather than filename alone.

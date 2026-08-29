subsystem: line
parent_domain: external-integration
architecture: ../../../../../domains/external-integration/subsystems/line/index.md
test_root: tests/domains/external-integration/subsystems/line/
integration_root: tests/domains/external-integration/subsystems/line/integration/
fixtures_root: tests/fixtures/

# Routing notes
The former `tests/line/` owner tree has moved under the canonical LINE subsystem root. Its existing `domain/`, `infrastructure/`, and `subsystems/` child names are retained as internal layout until later scoped semantic split; they no longer form a competing top-level test architecture. LINE/Scheduling boundary contracts for matching schedule confirmation and staff leave LIFF intake live under this subsystem integration root. Current additional owner-local integration coverage includes delivery-task action routes, safe configuration query/retirement guards, notification-rule mutation/query/replay routes, verified staff service-day media upload, Rich Menu image-upload typed receipt contracts, and the typed LINE admin capabilities/health contract.

# Deferred / higher-boundary
- `tests/test_staff_service_day_log_api.py` remains at the LINE/Scheduling boundary because verified LINE identity is used to issue a Scheduling service-day command.
- `tests/test_line_customer_service_first_release.py` remains at the release/relocation-sensitive boundary because it spans Customer Service, LINE, migration manifests, schema and static UI artifacts through repo-relative paths.
- Release/migration/schema, disposable-MySQL/E2E, Task97, legacy UI, and true cross-owner tests remain at their higher verification boundaries.

# Flat-test audit
The current flat-test audit found no additional high-confidence LINE owner-local tests outside the documented boundary/release-sensitive classes. Admit future cases by direct SUT/current ownership rather than filename alone.

module: line-identity-management
parent_subsystem: line
architecture: ../../../../../../domains/external-integration/subsystems/line/modules/line-identity-management.md
test_root: tests/domains/external-integration/subsystems/line/modules/line-identity-management/

# Owned verification
- `contract/test_role_scope_schema.py` — additive successor, hash binding and bounded schema shape.
- `contract/test_role_scoped_application.py` — shared customer/staff readback, one selected-role state and idempotent role selection.
- `contract/test_role_scoped_repository.py` — dual-role selection fail-closed, admin exclusivity and revoked-role rejection.
- `contract/test_binding_failure_streak.py` — one bounded streak and exactly one second-failure Customer Service escalation.
- `regression/test_same_type_replacement.py` — same-type replacement against the shared role-scoped root/event stream.
- `contract/test_terminal_closure_restore.py` — Orders closure handoff, fresh owner/binding/menu gates, dual-role no-op, replay and typed stale/revocation failures.

# Boundary
Release-chain and disposable-MySQL qualification remain at their declared higher verification roots. This Module owns only the LINE-side Staff retirement adaptation and post-revocation role menu intent; Staff lifecycle remains under the Staff Module root. Provider transport, existing revocation retry/success semantics and LINE-006 remain outside this slice.

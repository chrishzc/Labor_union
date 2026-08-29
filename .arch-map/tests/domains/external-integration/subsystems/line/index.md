subsystem: line
parent_domain: external-integration
architecture: ../../../../../domains/external-integration/subsystems/line/index.md
test_root: tests/domains/external-integration/subsystems/line/
integration_root: tests/domains/external-integration/subsystems/line/integration/
fixtures_root: tests/fixtures/

# Routing notes
The former `tests/line/` owner tree has moved under the canonical LINE subsystem root. Its existing `domain/`, `infrastructure/`, and `subsystems/` child names are retained as internal layout until later scoped semantic split; they no longer form a competing top-level test architecture. LINE/Scheduling boundary contracts for matching schedule confirmation and staff leave LIFF intake live under this subsystem integration root.

kind: test-index
schema_version: 2
architecture_map: ../index.md
test_root: tests/
global_root: layout_gap

# Test routing

Current `tests/` is a mixed legacy/architecture-aligned tree, so this index is intentionally sparse. Architecture-owned roots now exist for Orders, Scheduling, Finance Import, External Integration, Anomalies and other migrated owners; higher-boundary suites still remain under roots such as `tests/integration/`. Do not treat this map as a coverage report or migration authorization.

## Domains
- `orders` — `domains/orders/index.md`
- `scheduling` — `domains/scheduling/index.md`
- `case-import` — `domains/case-import/index.md`
- `payroll` — `domains/payroll/index.md`
- `finance-import` — `domains/finance-import/index.md`
- `external-integration` — `domains/external-integration/index.md`
- `anomalies` — `domains/anomalies/index.md`

## Cross-domain/global routing
- `tests/integration/` — shared higher-boundary legacy root; admit only scenario-relevant tests.
- `tests/e2e/` and `tests/hurl/` — system/API acceptance roots; use only when current acceptance crosses Domain/API boundaries.
- `tests/fixtures/` — shared legacy fixture root; ownership must be resolved by actual consumers before moving/removing.
- `tests/global/` — not currently present (`layout_gap`).

Domains omitted from this Test Map are not test-free; their physical ownership remains unresolved in the mixed tree and should be added only when a material task needs durable routing.

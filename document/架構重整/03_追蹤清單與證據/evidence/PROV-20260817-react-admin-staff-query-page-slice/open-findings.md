# Staff query page-slice open findings

## STAFF-Q-01 — Real browser evidence

- Status: `resolved`
- Scope: Staff page G6 only
- Closure: true password→TOTP Chrome Session、staff summaries 200與DOM/unavailable/disabled evidence已記錄。

## STAFF-Q-02 — Concurrent full-suite/build drift outside Staff write set

- Status: `resolved`
- Evidence: full React 450 pass／61 fail; failures are Orders tests/contracts. Full build errors are Orders plus one
  Anomalies import modifier issue; no Staff error remains after exact-file typecheck.
- Owner: respective Orders／Anomalies integration lanes.
- Closure: Integration Owner fresh full React 52 files／513 tests與build PASS。

## STAFF-Q-03 — Existing lint warnings

- Status: `external-existing`
- Evidence: `npm run lint` exit 0 with two Fast Refresh warnings in `src/components/MasterLayout.tsx`.
- Scope: outside Staff exact write set; not modified.

No unresolved Staff public-contract or DB/schema finding was introduced. Staff master／certification／bank and
mutation families remain owned by the already indexed Phase 3B1／3C gaps.

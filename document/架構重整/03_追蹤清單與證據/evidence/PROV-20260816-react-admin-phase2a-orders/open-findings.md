# Phase 2A open findings

| ID | Severity | Finding | Status | Evidence / next action |
|---|---|---|---|---|
| F-01 | P0 | order_status→7-stage inference | RESOLVED | adapter preserves raw status; 7-stage unavailable |
| F-02 | P0 | generated SOP status/timestamps | RESOLVED | all 11 dynamic facts unavailable |
| F-03 | P0 | fixed fake LINE notifications | RESOLVED | empty typed gap state; replay locked |
| F-04 | P0 | raw/cross-domain endpoints in Orders client | RESOLVED | exactly eight approved GET methods |
| F-05 | P0 | frontend buffer/finance/recommendation inference | RESOLVED | formulas removed; gaps explicit |
| F-06 | P0 | weak Zod defaults/records and permissive envelope | RESOLVED | Orders-local strict envelope/date/time/range tests |
| F-07 | P0 | real browser auth/API/DOM evidence | OPEN_BLOCKER | `BLOCKED_REAL_BROWSER_EVIDENCE` |
| F-08 | P0 | stale/contradictory evidence counts | RESOLVED | canonical receipts use 170 frontend / 45 backend counts |
| F-09 | P1 | error mapper retained 304/retired/raw `as any` behavior | RESOLVED | minimal status mapping; no raw payload inference |
| F-10 | P1 | UI hierarchy tests covered only five controls | RESOLVED | stable IDs and Drawer-specific disabled assertions |
| F-11 | P2 | full-suite React act warnings outside exact write set | OPEN_NON_BLOCKING | successor Foundation test-hygiene task; tests still pass |

## Completion recommendation

`blocked`. G1–G4 are current and pass; G5 requires user-controlled local-auth credentials/TOTP and test data.
Phase 2A must not be called completed/victory until that evidence exists.

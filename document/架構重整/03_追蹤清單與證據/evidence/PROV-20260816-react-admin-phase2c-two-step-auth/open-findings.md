# Phase 2C Open Findings

| ID | Severity | Finding | Status |
|---|---|---|---|
| P2C-F01 | P0 | 舊 receipt 在 Desktop 副本執行 | RESOLVED — current D workspace receipts supersede it |
| P2C-F02 | P0 | forbidden combined `/login` | RESOLVED — removed |
| P2C-F03 | P0 | permissive Zod schema | RESOLVED — strict schemas aligned |
| P2C-F04 | P0 | raw auth error/message branching | RESOLVED — bounded typed error |
| P2C-F05 | P0 | stale verify response could write Session | RESOLVED — generation guard before commit |
| P2C-F06 | P1 | Remember Me implied persistence | RESOLVED — memory-only wording |
| P2C-F07 | P1 | fake forgot-password alert | RESOLVED — inline unavailable message |
| P2C-F08 | P0 | Phase 2B presentation/full-suite failures | RESOLVED — current full suite 196/196 |
| P2C-F09 | P1 | existing React `act(...)` warnings | OPEN — non-blocking test hygiene debt |
| P2C-F10 | P1 | existing DataImport trailing whitespace blocks global diff-check | OPEN — out of Phase 2C write set |
| P2C-F11 | P0 | no real browser TOTP evidence | RESOLVED — Chrome challenge/verify 200 and Shell unlocked |
| P2C-F12 | P0 | Phase 2A query client exposed unapproved/raw routes | RESOLVED — exact eight typed query methods restored |
| P2C-F13 | P1 | Shell status client omitted current bearer token | RESOLVED — per-request memory token injection；Chrome 顯示系統在線 |

Phase 2C 無未解 P0 finding。P2C-F09/F10 保留為非阻擋且不由本包越界修正的相鄰技術債。

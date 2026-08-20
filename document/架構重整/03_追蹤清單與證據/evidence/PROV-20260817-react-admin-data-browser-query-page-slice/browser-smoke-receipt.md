# Data Browser Query Page-Slice Browser Smoke Receipt

Status: `NOT_RUN` / `AWAITING_REAL_BROWSER_EVIDENCE`.

Required closure after the user signs in through account→TOTP:

1. each of six tabs sends exactly one GET to its canonical source;
2. Network response fields match table and Drawer DOM;
3. search/cursor/empty/error/reload and source-switch abort are observed;
4. Drawer open/close/copy sends zero GET and copies only masked cells;
5. PATCH/source-correction controls are native disabled;
6. no POST/PUT/PATCH/DELETE, raw payload or PII appears.

Existing DB is permitted only for GET observation. Happy DOM, API-only 200 or direct DB output cannot pass this gate.

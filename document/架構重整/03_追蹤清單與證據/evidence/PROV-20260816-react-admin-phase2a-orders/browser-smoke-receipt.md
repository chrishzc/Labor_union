# Phase 2A browser smoke receipt

| Field | Observed value |
|---|---|
| date | 2026-08-16 |
| status | `BLOCKED_REAL_BROWSER_EVIDENCE` |
| API | `http://127.0.0.1:8000/health` returned 200 from an already-running local service |
| Vite | a task-owned hidden dev server on `127.0.0.1:5173` returned 200 |
| browser | Codex in-app browser, task-created temporary tab |
| navigation | `http://127.0.0.1:5173/#orders` |
| visible result | route guard displayed username/password stage and “下一步：進行雙重驗證” |
| blocker | no authorized username/password, TOTP and controlled non-production Orders case were supplied |
| forbidden shortcuts | no dev token, storage injection, DB user creation, password lookup or TOTP bypass attempted |
| cleanup | task-created browser tab closed; task-created Vite listener stopped; pre-existing API service left untouched |

## What remains

A human-controlled local-auth test identity and TOTP are required to complete:

1. password challenge → TOTP → Session;
2. authenticated `/api/v1/orders/summaries` Network response ↔ DOM comparison;
3. four Drawer/two Tab visibility and request-budget inspection;
4. proof that locked controls send no non-GET request.

Typing passwords/TOTP in a browser is sensitive-data transmission and requires action-time user participation/confirmation.
Happy-DOM and mocked client tests are not accepted as substitutes.

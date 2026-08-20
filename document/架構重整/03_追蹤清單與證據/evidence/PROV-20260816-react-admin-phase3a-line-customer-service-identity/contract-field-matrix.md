# Phase 3A Contract Field Matrix

Status: `CONTRACT_MATRIX_FROZEN`  
Base: `main@8615225481c8f72a9629289285516189b270cb36`  
Frozen by: Integration Owner  
Date: 2026-08-16

## Customer Service

| Surface/control | Owner | Method/path | Request / JSON path | Pydantic/source | Required / nullable / enum | Privacy | Error/status | Disposition / UI slot |
|---|---|---|---|---|---|---|---|---|
| `line.ticket.summary.waiting` | Customer Service | `GET /api/v1/customer-service/tickets/summary` | `data.waiting` | `api/schemas/customer_service.py:50-54` | required int | display | 401/403/503 | `READY_TYPED_DISPLAY` KPI |
| `line.ticket.summary.handling` | Customer Service | same | `data.handling` | same | required int | display | same | `READY_TYPED_DISPLAY` KPI |
| `line.ticket.summary.resolved_today` | Customer Service | same | `data.resolved_today` | same | required int | display | same | `READY_TYPED_DISPLAY` KPI |
| `line.ticket.table` | Customer Service | `GET /api/v1/customer-service/tickets` | `data.items[]` | `api/schemas/customer_service.py:12-48` | page/page_size required; ticket status `waiting|handling|resolved` | LINE ID masked; phone restricted display | 401/403/422/503 | `READY_TYPED_DISPLAY` tickets tab |
| `line.ticket.detail` | Customer Service | `GET /api/v1/customer-service/tickets/{ticket_id}` | `data.ticket`, `data.events[]` | `api/schemas/customer_service.py:12-40` | nullable client/case/phone/note/timestamps | raw internal note not log/snapshot | 401/403/404/503 | `READY_TYPED_DISPLAY` detail surface |
| `line.ticket.resolve.preview` | Customer Service | `POST /api/v1/customer-service/tickets/{ticket_id}/update/preview` | body `status="resolved"`, nullable `internal_note`, `expected_version`; header `X-Correlation-ID` | new strict DTO in `api/schemas/customer_service.py` | status literal resolved; version >=0; note <=4000 | note restricted | 401/403/404/409/422/503 | `READY_AFTER_BACKEND_LANE_B` |
| resolve preview view | Customer Service | same | `ticket_id,before_status,after_status,current_version,expected_version,blockers,preview_fingerprint,apply_ready` | new strict view | fingerprint 64-hex; statuses enum; blockers string[] | blockers display; fingerprint internal | schema mismatch fail closed | `READY_AFTER_BACKEND_LANE_B` Drawer |
| `line.ticket.resolve.apply` | Customer Service | `POST /api/v1/customer-service/tickets/{ticket_id}/update/apply` | preview body + `preview_fingerprint`; headers `Idempotency-Key`,`X-Correlation-ID` | new strict request | non-empty headers; 64-hex fingerprint | keys never DOM/log | 401/403/404/409/422/503 | `READY_AFTER_BACKEND_LANE_B` |
| resolve result | Customer Service | same | `data` as `CustomerServiceDetailView` | existing detail view | required ticket/events | restricted fields same as detail | replay same detail; mismatch 409 | receipt-equivalent then GET detail |
| legacy update | Customer Service | `PATCH /api/v1/customer-service/tickets/{ticket_id}` | existing request | existing route | typed success but no Preview | n/a | n/a | `OUT_OF_SCOPE`; React call count 0 |
| reply | Customer Service | `POST /api/v1/customer-service/tickets/{ticket_id}/reply` | existing request | existing route | external delivery intent | reply restricted | n/a | `OUT_OF_SCOPE`; React call count 0 |

Customer resolve fingerprint payload is frozen as canonical JSON fields:
`ticket_id,status="resolved",normalized_internal_note,current_status,current_version`。Preview零寫入；Apply鎖定
fresh ticket、重建相同payload並驗fingerprint。純狀態更新不得建立LINE delivery task。

## LINE Identity

| Surface/control | Owner | Method/path | Request / JSON path | Pydantic/source | Required / nullable / enum | Privacy | Error/status | Disposition / UI slot |
|---|---|---|---|---|---|---|---|---|
| `line.identity.table` | LINE Identity | `GET /api/v1/line/identity-bindings` | `data.items[]`,total,page,page_size | `api/schemas/line_identity_management.py:15-32` | status/subject enums; nullable revocation fields | full LINE ID internal-only; subject name restricted | 401/403/422/503 | `READY_TYPED_DISPLAY` with masked adapter |
| binding detail | LINE Identity | `GET /api/v1/line/identity-bindings/{line_user_id}` | `data` | same | required version/subject; nullable timestamps/request | URL segment never log/DOM; masked presentation only | 401/403/404/503 | `READY_TYPED_DISPLAY` |
| `line.identity.revocation.preview` | LINE Identity | `POST .../{line_user_id}/revocation/preview` | no JSON; `data.binding`,nullable publication/provider IDs,blockers | `api/schemas/line_identity_management.py:35-40` | blockers required string[] | provider ID internal-only | 401/403/404/409/503 | `READY_TYPED_DISPLAY` Drawer |
| reason | LINE Identity | local input then Apply | `reason` | apply request `:70-74` | trim 1..1000 | restricted, no log | whitespace rejected before request | `READY_TYPED_DISPLAY` input |
| `line.identity.revocation.apply` | LINE Identity | `POST .../{line_user_id}/revocation/apply` | expected_version,reason,idempotency_key,correlation_id | request `:70-74`; result `:49-68` | all required | keys/internal actor/provider/message not render | 401/403/404/409/422/503 | `READY_TYPED_INTERNAL_ONLY` result adapter |
| observed binding | LINE Identity | GET detail after Apply | status/version/revocation fields | binding view | `revocation_pending` is not revoked | masked only | failure preserves server status | `READY_TYPED_DISPLAY` |
| replacement/retry/manual | LINE Identity | existing POST routes | existing payloads | routes `74-112,151-189` | typed/raw errors | restricted | n/a | `OUT_OF_SCOPE`, native disabled |

Apply success means request accepted and authorization revoked; only a later server view may claim owner projection cleared
or status revoked. Automatic polling is not authorized; explicit refresh最多一個detail GET。

## Request budgets

| User action | Maximum network calls |
|---|---|
| Page mount tickets | summary 1 + list 1 |
| Open ticket | detail 1 |
| Resolve | preview 1 + apply 1 + detail re-query 1 |
| Page mount bindings | list 1 |
| Open binding | detail 1 |
| Revoke | preview 1 + apply 1 + detail re-query 1 |
| Local tab/filter/close | 0 |
| Any locked control | 0 non-GET and 0 alert/confirm |

Every request obtains the current in-memory session token at call time. No module-load cache or browser persistence.

## Locked control inventory

`line.ticket.open`, `line.richmenu.publish`, `line.identity.invite`, `line.identity.replacement`,
`line.identity.retry`, `line.identity.manual-complete`, `line.notification-rule.create`,
`line.notification-rule.save`, `line.faq.create`, `line.order-group.create`。


# Global FastAPI Typed Error Boundary Contract Matrix

Status：`FROZEN_AND_IMPLEMENTED`（2026-08-17）

| Contract surface | Frozen requirement | Live evidence | Result |
|---|---|---|---|
| JSON wrapper | `detail.error`且exact 8 fields | `api/error_contracts.py`及多個route已使用 | compatible |
| Typed semantics | 已完整typed payload不得double-wrap或改寫Domain語意 | category/code/message/blockers/version可原樣保留 | compatible |
| Request correlation | absent generate+inject；single valid preserve；invalid/duplicate 422且0 downstream | ASGI middleware在FastAPI Header validation前統一scope header | implemented／tested |
| Existing typed correlation | response-only只rebase correlation；其餘七欄/status/protocol headers不變 | 真Order Reopen typed 409與503+Retry-After | implemented／tested |
| Redaction | unknown／legacy sensitive detail不得穿透 | MFA challenge/provisioning及unknown Data Browser detail均有negative tests | implemented／tested |
| React transport | 只接受完整nested envelope；mismatch退回HTTP fallback且保留raw | strict Zod exact 8 fields，無any/unknown/record/passthrough | implemented／tested |
| Namespace | 只套`/api/v1/**`、`/internal/v1/**` | provider/public routes由default handlers維持 | implemented |
| CORS | exact methods/request headers；expose correlation/retry/auth headers | 包含Idempotency、preview fingerprint、If-Match／If-None-Match | implemented／tested |

## Human decision and implementation

採用的唯一precedence：request-bound correlation是受控namespace的唯一公開correlation。既有完整typed
`detail.error`若帶不同`correlation_id`，Global boundary只在HTTP error serialization重綁該欄；其餘七欄、
HTTP status與headers無損保留。Boundary不得改Domain command、receipt、audit、outbox、job或idempotency。
這是response-only correlation rebase，不是Domain semantic rewrite或double-wrap。

使用者已exact核准Correlation Precedence Amendment。Backend A–K matrix 72 tests、React strict decoder
focused 69 tests、full React 517 tests與build均PASS；lint exit 0並保留既有MasterLayout 2 warnings。

---
doc_type: gap-package
declared_status: superseded
identity: PROV-20260817-global-fastapi-typed-error-boundary-gap
date: 2026-08-17
owner: Global / API Boundary
domain: Global
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
successor: PROV-20260817-global-fastapi-typed-error-boundary-work-package
---

# Global FastAPI typed error boundary 缺口

## Business scenario

React 管理端呼叫任一核准 API 時，輸入驗證、認證、授權、衝突、不可用與未預期錯誤必須使用
`00_Global_共同契約.md` 的同一 typed error envelope。現行 FastAPI 沒有全域
`RequestValidationError` / `HTTPException` / unexpected exception boundary，各 route 分別回傳
`detail` string、`detail.code` 或 `detail.error`，使 React client 無法可靠地 fail closed。

## Current evidence

- `shared_kernel/errors.py` 已有 `ErrorCategory` / `FieldError` / `TypedError`。
- `api/schemas/base.py` 沒有 strict Global error response model。
- `api/main.py` 與 `api/` 目前沒有完整的 FastAPI exception-handler 組合。
- `ui_react/src/api/shared/transport.ts`只讀legacy `detail.code/message`，不strict decode正式
  `detail.error`；兩段式登入因此可能只收到generic HTTP code。
- 現行 request schemas沒有可供真route驗證extra-field拒絕的`extra="forbid"`入口；successor只允許
  收緊password challenge request，不得藉此全面改Auth payload。
- Staff、Scheduling、Holiday、Leave/Substitution 的 401/403/422 可在 route 執行前由 FastAPI
  產生，單改 route 不可能完成 Global typed contract。

## Decision required

1. 是否以單一 Global FastAPI boundary 為 public error contract 唯一 owner；
2. 舊 route 的 `detail` 載荷只能由明確 adapter 轉換，不得以 message substring 猜測業務 code；
3. correlation id 的請求 header、回應 header 與 envelope 字段是否使用同一 canonical value；
4. legacy route 遷移期如何避免重複包裝已 typed 的 Domain error。

已收斂到successor的補充邊界：管理端JSON只涵蓋`/api/v1/**`與`/internal/v1/**`；provider webhook、
LIFF/gateway與legacy public surfaces維持原protocol。Correlation header固定`X-Correlation-ID`及
`^[A-Za-z0-9][A-Za-z0-9._:-]{0,190}$`，非法值不得回顯。

## Required successor

`PROV-20260817-global-fastapi-typed-error-boundary-work-package.md`

## DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | PASS | HTTP boundary only |
| Change inventory | PASS | 0 schema / seed / backfill / destructive |
| Static release gate | NOT_RUN | no DB release |
| Descriptor gate | NOT_RUN | no DB object |
| Read-only plan gate | NOT_RUN | not applicable |
| Engine verification gate | NOT_RUN | no DB work |
| Developer acceptance gate | NOT_RUN | no existing DB operation |

結論：`DB_CHANGE_NOT_READY`。

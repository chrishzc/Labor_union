# Phase 2B Open Findings & Gap Register

**Document Code**: `PROV-20260816-react-admin-phase2b-orders-open-findings`  
**Milestone**: Phase 2B Orders Safe Mutations (Confirmed Service Dates & Controlled Reopen)  
**Date**: 2026-08-16  
**Integration Owner**: `teamwork_preview_orchestrator_3`

---

## 1. Documented Backend Gaps (`BACKEND_GAP`)

| Gap ID | Description | Location | Handling & Rationale | Successor Wave / Disposition |
|---|---|---|---|---|
| **GAP-2B-01** | FastAPI pre-route validation error format | `api/main.py` / FastAPI pre-route handlers | When required HTTP headers (e.g. `Idempotency-Key`, `X-Correlation-ID`) or query parameters fail FastAPI validation before reaching route handlers, FastAPI returns its default `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}` format rather than the internal `{"detail": {"error": {...}}}` envelope. Modifying `api/main.py` is a forbidden shared hotspot in Phase 2B. | Handled gracefully in `order_mutation_errors.ts` as `OrderMutationBackendGapError` with `isBackendGap: true`. |
| **GAP-2B-02** | Unconverged Global Auth 401/403 format | `api/security/` / `api/main.py` | FastAPI HTTPBearer returns standard 401/403 strings when token is missing or malformed. | Handled by frontend error normalizer without assumptions of global error convergence. |

---

## 2. Explicit Out-of-Scope Capabilities (Locked Controls)

The following capabilities were intentionally excluded from Phase 2B and remain locked/disabled on the UI:

| Capability | Reason for Exclusion | Future Successor Requirement |
|---|---|---|
| Terms Preview / Apply | Preview view contains raw un-typed dict impacts across scheduling, client finance, payroll, and lifecycle. | Dedicated typed impact domain models. |
| Actual Start Preview / Apply | Contains raw cross-domain impacts requiring multi-domain transaction boundary. | Cross-domain typed contract wave. |
| Cancellation Preview / Apply | Preview view contains raw refund/payout projections; requires day-by-day owner UI. | Hardened cancellation workflow wave. |
| Assignment Plan Preview / Apply | Raw buffer/impact dict; constitutes execution scheduling rather than formal candidate recommendation. | Scheduling / Matching typed contract. |
| Contract Completion Apply | Must be triggered by Contract Signing signed event and outer UoW, not a manual button. | Event-driven contract workflow. |
| Candidate Pool / Resume / Willingness | HTTP endpoints currently return `BaseResponse[dict]`. | Matching domain typed contract. |
| LINE Manual Replay | Crosses LINE bounded domain without approved order-scoped typed timeline. | LINE notification catalog wave. |

---

## 3. Residual Blockers

- **`BLOCKED_REAL_BROWSER_EVIDENCE`**: Live password $\to$ TOTP $\to$ session flow requires human-in-the-loop MFA credentials.
- **`BLOCKED_TEST_DATA`**: Dedicated disposable test records for live mutation execution require operator provisioning.

Gates G0 through G5 and G7 are complete and verified; G6 is blocked by external prerequisites without compromise of codebase integrity.

## 4. 2026-08-16 Fresh Audit Remediation

獨立重審發現並已修正：

1. `outcome_unknown` 期間原本仍可改日期／reason，且正常 Apply 仍可點擊；現已由 Store 與 DOM 雙層鎖定，
   只允許相同 payload + 相同 key 的專用 replay。
2. receipt 已收到後 re-query 失敗原本會誤進 `outcome_unknown`；現改為保留 receipt 的
   `observation_failed`，只重試 Query，不重送 Apply。
3. Adapter 原本含 `unknown as` 與缺 receipt 時的硬編 fallback；現已移除，缺 receipt 固定 fail closed。
4. stale code 對齊 live backend 的 service-date、order、client-finance、payroll 與 preview conflict codes。

上述修正使舊 verification receipt 失效；以同目錄更新後的 current-candidate receipt 為準。

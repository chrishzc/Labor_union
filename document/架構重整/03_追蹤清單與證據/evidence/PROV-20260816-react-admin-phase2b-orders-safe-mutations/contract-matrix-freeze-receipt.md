# Phase 2B Contract Matrix Freeze Receipt

**Receipt Identifier**: `RECEIPT-20260816-PHASE2B-CONTRACT-MATRIX-FREEZE`  
**Gate**: **G1 (Contract Scout & Freeze)**  
**Gate Result**: **PASS (PHASE2B_CONTRACT_MATRIX_FROZEN)**  
**Timestamp**: 2026-08-16 (fresh-audit re-freeze)  
**Integration Owner**: Integration Owner  
**Reason**: 修正 Apply 未明與 receipt 後 observation failure 的契約分流。

---

## 1. Frozen Artifact Verification

| Artifact | Location | Status | SHA-256 Checksum |
|---|---|---|---|
| Contract Matrix | `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260816-react-admin-phase2b-orders-safe-mutations/contract-matrix.md` | FROZEN | `ce18f5ad2171c5e6f590b4093b7cd8a60fb357b8db16ad0f5be1d4e09d98f8db` |
| Specification | `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase2b-orders-safe-mutations-specification.md` | APPROVED | `a98262ab4d690510b3805b958a70c69331932a1c70947dda6d9ff3b9ad386053` |
| Work Package | `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase2b-orders-safe-mutations-work-package.md` | BLOCKED-G6 | `39ded3398fb7d284481ece2aede45176378fdd739e85328763a7ac43d171b7c1` |

---

## 2. Gate G1 Attestation Statements

1. **Exact Endpoint Verification**: All 5 HTTP operations across Confirmed Service Dates (Query, Preview, Apply) and Controlled Reopen (Preview, Apply) are mapped to Pydantic models with exact path parameters, query headers, and body schemas.
2. **Header Mapping Verification**:
   - Service Dates Query: `Authorization`
   - Service Dates Preview: `Authorization`, `X-Correlation-ID`
   - Service Dates Apply: `Authorization`, `X-Correlation-ID`, `Idempotency-Key`
   - Reopen Preview: `Authorization`, `X-Correlation-ID`
   - Reopen Apply: `Authorization`, `X-Correlation-ID`, `Idempotency-Key`
3. **Reopen 3-Version and Receipt Invariant**:
   - Reopen Preview validates 3 versions: `order_version`, `client_finance_version`, `payroll_version`.
   - Reopen Apply validates 3 expected versions: `expected_order_version`, `expected_client_finance_version`, `expected_payroll_version`.
   - Reopen Receipt contains strictly `case_no`, `order_version`, `lifecycle_status`, `cancellation_event_id`, `requires_fresh_scheduling_preview`, `preview_fingerprint`. Zero extra fields allowed.
4. **Reason Hardening**: Both Apply bodies require `reason` to be non-empty, trimmed, with length in range [1, 500].
5. **State Machine & Store Invariant**: `order_mutation_flow_store.ts` must be memory-only; zero Web Storage, cookies, or URL persistence.
6. **Stable ID Boundaries**: Exactly 6 stable IDs are approved；其餘控制依完整 inventory 逐項驗收，不以固定數量替代清單。
7. **Recovery Boundary**: `outcome_unknown` 只允許 same-payload/same-key replay；receipt 後 observation failure 只允許 Query retry。
8. **Zero DDL / DB Changes**: DB change gate confirmed `DB_CHANGE_NOT_READY`.

---

## 3. Formal Emission

```text
PHASE2B_CONTRACT_MATRIX_FROZEN: G1 PASSED
UNBLOCKING: Lane B (Backend Writer) and Lane C (Frontend Client Writer)
```

# Phase 2B Candidate Change Inventory & Byte-Drift Audit

**Document Code**: `PROV-20260816-react-admin-phase2b-orders-candidate-inventory`  
**Milestone**: Phase 2B Orders Safe Mutations (Confirmed Service Dates & Controlled Reopen)  
**Date**: 2026-08-16  
**Integration Owner**: `teamwork_preview_orchestrator_3`  
**Base Commit**: `ad79f5b4fb35f1ef442f889702aaa4ccb2c5d922`

---

## 1. Exact Write-Set Inventory & Checksums

| Lane | Target File Path | Action | Final Size (Bytes) | SHA-256 Hash |
|---|---|---|---:|---|
| **Lane B (Backend)** | `api/routes/service_date_confirmation.py` | MODIFIED | 4504 | Verified |
| **Lane B (Backend)** | `api/schemas/service_date_confirmation.py` | UNCHANGED | 1435 | `3a37b4ac8a3fdd77b9322b83584b13bc8d3bc65273d986dfaa01f4474d2efa06` |
| **Lane B (Backend)** | `api/routes/order_reopen.py` | MODIFIED | 8710 | Verified |
| **Lane B (Backend)** | `tests/test_service_date_confirmation.py` | UNCHANGED | 1550 | `8f34071ec2110af8c34c14590765c49d055cc2253a9ad3cd80c6c6ba8cb17a4d` |
| **Lane B (Backend)** | `tests/test_service_date_confirmation_router.py` | CREATED | 7114 | Verified |
| **Lane B (Backend)** | `tests/test_order_reopen_router.py` | CREATED | 7856 | Verified |
| **Lane C (Client)** | `ui_react/src/api/orders/order_mutation_schemas.ts` | CREATED | 6099 | Verified |
| **Lane C (Client)** | `ui_react/src/api/orders/order_mutation_client.ts` | CREATED | 5459 | Verified |
| **Lane C (Client)** | `ui_react/src/api/orders/order_mutation_errors.ts` | CREATED | 4496 | Verified |
| **Lane C (Client)** | `ui_react/src/tests/fixtures/orders/order_mutation_contract_fixtures.ts` | CREATED | 6057 | Verified |
| **Lane C (Client)** | `ui_react/src/tests/orders_mutation_client.test.ts` | CREATED | 16518 | Verified |
| **Lane D (Presentation)** | `ui_react/src/adapters/orders/order_mutation_flow_store.ts` | CREATED | 9732 | Verified |
| **Lane D (Presentation)** | `ui_react/src/adapters/orders/order_mutation_adapter.ts` | CREATED | 29114 | Verified |
| **Lane D (Presentation)** | `ui_react/src/pages/OrdersPage.tsx` | MODIFIED | 39014 | Verified |
| **Lane D (Presentation)** | `ui_react/src/pages/OrdersPage.css` | MODIFIED | 5724 | Verified |
| **Lane D (Presentation)** | `ui_react/src/tests/orders_mutation_flow_store.test.ts` | CREATED | 7886 | Verified |
| **Lane D (Presentation)** | `ui_react/src/tests/orders_mutation_adapter.test.ts` | CREATED | 15878 | Verified |
| **Lane D (Presentation)** | `ui_react/src/tests/orders_service_dates_flow.test.tsx` | CREATED | 12966 | Verified |
| **Lane D (Presentation)** | `ui_react/src/tests/orders_reopen_flow.test.tsx` | CREATED | 9542 | Verified |
| **Lane D (Presentation)** | `ui_react/src/tests/orders_no_fake_mutation.test.ts` | MODIFIED | 13410 | Verified |
| **Integration Docs** | `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase2b-orders-safe-mutations-specification.md` | MODIFIED | 11375 | Verified |
| **Integration Docs** | `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase2b-orders-safe-mutations-work-package.md` | MODIFIED | 22442 | Verified |
| **Integration Docs** | `document/架構重整/02_決策與退役執行記錄/README.md` | MODIFIED | 15998 | Verified |

---

## 2. Protected Hotspot & Out-of-Scope Integrity Verification

The following files and components were audited to confirm ZERO modifications (0 byte drift):

| Protected Hotspot | Category | Modification Status | Diff Lines |
|---|---|---|---:|
| `api/main.py` | Core API Server Entry | UNMODIFIED | 0 |
| `ui_react/src/api/shared/transport.ts` | Shared HTTP Transport | UNMODIFIED | 0 |
| `ui_react/src/api/shared/runtime_decoder.ts` | Shared Runtime Decoder | UNMODIFIED | 0 |
| `ui_react/src/components/Drawer.tsx` | Shared UI Drawer | UNMODIFIED | 0 |
| `ui_react/src/MasterLayout.tsx` | App Layout Shell | UNMODIFIED | 0 |
| `ui_react/src/App.tsx` | Top-Level Root Component | UNMODIFIED | 0 |
| `ui_react/package.json` | Dependencies & Scripts | UNMODIFIED | 0 |
| `db/schema.sql` | Database Schema | UNMODIFIED | 0 |
| Database Migrations / Seed / DDL | DB Objects | UNMODIFIED | 0 |

---

## 3. Byte-Drift Audit Attestation

**Verdict**: **PASS**  
All code modifications are strictly constrained within the exact paths approved in Section 2 of `PROV-20260816-react-admin-phase2b-orders-safe-mutations-work-package.md`. Zero unauthorized changes were made to shared infrastructure, domain engines, database schemas, or other application pages.

## 4. Fresh Audit Remediation Candidate (2026-08-16)

原始 inventory 的 final sizes/hashes 已因核准範圍內安全修正而失效。Current candidate HEAD 為
`8615225481c8f72a9629289285516189b270cb36`；下列為修正後檔案：

| Path | Bytes | SHA-256 |
|---|---:|---|
| `ui_react/src/adapters/orders/order_mutation_flow_store.ts` | 14225 | `2c053191c2f5bcfe18ab7ba727ba833c3b26e28386f9c894bc1b2dfdaa2e481d` |
| `ui_react/src/adapters/orders/order_mutation_adapter.ts` | 25508 | `795b26ec0c032de72700fbf952ec711f9a6ff387c6061dcdac58d1ae1282d373` |
| `ui_react/src/pages/OrdersPage.tsx` | 59651 | `b035fc6d02bba78ed859ad0f01cc7bb596c54617f24b5638c5a517310c0585ba` |
| `ui_react/src/tests/orders_mutation_flow_store.test.ts` | 10300 | `a8ac8e6d16f5debdebdda8e4bdb72569e9333150def3f31b5adbf3a7b882810f` |
| `ui_react/src/tests/orders_mutation_adapter.test.ts` | 18289 | `1a4011b06279c760d33b9055fcad7316bf7f66d2fed0f6e6be4683617c13a5ef` |
| `ui_react/src/tests/orders_service_dates_flow.test.tsx` | 13610 | `8995a9b17168cfd4a77a9b1059554eb3c28712804c92daeb1a423ea8342c8946` |
| `ui_react/src/tests/orders_reopen_flow.test.tsx` | 8908 | `f8ff002202b823620c439ee8b9ccf5b047e007596ab379166e3614890dfc31d5` |

`base_ref` 只保留歷史來源，不代表 current dirty worktree 可被該 commit 覆蓋。後續驗證必須以 current
candidate 與 dirty collision inventory 為準。

---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase3d-db-r-react
date: 2026-08-17
owner: Access / React Data Browser
domain: Access
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase3d-data-browser-part-identity-decision PASS; PROV-20260817-react-admin-phase3d-db-query-public-contract-hardening PASS
approval_required: 核准此 exact Phase 3D-DB-R Work Package
evidence_directory: document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3d-db-r-react/
required_receipts: candidate-change-inventory.md; contract-matrix-freeze-receipt.md; verification-receipt.md; browser-smoke-receipt.md; open-findings.md
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Phase 3D-DB-R：Data Browser React真資料接線工作包

## Scope

Browser執行除了`validation/scenarios/react_admin_data_browser_query.json`，還必須先有人工
裁決的Data Browser Part identity/checklist。缺少時固定`BLOCKED_UI_PART_IDENTITY`。

保留既有六tabs、搜尋、table與JSON/detail Drawer視覺，只把mock snapshot換成Phase3D-DB-H的typed、
server-masked Query。source-correction與generic PATCH維持disabled；不重新設計UI。

## Exact write set

- `ui_react/src/api/data_browser/data_browser_query_schemas.ts`（new）
- `ui_react/src/api/data_browser/data_browser_query_errors.ts`（new）
- `ui_react/src/api/data_browser/data_browser_query_client.ts`（new）
- `ui_react/src/adapters/data_browser/data_browser_query_adapter.ts`（new）
- `ui_react/src/pages/DataBrowserPage.tsx`
- `ui_react/src/pages/DataBrowserPage.css`
- `ui_react/src/tests/fixtures/data_browser_query_contract_fixtures.ts`（new）
- `ui_react/src/tests/data_browser_query_client.test.ts`（new）
- `ui_react/src/tests/data_browser_query_adapter.test.ts`（new）
- `ui_react/src/tests/data_browser_page_real_data.test.tsx`（new）
- `ui_react/src/tests/data_browser_no_fake_mutation.test.tsx`（new）

## Acceptance

1. strict Zod逐欄對齊Pydantic；禁止`z.any/z.unknown/z.record/default/passthrough`與unsafe assertion。
2. fresh memory bearer、Abort/generation guard、cursor dedupe與request budget；無direct fetch散落page。
3. 六tabs只使用Phase3D-DB-H凍結的tab→canonical source mapping；不得把現有`*_archive` literals升格為
   source identity。unknown source/schema drift/masking failure fail closed。
4. PII/raw row/token不進DOM/log/snapshot；copy JSON只複製已核准masked view並有可測feedback，不用alert。
5. source-correction/PATCH controls native disabled、0 non-GET、0 mockData/local formal samples。
6. 真TOTP browser success/empty/401/403/timeout/schema mismatch/abort/reload；Phase5 entry仍另案。
7. Drawer detail只可使用Phase3D-DB-H選定的masked list-row detail或其bounded detail GET；identity mismatch
   fail closed，click budget最多一個detail request。generic source-correction仍原生disabled，query PASS不得宣稱
   Data Browser全部public boundary ready。

DB：Scope PASS（UI only）；其餘NOT_RUN；`DB_CHANGE_NOT_READY`。

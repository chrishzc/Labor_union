---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase4c-k-r-react
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
owner: Knowledge Retrieval React Integration Owner
domain: Knowledge Retrieval
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-line-knowledge-authorization-normalization PASS; PROV-20260817-react-admin-phase4c-knowledge-public-query-hardening PASS; PROV-20260817-react-admin-phase4c-d-r-react PASS
approval_required: 核准此 exact Phase 4C-K-R Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: browser-required
---

# Phase 4C-K-R：Knowledge／FAQ catalog React工作包

## Scope與write set

移除faq tab兩筆硬編FAQ，改接masked catalog；只顯示id/title/lifecycle/version/updated_at與bounded pagination。
不接全文、URI、question/answer/citation、LINE task或任何FAQ mutation。

兩個 exact prerequisites 必須皆 PASS；前端不得以 menu visibility 或 local role mapping 取代授權契約。

- `ui_react/src/api/knowledge/knowledge_catalog_client.ts`
- `ui_react/src/api/knowledge/knowledge_catalog_schemas.ts`
- `ui_react/src/api/knowledge/knowledge_catalog_errors.ts`
- `ui_react/src/adapters/knowledge/knowledge_catalog_adapter.ts`
- `ui_react/src/pages/LineManagementPage.tsx`
- `ui_react/src/pages/LineManagementPage.css`
- `ui_react/src/tests/knowledge_catalog_client.test.ts`
- `ui_react/src/tests/knowledge_catalog_adapter.test.ts`
- `ui_react/src/tests/line_faq_catalog_flow.test.tsx`
- `ui_react/src/tests/line_management_no_fake_mutation.test.tsx`
- `ui_react/src/tests/fixtures/knowledge/knowledge_catalog_contract_fixtures.ts`
- `validation/scenarios/react_admin_knowledge_catalog_query.json`（read-only consume；由Phase4 Scenario Lineage唯一擁有）

新增`line.faq.catalog|refresh|filter|item|empty|unavailable`；`create|publish|retire|reindex`維持disabled。

Exact client只可呼叫`GET /api/v1/knowledge/items?limit=<bounded>&lifecycle_status=<safe-enum>`並strict decode
backend frozen envelope；不得呼叫item detail、jobs、indexes、questions或mutation routes。Pagination UI必須
符合backend實際`limit` contract，不得自創page/page_size或total。任何content/source identity/URI/
question/answer/citation/correlation/delivery task等欄位出現在transport、adapter、DOM、log或snapshot均fail。

## Gates

G0 backend/exact approval；G1 masked catalog matrix；G2 strict decoder/auth/pagination；G3 adapter zero content/URI；
G4 lazy load/abort/stale/empty/error；G5 zero non-GET/mock/fake；G6 full React/build/lint/UTF-8/diff/content leak；
G7真browser controlled catalog。與4C-D-R共享page，只能由單一Integration Writer串行整合。

G7使用`validation/scenarios/react_admin_knowledge_catalog_query.json`的controlled published/draft sentinels，
保存Network→typed DOM與masking evidence；空catalog或writer fixture不能冒充。禁止修改shared transport/Auth、
package/lockfile、其他pages與既有Rules/Rich Menu/Customer Service/Identity clients。

DB：Scope PASS，其餘NOT_RUN；`DB_CHANGE_NOT_READY`。

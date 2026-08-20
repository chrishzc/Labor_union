---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase4c-d-r-react
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
owner: LINE Delivery React Integration Owner
domain: LINE Delivery
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-line-knowledge-authorization-normalization PASS; PROV-20260817-react-admin-phase4c-line-delivery-public-query-hardening PASS; PROV-20260816-react-admin-phase4c-line-rules-rich-menu-query PASS
approval_required: 核准此 exact Phase 4C-D-R Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: browser-required
---

# Phase 4C-D-R：LINE Delivery observability React工作包

## Scope與write set

只在現有push_queue tab新增masked summary/list/detail GET；不把notification-rule catalog冒充task queue，
不接cancel/run-now/retry，不喚醒worker/provider。

frontmatter列出的每一個 exact prerequisite都必須有fresh PASS；前端不得把 role menu visibility當authorization normalization。

`push_queue`目前實際承載Notification Rules catalog；本包不得覆蓋或改名冒充Delivery。UI必須在該
workspace內新增可辨識的secondary view／sub-tab：「通知規則」與「Delivery任務」，預設及route state
由既有六-tab頁管理。Rules view繼續使用既有Phase4C-Q client；Delivery view才可發三個核准GET。

- `ui_react/src/api/line_delivery/line_delivery_query_client.ts`
- `ui_react/src/api/line_delivery/line_delivery_query_schemas.ts`
- `ui_react/src/api/line_delivery/line_delivery_query_errors.ts`
- `ui_react/src/adapters/line_delivery/line_delivery_query_adapter.ts`
- `ui_react/src/pages/LineManagementPage.tsx`
- `ui_react/src/pages/LineManagementPage.css`
- `ui_react/src/tests/line_delivery_query_client.test.ts`
- `ui_react/src/tests/line_delivery_query_adapter.test.ts`
- `ui_react/src/tests/line_delivery_query_flow.test.tsx`
- `ui_react/src/tests/line_management_no_fake_mutation.test.tsx`
- `ui_react/src/tests/fixtures/line_delivery/line_delivery_query_contract_fixtures.ts`
- `validation/scenarios/react_admin_line_delivery_query.json`（read-only consume；由Phase4 Scenario Lineage唯一擁有）

新增`line.delivery.summary|table|refresh|detail|filter|pagination`；`cancel|run-now|retry`存在但disabled。
禁止recipient/payload/message preview/provider/correlation/raw error/actor/reason進DOM。

Exact client allowlist只有`GET /api/v1/line/tasks/summary`、`GET /api/v1/line/tasks`與
`GET /api/v1/line/tasks/{task_id}`。List filters只允許status/safe source type/scheduled range/page/page_size；
禁止recipient/user/source identity。Success必須strict decode Global envelope與backend frozen public views；
所有non-GET、raw dict fallback、hard-coded queue item及existing query client修改均禁止。

## Gates

G0 backend/exact approval；G1 masked field matrix；G2 strict decoder/auth/pagination；G3 adapter零敏感欄位；
G4 tab lazy load/abort/stale/detail；G5 fetch只GET、controls disabled、0 mock/fake；G6 full React/build/lint/
UTF-8/diff/PII；G7真browser controlled task。與4C-K-R共享page，只能由單一Integration Writer串行整合。

G7使用`validation/scenarios/react_admin_line_delivery_query.json`的controlled actor/task/status sentinel，
逐一保存Network endpoint/status與masked DOM assertion；empty/unavailable或component fixture不能冒充真資料。
禁止修改shared transport/Auth、package/lockfile、其他pages、既有Rules/Rich Menu query clients。

DB：Scope PASS，其餘NOT_RUN；`DB_CHANGE_NOT_READY`。

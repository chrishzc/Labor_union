---
doc_type: work-package
declared_status: superseded
identity: PROV-20260817-react-admin-phase3b-q-h-scheduling-current-public-query
date: 2026-08-17
owner: Scheduling / API Boundary Integration Owner
domain: Scheduling
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance completed with PHASE3_SCENARIO_LINEAGE_METADATA_READY; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260816-react-admin-phase3b1-staff-contract-hardening-selector-amendment PASS
approval_required: 核准此 exact Phase 3B-Q-H Scheduling Current Public Query Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: not-applicable
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
successor: PROV-20260817-react-admin-scheduling-query-page-slice-work-package
---

# Phase 3B-Q-H：Scheduling Current public query / auth hardening

> 2026-08-17：依逐頁精簡遷移裁決，本提案與React Q-R合併由單一Scheduling Query Page-Slice承接；
> 本文件未曾取得exact核准，現標`superseded`。

## Business scenario

Controlled input固定來自`validation/scenarios/react_admin_scheduling_current_query.json`與其
fixture/expected lineage；缺少時不得啟動backend writer。

已啟用的內部使用者查詢去敏 staff current-calendar，作為 React 甘特投影的唯一 server
lineage。查詢不得因歷史 role/capability 分流而導致同為 enabled user 看到不同業務
功能，也不得 commit。

## Exact write set

- `api/routes/scheduling_current.py`
- `api/schemas/scheduling_current.py`
- `tests/test_scheduling_current_router.py`（new）
- `tests/test_scheduling_current_api_client.py`
- `tests/test_scheduling_current_projection_workflow.py`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3b-q-h-scheduling-current-public-query/`（new）

## Contract and acceptance

1. 使用正式 enabled-principal policy；不保留 `require_system_admin` 造成的業務功能差異。
2. Path/range/mutual parameter validation 與 auth 全部由 Global typed error boundary 統一。
3. Response/nested view strict；date/lifecycle/occupancy/projection token 只回 server facts，不附帶
   PII、payroll、eligibility 或隱式推導。
4. Query path 0 commit / 0 lock-for-write / 0 outbox / 0 job / 0 provider call。
5. 測 success、empty、unauthenticated、disabled principal、invalid range、not-found、storage unavailable、
   duplicate date/assignment fail closed 與 correlation/redaction。
6. 本包不修 React；完成後才能啟動 Phase 3B-Q-R。

## DB gate

Scope / Change inventory `PASS`（query-only, 0 DB change）；其餘 `NOT_RUN`；
結論 `DB_CHANGE_NOT_READY`。

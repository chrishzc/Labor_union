---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase3d-r-anomaly-detail-react
date: 2026-08-17
owner: Anomalies React Integration Owner
domain: Anomalies
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase3d-anomalies-public-detail-hardening PASS
approval_required: 核准此 exact Phase 3D-R Work Package
evidence_directory: document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3d-r-anomaly-detail-react/
required_receipts: candidate-change-inventory.md; contract-matrix-freeze-receipt.md; verification-receipt.md; browser-smoke-receipt.md; open-findings.md
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Phase 3D-R：Anomaly detail／recovery React query 工作包

## Scope

Browser/DOM驗收使用上游Anomaly successor scenario與
`validation/ui_business_workflows/part_14_anomalies/`；component fixture不得代替。

只把既有Anomalies Drawer接到typed detail/timeline/evidence/recovery Query。Claim、Resolve與Warning transition
維持native disabled；recovery metadata不得顯示成「已修復」。前置3D-H未完成時本包不可施工。

## Exact write set

- `ui_react/src/api/anomalies/anomaly_detail_client.ts`
- `ui_react/src/api/anomalies/anomaly_detail_schemas.ts`
- `ui_react/src/api/anomalies/anomaly_detail_errors.ts`
- `ui_react/src/adapters/anomalies/anomaly_detail_adapter.ts`
- `ui_react/src/pages/AnomaliesPage.tsx`
- `ui_react/src/pages/AnomaliesPage.css`
- `ui_react/src/tests/anomaly_detail_client.test.ts`
- `ui_react/src/tests/anomaly_detail_adapter.test.ts`
- `ui_react/src/tests/anomalies_detail_flow.test.tsx`
- `ui_react/src/tests/anomalies_no_fake_mutation.test.tsx`
- `ui_react/src/tests/fixtures/anomalies/anomaly_detail_contract_fixtures.ts`

## Stable surfaces

保留`anomalies.card.drawer_open`、`anomalies.drawer`、`.root-evidence`、`.recovery`；新增
`anomalies.drawer.detail|timeline|evidence`。`anomalies.card.claim`與`anomalies.drawer.resolve`必須disabled。

## Gates

G0 exact approval/backend receipt；G1 strict field/redaction matrix；G2 strict Zod negative cases；G3 adapter零推導；
G4 lazy detail/abort/stale/error/close-switch tests；G5 zero non-GET/mock/alert/confirm；G6 full React build/lint/test、
UTF-8/diff/PII；G7真FastAPI+Vite Network↔DOM。Happy DOM或HTTP 200不能替代G7。

DB：Scope PASS，其餘NOT_RUN；`DB_CHANGE_NOT_READY`。

---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase3d-anomalies-public-detail-hardening
date: 2026-08-17
owner: Anomalies / Access Integration Owner
domain: Anomalies
source_gap: PROV-20260817-react-admin-phase3d-anomalies-warning-mutation-gap
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase2d-h-closure-gate-amendment PASS; PROV-20260816-react-admin-phase2d-backend-public-contract-hardening PASS
approval_required: 核准此 exact Phase 3D-H Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: not-applicable
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Phase 3D-H：Anomalies public detail／recovery hardening 工作包

## 0. 目的與前置門

Controlled lineage採用`ANOM-PROJECTOR-CLOSED-LOOP-003`、`ANOM-SCHEDULING-CLOSED-LOOP-002`與
`ANOM-CLOSED-LOOP-001`；必須由Phase3 scenario matrix記錄supplement/expected/fresh receipt，不得
直接把舊receipt當本包PASS。

本包為proposed，只修後端Query/detail/recovery public contract；不啟用Claim／Resolve／warning transition，
不改React、不執行owner repair、不改DB/schema。Phase 2D-H disposable MySQL與affected-scope regression未閉合時，
本包最高狀態為`implemented-awaiting-phase2d-h-engine-gate`。

## 1. Exact write set

- `api/schemas/anomaly_registry.py`
- `api/schemas/anomaly_recovery.py`
- `api/routes/anomaly_registry.py`
- `api/routes/anomaly_recovery.py`
- `subsystems/anomalies/alert_workflow.py`
- `subsystems/anomalies/root_fact_projection_workflow.py`
- `tests/test_anomaly_registry_router.py`
- `tests/test_finance_anomaly_registry_contract.py`
- `tests/test_anomaly_public_detail_recovery_contract.py`（new）

Import Warning transition、repository、Domain、React、shared handler/Auth、DB/schema不在本包。需要任一路徑時
固定`SCOPE_EXPANSION_REQUIRED`。

### Integration document write set

- `document/架構重整/01_規格基線/06_Anomalies_Domain.md`
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- 本工作包、`02/README.md`與
  `03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3d-anomalies-public-detail-hardening/`（new）

只由Integration Owner寫入。

## 2. Contract policy

- `display_snapshot`、timeline、source bindings不得使用raw dict穿越public boundary。
- 每個definition的display/evidence/action由server typed discriminated view提供；未知definition/action fail closed。
- public detail只放去敏evidence與stable action metadata，不放raw payload、完整個資、SQL/table/internal path。
- recovery只回owner bounded Preview入口與required inputs/capability/completion predicate；不在Anomalies route代做repair。
- Resolve語意不得在任何label/message暗示root repaired。

## 3. 分工

Contract Scout（Luna，唯讀）先凍結每個definition variant；Primary擁有schema/route/workflow；Terra在freeze後
補disjoint tests；Luna final audit；Integration Owner唯一寫docs/evidence/index。

## 4. G0–G7

- G0 exact approval、Phase2D-H狀態記錄、0 DB/React/mutation。
- G1 detail/timeline/action/recovery逐欄typed/redaction矩陣。
- G2 success/empty/unknown-definition/null/extra/malformed fail closed。
- G3 auth、401/403/404/409/503、typed error/correlation。
- G4 Query零寫：0 commit、0 repair、0 outbox/provider。
- G5 Resolve wording與completion predicate tests證明不宣稱root repaired。
- G6 focused/full anomaly regression、UTF-8、diff、PII/raw-dict/secret scan。
- G7 evidence來自current route/application，不接受自創fixture或HTTP 200充數。

## 5. Required commands

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp\phase3d-h -q `
  tests\test_anomaly_registry_router.py `
  tests\test_finance_anomaly_registry_contract.py `
  tests\test_anomaly_public_detail_recovery_contract.py
git diff --check -- api/schemas/anomaly_registry.py api/schemas/anomaly_recovery.py api/routes/anomaly_registry.py api/routes/anomaly_recovery.py subsystems/anomalies/alert_workflow.py subsystems/anomalies/root_fact_projection_workflow.py tests/test_anomaly_registry_router.py tests/test_finance_anomaly_registry_contract.py tests/test_anomaly_public_detail_recovery_contract.py
```

## 6. Completion boundary

本包通過後只解鎖既有`PROV-20260817-react-admin-phase3d-r-anomaly-detail-react`唯讀detail/recovery接線。
Import Warning transition另由`PROV-20260817-react-admin-phase3d-warning-transition-receipt-hardening`→
`PROV-20260817-react-admin-phase3d-w-r-warning-transition-react`鏈處理；Claim／Resolve尚無核准owner/state契約，
仍停在gap，不得用detail或warning receipt順便解鎖。owner repair與HCM Apply仍由各自bounded successor擁有。

## 7. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | PASS | query/public contract；0 schema |
| Change inventory | NOT_RUN | 無DB change |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無owned-object變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 上游Phase2D-H仍需閉合 |
| Developer acceptance gate | NOT_RUN | 不操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。

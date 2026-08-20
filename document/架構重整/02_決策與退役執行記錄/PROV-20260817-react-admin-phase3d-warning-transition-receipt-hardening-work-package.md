---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase3d-warning-transition-receipt-hardening
date: 2026-08-17
owner: Import Warning / Anomalies Integration Owner
domain: Anomalies / Case Import
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase2d-h-closure-gate-amendment PASS; PROV-20260816-react-admin-phase2d-backend-public-contract-hardening PASS
approval_required: 核准此 exact Phase 3D-W-H Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: not-applicable
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Phase 3D-W-H：Import Warning transition receipt hardening工作包

## Goal

Controlled input固定來自`validation/scenarios/react_admin_import_warning_transition.json`，並保留
`CI-CASE-IMPORT-001`、`FI-CANONICAL-STAGING-003`、`FI-STAGING-DEDUP-002`的source mapping。

收斂既有Preview／Apply transition的public contract，使Apply回獨立terminal receipt並可authenticated re-query；
不接React、不執行owner repair/re-import、不解鎖HCM Apply、不改DB/schema。

## Exact write set

- `api/schemas/import_warning_tracking.py`
- `api/routes/import_warning_tracking.py`
- `subsystems/anomalies/import_warning_tracking_workflow.py`
- `infrastructure/mysql/import_warning_tracking_repository.py`
- `tests/test_import_warning_tracking.py`
- `tests/test_import_warning_tracking_workflow.py`
- `tests/test_import_warning_tracking_api.py`
- `tests/test_import_warning_tracking_api_client.py`
- `tests/test_import_warning_tracking_api_disposable_mysql_e2e.py`
- `tests/test_import_warning_transition_receipt_contract.py`（new）
- `tests/test_import_warning_tracking_disposable_mysql_e2e.py`

## Contract/invariants

- Preview zero-write；Apply fresh expected version並驗證canonical payload。
- Apply回`WarningTransitionReceiptView`，不得重用Preview view；包含occurrence identity、before/after status、
  resulting version、receipt identity、correlation與replayed flag，不回PII/raw evidence。
- authenticated receipt/re-query可辨識unknown outcome；same-key/same-payload同receipt，mismatch conflict。
- warning transition只改tracking workflow，不冒充owner root修復或HCM re-import完成。
- repository不得hidden commit；若既有table不足立即`DB_SCOPE_REQUIRED`。

## Integration document write set

- `document/架構重整/01_規格基線/06_Anomalies_Domain.md`
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- 本工作包、`02/README.md`與
  `03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3d-warning-transition-receipt-hardening/`（new）

只由Integration Owner寫入。

## Gates

G0 exact approval/upstream gate；G1 Preview/Apply/receipt/error matrix；G2 zero-write/fresh/replay/conflict；
G3 single UoW/hidden-commit scan；G4 auth/typed errors/redaction；G5 disposable MySQL；G6 regression/UTF-8/diff/
PII；G7 evidence。skip engine即BLOCKED。

G5必須同時執行現有真HTTP＋disposable MySQL E2E，驗terminal receipt identity、before/after、replayed、
authenticated receipt lookup、re-query observation、outbox count與任一失敗的完整rollback。Backend PASS後只解鎖
`PROV-20260817-react-admin-phase3d-w-r-warning-transition-react`；Claim／Resolve與owner root repair仍是獨立gap。

## Required command

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp\phase3d-warning -q `
  tests\test_import_warning_tracking.py tests\test_import_warning_tracking_workflow.py `
  tests\test_import_warning_tracking_api.py tests\test_import_warning_tracking_api_client.py `
  tests\test_import_warning_tracking_api_disposable_mysql_e2e.py `
  tests\test_import_warning_transition_receipt_contract.py tests\test_import_warning_tracking_disposable_mysql_e2e.py
```

## DB gate

| Gate | Status | Evidence／reason |
|---|---|---|
| Scope gate | BLOCKED | 尚未exact核准且scenario/upstream prerequisites未PASS |
| Change inventory | BLOCKED | 核准前須列existing warning status/version、transition receipt、audit/outbox runtime writes；0 schema不等於0 DB write |
| Static release gate | NOT_RUN | 無schema release |
| Descriptor gate | NOT_RUN | 若現有table不足固定DB_SCOPE_REQUIRED |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 核准後要求真HTTP＋disposable MySQL，skip即BLOCKED |
| Developer acceptance gate | NOT_RUN | 不操作既有資料庫 |

總結固定`DB_CHANGE_NOT_READY`。

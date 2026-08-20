---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase4b-client-finance-public-contract-hardening
date: 2026-08-17
owner: Client Finance
domain: Client Finance
approval_required: 核准此 exact Phase 4B-CF-H Work Package
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer; required-before-writer; preserve-all-user-work
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: not-applicable
---

# Phase 4B-CF-H：Client Receipt／Refund／Reversal public contract工作包

## Exact production write set

- `api/routes/client_receipt_reconciliation.py`
- `api/schemas/client_receipt_reconciliation.py`
- `api/routes/client_refund_reversal.py`
- `api/schemas/client_refund_reversal.py`

## Exact test／doc write set

- `tests/test_client_receipt_reconciliation_public_contract.py`（new）
- `tests/test_client_refund_reversal_public_contract.py`（new）
- `tests/test_client_receipt_deposit_projection.py`
- `tests/test_client_refund_reversal_route.py`
- `document/架構重整/01_規格基線/16_Staff_Payables與Client_Refund正式規格.md`（Integration Owner only）
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`（Integration Owner only）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase4b-client-finance/`（new）

## Acceptance

1. receipt preview candidate與refund/reversal query arrays改成bounded nested views；public response 0 `dict[str,Any]`。
2. status/event/purpose/correction type與field errors使用strict item/literals，不用generic string/map。
3. 保留Domain single-UoW、fresh fact、stale、fingerprint、idempotency/replay及rollback，不重算金額。
4. 所有route使用正式同權限政策的`require_admin`；401／403只承諾fail closed與零PII，route/domain產生的
   404／409／422／503使用typed envelope。不得新增capability差異或把shared auth漂移藏在本包。
5. Preview 0 write、Apply receipt/re-query、same-key replay/conflict與disposable MySQL invariants通過。
6. React不得把HTTP 200或local state當settled/refunded；React successor另案。
7. 所有mutation reason在server trim後必須1–500字；空白、控制字元與超長固定typed validation error，
   reason納入canonical fingerprint。使用真FastAPI TestClient覆蓋request/response，不以直接呼叫function代替。
8. Scenario映射固定覆蓋Part 00 P00-G46／G47／G53。

DB Gate：Scope PASS（0 schema）；其餘NOT_RUN；`DB_CHANGE_NOT_READY`。

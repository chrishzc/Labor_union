---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-access-audit-public-query-hardening
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
owner: Access Audit Integration Owner
domain: Access / Security Audit
approval_required: 核准此 exact Access Audit Public Query Hardening Work Package
evidence_directory: document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-access-audit-public-query-hardening/
required_receipts: candidate-change-inventory.md; contract-matrix-freeze-receipt.md; verification-receipt.md; open-findings.md
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: not-applicable
prerequisites: PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS
presentation_prerequisite: Account Center page integration precedes Access Audit only because AccountManagementPage.tsx is a shared hot spot; backend query hardening is independent
---

# Access Audit public Query hardening工作包

## 0. Scope

現行list已有typed外殼，但Subsystem items仍是raw dict，detail的`details`允許任意dict/list/primitive。核准後本包只
建立authenticated、server-masked、closed audit list/detail views；Audit是所有enabled internal users可查的獨立
read surface，不是root-only Account Center mutation。0 mutation、0 archive/delete、0 DB/schema。

## 1. Exact write set

- `api/routes/admin_audit.py`
- `api/schemas/admin_audit.py`
- `subsystems/access/security_audit_query.py`
- `tests/test_admin_security_audit_policy.py`
- `tests/test_access_audit_public_query_contract.py`（new）
- `validation/scenarios/react_admin_access_audit_query.json`（new）

Integration Owner另可更新正式Access規格、本WP、`02/README.md`與專屬evidence。Account Center、Jobs、React、
shared handler、DB/schema/dependency不在write set。

## 2. Contract與acceptance

- List/detail均為closed Pydantic views；不允許`Any`、任意`details`、raw JSON穿透。
- Public fields只含audit identity、time、masked actor display、action family、masked target、outcome、bounded reason/code；
  IP、token、secret、TOTP seed、full payload、bank/identity/contact資料與storage/internal error禁止輸出。
- Query 0 commit/0 archive/0 mutation；pagination/filter由server權威，invalid filter typed 422，401/403 fail closed。
- 詳細資料採approved discriminated detail union或safe key/value allowlist；未知action/detail shape固定redacted，不回raw。
- Tests涵蓋success/empty/pagination/filter/not-found/401/403、extra/missing/null、PII leak corpus、query 0 write。
- G0 exact approval；G1 field/redaction matrix；G2 backend strict views；G3 focused tests；G4 static leak scan；
  G5 full Access regression/UTF-8/diff；G6 evidence receipt。未通過不得啟動React successor。

## 3. DB gate

| Gate | 狀態 | 理由 |
|---|---|---|
| Scope gate | PASS | existing audit Query hardening，0 DB |
| Change inventory | PASS | 0 schema/seed/backfill/destructive |
| Static release gate | NOT_RUN | 不適用 |
| Descriptor gate | NOT_RUN | 不適用 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不適用 |

總結：`DB_CHANGE_NOT_READY`。

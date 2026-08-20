---
doc_type: work-package
declared_status: superseded
identity: PROV-20260817-react-admin-phase6b-artifact-health-private-contract-amendment
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
owner: Global Runtime / Private Operations Integration Owner
domain: Global Runtime
authority: awaiting-exact-human-approval
successor: PROV-20260817-react-admin-phase6b-production-hosting
superseded_reason: private read-only artifact-health contract已吸收進最小Phase6B HOST spec/WP
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS
approval_required: 核准此 exact Phase 6B Artifact Health Private Contract Amendment Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: not-applicable
---

# Phase 6B Artifact Health Private Contract 修訂工作包

> Superseded：本修訂未獨立施工；其service-auth read-only attestation已由
> `PROV-20260817-react-admin-phase6b-production-hosting`完整吸收，不再作HOST activation blocker。

## 0. Business scenario

Phase6B-HOST需要讓monitor驗證目前實際掛載的immutable React artifact，但不能以generic HTTP 200、目錄mtime
或browser-visible filesystem path冒充健康。正式typed owner是Private Operations；本包只補active mounted
artifact的read-only attestation。current／previous候選綁定與切換仍由HOST本機selector contract擁有。

## 1. Exact write set

- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase6b-production-hosting-specification.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase6b-production-hosting-work-package.md`
- `infrastructure/runtime/react_admin_artifact.py`
- `api/schemas/private_operations.py`
- `api/routes/private_operations.py`
- `api/dependencies/private_operations.py`
- `tests/test_private_runtime_operations.py`
- `tests/test_react_admin_static_hosting.py`
- `document/架構重整/01_規格基線/18_Global_Deployment與治理正式規格.md`（Integration Owner only）
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`（Integration Owner only）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase6b-production-hosting/`（Integration Owner only）

## 2. Public/private boundary

1. endpoint只接受service authentication，browser principal不得直接取得private runtime attestation。
   Exact transport固定為`POST /internal/v1/runtime/react-admin/artifact-health`，request body為closed空object；
   不接受selector、path或filesystem identity由caller任意注入。
2. response只包含server目前實際掛載的`active_selector`（`current | previous`）、release identity、API compatibility
   revision、manifest digest、root marker與checked-asset summary；caller不能用request選擇或探查另一個artifact。
3. filesystem path、secret、token、environment、raw manifest、asset內容及operator credential不得出現在response/error/log/receipt。
4. server active selector未知、mounted artifact缺失、digest mismatch、API compatibility drift與extra served file均typed fail closed。
5. Private Operations query唯讀；不得commit DB、建立monitor observation或觸發LINE intent。

## 3. Acceptance

- schema closed且negative tests覆蓋missing/extra/wrong/null、401/403、active selector與digest drift，並證明request
  無selector/path欄位且不能讀取未掛載的previous artifact。
- HOST與RUN只消費此單一attestation，不得建立第二套validator。
- generic `/health`或`/admin/` 200不能替代typed artifact health。
- 0 DB schema／migration／seed／backfill、0 external provider、0 entry／Streamlit mutation；僅允許exact write set
  中列出的API transport schema。
- 本修訂先freeze並交接HOST spec/WP與Private Operations contract；HOST不得與本修訂同時寫
  `react_admin_artifact.py`、HOST spec/WP或共享tests。HOST G0須引用本修訂fresh PASS receipt與base ref。

## 4. DB gate

| Gate | Status | Evidence／reason |
|---|---|---|
| Scope gate | BLOCKED | 尚未取得exact approval；核准後為private read-only contract |
| Change inventory | PASS | 0 DB/schema/seed/backfill |
| Static release gate | NOT_RUN | 無DB release |
| Descriptor gate | NOT_RUN | 無schema object |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作既有DB |

結論：`DB_CHANGE_NOT_READY`。

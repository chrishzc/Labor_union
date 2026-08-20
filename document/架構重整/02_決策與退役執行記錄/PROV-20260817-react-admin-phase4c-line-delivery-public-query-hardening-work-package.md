---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase4c-line-delivery-public-query-hardening
date: 2026-08-17
owner: LINE Delivery / Access Integration Owner
domain: LINE Delivery
source_gap: PROV-20260816-react-admin-phase4c-line-delivery-public-query-gap
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-line-knowledge-authorization-normalization PASS
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
approval_required: 核准此 exact Phase 4C-D Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: not-applicable
---

# Phase 4C-D：LINE Delivery server-masked public query hardening 工作包

## 0. 狀態與目標

本包尚未核准。核准後只建立 Delivery task summary/list/detail 的 authenticated、typed、server-masked
Query contract。cancel／run-now／retry與worker wake-up全部不在範圍；不接 React、不呼叫 provider、
不改 DB/schema。

開工前 `PROV-20260817-line-knowledge-authorization-normalization` 必須 PASS；不得沿用現行 role→capability
漂移，也不得把前端選單隱藏當作授權修復。此 prerequisite 未通過時 G0 固定 BLOCKED。

## 1. Exact write set

- `api/routes/line_tasks.py`
- `api/schemas/line_tasks.py`
- `subsystems/line/delivery_admin_contracts.py`
- `subsystems/line/delivery_admin_application.py`
- `infrastructure/mysql/line_delivery_task_repository.py`
- `tests/line/subsystems/test_line_delivery_public_query.py`（new）
- `tests/test_line_delivery_public_query_route.py`（new）

Mutation routes的既有程式碼只可characterization，不得重構或改行為。shared handler、worker、React、
provider adapter、DB/schema/dependency不在write set。

### Integration document write set

- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md`
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md`
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- 本工作包、`02/README.md`與
  `03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase4c-line-delivery-public-query-hardening/`（new）

只由Integration Owner寫入。

## 2. Public view policy

允許：bounded status/count、task type的安全label、attempt count、created/updated/next-run timestamps、
safe source label、worker summary。禁止：recipient identity／type、payload JSON、message preview、provider ID、
correlation、raw error、source identifiers、完整 actor/reason。Detail仍不得放寬此政策。

Query 必須0 commit、0 enqueue、0 worker wake-up、0 provider call。pagination/filter需allowlist與bounded page size。

Exact public endpoints固定為：

- `GET /api/v1/line/tasks/summary`
- `GET /api/v1/line/tasks?page=<n>&page_size=<n>&status=<safe-enum>&source_type=<safe-enum>&scheduled_from=<iso>&scheduled_to=<iso>`
- `GET /api/v1/line/tasks/{task_id}`

List只允許`status`、server-defined safe `source_type`、scheduled date range、page與page_size；必須拒絕
`user_id`、recipient identity與arbitrary source identity filter。Summary worker view只可輸出safe bounded
status/count/timestamp，不含host、PID、thread、path或internal runtime detail。

Detail attempts必須使用封閉`LineDeliveryAttemptPublicView` allowlist；禁止`asdict()`穿透
`correlation_id`、`provider_message_id`、raw `error_code/error_message`或等價內容。Malformed repository item、
unknown enum與extra sensitive field必須在route/application boundary fail closed並回Global typed error envelope，
不得把internal/provider exception文字放response或log receipt。

## 3. Lanes

1. Contract Scout（Luna，唯讀）：逐欄 allow/deny、route/auth/error矩陣。
2. Application Writer（Terra）：contracts/application only。
3. Route/Repository Writer（Primary）：route/schema/repository only。
4. Test Writer（Terra）：兩個new tests only。
5. Auditor（Luna，唯讀）：敏感欄位、non-GET、commit/provider/write-set掃描。
6. Integration Owner：唯一文件/evidence/index writer。

## 4. G0–G7

- G0 exact approval、dirty preservation、exact write set、0 DB/React/provider mutation。
- G1 summary/list/detail逐欄Pydantic與masking matrix frozen。
- G2 auth/capability、401/403、invalid filter/page、typed errors與correlation。
- G3 strict success/empty/null/enum/extra-field contract tests。
- G4 query zero-write：commit/enqueue/wake/provider spies全部0。
- G5 list/detail response不得包含deny-list欄位或等價內容；log/exception亦不得洩漏。
- G6 focused regression、UTF-8、diff/secret/PII/raw-dict掃描。
- G7 evidence含真application/route結果，不接受只測自創fixture。
- G8 route-level negative tests覆蓋recipient/user filter拒絕、attempt allowlist、malformed repository result、
  log/exception redaction及所有stable status→code mappings。

## 5. Required commands

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp\phase4c-d -q `
  tests\line\subsystems\test_line_delivery_public_query.py `
  tests\test_line_delivery_public_query_route.py `
  tests\line\domain\test_line_delivery_domain.py
git diff --check -- api/routes/line_tasks.py api/schemas/line_tasks.py subsystems/line/delivery_admin_contracts.py subsystems/line/delivery_admin_application.py infrastructure/mysql/line_delivery_task_repository.py tests/line/subsystems/test_line_delivery_public_query.py tests/test_line_delivery_public_query_route.py
```

## 6. Completion boundary

Backend hardening通過後，仍需獨立 React query-only Work Package 才能移除LineManagementPage的static queue。
Delivery controls一律維持native disabled，外送mutation必須另案。

## 7. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | PASS | 只讀public query hardening |
| Change inventory | NOT_RUN | 無DB/schema |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無owned-object變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。

---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase4c-knowledge-public-query-hardening
date: 2026-08-17
owner: Knowledge Retrieval / Access Integration Owner
domain: Knowledge Retrieval
source_gap: PROV-20260816-react-admin-phase4c-knowledge-public-query-gap
adjacent_gap: PROV-20260817-knowledge-sensitive-detail-public-contract-gap
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-line-knowledge-authorization-normalization PASS
approval_required: 核准此 exact Phase 4C-K Work Package
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer; required-before-writer; preserve-all-user-work
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: not-applicable
---

# Phase 4C-K：Knowledge／FAQ catalog public query hardening 工作包

## 0. 狹窄目標

本包為 proposed。核准後只建立 FAQ catalog 的 authenticated、typed、server-masked Query contract，
並移除 read path 的 hidden commit。不得開放item全文、source URI、question/answer/citations、LINE task identity，
不得改 ingest/review/publish/retire/reindex/question/retry，也不接 React或外部index/provider。

開工前 `PROV-20260817-line-knowledge-authorization-normalization` 必須 PASS；不得以現行 role capability
或 React menu visibility 取代正式的 enabled-principal 授權契約。未通過時 G0 固定 BLOCKED。

Canonical catalog endpoint固定沿用
`GET /api/v1/knowledge/items?limit=<1..500>&lifecycle_status=<safe-enum>`，但將其success改成封閉typed
envelope與masked item list；本包不自行發明`page/page_size`。既有`GET /items/{item_id}`、jobs、indexes及
questions是legacy-sensitive routes，不得被React使用，也不得藉本包宣稱已安全；其detail/full-content政策
由adjacent gap另案裁決。開工前必須先characterize current Streamlit/API callers，避免靜默破壞相容性。

## 1. Exact write set

- `api/routes/knowledge_retrieval.py`
- `api/schemas/knowledge_retrieval.py`
- `subsystems/knowledge_retrieval/contracts.py`
- `subsystems/knowledge_retrieval/application.py`
- `infrastructure/mysql/knowledge_retrieval_repository.py`
- `tests/line/subsystems/test_knowledge_public_catalog_query.py`（new）
- `tests/test_knowledge_public_catalog_route.py`（new）
- `tests/test_line_knowledge_retrieval_boundary.py`

Unit of Work class、mutation workflow、external index、LINE delivery、React、shared handler、DB/schema/dependency
均不在本包；若移除query commit需要shared UoW變更，固定回報`SHARED_UOW_SCOPE_REQUIRED`。

### Integration document write set

- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md`
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md`
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- 本工作包、`02/README.md`與
  `03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase4c-knowledge-public-query-hardening/`（new）

只由Integration Owner寫入。

## 2. Frozen catalog policy

Catalog只允許：item id、title、lifecycle、version、updated_at及必要的bounded pagination metadata。
不允許 content、source identity/URI、question、answer、citations、correlation、delivery task ID、raw metadata。
本波不新增detail endpoint；既有detail/question routes不得被React client使用。

所有 catalog Query 必須0 commit、0 enqueue、0 external index、0 LINE provider call。

Application Writer負責把`list_items`移到明確read-only path；route-level commit spy必須證明connection/UoW
commit、rollback、enqueue及provider/index calls均為0。只移除一行`commit()`而沒有read transaction
ownership與malformed repository fail-closed test不算完成。Global typed errors需有stable code/status、
correlation與redaction；raw internal/storage/source文字不得穿透response、log或snapshot。

## 3. Lanes

1. Contract Scout（Luna，唯讀）：field allow/deny、auth/error、commit call graph。
2. Application Writer（Terra）：contracts/application only，移除query hidden commit。
3. Route/Repository Writer（Primary）：route/schema/repository only。
4. Test Writer（Terra）：三個test paths only。
5. Auditor（Luna，唯讀）：commit/external side effect/sensitive content/write-set scan。
6. Integration Owner：唯一文件/evidence/index writer。

## 4. G0–G7

- G0 exact approval與write-set；0 DB/React/external side effect。
- G1 catalog field matrix frozen；每個欄位有Pydantic/domain來源與redaction。
- G2 auth/capability、401/403、pagination/filter、typed errors。
- G3 strict success/empty/null/enum/extra-field與malformed repository result fail closed。
- G4 讀取路徑0 commit；repository/UoW/external index/LINE spies證明0 side effect。
- G5 deny-list欄位不在response、log、exception或snapshot。
- G6 focused regression、UTF-8、diff/secret/raw-dict/skip掃描。
- G7 evidence必須使用current application/route，不能只測writer fixture。
- G8 legacy detail/jobs/indexes/questions仍存在時，evidence須明列其restricted status與adjacent gap；不得把
  catalog hardening宣稱為Knowledge所有public reads安全。

## 5. Required commands

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp\phase4c-k -q `
  tests\line\subsystems\test_knowledge_public_catalog_query.py `
  tests\test_knowledge_public_catalog_route.py `
  tests\test_line_knowledge_retrieval_boundary.py
git diff --check -- api/routes/knowledge_retrieval.py api/schemas/knowledge_retrieval.py subsystems/knowledge_retrieval/contracts.py subsystems/knowledge_retrieval/application.py infrastructure/mysql/knowledge_retrieval_repository.py tests/line/subsystems/test_knowledge_public_catalog_query.py tests/test_knowledge_public_catalog_route.py tests/test_line_knowledge_retrieval_boundary.py
```

## 6. Completion boundary

本包只讓FAQ catalog具備安全public query。React wiring、FAQ mutation、全文detail、外部index與LINE回覆均另案；
LineManagementPage既有Create/Publish控制繼續native disabled。

## 7. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | PASS | query contract與hidden commit修正；0 schema |
| Change inventory | NOT_RUN | 無DB/schema |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無owned-object變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。

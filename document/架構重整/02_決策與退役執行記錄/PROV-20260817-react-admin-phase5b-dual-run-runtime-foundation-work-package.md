---
doc_type: work-package
declared_status: approved
identity: PROV-20260817-react-admin-phase5b-dual-run-runtime-foundation
date: 2026-08-17
owner: Integration Owner
specification: PROV-20260817-react-admin-phase5b-dual-run-runtime-foundation
spec_path: PROV-20260817-react-admin-phase5b-dual-run-runtime-foundation-specification.md
authority: awaiting-exact-human-approval
approval_required: 核准此 exact Phase 5B Work Package
approval_evidence: user-replied-核准此-exact-Phase-5B-Work-Package
prerequisites: PROV-20260817-react-admin-phase5a-entry-governance-rollback PASS
prerequisite_rule: prerequisite requires fresh PASS evidence
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: launcher/preflight/smoke/runtime-boundary drift requires fresh read and re-freeze
ui_execution_mode: local-three-service-get-only-smoke
db_change: none
---

# React Phase 5B：最小三服務 Dual-run Work Package

## 0. Activation and outcome

只有人工明確回覆：

```text
核准此 exact Phase 5B Work Package
```

才可修改production／tests。本包只交付API 8000、Streamlit 8501、React 5173的本機啟動、獨立health、
relative `/api`與owned-process cleanup。它不切entry、不host production、不retire Streamlit、不寫monitor／DB。

## 1. Exact production write set

- `scripts/launcher_preflight.py`
- `scripts/launchers/start_local_development.bat`
- `scripts/launchers/start_local_development.sh`
- `scripts/smoke_local_development_launcher.py`
- `ui_react/src/api/client.ts`（只移除absolute 8000 fallback；不得新增caller）
- `scripts/launchers/README.md`

`scripts/run_service_monitor.py`不在write set；Phase5B smoke不得啟動它。Private Operations、LINE alerts、
workers/providers、DB、API/main、Vite config、shared transport/Auth、package/lock、business pages、entry queue/
manifest、hosting與Phase6 files全部禁止修改。

## 2. Exact test and evidence write set

- `tests/test_launcher_dry_run.py`
- `tests/test_launcher_inventory.py`
- `tests/test_local_development_launcher_smoke.py`
- `tests/test_online_script.py`
- `tests/test_react_dual_run_infrastructure.py`（new）
- `ui_react/src/tests/legacy_api_client_runtime_boundary.test.ts`（new）
- 本spec／WP
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase5b-dual-run-runtime-foundation/contract-matrix.md`
- `.../candidate-change-inventory.md`
- `.../verification-receipt.md`
- `.../runtime-smoke-receipt.md`
- `.../open-findings.md`

不修改`tests/test_private_runtime_operations.py`；monitor persistence已排除，不是本包驗收面。

## 3. Required implementation

### Preflight／dry-run

- 驗Python/uvicorn/streamlit、npm、React package/entry及8000/8501/5173 ports。
- dry-run輸出三個exact commands、health predicates、startup order與monitor/workers/providers=`disabled`。
- dry-run 0 child process、0 Docker、0 DB/API call。
- 不讀取或要求`LABOR_UNION_TEST_MODE`、`lu_test_*`或test DB。

### Controlled smoke

- 三服務全部bind`127.0.0.1`；Vite固定`--strictPort`。
- API health 200；Streamlit health 200；React 200＋HTML＋`id="root"`。
- 經5173 relative `/api`取得backend response；browser/runtime不得直連8000。
- smoke環境固定禁用monitor、LINE delivery、durable、incident、knowledge、consumer與provider workers。
- 可使用existing DB做GET query smoke，但0 POST/PUT/PATCH/DELETE、0 seed/migration/repair/reset/fixture。
- 成功、timeout、partial start、Ctrl+C／normal exit都只清owned PID tree／process group。
- 每run使用唯一`scratch/phase5b-dual-run/<run-id>/`log directory。

### Relative API boundary

- `ui_react/src/api/client.ts`移除`http://localhost:8000`與`127.0.0.1:8000` browser fallback。
- production React dependency closure不得含absolute API origin、generic import resurrection或CORS workaround。

## 4. Anti-laziness rules

- 不以build、TCP open或API health代替React health。
- 不因port occupied殺未知process或漂移到新port。
- 不啟monitor後再宣稱GET-only；process inventory出現monitor/worker即FAIL。
- 不以既有`union_db`執行mutation；GET頁面能顯示不代表entry cutover。
- 不用dev token/no-auth、CORS wildcard、absolute origin或fake health。
- Windows／Unix程式契約都要完成；無真Unix環境時receipt標`BLOCKED_UNIX_RUNTIME_EVIDENCE`。
- 開工前保存branch、HEAD、`git status --short`與write-set collision；不reset/clean/stash/checkout。

## 5. Gates

| Gate | PASS condition |
|---|---|
| G0 | exact approval、Phase5A fresh PASS、write-set閉合、0 DB/monitor/provider mutation |
| G1 | dry-run三commands/ports/health/disabled inventory，0 process/DB/Docker |
| G2 | preflight artifacts/ports fail closed，不要求`lu_test_*` |
| G3 | 三服務順序ready；failure與exit只清owned children |
| G4 | React HTML/root marker＋relative `/api` proxy；0 absolute8000 fallback |
| G5 | existing DB GET-only smoke；0 non-GET、0 monitor/worker/provider process |
| G6 | Windows/Unix契約與README一致 |
| G7 | focused tests、React boundary test、build/lint、UTF-8/header/diff/secret/write-set PASS |

## 6. Required commands

```powershell
.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp/phase5b -q `
  tests/test_launcher_dry_run.py `
  tests/test_launcher_inventory.py `
  tests/test_local_development_launcher_smoke.py `
  tests/test_online_script.py `
  tests/test_react_dual_run_infrastructure.py

npm --prefix ui_react test -- src/tests/legacy_api_client_runtime_boundary.test.ts
npm --prefix ui_react run lint
npm --prefix ui_react run build
scripts\launchers\start_local_development.bat --dry-run
scripts\launchers\start_local_development.bat --smoke-test
git diff --check
```

Unix launcher在受控Unix環境執行等價dry-run/smoke；缺環境不得冒充cross-platform PASS。

## 7. Evidence semantics

`runtime-smoke-receipt.md`至少保存run id、exact commands、ports、三個ready結果、proxy結果、process inventory、
owned cleanup與GET-only/non-GET counts；不得包含token、帳密、TOTP、完整個資或raw logs。

Phase5B完成只代表`local-three-service-foundation-validated`。逐entry candidate、navigation switch、production
artifact與Streamlit retirement各自仍須獨立工作包與人工核准。

## 8. DB gate

| Gate | Status | Reason |
|---|---|---|
| Scope／Change inventory | PASS after exact approval | 0 schema/seed/backfill/destructive；smoke GET-only |
| Static release／Descriptor／Read-only plan／Engine／Developer acceptance | NOT_RUN | 不建立test DB、不操作existing DB mutation |

結論：`DB_CHANGE_NOT_READY`。這不阻擋三服務foundation，也不授權任何DB/monitor side effect。

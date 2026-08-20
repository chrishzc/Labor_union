---
doc_type: work-package
declared_status: approved
identity: PROV-20260817-react-admin-phase6b-runtime-integration
date: 2026-08-17
owner: Integration Owner
specification: PROV-20260817-react-admin-phase6b-runtime-integration
spec_path: PROV-20260817-react-admin-phase6b-runtime-integration-specification.md
authority: awaiting-exact-human-approval-and-hard-prerequisite-receipts
approval_required: 核准此 exact Phase 6B-RUN Work Package
approval_evidence: user-replied-核准此-exact-Phase-6B-RUN-Work-Package
activation_blocker: fresh Phase5B PASS receipt and closed HOST release-approval receipt
prerequisites: fresh Phase5B PASS receipt; closed Phase6B-HOST release-approval receipt
absorbs: PROV-20260817-react-admin-phase6b-run-phase5b-prerequisite-amendment
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
---

# Phase 6B-RUN：React production runtime integration Work Package（防偷懶版）

## Activation

只有Phase5B minimal three-service dual-run具有fresh PASS receipt、Phase6B-HOST具有closed release-approval receipt，
且人工明確回覆「核准此 exact Phase 6B-RUN Work Package」後才可施工。Phase5A rollback由Phase5B receipt傳遞，
不再是RUN另一個直接前置。任一receipt缺失、stale或identity不一致固定fail closed。
本核准不授權Streamlit retirement、entry cutover、DB schema或真provider side effect。

## Minimal exact write set（唯一有效）

- `scripts/launcher_preflight.py`（只接HOST local typed health）
- `scripts/launchers/start_local_development.bat`
- `scripts/launchers/start_local_development.sh`
- `scripts/smoke_local_development_launcher.py`（只做read-only health rehearsal）
- `scripts/run_service_monitor.py`（只新增獨立React read-only probe，不寫observation／alert intent）
- `infrastructure/http/private_operations_client.py`（只消費HOST closed artifact-health method）
- `tests/test_launcher_dry_run.py`
- `tests/test_local_development_launcher_smoke.py`
- `tests/test_react_production_runtime_integration.py`（new；Integration Owner唯一writer）
- `tests/test_private_runtime_operations.py`（HOST owner；RUN只讀 regression，不得修改）
- `tests/test_entrypoint_review_queue.py`（唯讀queue integrity regression）
- 本spec／WP與RUN evidence（Integration Owner only）

禁止修改ngrok、migration rehearsal、migration runner、HOST builder／validator、API、Vite、React／Streamlit source、
entry queue、DB、pyproject／lock或provider。下面舊的廣泛write set與lane分工已被本節取代，不再構成授權。

## Exact lanes／owners

1. Contract Scout（Luna，read-only）：凍結HOST health DTO、Phase5B/HOST receipt identities、launcher/monitor probe矩陣、
   queue before/after integrity與two-artifact rehearsal assertions。
2. Launcher Writer（Terra）：只改preflight、`.bat/.sh`、smoke及其兩個launcher tests；不得改monitor/client/shared test。
3. Monitor Client Writer（Primary）：只改`run_service_monitor.py`與`private_operations_client.py`；probe唯讀、0 DB/provider。
4. Integration Test Writer（Integration Owner）：唯一修改`test_react_production_runtime_integration.py`與evidence；
   HOST／queue tests只讀重跑。
5. Fresh Auditor（Luna，read-only）：驗receipt freshness、queue hash、unexpected paths、source deletion、UTF-8/diff/secret。

同一path只有一位writer；base drift需重新freeze。approval phrase保持本文件frontmatter所列exact文字。

## Minimal acceptance

- launcher pre-child probe與monitor post-API probe各自驗同一HOST release／manifest／API compatibility identity。
- current→previous→current rehearsal只改artifact selector；Domain／receipt fingerprint前後完全不變。
- queue file digest、row count、entry IDs與statuses前後相同；禁止執行queue generator。
- source/dependency changed-path inventory為0；無delete/move/retire。
- focused launcher、monitor-client、integration tests與HOST/queue read-only regressions PASS。
- 缺真current/previous artifact或runtime evidence時標blocked，不以mock／HTTP 200替代。

## Superseded broad write set（不得執行）

- `scripts/launcher_preflight.py`
- `scripts/launchers/start_local_development.bat`
- `scripts/launchers/start_local_development.sh`
- `scripts/launchers/start_fastapi_ngrok.py`
- `scripts/smoke_local_development_launcher.py`
- `scripts/run_service_monitor.py`
- `infrastructure/http/private_operations_client.py`（只新增HOST frozen artifact-health typed client method）
- `scripts/launchers/README.md`
- `infrastructure/migration/rehearsal_runtime.py`
- `scripts/migrate_preserved_database_additive_schema.py`
- `tests/test_launcher_dry_run.py`
- `tests/test_launcher_inventory.py`
- `tests/test_local_development_launcher_smoke.py`
- `tests/test_online_script.py`
- `tests/test_development_launcher_commands.py`
- `tests/test_preserved_database_plan_contract.py`
- `tests/test_react_production_runtime_integration.py`（new）
- 本spec／WP、`02` README、主React計畫（Integration Owner only）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase6b-runtime-integration/contract-matrix.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase6b-runtime-integration/candidate-change-inventory.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase6b-runtime-integration/verification-receipt.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase6b-runtime-integration/runtime-rehearsal-receipt.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase6b-runtime-integration/open-findings.md`

禁止修改Phase6B-HOST artifact builder／validator、`api/main.py`、Vite、React pages、API／Domain、DB、entry queue、
pyproject／lock或任何Streamlit business page。若需要其中任一路徑，固定`SCOPE_EXPANSION_REQUIRED`。

## Superseded broad lanes（不得執行）

1. Luna Contract Scout唯讀凍結Windows／Unix／ngrok／rehearsal caller matrix、artifact selector、health、rollback、
   disposable DB與worker disposition；freeze前不得寫production。
2. Freeze後：
   - Terra Launcher Writer只改preflight、local/ngrok launchers、smoke，以及
     `test_launcher_dry_run.py`、`test_launcher_inventory.py`、`test_local_development_launcher_smoke.py`、
     `test_online_script.py`、`test_development_launcher_commands.py`。
   - Primary Monitor/Rehearsal Writer只改monitor、Private Operations client、rehearsal runtime／migration caller，
     以及`test_preserved_database_plan_contract.py`。
3. Integration Owner唯一修改`test_react_production_runtime_integration.py`、shared README、spec／WP、主計畫與
   evidence；Terra／Primary需要跨lane assertion時只提交精確test delta，不得直接競寫此shared test。
4. Luna Fresh Auditor只回傳raw commands、exit codes、browser/network、owned-process與unexpected-path evidence。

`test_private_runtime_operations.py`由Phase6B Artifact Health／Private Operations Owner唯一擁有；本包只能在
該amendment freeze後唯讀重跑，不得修改。`test_entrypoint_review_queue.py`與
`tests/line/infrastructure/test_line_schema_stage6.py`同樣是唯讀regression；任一需要修改即
`SCOPE_EXPANSION_REQUIRED`。同一test path只能有一位writable owner，跨lane assertion由Integration Owner另行裁決。

## Anti-laziness rules

- 不得把Phase5B Vite 5173 ready冒充production `/admin/` artifact ready。
- 不得用HTTP 200、dist存在、artifact tests或截圖代替release identity＋asset digest＋API compatibility。
- dry-run必須0 side effect；controlled smoke必須在第一個child process前拒絕空/default/`union_db`及任何
  enabled delivery consumer。
- batch／shell／ngrok共同呼叫同一pre-child controlled-runtime guard；它必須在Docker、schema-current、DB/API
  probe或任何subprocess前完成profile、disposable namespace、workers與HOST selector attestation驗證。
- Windows只清owned PID tree；Unix只清owned process group；unknown PID／port owner固定fail closed。
- ngrok不得暴露Vite dev或未驗證artifact，不得新增public hostname／provider決策。
- migration rehearsal保留Streamlit target，且React restart／health不得改變migration transaction或DB data。
- browser必須真兩段式登入；receipt不得保存帳密、TOTP、challenge、token、provider ID或PII。
- 不得刪除React/Streamlit health rows或用資料回滾證明presentation rollback。
- 不得新增第二套artifact validator；RUN只消費HOST frozen attestation。不得修改entry status；結案仍須跑
  queue validator並證明0 entry transition。
- monitor只能透過`PrivateOperationsClient`的closed artifact-health method取得attestation；不得把artifact
  identity塞入任意`details`、自行讀目錄mtime或繞過service auth。
- health固定兩階段：任何child啟動前由HOST本機validator驗current／previous bindings；API ready後由
  Private Operations closed endpoint驗active mounted artifact。pre-child不得假呼尚未啟動的API，post-API不得
  只重跑local validator冒充實際mount觀察。
- 驗收只可唯讀執行queue validator；禁止執行會覆寫queue的
  `scripts.generate_entrypoint_review_queue`。必須保存queue file與row status的before/after integrity證據。

## Superseded broad gates（reference only）

| Gate | PASS condition |
|---|---|
| G0 | exact approval、RUN prerequisite amendment、Phase5A rollback、Phase5B controlled dual-run與Phase6B-HOST fresh receipts/base refs、shared path serial handoff、dirty/collision inventory、0 unexpected paths |
| G1 | caller/command/port/health/selector/worker/disposable-DB matrix獨立freeze |
| G2 | Windows／Unix／ngrok／rehearsal使用同一validated artifact identity；差異明列且fail closed |
| G3 | shared pre-child guard先於Docker/DB/API/process；dry-run 0 side effect；controlled smoke拒絕union_db、0 delivery consumer/provider、owned cleanup |
| G4 | API／Streamlit／React production health分離；pre-child local HOST attestation與post-API private active-mounted attestation均PASS且identity一致；generic probe不可代替 |
| G5 | current→previous→current artifact rehearsal通過；Streamlit exact rollback仍可用；Domain data不回滾 |
| G6 | 真browser password→TOTP→`/admin/`同源API→Streamlit rollback Network/DOM evidence |
| G7 | focused/full tests、queue validator PASS、queue before/after integrity與row status完全不變、UTF-8、diff/secret scan及evidence完整；產出closed RUN release approval receipt，不得以implementation/test PASS代替，亦不得稱entry retired |

## Superseded broad commands（不得作minimal RUN required set）

```powershell
.venv\Scripts\python.exe -m pytest -W error -p no:cacheprovider `
  --basetemp .pytest_tmp/phase6b-runtime -q `
  tests/test_launcher_dry_run.py `
  tests/test_launcher_inventory.py `
  tests/test_local_development_launcher_smoke.py `
  tests/test_online_script.py `
  tests/test_development_launcher_commands.py `
  tests/test_private_runtime_operations.py `
  tests/test_entrypoint_review_queue.py `
  tests/test_preserved_database_plan_contract.py `
  tests/test_react_production_runtime_integration.py `
  tests/line/infrastructure/test_line_schema_stage6.py
scripts\launchers\start_local_development.bat --dry-run
git diff --check
```

真runtime／browser／two-artifact rehearsal需另在受控環境執行；缺Unix、credential、disposable DB或previous
artifact時固定回對應BLOCKED code，不得以其他平台或mock替代。

## Minimal DB gate

| Gate | Status／expected |
|---|---|
| Scope | approval前BLOCKED；核准且hard prerequisites fresh後PASS（read-only runtime probes） |
| Change inventory | PASS（0 DB/schema/seed/backfill/business row write） |
| Static release／Descriptor／Read-only plan／Engine／Developer acceptance | NOT_RUN |

Minimal RUN不連DB、不寫monitor observation、不建立alert intent，也不需要global DB engine evidence。總結仍為
`DB_CHANGE_NOT_READY`，只表示本包未授權DB change，不阻擋read-only runtime integration。

## Superseded broad DB gate（reference only）

| Gate | 未核准現況 | 核准後本包預期 |
|---|---|---|
| Scope | BLOCKED | PASS（runtime integration；0 DB schema） |
| Change inventory | BLOCKED | PASS前須列monitor observation／alert-intent資料效果、replay與rollback |
| Static release | NOT_RUN | NOT_RUN |
| Descriptor | NOT_RUN | NOT_RUN |
| Read-only plan | NOT_RUN | NOT_RUN |
| Engine verification | NOT_RUN | PASS僅限disposable/test DB runtime evidence |
| Developer acceptance | NOT_RUN | NOT_RUN |

總結固定`DB_CHANGE_NOT_READY`；不得操作任何既有`union_db`。

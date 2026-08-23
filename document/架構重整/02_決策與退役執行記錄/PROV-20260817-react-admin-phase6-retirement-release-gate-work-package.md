---
doc_type: work-package
declared_status: in-progress
identity: PROV-20260817-react-admin-phase6-retirement-release-gate
date: 2026-08-17
owner: Integration Owner
specification: PROV-20260817-react-admin-phase6-retirement-release-gate
spec_path: PROV-20260817-react-admin-phase6-retirement-release-gate-specification.md
authority: exact-human-approved-validator-installed-not-ready
approval_required: 核准此 exact Phase 6A Work Package
approval_evidence: user-replied-核准此-exact-Phase-6A-Work-Package
absorbs: PROV-20260817-react-admin-phase6a-validator-installation-gate-amendment
activation_blocker: none for installation mode; final readiness remains blocked by readiness_prerequisites
prerequisites: none for installation mode
readiness_prerequisites: PROV-20260817-react-admin-phase5a-entry-governance-rollback PASS; PROV-20260817-react-admin-phase5b-dual-run-runtime-foundation PASS; PROV-20260817-react-admin-phase6b-production-hosting release-approved; PROV-20260817-react-admin-phase6b-runtime-integration release-approved; per-entry production switch and closed observation receipts
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: not-applicable
---

# Phase 6A：Retirement release gate Work Package（防偷懶版）

## Activation

人工明確回覆「核准此 exact Phase 6A Work Package」後即可安裝唯讀validator，即使Phase5尚未完成；
不要求先完成Phase5A/5B、global DB engine、browser或source inventory。安裝成功固定同時回傳
`validator_installation_status=VALIDATOR_INSTALLED_NOT_READY`及`overall_status=PHASE6_NOT_READY`。

這只代表installation可用，不使本release-gate Work Package completed。只有Phase5A/5B、所有legacy entry
production switch與closed observation、Phase6B HOST/RUN、forward-data、rollback、retention及release approval全部PASS後，
default readiness run才可能輸出ready態。提前安裝永不授權source刪除、retirement、navigation switch或runtime變更。

## Installation exact write set（Phase5前可執行）

- `validation/scenarios/react_admin_retirement_requirements.json`（獨立owner維護；validator唯讀）
- `scripts/validate_streamlit_retirement_readiness.py`
- `tests/test_streamlit_retirement_readiness.py`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase6-readiness/validator-installation-receipt.md`
- 本spec／WP（Integration Owner only）

Installation只讀requirements／registry／receipt schemas與negative fixtures，不要求或生成
`retirement-source-inventory.json`、production receipts、browser或DB evidence。

| Installation Gate | PASS condition |
|---|---|
| I0 | exact approval；0 source/runtime/DB/provider mutation |
| I1 | strict schemas與missing input fail closed |
| I2 | negative vectors回stable codes |
| I3 | 0 DB/browser/services/generator/source write |
| I4 | `VALIDATOR_INSTALLED_NOT_READY`＋`PHASE6_NOT_READY`，receipt與release readiness分離 |

I0～I4 PASS不改變下列G0～G7 final gates。

## Exact write set

- `validation/scenarios/react_admin_retirement_requirements.json`
- `scripts/validate_streamlit_retirement_readiness.py`
- `tests/test_streamlit_retirement_readiness.py`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase6-readiness/retirement-source-inventory.json`（Independent Inventory Owner only）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase6-readiness/validation-receipt.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase6-readiness/contract-matrix.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase6-readiness/requirements-freeze-receipt.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase6-readiness/candidate-change-inventory.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase6-readiness/open-findings.md`
- 本spec／WP、`02` README與主React計畫（Integration Owner only）

## Explicitly forbidden

不得修改／刪除`ui/**`、pyproject/lock、launcher、monitor、API、CORS、deployment、entry queue、DB，
不得啟停服務或把failure改成warning。此包只建立readiness gate。

不得把`grep/rg`零命中、queue snapshot更新、receipt檔案存在、unit tests通過或`npm run build`當作
retirement proof；不得讓validator與expected inventory由同一generator產生。

兩種mode都禁止刪除／搬移／retire／修改source bytes，禁止更新navigation target、entry queue、registry disposition、
launcher、dependency、retention state或receipt結果。Validator只回報，不執行修復。

React逐頁query completion不要求本validator或global DB engine；bounded mutation只遵守自身DB gate。
只有Phase5 switch與Phase6 source retirement受final gates約束。

## Multi-agent execution protocol

1. Luna Contract Scout唯讀凍結10個legacy identities、Phase5A minimum 11個React baseline及其後所有已核准
   identity amendments所形成的latest exact set、full entry registry、receipt schema、current SSOT／archive
   inbound list、runtime/dependency/source manifest schema；freeze前不得寫script/tests。
2. Freeze後Terra Validator Writer只改requirements JSON、validator script與focused test；不得修改任何
   source候選、queue、launcher、dependency或receipt status。requirements由Contract Scout／Integration Owner
   freeze；`retirement-source-inventory.json`改由獨立Inventory Owner依latest worktree產生，兩者不得同人同次生成。
3. Luna Adversarial Tester只提供missing／extra／duplicate／stale／unknown、自我生成expected、假receipt、
   batch-delete與skip-test負向vectors；不得與Validator Writer共用expected fixture owner。
4. Integration Owner唯一更新spec／WP、README、主計畫與除source inventory外的evidence，fresh-read後親自
   執行validator並記錄`PHASE6_NOT_READY`；不得寫`retirement-source-inventory.json`，也不得因script tests綠而標Phase6 completed。
5. Fresh Auditor只回傳raw command、exit code與unexpected-path inventory，不寫receipt／status。

## Gates

| Gate | PASS condition |
|---|---|
| G0 | exact approval；Phase5A/5B、每entry exact runtime switch successor與post-switch observation、HOST/RUN獨立release approval均有fresh receipt |
| G1 | requirements與retirement inventory來源獨立；兩份輸入各有`requirements_producer`／`inventory_producer`、共同`registry_revision`與獨立generation receipt；10 legacy＋latest approved React registry revision及full API/CLI/UI registry都exact，無自我生成expected |
| G2 | 10個Streamlit及完整one-to-many groups均有`phase5_navigation_switch_production_receipt`＋`phase5_observation_receipt`；signed manifest current target為React、previous target為Streamlit、one-entry CAS/audit與switch-back rehearsal成立 |
| G3 | mutation entries全部完成disposable React→Streamlit→React雙向forward-data query/repair/replay proof |
| G4 | 已核准且完成Phase6B；production artifact、same-origin `/admin/` hash-route static serving/reload、health/CSP/cache/API compatibility與rollback identity完整；禁止root wildcard且不得攔截API/health/LINE |
| G5 | Phase6B-HOST與獨立Phase6B-RUN均完成；launcher/monitor/ngrok/rehearsal/dependency/tests/current SSOT／active index／archive successor inventory完整 |
| G6 | missing/extra/duplicate/stale receipt及unknown status負向測試fail closed；每筆observation為closed outcome且retention合法依序轉移 |
| G7 | G6 closed後才以fresh BusinessClock、source inventory、owner approval與rollback trigger重新判定；validator、UTF-8、diff/secret scan通過，結果與實際狀態一致 |

## Required commands

```powershell
.venv\Scripts\python.exe -m pytest -W error -p no:cacheprovider `
  --basetemp .pytest_tmp/phase6-retirement -q `
  tests/test_streamlit_retirement_readiness.py `
  tests/test_entrypoint_review_queue.py `
  tests/test_launcher_inventory.py `
  tests/test_local_development_launcher_smoke.py `
  tests/test_online_script.py `
  tests/test_architecture_review_matrix_deployment_retirement.py
.venv\Scripts\python.exe -m scripts.validate_streamlit_retirement_readiness `
  --requirements validation/scenarios/react_admin_retirement_requirements.json `
  --inventory document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase6-readiness/retirement-source-inventory.json
npm --prefix ui_react run lint
npm --prefix ui_react run build
npm --prefix ui_react test
git diff --check
```

在current state，default release-readiness command必須非零並輸出machine-readable`PHASE6_NOT_READY`及所有
fail-closed codes；`--installation-check`可在I0～I4 PASS時exit 0，但仍須同時輸出
`VALIDATOR_INSTALLED_NOT_READY`與`PHASE6_NOT_READY`。pytest驗證正確拒絕可PASS，但不等於retirement ready。

Validator安裝結果另有獨立狀態`VALIDATOR_INSTALLED_NOT_READY`。它只表示script、schema、負向vectors與
machine-readable拒絕結果可用；不得寫成Phase6A completed、release-ready或entry-retirement-ready。只有下述
`overall_status`的兩個ready狀態才是release gate輸出。

Validator的`overall_status`固定三態：`PHASE6_NOT_READY`、`PHASE6_READY_FOR_ENTRY_RETIREMENT`、
`PHASE6_READY_FOR_FINAL_DEPENDENCY_CLEANUP`。第一個ready只允許依6C template啟動單一entry retirement；第二個
ready還必須額外具有10個removal receipts、rollback retention expiry＋owner approval、fresh caller inventory
零剩餘Streamlit runtime owner及歷史evidence保留。未知／矛盾狀態一律回NOT_READY。

Candidate/readiness evidence、docs-only navigation decision或queue disposition不得充當runtime switch receipt。
缺件分別輸出`PHASE5_ENTRY_SWITCH_MISSING`、`PHASE5_ENTRY_SWITCH_OBSERVATION_INCOMPLETE`或
`PHASE5_ENTRY_TARGET_NOT_REACT`。Phase6B-HOST/RUN只有implementation PASS而無獨立release-approval receipt亦不得ready。
每筆observation receipt另須有started_at、ended_at、closed outcome及retention state；retention尚為
`pending | active | completed_not_expired`時輸出`ROLLBACK_RETENTION_ACTIVE`，不得授權source removal。
retention closed enum固定為`pending | active | completed_not_expired | expired_approved`；只有
`expired_approved`且`retention_end <= BusinessClock`、release-owner deletion approval與fresh source inventory
同時成立，才可進入任何removal gate。

`observation_outcome`固定為`closed_success | closed_failure | outcome_unknown`；只有`closed_success`可由
`active`前進到`completed_not_expired`，並在到期、owner approval、無active rollback trigger時前進到
`expired_approved`。禁止跳態、倒退或以source count推導。Gate順序固定
`G0 → G1 → G2 → G3 → G4 → G5 → G6 → G7`；G7不得在G6 observation／retention尚未closed時預先PASS。

G1必須具體驗證requirements canonical input由Contract Scout／Integration Owner維護且freeze；candidate source
inventory由不同owner依latest worktree產生。Validator與queue generator均不得寫入兩者；不一致固定輸出
`INDEPENDENT_MANIFEST_MISMATCH`。Registry sources至少逐一定位`ui/app.py::PAGE_REGISTRY`、React
route/type/render wiring、mounted API、CLI及launcher／monitor／rehearsal callers。
若`requirements_producer == inventory_producer`、任一producer缺失、`registry_revision`不同，或同一producer／
同一revision同時產生expected與candidate，也固定輸出`INDEPENDENT_MANIFEST_MISMATCH`。
任何Phase5 identity amendment完成後，舊freeze receipt立即stale；必須由Integration Owner更新requirements
revision並重新freeze，不能由validator或route generator自動改expected。

`retirement-source-inventory.json`必須逐一列出明確path，禁止glob。每筆至少包含Git state
（tracked／modified／untracked／ignored／deleted）、dynamic/static callers、launcher／monitor／migration-
rehearsal callers、dependency owner、test disposition、replacement identity、current/archive inbound links、
integrity digest、retain／migrate_then_remove／remove disposition、release identity、deletion authorization、
rollback retention、restore procedure、observation window、generated_at、base_ref、scope／exclude rules、
reproducible command、files_count／matches_count、`inventory_producer`、`registry_revision`與open findings。
requirements輸入另須含`requirements_producer`與同一`registry_revision`；缺任一欄固定fail closed。

Current至少需覆蓋`ui/`全部source、`streamlit`／`streamlit-cropper`直接caller、local/ngrok launcher、preflight、
smoke、monitor、migration rehearsal、`pyproject.toml`、`uv.lock`、`.env.example`與所有Streamlit tests；不得用
舊候選清單或`rg streamlit`零命中取代path-level disposition。

## Current expected result

以2026-08-17現況執行必須回傳`PHASE6_NOT_READY`，不得以validator本身通過測試宣稱retirement ready。

### 2026-08-20 installation result

- Installation gates I0～I4：PASS。
- `validator_installation_status=VALIDATOR_INSTALLED_NOT_READY`。
- `overall_status=PHASE6_NOT_READY`；default readiness fail closed於
  `SOURCE_RETIREMENT_MANIFEST_INCOMPLETE`。
- 本Work Package維持`in-progress`；未刪除、搬移或retire任何Streamlit source，亦未改navigation target。
- Phase5B fresh Windows runtime smoke已PASS；HOST/RUN獨立release approval、Phase6A G4真challenge→TOTP→same-origin API browser，以及逐entry production switch／closed observation仍未閉合，因此不得進入6C removal。

## DB gate

本包0 DB/schema/migration/seed/backfill。未核准現況Scope為BLOCKED；核准後此readiness-only包Scope可PASS，
Change inventory PASS（0 DB change），其餘NOT_RUN。總結固定`DB_CHANGE_NOT_READY`。

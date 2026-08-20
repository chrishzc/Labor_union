---
doc_type: implementation-specification
declared_status: proposed
identity: PROV-20260817-react-admin-phase6c-per-entry-retirement-template
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
prerequisites: PROV-20260817-react-admin-phase5a-entry-governance-rollback PASS; PROV-20260817-react-admin-phase5b-dual-run-runtime-foundation PASS; PROV-20260817-react-admin-phase6-retirement-release-gate PHASE6_READY_FOR_ENTRY_RETIREMENT; PROV-20260817-react-admin-phase6b-production-hosting release-approved; PROV-20260817-react-admin-phase6b-runtime-integration release-approved; entry-specific production switch and closed observation receipts PASS
owner: Entry Governance / Release Integration Owner
scope: one Streamlit runtime entry per successor Work Package
authority: template-only-no-retirement-authorization
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
---

# Phase 6C：逐 entry Streamlit 退役 Work Package模板

## 1. 使用條件

本模板只用來建立未來單一entry的exact Work Package，不授權刪除。每包開始前必須同時具備：

1. Phase5A canonical registry與entry-specific rollback已PASS。
2. Phase5B dual-run runtime、Phase6B-HOST production artifact與Phase6B-RUN runtime integration皆已release-approved。
3. Phase6A validator在最新target PASS。
4. 該entry的React replacement、真TOTP browser、forward-written-data oracle、Streamlit rollback與觀測期receipt均PASS。
5. rollback retention狀態只允許`pending | active | completed_not_expired | expired_approved`；前三態下
   source、tests、runtime dependency與previous artifact必須保持可執行，且source disposition固定`retain`。
6. 該entry具有獨立`phase5_navigation_switch_production_receipt`與`phase5_observation_receipt`：canonical
   admin entry map在signed manifest revision的current target為React、previous target為Streamlit，one-entry
   CAS/audit、switch-back rehearsal及完整post-switch observation皆PASS。

任一條缺失固定`PHASE6_ENTRY_RETIREMENT_NOT_READY`，不得以static caller零命中、build、unit tests、HTTP 200、
screenshot或queue status代替。

## 2. 單包必要 frontmatter

```yaml
doc_type: work-package
declared_status: proposed
identity: PROV-<date>-react-admin-phase6c-retire-<entry-key>
owner: <bounded owner> / Entry Governance Integration Owner
source_entry: ui:<runtime-page.py>
replacement_entries: [ui-react:#<route>]
rollback_key: <entry-key>
phase5_receipt: <exact path>
phase5_navigation_switch_receipt: <exact path>
phase5_observation_receipt: <exact path>
phase6a_receipt: <exact path>
phase6b_artifact: <version/digest identity>
phase6b_host_release_approval_receipt: <exact path>
phase6b_run_release_approval_receipt: <exact path>
registry_revision: <exact revision>
requirements_revision: <exact Phase6A requirements revision>
source_manifest_path: <exact independent inventory path>
navigation_manifest_revision: <exact production switch manifest revision>
observation_outcome: <closed_success|closed_failure|outcome_unknown>
retention_identity: <exact identity>
retention_state: <pending|active|completed_not_expired|expired_approved>
retention_end: <BusinessClock timestamp>
deletion_candidate_receipt: <exact path or pending>
deletion_release_receipt: <exact path or pending>
deletion_approval_receipt: <exact owner-bound path or pending>
approval_required: 核准此 exact Phase 6C <entry-key> Retirement Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
```

## 3. Exact write-set產生規則

每個future WP必須late-bind具體檔案，禁止glob。允許類型只有：

- 該單一`ui/pages/<page>.py`及其只被本entry擁有的component/client；shared path不得直接刪。
- 該entry的focused Streamlit tests，且每個test要逐筆裁決為move、rewrite、replacement或retention；禁止skip。
- entry queue中該legacy row與replacement rows只能由Release Integration Owner在G9 late-bind；bounded entry
  writer不得直接修改共享queue或generator，只能提交精確status delta proposal。
- 該entry的operator rollback、observation與retirement evidence目錄。
- 必要的registry/launcher dependency delta只能由唯一Integration Owner在fresh caller inventory後修改。

以下永遠不是單一entry包的合法write set：`ui/**`、`tests/**`、`pyproject.toml`、`uv.lock`、launcher、monitor、
`api/main.py`、shared components、queue generator、archive manifest或dependency cleanup。命中shared hot spot即另立successor。

## 4. 必要契約矩陣

每一candidate至少逐path列：Git state（tracked／modified／untracked／ignored／deleted）、runtime dynamic caller、
direct/indirect caller、launcher／monitor／migration-rehearsal caller、operator、business scenario、replacement route、
read/write owner、forward-written receipt/job/anomaly、rollback URL、focused tests、shared dependency owner、current／
archive inbound links、integrity digest、test disposition、observation window、rollback trigger、retention end、restore
procedure、release identity、deletion authorization、base_ref、scope/exclude、reproducible inventory command、
files_count／matches_count與open findings。未知欄位固定fail closed；禁止用舊候選清單或glob補值。

## 5. G0～G9

| Gate | PASS條件 |
|---|---|
| G0 Scope | exact人工核准、dirty preservation、單一entry、最新base無drift |
| G1 Identity | registry/source/replacement/rollback key唯一；Phase5 candidate、runtime switch與observation receipts均可追溯，canonical target確為React |
| G2 Caller | runtime dynamic import、navigation、launcher、monitor、docs、tests與dependency caller完整 |
| G3 Behavior | React success/empty/error/auth/timeout/reload與舊entry parity成立；switch/forward proof先完成 |
| G4 Mutation | React寫入後Streamlit能query/repair/replay；無Domain data rollback |
| G5 Rollback | previous artifact與entry-specific Streamlit URL在觀測期內可操作，並完成switch-back rehearsal |
| G6 Observation | Streamlit bytes/runtime仍可執行期間完成完整window；canonical admin entry解析到React，Streamlit只由exact rollback URL到達，receipt有started_at/ended_at/closed outcome |
| G7A Removal authority | 僅在`observation_outcome=closed_success`、`retention_state=expired_approved`、`retention_end <= BusinessClock`、source disposition=`remove`、fresh inventory與candidate path/source digest/manifest revision一致、bytes由本entry單獨擁有、無current caller/shared dependency/current SSOT inbound、owner approval綁定entry/path/digest/revision、無active rollback trigger且restore/rollback/forward-data provenance皆保存時，產出candidate removal authority；不得在此gate直接刪正式bytes |
| G7B Candidate removal | 在隔離candidate上只移除G7A核准的exact bytes，先執行focused/full backend/frontend/entry validator/launcher/browser rollback tests；失敗必須保留或回復原bytes，且不得更新queue、retention或正式source。只有candidate PASS後才可產出deletion release receipt並套用相同path/digest/revision的正式移除 |
| G8 Regression | 正式移除後再次執行focused/full backend/frontend/entry validator/launcher tests、UTF-8/diff/secret scan；結果須與G7B candidate receipt一致 |
| G9 Release | queue transition、source disposition、restore identity、evidence index同步；不自動啟下一entry |

Gate順序固定`G0 → G1 → G2 → G3/G4 → G5 → G6 → G7A → G7B → G8 → G9`，不得平行或倒置。
G7B deletion release receipt完成前不得進G8/G9，也不得啟動下一entry。G7A/G7B仍只可移除已證明由本entry單獨擁有的bytes；
shared assets/callers始終保留或另立successor。

## 6. 十個 legacy entry 必須各自成包

```text
data-browser
orders
scheduling
finance
form-management
anomalies
line-management
system-status
access-management
data-import
```

一對多React replacement（Orders、Finance、Data Import）必須整個replacement group都完成，不能只驗一個route。
Form Management沒有dedicated successor前固定不可建立retirement WP。

## 7. 最後 dependency cleanup

只有十包全部完成、rollback retention結束、fresh caller inventory證明最後一個Streamlit runtime owner消失後，
才依`PROV-20260817-react-admin-phase6c-final-streamlit-dependency-cleanup-gap.md`建立另一個exact cleanup WP。
已封存歷史evidence與migration receipts不是刪除目標。

DB Gate：Scope PASS（template/doc only）、Change inventory PASS（0 DB change）；其餘NOT_RUN；
`DB_CHANGE_NOT_READY`。

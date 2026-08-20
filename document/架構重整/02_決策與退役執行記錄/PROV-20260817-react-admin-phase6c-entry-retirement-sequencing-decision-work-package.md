---
doc_type: work-package
declared_status: approved
identity: PROV-20260817-react-admin-phase6c-entry-retirement-sequencing-decision
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
owner: Entry Governance Integration Owner
domain: Global Entry Governance
authority: awaiting-exact-human-approval
prerequisites: none (docs-only sequencing decision)
execution_prerequisites: Phase6A ready-for-entry-retirement; Phase6B-HOST/RUN release-approved; per-entry production switch and closed observation receipts
approval_required: 核准此 exact Phase 6C Entry Retirement Sequencing Decision Work Package，並採用 Option A
approval_evidence: user-replied-核准此-exact-Phase-6C-Entry-Retirement-Sequencing-Decision-Work-Package-Option-A
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: not-applicable
---

# Phase 6C Entry Retirement Sequencing 決策工作包

## 0. Decision

本包只凍結逐entry promotion順序，不授權任何source刪除。推薦Option A：依風險與現有readiness由低到高
串行，任一時間exactly one active retirement candidate。

## 1. Option A（recommended）

```text
system-status
→ anomalies
→ orders（orders + order-tracker 同組）
→ line-management
→ data-browser
→ scheduling
→ finance（finance + reports 同組）
→ access-management
→ data-import（六 family 同組）
→ form-management（只有dedicated replacement/owner核准後才可加入）
```

Option B為逐次人工自由選擇下一entry，但仍禁止平行；因容易繞過依賴，非推薦。

## 2. Exact docs-only write set

- 本文件
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase6c-per-entry-retirement-template.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase6c-per-entry-retirement-readiness-gap.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase6c-final-streamlit-dependency-cleanup-gap.md`
- `document/架構重整/01_規格基線/19_Global_Entry_Point_Governance.md`
- `document/功能開發計畫/React管理端遷移與UI真實業務流程驗收計畫.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/work-package-dependency-matrix.md`
- `document/架構重整/02_決策與退役執行記錄/README.md`

## 3. Promotion invariant

- 下一個retirement WP只能在前一包observation window已closed、`retention_state=expired_approved`、G7 deletion
  receipt、fresh Phase6A與registry/launcher/browser evidence全部PASS後提出。
- Promotion不得由`retention_state`單欄推導。前一entry必須依
  `G0 → G1 → G2 → G3/G4 → G5 → G6 → G7 → G8 → G9`完成；G9包含path-level deletion receipt、
  queue/disposition同步、restore provenance與evidence index。未完成G9前，下一entry不得建立、核准或執行。
- 每個候選在進入retirement前，必須另有production-same-origin
  `phase5_navigation_switch_production_receipt`與`phase5_observation_receipt`；readiness candidate、docs-only
  navigation decision或local dual-run rehearsal均不得替代。
- 每包仍需自己的exact human approval、source/caller/test disposition與restore procedure。
- Form Management在owner與dedicated replacement未裁決前固定不進候選序列。
- 最終dependency cleanup只能在10個entry全部完成且retention到期後另立exact WP。

## 4. DB gate

本包docs-only：Scope `PASS`、Change inventory `PASS`（0 DB change），其餘`NOT_RUN`；仍為
`DB_CHANGE_NOT_READY`，且不構成retirement授權。

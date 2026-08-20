---
doc_type: work-package
declared_status: superseded
identity: PROV-20260817-react-admin-phase6b-run-phase5b-prerequisite-amendment
successor: PROV-20260817-react-admin-phase6b-runtime-integration
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
owner: Global Runtime Integration Owner
domain: Global Runtime
authority: awaiting-exact-human-approval
superseded_reason: fresh Phase5B prerequisite已直接整合進Phase6B-RUN canonical spec／WP；本修訂不再獨立核准或施工
prerequisites: none (docs/gate-only prerequisite correction)
approval_required: 核准此 exact Phase 6B-RUN Phase 5B Prerequisite Amendment Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: not-applicable
---

# Phase 6B-RUN Phase 5B 前置門修訂工作包

> Superseded：本修訂未獨立施工；fresh Phase5B PASS receipt 已由
> `PROV-20260817-react-admin-phase6b-runtime-integration` 的 canonical spec／WP 吸收，
> 不再需要獨立核准。請以 RUN canonical package 的 hard prerequisite 與 fail-closed code 為準。

## 0. Scope

Phase6B-RUN目前只明列Phase5A與HOST為前置，但local dual-run的disposable DB、worker shutdown、owned-process
cleanup與三服務health證據由Phase5B擁有。本修訂使Phase5B fresh receipt成為RUN activation與G0必要條件。

## 1. Exact write set

- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase6b-runtime-integration-specification.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase6b-runtime-integration-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase6-retirement-release-gate-specification.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase6-retirement-release-gate-work-package.md`
- `document/功能開發計畫/React管理端遷移與UI真實業務流程驗收計畫.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/work-package-dependency-matrix.md`
- `document/架構重整/02_決策與退役執行記錄/README.md`

## 2. Acceptance

1. RUN activation固定要求Phase5A、Phase5B與Phase6B-HOST三份fresh receipts。
2. 缺Phase5B receipt時輸出`BLOCKED_PHASE5B_DUAL_RUN_EVIDENCE`，且在Docker、DB probe、child process、monitor write前退出。
3. stale、scope不符、使用`union_db`、delivery consumer未關閉或owned cleanup未證明的Phase5B receipt一律不接受。
4. 本修訂只改文件與gate，不修改launcher、monitor、runtime、DB或provider。
5. 本修訂先freeze並交接RUN spec/WP；兩包不得同時寫共享文件。RUN G0必須引用本修訂fresh PASS receipt
   與base ref，否則固定`BASE_DRIFT`。

## 3. DB gate

未核准Scope `BLOCKED`；核准後Scope／Change inventory `PASS`（docs/gate-only、0 DB change），其餘
`NOT_RUN`；結論固定`DB_CHANGE_NOT_READY`。

---
doc_type: work-package
declared_status: superseded
identity: PROV-20260817-react-admin-phase6a-validator-installation-gate-amendment
successor: PROV-20260817-react-admin-phase6-retirement-release-gate-work-package
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
owner: Integration Owner
domain: Global Entry Governance / Retirement
authority: awaiting-exact-human-approval
prerequisites: none
approval_required: 核准此 exact Phase 6A Validator Installation Gate Amendment Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: not-applicable
---

# Phase 6A Validator Installation Gate 修訂工作包

> 2026-08-17：installation／release-readiness拆分已直接整合回Phase6A canonical spec／WP；本提案未曾
> exact核准，現標`superseded`，不再需要獨立核准。

## 0. Business scenario

Phase 6A validator必須能在Phase 5尚未完成時先建立並正確拒絕退役，但「validator安裝完成」不得被
誤解為「release readiness通過」。本修訂將兩者拆成獨立狀態與exit contract。

只有人工回覆：

> 核准此 exact Phase 6A Validator Installation Gate Amendment Work Package

後，才可修改下列文件與validator契約。本包不授權刪除Streamlit、切換entry或修改runtime。

## 1. Exact write set

- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase6-retirement-release-gate-specification.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase6-retirement-release-gate-work-package.md`
- `validation/scenarios/react_admin_retirement_requirements.json`
- `scripts/validate_streamlit_retirement_readiness.py`
- `tests/test_streamlit_retirement_readiness.py`
- `document/功能開發計畫/React管理端遷移與UI真實業務流程驗收計畫.md`（Integration Owner only）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/work-package-dependency-matrix.md`（Integration Owner only）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase6-readiness/`（除`retirement-source-inventory.json`外由Integration Owner only；該檔由Independent Inventory Owner only）

## 2. Frozen result contract

1. `validator_installation`只證明requirements schema、independent inventory input、negative vectors與machine-readable output已安裝。
2. Current run必須非零退出並輸出`PHASE6_NOT_READY`及所有未滿足code；此結果可作installation PASS。
3. `release_readiness`只有Phase5 entry evidence、Phase6B-HOST/RUN、forward-data、rollback、observation與source manifest全部PASS才可為ready。
4. pytest可證明validator正確拒絕，但不得把pytest PASS、script存在或receipt存在寫成retirement ready。
5. requirements canonical input與candidate inventory必須由不同owner產生；validator不得自動改expected。
6. installation receipt的唯一成功狀態為`VALIDATOR_INSTALLED_NOT_READY`；它不得使本Phase6A release-gate
   Work Package標成completed，也不得映射成任何`PHASE6_READY_*`狀態。
7. requirements輸入必填`requirements_producer`與`registry_revision`；candidate inventory必填
   `inventory_producer`與同一`registry_revision`。producer相同、revision不一致、欄位缺失或同次自我生成
   expected/candidate一律`INDEPENDENT_MANIFEST_MISMATCH`。

## 3. Acceptance

- 缺Phase5 evidence時validator仍可執行，且不讀寫production／DB／provider。
- missing／extra／duplicate／stale／unknown／自我生成expected均fail closed。
- installation receipt與release readiness receipt使用不同欄位、狀態與人工作業入口。
- requirements producer、inventory producer及registry revision可機械比對，且由不同owner簽署。
- 0 source deletion、0 launcher/dependency change、0 DB change。
- 本修訂先freeze並交接Phase6A主包；兩包不得同時寫spec/WP/validator/tests。修訂receipt與base ref未被主包
  fresh-read接受前，Phase6A主包writer不得開始。

## 4. DB gate

| Gate | Status | Evidence／reason |
|---|---|---|
| Scope gate | BLOCKED | 尚未取得exact approval；核准後只安裝read-only validator |
| Change inventory | PASS | 0 DB/schema/seed/backfill |
| Static release gate | NOT_RUN | 無DB release |
| Descriptor gate | NOT_RUN | 無schema object |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作既有DB |

結論：`DB_CHANGE_NOT_READY`。

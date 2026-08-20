---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase3d-data-browser-part-identity-decision
date: 2026-08-17
owner: React Validation Governance Integration Owner
domain: Global Validation Governance / Data Browser
source_gap: PROV-20260817-react-admin-phase3d-data-browser-part-identity-gap
authority: awaiting-exact-human-approval
approval_required: 核准此 exact Data Browser UI Part Identity Decision Work Package，並採用 Option A
prerequisites: none (docs-only identity decision)
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
ui_execution_mode: not-applicable
---

# Data Browser UI Part／Scenario Identity 決策工作包

## 0. Recommended decision

採用Option A：建立dedicated Data Browser UI Part，provisional semantic identity為`part-data-browser`；canonical
數字Part ID只由Integration Owner在最新Part catalog、未追蹤檔案與inbound links盤點後late-bind。Data Browser
只擁有masked Query／typed detail／source lineage顯示；source correction仍由owning-domain recovery contract承接。

Option B是把Data Browser放入既有維運／異常Part的明確子scenario。若人工選Option B，仍需凍結唯一scenario
path、entry identity與rollback mapping，不能只寫「歸在異常」。

## 1. Exact docs／metadata write set

- 本工作包
- `PROV-20260817-react-admin-phase3d-data-browser-part-identity-gap.md`
- `document/功能開發計畫/UI真實業務流程測試資料與驗收主計畫.md`（只登記核准Part identity／owner）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase3-scenario-lineage-matrix.md`
- `validation/ui_business_workflows/README.md`
- `validation/ui_business_workflows/checklist_manifest.yaml`
- 核准後late-bind的單一Data Browser Part目錄：`README.md`、`checklist.md`、`expected.yaml`、
  `result_summary.md`；初始結果只能`NOT_RUN`。
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3d-data-browser-part-identity-decision/`
- `document/架構重整/02_決策與退役執行記錄/README.md`（Integration Owner only）

禁止修改React、FastAPI、Streamlit、tests、DB／schema、entry queue或既有Part bytes。未完成namespace／collision
盤點前不得自行指定整數Part編號或建立占位目錄。

## 2. Frozen owner boundary

- Data Browser Part：allowlisted source catalog、masked pagination、typed detail、immutable metadata與copy/download權限。
- Anomalies Part：異常、warning、recovery entry；不吸收generic source browsing。
- Import Part：workbook／bank source Preview／Apply；不吸收跨source archive query。
- owning Domain：source correction Preview／Apply；Data Browser不得以generic patch取代。
- Phase5 entry identity仍是`#data-browser`；Part identity不自動授權cutover。

## 3. Acceptance／anti-fake gates

1. Option A／B與人工核准文字被唯一decision receipt記錄。
2. Integration Owner fresh掃描Part catalog、current inbound links與untracked候選後才late-bind canonical ID；不得使用
   「目前最大值＋1」作reservation。
3. scenario→fixture→expected→checklist→result summary→receipt manifest引用閉合，且result初始`NOT_RUN`。
4. owner boundary明確禁止raw row、PII、generic source correction與entry cutover混入。
5. Data Browser backend／React WPs只可在本決策與Phase3 Scenario Lineage PASS後啟動。
6. strict UTF-8、YAML／JSON decode、duplicate identity、dangling link與write-set audit通過。

## 4. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | docs／metadata identity decision |
| Change inventory | PASS | 0 schema／seed／backfill／destructive |
| Static release | NOT_RUN | 無DB release |
| Descriptor | NOT_RUN | 無DB object |
| Read-only plan | NOT_RUN | 無migration |
| Engine verification | NOT_RUN | 後續query package |
| Developer acceptance | NOT_RUN | 不操作既有DB |

結論：`DB_CHANGE_NOT_READY`。

---
doc_type: work-package
declared_status: completed
identity: PROV-20260817-react-admin-phase3-scenario-lineage-governance
date: 2026-08-17
owner: Global Validation Governance Integration Owner
domain: Global / React Phase 3
source_gap: PROV-20260817-react-admin-phase3-scenario-lineage-governance-gap
prerequisites: none
approval_required: 核准此 exact Phase 3 Scenario Lineage Governance Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: no-browser-execution
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Phase 3 Scenario Lineage Governance 工作包

## Scope

只建立可版本化的scenario/fixture/expected/UI checklist contracts與validator；不執行production、
DB、browser、LINE/provider或正式業務mutation，不預填驗收PASS receipt。

## Exact write set

- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase3-scenario-lineage-matrix.md`
- `validation/catalog/phase3_scenario_lineage.json`（new；唯一machine-readable Phase 3 lineage manifest）
- `validation/scenarios/global_fastapi_typed_error_boundary.json`
- `validation/scenarios/react_admin_staff_safe_actions.json`
- `validation/scenarios/react_admin_scheduling_current_query.json`
- `validation/scenarios/react_admin_leave_substitution.json`
- `validation/scenarios/react_admin_holiday_policy.json`
- `validation/scenarios/react_admin_access_audit_query.json`
- `validation/scenarios/react_admin_import_warning_transition.json`
- `validation/scenarios/react_admin_data_browser_query.json`
- `validation/fixtures/phase3/`
- `validation/expected/phase3/`
- `validation/receipts/phase3/README.md`
- `validation/receipts/phase3/manifest.json`
- `validation/ui_business_workflows/README.md`
- `validation/ui_business_workflows/checklist_manifest.yaml`
- `validation/ui_business_workflows/part_04_staff_matching/README.md`
- `validation/ui_business_workflows/part_04_staff_matching/checklist.md`
- `validation/ui_business_workflows/part_04_staff_matching/expected.yaml`
- `validation/ui_business_workflows/part_04_staff_matching/result_summary.md`
- `validation/ui_business_workflows/part_09_scheduling/README.md`
- `validation/ui_business_workflows/part_09_scheduling/checklist.md`
- `validation/ui_business_workflows/part_09_scheduling/expected.yaml`
- `validation/ui_business_workflows/part_09_scheduling/result_summary.md`
- `validation/ui_business_workflows/part_14_anomalies/README.md`
- `validation/ui_business_workflows/part_14_anomalies/checklist.md`
- `validation/ui_business_workflows/part_14_anomalies/expected.yaml`
- `validation/ui_business_workflows/part_14_anomalies/result_summary.md`
- `tests/test_phase3_scenario_lineage.py`（new）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-scenario-lineage-governance/candidate-change-inventory.md`（new）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-scenario-lineage-governance/contract-matrix-freeze-receipt.md`（new）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-scenario-lineage-governance/verification-receipt.md`（new）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-scenario-lineage-governance/open-findings.md`（new）

Integration Owner結案同步write set：本工作包、source gap
`PROV-20260817-react-admin-phase3-scenario-lineage-governance-gap.md`及
`document/架構重整/02_決策與退役執行記錄/README.md`。其他writer不得競寫這三個shared files。

Data Browser Part identity尚未裁決；本包只建scenario contract，不建立臨時UI Part目錄。

## Frozen successor identities

下表凍結的是semantic scenario identity，不使用「目前最大序號＋1」：

| Scenario path | `scenario_id` | Revision | Suite／Track | Part／UI checklist |
|---|---|---:|---|---|
| `global_fastapi_typed_error_boundary.json` | `GERR-REACT-ADMIN-TYPED-BOUNDARY` | 1 | `GERR`／`B` | Part 00；無browser execution |
| `react_admin_staff_safe_actions.json` | `SCH-REACT-ADMIN-STAFF-SAFE-ACTIONS` | 1 | `SCH`／`A` | Part 04 |
| `react_admin_scheduling_current_query.json` | `SCH-REACT-ADMIN-CURRENT-QUERY` | 1 | `SCH`／`A` | Part 09 |
| `react_admin_leave_substitution.json` | `SCH-REACT-ADMIN-LEAVE-SUBSTITUTION` | 1 | `SCH`／`A` | Part 09 |
| `react_admin_holiday_policy.json` | `SCH-REACT-ADMIN-HOLIDAY-POLICY` | 1 | `SCH`／`A` | Part 09 |
| `react_admin_access_audit_query.json` | `AC-REACT-ADMIN-AUDIT-QUERY` | 1 | `AC`／`A` | cross-cutting Access；本包不私配新Part |
| `react_admin_import_warning_transition.json` | `ANOM-REACT-ADMIN-WARNING-TRANSITION` | 1 | `ANOM`／`A` | Part 14 |
| `react_admin_data_browser_query.json` | `GDATA-REACT-ADMIN-DATA-BROWSER-QUERY` | 1 | `GDATA`／`A` | `BLOCKED_DECISION`，等待Data Browser Part identity |

每個scenario JSON內的`scenario_id`、`revision`、`suite_id`與`track`必須與本表及catalog完全相同。
Data Browser scenario可保存API/masking契約與阻擋原因，但在Part decision PASS前不得標UI-ready、不得建立
臨時Part目錄或browser PASS receipt。

## Machine-readable lineage contract

`validation/catalog/phase3_scenario_lineage.json`是本包唯一machine-readable routing manifest；Markdown
matrix只做人類摘要。catalog的expected scenario set必須硬編為上表八個identity，不得掃描目錄後把發現結果
當expected。每筆至少包含：

- `work_package_identity`、`scenario_id`、`revision`、`part`、`owner`、`suite_id`、`track`；
- `source_scenario_ids`、可解析`source_refs`與逐欄`source_to_successor_mapping`；
- `dependencies`，每筆type只能是`hard-dependency | soft-dependency | independent-lane | global-dependency`；
- `business_clock`／timezone、command lineage與fixture／expected/checklist paths；
- DB／API／UI／replay／recovery oracle applicability及N/A／blocked reason；
- required runtime receipt identities、browser execution mode、disposition、missing artifacts、activation blockers；
- PII分類與fixture generation/redaction metadata。

manifest中dependency graph必須無cycle、無dangling identity。Scenario、fixture、expected、checklist及receipt
path必須唯一且存在；blocked future runtime receipt可以在manifest中宣告required identity，但不得建立假PASS
payload。

`validation/receipts/phase3/manifest.json`只登錄future runtime receipt identity、owner、scenario revision及狀態；
初始狀態只允許`missing | not_run | blocked`。README明確說明metadata-ready不等於DB/API/browser PASS。

## Acceptance / anti-lazy gates

1. strict decode全部JSON/YAML；IDs unique，refs/paths存在，dag無循環。
2. source→successor mapping逐欄標unchanged/renamed/regenerated/superseded/unresolved。
3. fixture只包root/external input，禁止直接seed projection/receipt/outbox/status。
4. expected分DB/API/UI/replay/recovery適用性；N/A/blocked有理由。
5. result_summary初始只能`NOT_RUN`，不得預填PASS。
6. 掃描PII/secret/token/bank/LINE recipient，不得使用正式資料。
7. validator的expected set為獨立清單，不得由同一discovery函式自我生成後自證。
8. 每份fixture asset manifest必填`data_classification`（`synthetic | deidentified | invalid-by-design`）、
   `generation_method`、`allowed_use`與`redaction_policy`；缺一fail closed。
9. 所有`result_summary.md`初始只允許`NOT_RUN`與blocked reason。大小寫不敏感出現`PASS`、`PASSED`、
   `completed`、`success`、偽assertion count或偽runtime receipt identity即失敗。
10. expected YAML/JSON只保存oracle，不得包含`actual`、observed runtime data或generated receipt。
11. tests必須用獨立expected set驗missing/extra/duplicate/dangling/cycle/unknown dependency type，以及
    Data Browser未裁決時誤標UI-ready。

## Required commands

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider `
  --basetemp .pytest_tmp\phase3-lineage -q tests\test_phase3_scenario_lineage.py
```

另由Integration Owner執行所有本包JSON/YAML strict decode、UTF-8/BOM、PII/secret、`.skip/.todo/.only`、
exact write-set與scoped `git diff --check`。本包禁止啟動DB/browser/provider或production mutation；任何這類
receipt在本包只能保持`NOT_RUN`／`blocked`。

## Completion boundary

本包最高輸出為`PHASE3_SCENARIO_LINEAGE_METADATA_READY`。它只解除下游「缺metadata/test-data contract」
的activation gate，不證明任何backend、DB、React或browser flow完成。Matrix中的`TEST_DATA_GAP`／
`BLOCKED_UPSTREAM`只有在對應successor產出真receipt後才可轉為PASS；本包不得自行改寫。

2026-08-17 Integration Owner以獨立basetemp重跑validator：10 passed。八個scenario、fixture、expected、
Part 04／09／14 checklist與future receipt registry均已建立；所有runtime receipt仍為`missing | not_run |
blocked`。本包狀態因此為`completed`，但輸出僅為metadata-ready，不代表DB、FastAPI、React、browser、
replay或provider已驗收。

## DB gate

Scope / Change inventory `PASS`（metadata only）；其餘`NOT_RUN`；`DB_CHANGE_NOT_READY`。

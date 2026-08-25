---
doc_type: work-package
declared_status: completed
identity: PROV-20260817-react-admin-phase4-scenario-lineage-governance
date: 2026-08-17
owner: React Migration Integration Owner
domain: Global Validation Governance
source_gap: PROV-20260817-react-admin-phase4-scenario-lineage-governance-gap
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance completed with PHASE3_SCENARIO_LINEAGE_METADATA_READY
activation_state: completed-metadata-only
authority: exact-human-approved-completed
approval_required: 核准此 exact Phase 4 Scenario Lineage Governance Work Package
approved_at: 2026-08-22
completed_at: 2026-08-22
base_branch: main
base_head: f9240b9e3abbcf665b5c979e0973f675197d8494
dirty_baseline: required-before-writer; preserve-all-user-work
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
ui_execution_mode: not-applicable
---

# Phase 4 Scenario Lineage Governance 工作包

## 0. Scope

只補 Phase 4 controlled scenario、去敏 fixture、expected oracle、receipt manifest 與 browser checklist identity。
不修改 production、React page、API、Domain、DB、provider，也不執行 browser 或資料庫。完成只代表後續 writer
取得可追溯輸入，不代表任何 Phase 4 runtime slice 可啟動。

## 1. Exact write set

- `validation/scenarios/react_admin_line_delivery_query.json`（new）
- `validation/scenarios/react_admin_knowledge_catalog_query.json`（new）
- `validation/scenarios/react_admin_knowledge_lifecycle.json`（new）
- `validation/scenarios/react_admin_rich_menu_publication.json`（new）
- `validation/scenarios/react_admin_notification_rule_mutation.json`（new）
- `validation/scenarios/durable_job_public_outcome.json`（new）
- `validation/catalog/phase4_scenario_lineage.json`（new；唯一machine-readable lineage manifest）
- `validation/fixtures/phase4/react_admin_line_delivery_query.json`（new）
- `validation/fixtures/phase4/react_admin_knowledge_catalog_query.json`（new）
- `validation/fixtures/phase4/react_admin_knowledge_lifecycle.json`（new；synthetic multi-actor lifecycle）
- `validation/fixtures/phase4/react_admin_rich_menu_publication.json`（new）
- `validation/fixtures/phase4/react_admin_notification_rule_mutation.json`（new）
- `validation/fixtures/phase4/durable_job_public_outcome.json`（new）
- `validation/fixtures/phase4/staff_payout_durable_job.json`（new；links SP-PAYABLE-QUERY-001 to JOB lifecycle）
- `validation/expected/phase4/react_admin_line_delivery_query.json`（new）
- `validation/expected/phase4/react_admin_knowledge_catalog_query.json`（new）
- `validation/expected/phase4/react_admin_knowledge_lifecycle.json`（new；receipt／re-query／author-separation oracle）
- `validation/expected/phase4/react_admin_rich_menu_publication.json`（new）
- `validation/expected/phase4/react_admin_notification_rule_mutation.json`（new）
- `validation/expected/phase4/durable_job_public_outcome.json`（new）
- `validation/expected/phase4/staff_payout_durable_job.json`（new；accepted／terminal／re-query分離）
- `validation/receipts/phase4/README.md`（new；receipt manifest，不偽造 runtime receipt）
- `validation/receipts/phase4/manifest.json`（new；初始只記missing/not_run/blocked，不偽造runtime結果）
- `tests/test_phase4_scenario_lineage.py`（new）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase4-scenario-lineage-governance/candidate-change-inventory.md`（new）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase4-scenario-lineage-governance/contract-matrix-freeze-receipt.md`（new）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase4-scenario-lineage-governance/verification-receipt.md`（new；metadata-only結果）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase4-scenario-lineage-governance/open-findings.md`（new）
- 本工作包、source gap與`02_決策與退役執行記錄/README.md`（Integration Owner only）

既有 canonical scenarios、fixtures、expected、receipts只可讀取與引用，不得覆蓋或重產。
本包也不得建立`validation/ui_business_workflows/phase4/`或其他按遷移Phase命名的平行checklist根。
Browser checklist只引用Part 00已凍結的`validation/ui_business_workflows/part_01_import/`至
`part_16_end_to_end/`canonical paths；缺少的Part檔案只能在manifest標記`missing/blocked`，由該Part的
owning successor另案建立。本包不代替Part owner寫入checklist、expected或result summary。

Phase3已輸出可追溯的`PHASE3_SCENARIO_LINEAGE_METADATA_READY`；Current activation只等待本工作包exact human
approval。Global typed error boundary／correlation runtime evidence不是本metadata包前置，也不得由本包冒領。

## 2. Artifact contract

每個 Phase 4 family 必須有 machine-checkable record：

`work_package_identity`、`source_scenario_ids`、`successor_scenario_id/path`、`revision`、`part`、`owner`、
`dependencies`、timezone-aware `business_now`、`command_lineage`、逐欄`lineage_mappings`（只允許
`unchanged | renamed | regenerated | superseded | unresolved`）、`fixture_paths`、`expected_paths`、
`db_oracle`、`api_oracle`、`ui_oracle`、`replay_oracle`、`recovery_oracle`及各自
`required | optional | not_applicable | blocked`、`required_runtime_receipt_ids`、`browser_checklist_path`、
`browser_execution_mode`、`shared_hot_spot`、`disposition`、`missing_artifacts`、`activation_blockers`、
`pii_classification`與artifact digest linkage。

Manifest contract固定`labor-union-phase4-scenario-lineage/v1`與`manifest_revision: 1`。Dependency type只允許
`hard-dependency | soft-dependency | independent-lane | global-dependency`；browser execution mode只允許
`browser-required | browser-file-dialog-assisted | browser-blocked | not-applicable`。缺少canonical checklist時固定
`browser-blocked`、`browser_checklist_step_ids: []`並在`missing_artifacts`列出exact path與owning Part；只有checklist
存在且mode不是`browser-blocked`時，step IDs才必填、非空且全manifest唯一。Fixture asset必填`data_classification`（
`synthetic | deidentified | invalid-by-design`）、`generation_method`、`allowed_use`與`redaction_policy`。
Digest固定SHA-256，由Integration Owner freeze，僅作artifact完整性，不作task identity。

六個successor identity凍結為：

- `LINE-REACT-DELIVERY-QUERY-001`（suite `LINE`、track `A`）
- `KN-REACT-CATALOG-QUERY-001`（suite `KN`、track `A`）
- `KN-REACT-LIFECYCLE-001`（suite `KN`、track `A`）
- `LINE-RICH-MENU-PUBLICATION-001`（suite `LINE`、track `A`）
- `LINE-NOTIFICATION-RULE-001`（suite `LINE`、track `A`）
- `JOB-PUBLIC-OUTCOME-001`（suite `JOB`、track `B`）

既有Import／Finance／Payout／Subsidy coverage不得把`successor`留成`—`。本包固定採
`ADOPT_IN_PLACE`，逐筆引用現有canonical scenario exact path：

- HCM／case workbook：`CI-CASE-IMPORT-001` → `validation/scenarios/CI-CASE-IMPORT-001.json`
- BeClass／Staff Historical／Historical Orders共同根：`CI-CANONICAL-ROOTS-002` →
  `validation/scenarios/CI-CANONICAL-ROOTS-002.json`；各family仍需獨立fixture／receipt lineage
- Finance Import：`FI-IMPORT-AND-RECONCILIATION-001` →
  `validation/scenarios/FI-IMPORT-AND-RECONCILIATION-001.json`
- Accounts Payable：`APX-PAYABLE-VIEWMODEL-002` →
  `validation/scenarios/APX-PAYABLE-VIEWMODEL-002.json`
- Client Finance：`CF-EXPLICIT-REFUND-RECOVERY-002` →
  `validation/scenarios/CF-EXPLICIT-REFUND-RECOVERY-002.json`
- Staff Payout：`SP-EXACT-PAYOUT-STATE-002` →
  `validation/scenarios/SP-EXACT-PAYOUT-STATE-002.json`
- Government Subsidy：`GS-CLAIM-FUNDING-001` →
  `validation/scenarios/GS-CLAIM-FUNDING-001.json`

`ADOPT_IN_PLACE`只凍結scenario identity與path；缺fixture、expected、runtime receipt、browser checklist或
authority時仍為blocked，不得因source scenario存在而啟動production writer。

檔名可維持既有human-readable proposal，但scenario內identity、fixture/expected/receipt manifest linkage必須使用
上述exact ID；不得由writer另選或遞增。source refs至少包含：LINE Delivery對應
`document/資料庫、資料處理/新版測試資料規則矩陣_草案.md`的`LINE-02`／`LSM-02`與
`document/功能開發計畫/Part_00_全域測試資料治理與Scenario契約.md#7.3.1`；Rich Menu對應
`document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md#3.5`；Knowledge對應
同檔`#6.1`／`#6.2`；Durable Job對應
`document/資料庫、資料處理/新版驗證雙軌總計畫_草案.md#6.1`及
`JOB-DURABLE-001`／`JOB-QUEUE-LIFECYCLE-002`。Validator必須驗證source檔案與anchor存在。

Rich Menu與Notification Rules目前沒有canonical source scenario；兩筆必須使用
`source_scenario_ids: []`與`source_scenario_absence_reason: no canonical scenario exists`，並以正式規格anchor
及active gap作lineage。禁止為通過validator偽造既有scenario。

Manifest另須有完整`coverage_records`，不得只列六個successor。Hard-coded coverage IDs至少涵蓋：
`PH4-HCM-APPLY`、`PH4-BECLASS-WORKBOOK`、`PH4-STAFF-HISTORICAL-WORKBOOK`、
`PH4-HISTORICAL-ORDERS-WORKBOOK`、`PH4-FINANCE-IMPORT`、`PH4-ACCOUNTS-PAYABLE`、
`PH4-CLIENT-FINANCE`、`PH4-STAFF-PAYOUT`、`PH4-GOVERNMENT-SUBSIDY-REPORT`、
`PH4-LINE-DELIVERY-QUERY`、`PH4-KNOWLEDGE-CATALOG-QUERY`、`PH4-KNOWLEDGE-LIFECYCLE`、
`PH4-RICH-MENU-PUBLICATION`、`PH4-NOTIFICATION-RULE-MUTATION`與`PH4-DURABLE-JOB-OUTCOME`。
每筆逐一列現有scenario/fixture/expected exact path、planned successor、receipt identity、browser checklist step IDs、
disposition、activation blockers與shared writer；缺件保持`missing/not_run/blocked`。

Runtime receipt尚不存在時只在manifest標記`missing | not_run | blocked`，不得使用`present`或建立假PASS receipt。
Scenario fixture不得含真姓名、
電話、LINE ID、銀行帳號、token、secret、provider credential或正式資料列。

## 3. Acceptance

1. 六個 successor scenario皆可strict decode；有canonical source者追到Part 00與既有Domain scenario，無source者
   使用正式absence reason與spec/gap anchors。
2. Manifest hard-coded expected set包含六個successor及上述15個coverage records；矩陣逐WP精確列出缺少的
   receipt／fixture／expected／browser checklist，不再只寫`SUPPLEMENT`。
3. HCM、Finance Import、AP、Client Finance、Staff Payout、Subsidy既有缺失receipt被標為runtime requirement，
   不建立假receipt。Staff Payout fixture/expected只凍結受控資料與oracle，不得把JobAccepted寫成terminal success，
   也不得在Durable Public Outcome尚未PASS時標成runtime-ready。
4. DataImportPage、FinancePage、LineManagementPage shared writer序列可由matrix機械驗證；browser
   checklist path只能落在Part 00 canonical `part_01`～`part_16` owners，禁止`phase4/`平行根。
5. 測試包含missing／extra／duplicate scenario、dangling path、PII deny-list、unknown disposition與自我生成expected反例。
6. `tests/test_phase4_scenario_lineage.py`必須自行遞迴驗證Phase4子目錄；現有全域scenario/fixture/receipt
   verifier只掃root glob，不能冒充已涵蓋Phase4。
7. 全部新增JSON/YAML/Markdown/test code掃描真姓名、電話、email、LINE user ID、銀行帳號、token、secret、
   credential、provider URL與raw payload；禁止`.skip/.todo/.only`、snapshot-only、只驗HTTP 200或同一parser
   同時生成actual/expected。
8. 不新增requests/provider SDK/DB connector/browser launcher；scoped diff以開工前dirty baseline比對，不把既有dirty
   worktree算入候選，也不得覆蓋既有artifact。
9. strict UTF-8、scoped diff、secret/PII與write-set audit通過；0 production／DB／browser／provider side effect。
10. dependency DAG的missing/extra/duplicate/dangling/cycle/unknown type及self-generated expected負向測試fail closed；
    每個browser checklist以scenario ID分組且step ID唯一，不得以一份泛化清單冒充五條flow。

## 4. Required command and completion boundary

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider `
  --basetemp .pytest_tmp\phase4-lineage -q tests\test_phase4_scenario_lineage.py
```

另執行全部JSON/YAML strict decode、UTF-8/BOM、PII/secret、`.skip/.todo/.only`、exact write-set與scoped
`git diff --check`。本包最高輸出只能是`PHASE4_SCENARIO_LINEAGE_METADATA_READY`；禁止使用`PASS`、
`completed`或`success`冒充任何runtime、DB、browser或provider驗收。

### 4.1 Rules／Rich Menu scoped prerequisite progress（2026-08-20）

| Family | Scenario／fixture／expected | Catalog／receipt state | Runtime state |
|---|---|---|---|
| Rich Menu publication | `LINE-RICH-MENU-PUBLICATION-001` scoped metadata present；contract test `11 passed` | local metadata prerequisite `PASS`；receipt `missing`；browser checklist `blocked` | backend/provider/browser/DB `not_run` |
| Notification Rules mutation | `LINE-NOTIFICATION-RULE-001` scoped metadata present；contract test `11 passed` | local metadata prerequisite `PASS`；receipt `missing`；browser checklist `blocked` | backend/provider/browser/DB `not_run` |

本次只建立上述兩個user-authorized backend prerequisite，catalog明確列出其餘四個Phase 4 family未納入。
此 scoped evidence 的最高輸出為`PHASE4_RULES_RICHMENU_METADATA_READY`；不變更本工作包的`proposed`／
`blocked-prerequisites`狀態，也不構成完整`PHASE4_SCENARIO_LINEAGE_METADATA_READY`、production、provider、
browser或database驗收。

2026-08-20使用者只核准以這兩組scoped metadata作Rules／Rich Menu兩個backend工作包的local prerequisite；
此裁決不核准或啟動其餘四個family，也不改變本工作包整體authority／activation state。

## 5. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | validation metadata only |
| Change Inventory | PASS | 0 schema／seed／backfill／destructive |
| Static Release | NOT_RUN | 不適用 |
| Descriptor | NOT_RUN | 不適用 |
| Read-only Plan | NOT_RUN | 不適用 |
| Engine Verification | NOT_RUN | 不操作資料庫 |
| Developer Acceptance | NOT_RUN | 不操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。

## 6. Completion record（2026-08-22）

使用者已核准本 exact 工作包並將 shared catalog／scenario integration writer ownership 轉移至本任務。唯一
integration writer 已建立完整 6 個 successor scenarios、15 筆 coverage records、fixture／expected lineage、
metadata-only receipt registry 與 fail-closed validator。

Focused verification：

```text
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp\phase4-lineage -q tests\test_phase4_scenario_lineage.py
14 passed in 0.98s
```

本工作包唯一完成輸出為 `PHASE4_SCENARIO_LINEAGE_METADATA_READY`。所有 runtime receipt 仍為
`missing | not_run | blocked`；database、browser、provider 與 production 均未執行。第 4.1 節只保留
2026-08-20 scoped 歷史，已由本次完整 metadata completion 接續，絕不代表任何 runtime PASS。

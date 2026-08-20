---
doc_type: work-package
declared_status: blocked
identity: PROV-20260817-react-admin-phase4b-subsidy-report-authority-hardening
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
owner: Government Subsidy Reporting Integration Owner
domain: Government Subsidy / Reporting / Access
source_gap: PROV-20260816-react-admin-phase4b-subsidy-reconciliation-public-contract-gap
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-government-subsidy-reporting-authority-decision PASS; PROV-20260817-react-admin-phase4b-ap-public-contract-hardening PASS
shared_hot_spot: api/routes/finance_reports.py
shared_route_writer_order: AP-H -> Subsidy-H
approval_required: 核准此 exact Phase 4B-S Work Package
activation_blocker: PROV-20260817-government-subsidy-reporting-authority-gap
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: not-applicable
---

# Phase 4B-S：Subsidy report authority 與 public contract hardening 工作包

## 0. 狀態與狹窄目標

本包目前因Reporting authority未決而blocked，不能直接作為production核准。只有人工完成
`PROV-20260817-government-subsidy-reporting-authority-gap`逐欄裁決後，才可重新核准並把既有quarterly／annual query收斂成
Government Subsidy 擁有的 typed、authenticated、server-masked read model；不接 React、不建立 weekly
三-sheet報表、不修改補助 claim／ledger／付款狀態、不改 DB/schema。

現已確認live query含legacy跨表欄位、rate與公式，無法由current approved Government Subsidy specs唯一決定。
在authority matrix無未決欄位前，以下production paths全部視為conditional write set，禁止writer開工。

`api/routes/finance_reports.py`亦屬
`PROV-20260817-react-admin-phase4b-ap-public-contract-hardening`的exact write set。authority完成並重新核准後，
本包仍不得與AP-H平行施工。AP-H必須先freeze production diff、focused tests與candidate inventory；Integration
Owner fresh-read後才可啟動本包的唯一Subsidy route writer。

## 1. Exact write set

### 決策階段exact write set

- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-government-subsidy-reporting-authority-gap/report-field-authority-matrix.md`（new）
- authority gap、本工作包與必要正式規格/index（Integration Owner only）

### authority完成後才可重新核准的conditional production write set

- `api/routes/finance_reports.py`
- `api/schemas/government_subsidy_report.py`（new）
- `subsystems/government_subsidy/reconciliation_register_query.py`
- `tests/test_subsidy_reconciliation_register.py`
- `tests/test_government_subsidy_report_public_contract.py`（new）

任何 repository、Domain、shared handler、React、dependency、DB/schema 變更都不在本包。需要時固定
`SCOPE_EXPANSION_REQUIRED` 並停止該 lane。

conditional production lane啟動時，`api/routes/finance_reports.py`只能有一位writer，且candidate inventory
必須記錄與AP-H的collision disposition；沒有此紀錄固定G0 `BLOCKED_SHARED_WRITER_COLLISION`。

### Integration document write set

- `document/架構重整/01_規格基線/14_Government_Subsidy_Domain.md`
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- 本工作包、`02/README.md`與
  `03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase4b-subsidy-report-authority-hardening/`（new）

只由Integration Owner在authority matrix freeze後寫入。

## 2. 必須由 contract matrix 證明

- 每個季度／年度欄位的 owner root fact、公式、日期／時區、nullable與redaction；
- Preview DISPLAY 欄位與 XLSX EXPORT_ONLY 欄位分離；
- eligibility、hours、rate、amount 不能以跨表現況推導冒充 approved authority；
- quarterly／annual aggregate conservation；
- response metadata：report period、generated_at、source/version lineage、correlation；
- binary filename、content type、size、SHA-256及preview/export lineage政策。

## 3. 執行分工

1. Authority Scout（Primary，唯讀）：以正式 Government Subsidy 規格裁決公式/root facts；不以live code覆蓋規格。
2. Contract Scout（Luna，唯讀）：逐欄矩陣與 route/error inventory。
3. Backend Writer（Primary/Terra）：只改三個production paths。
4. Test Writer（Terra）：只改兩個test paths。
5. Auditor（Luna，唯讀）：anti-raw/PII/side-effect/write-set驗證。
6. Integration Owner：唯一文件/evidence/index writer。

Authority matrix未freeze時不得寫production。任何公式為DECISION_REQUIRED時整包維持blocked；不得用live SQL、
hard-coded rate、ReportsPage樣本或fixture補權威。

## 4. G0–G7

- G0 authority gap已人工關閉並取得新的exact production approval、scope/write-set、0 DB/React。
- G1 authority matrix無未解owner/formula；否則BLOCKED。
- G2 quarterly/annual Pydantic strict views；無 raw dict／extra／implicit default。
- G3 auth、capability、typed errors、correlation與PII server masking。
- G4 query read-only：0 commit、0 mutation、0 external side effect；aggregate conservation通過。
- G5 XLSX metadata/hash/size/filename/empty與failure tests。
- G6 focused regression、UTF-8、diff/secret/PII掃描通過。
- G7 evidence引用真route/application測試；禁止以ReportsPage樣本、Streamlit畫面或HTTP 200充數。
- Scenario映射固定覆蓋Part 00 P00-G47／G48／G54；authority未決時不得產生production expected。

## 5. Required commands

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp\phase4b-s -q `
  tests\test_subsidy_reconciliation_register.py `
  tests\test_government_subsidy_report_public_contract.py
git diff --check -- api/routes/finance_reports.py api/schemas/government_subsidy_report.py subsystems/government_subsidy/reconciliation_register_query.py tests/test_subsidy_reconciliation_register.py tests/test_government_subsidy_report_public_contract.py
```

## 6. Out of scope／後續

FinancePage／ReportsPage的canonical entry、generic weekly workbook、React Preview/Download及browser驗收都另案。
本包通過不代表 Phase 4B、Finance或Reports page完成。

## 7. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | PASS | 明確排除DB/schema |
| Change inventory | NOT_RUN | 無DB write set |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無owned-object變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。

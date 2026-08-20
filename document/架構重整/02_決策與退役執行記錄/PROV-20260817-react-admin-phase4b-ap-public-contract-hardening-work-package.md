---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase4b-ap-public-contract-hardening
date: 2026-08-17
owner: Staff Payables Reporting / Access Integration Owner
domain: Staff Payables / Access
source_gap: PROV-20260816-react-admin-phase4b-accounts-payable-public-contract-gap
approval_required: 核准此 exact Phase 4B-AP-H Work Package
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer; required-before-writer; preserve-all-user-work
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: not-applicable
---

# Phase 4B-AP-H：Accounts Payable public contract hardening 工作包

## 0. 授權狀態與目標

本工作包尚未取得 exact 人工核准，只能進行唯讀盤點。核准後只修 Accounts Payable
Preview／Export／Archive 的管理端 public contract；不接 React、不改付款狀態、不新增報表公式、
不改 DB/schema/migration，也不退役 Streamlit。

`api/routes/finance_reports.py`同時是
`PROV-20260817-react-admin-phase4b-subsidy-report-authority-hardening`的conditional production path。
固定順序為`AP-H → AP-H tests/evidence freeze → Subsidy-H fresh-read → Subsidy-H`。AP-H是該route的
canonical first writer；不得以不同測試檔或endpoint為由讓兩位writer同時修改該檔。

目標是讓後續 React Finance read/download slice 可以只使用 server-masked typed Preview 與受保護的
binary artifact metadata，而不接觸完整銀行帳號、身分證或 raw dict。

## 1. 已凍結的產品與安全裁決

1. Staff Payables Reporting 擁有報表 query/export；UI 不重算金額或付款狀態。
2. JSON Preview 只輸出去敏欄位。完整法定付款資料只存在於具備核准 capability 的 XLSX 下載內容，
   不得寫入 DOM、log、receipt 或測試 snapshot。
3. Preview 與 Export 都是 fresh snapshot。若無正式 fingerprint-bound artifact，本波不得宣稱兩者 byte-for-byte
   對應；response 必須清楚標示其 snapshot identity／generated_at。
4. Archive list 只回 metadata；本波不新增 archive download endpoint。
5. legacy `/accounts-payable-summary` 維持 410，不得復活。

## 2. Exact write set

- `api/routes/finance_reports.py`
- `api/schemas/accounts_payable_export.py`
- `subsystems/staff_payables/accounts_payable_export.py`（只限凍結`generated_at`／snapshot lineage authority）
- `tests/test_finance_reports_accounts_payable_public_contract.py`（new）
- `tests/test_accounts_payable_export_workflow.py`
- `tests/test_accounts_payable_export_sources.py`

除上述路徑外一律只讀。若需要修改 Access capability、shared exception handler、其他application/repository、
archive adapter、React、dependency、DB 或 schema，固定回報 `SCOPE_EXPANSION_REQUIRED`，不得自行擴張。

本包的production writer是`api/routes/finance_reports.py`在該批次的唯一first writer；Integration Owner開工前
必須檢查Subsidy包狀態、collision inventory與base drift，並把上述固定順序寫入candidate inventory。

### Integration document write set

- `document/架構重整/01_規格基線/05_Staff_Payables_Export_Domain.md`
- `document/架構重整/01_規格基線/16_Staff_Payables與Client_Refund正式規格.md`
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- 本工作包、`02/README.md`與
  `03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase4b-ap-public-contract-hardening/`（new）

只由Integration Owner寫入。

## 3. 實作要求

- 三個routes必須使用正式同權限政策的`require_admin`；不得新增system-only／capability差異。401／403只承諾
  fail closed與零PII；route產生的404／422／503才要求Global typed error。若需收斂shared auth envelope另立工作包。
- Preview success 必須有 explicit Pydantic response model；禁止 `dict[str, Any]`、裸 dict、任意 extra fields。
- masked bank/identity display 由 server 產生；不得把完整值送到 browser 後再 mask。
- Export response 必須提供安全 filename、content type、content length、SHA-256、generated_at、correlation ID；
  filename 不得含客戶／月嫂姓名或帳號。
- Archive list 必須 typed、bounded、authenticated；不得暴露 local path。
- `view`、`target_month` 的合法值、月份語意與錯誤狀態要成為 public contract，不得靜默忽略。
- Query/Export不得更改付款或ledger。GET Export每次產生新archive，不得描述成idempotent；必須使用安全唯一
  filename、拒絕覆寫既有artifact、驗證digest，且archive失敗不影響Domain facts。
- Scenario映射固定覆蓋Part 00 P00-G47／G50／G51／G58；JSON只masked，完整法定資料只在授權XLSX內容。

## 4. 互斥 lanes

1. Contract Scout（Luna，唯讀）：逐欄 route→Pydantic→UI policy 矩陣，列 DISPLAY／EXPORT_ONLY／REDACTED。
2. Backend Writer（Primary/Terra）：只改兩個 production paths與新 route test。
3. Regression Writer（Terra）：只補兩個既有 workflow/source tests；不得改 production。
4. Auditor（Luna，唯讀）：重跑命令、PII/raw-dict/write-set掃描；不寫 evidence。
5. Integration Owner：唯一可更新本工作包、README 與 evidence receipt。

Contract matrix 未 freeze 前 Backend Writer 不得開工；writer 產生的 fixture 不得成為唯一契約來源。

## 5. G0–G7 驗收

- G0 Scope：exact approval、dirty baseline、write-set 外 bytes未變；0 DB/schema/dependency/React。
- G1 Contract：每個 public field有Pydantic來源、nullable、display policy；PII欄位有server masking test。
- G2 Auth/Error：`require_admin`的401／403 fail closed且零PII；invalid month/view、route typed 404／422／503與correlation通過。
- G3 Preview：success／empty／large bounded result、0 full bank/identity leakage、0 Domain write。
- G4 Export：XLSX magic/content type、安全filename、size/hash一致、correlation、失敗fail closed。
- G5 Archive：typed bounded metadata、無local path、每次新artifact安全唯一、hash mismatch／overwrite fail closed；
  不宣稱GET Export idempotent。
- G6 Regression：focused pytest、strict UTF-8、`git diff --check`、secret/PII/raw-dict掃描通過。
- G7 Evidence：保存命令、exit code、真實測試數；不得以 mock client、HTTP 200或檔案存在宣稱完成。

## 6. 必跑命令

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp\phase4b-ap-h -q `
  tests\test_finance_reports_accounts_payable_public_contract.py `
  tests\test_accounts_payable_export_workflow.py `
  tests\test_accounts_payable_export_sources.py
git diff --check -- api/routes/finance_reports.py api/schemas/accounts_payable_export.py tests/test_finance_reports_accounts_payable_public_contract.py tests/test_accounts_payable_export_workflow.py tests/test_accounts_payable_export_sources.py
```

## 7. 完成邊界

最高狀態只代表 backend public contract hardened；React Preview／Download 仍需另立工作包與真 browser
download evidence。沒有受控 capability/browser前不得稱 Phase 4B 或 Finance page 完成。

## 8. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | PASS | 本包明確排除 DB/schema |
| Change inventory | NOT_RUN | 無 DB write set |
| Static release gate | NOT_RUN | 無 release |
| Descriptor gate | NOT_RUN | 無 owned-object變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。

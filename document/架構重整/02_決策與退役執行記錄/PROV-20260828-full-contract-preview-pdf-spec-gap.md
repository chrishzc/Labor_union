# 完整客戶／服務人員契約預覽與 PDF 規格缺口

- `spec_gap_id`: `PROV-20260828-full-contract-preview-pdf`
- `declared_status`: `proposed`
- `authority_status`: `AUTHORITY_REQUIRED`
- `terminal_status`: `SPEC_GAP`
- `current_task`: `CUR-CONTRACT-FULL-PREVIEW-01`
- `owner`: Contract Signing／Orders／Scheduling／Client／Staff／Client Finance／Controlled Files
- `priority`: LINE模組1～4之後（未另行指定前）
- `canonical_rules`: `21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md`、Global controlled-file/PDF contracts
- `reference_templates`: `db/templates/contracts/contract_client_copy.xlsx`、`db/templates/contracts/服務人員契約.xlsx`、`tpl_info_01.json`、`tpl_info_02.json`

## 1. Objective 與可觀察結果

1. 使用者選定一筆訂單後，客戶契約與服務人員契約都必須只使用該案件的current owner facts。
2. 切換訂單時，舊案預覽立即失效；不得短暫顯示在新案，也不得混入舊assignment。
3. 客戶契約預覽完整模板、法律條款、付款／服務資料與簽章區；服務人員契約同樣完整。
4. 兩者都可下載真實 `application/pdf`；preview 與 download 使用同一份 bytes，不得以HTML、`window.print()`或「契約草稿預覽（非正式）」代替。
5. 服務人員契約必須綁定exact assignment；同案多位服務人員時逐位選擇，不得猜測representative staff。

## 2. Current evidence 與 live drift

| Surface | Current evidence | Gap |
|---|---|---|
| React Orders | `ui_react/src/pages/OrdersPage.tsx` 只有手寫條款摘要與非正式草稿 | 沒有完整雙方 PDF 預覽 |
| legacy Streamlit | `ui/pages/form_management/tab3_contract_management.py`／`shared.py` | 契約為HTML/CSS鏡像；「導出PDF」實際下載HTML |
| current renderer | `infrastructure/db/contract_unsigned_pdf_repository.py` | facts SQL只覆蓋部分客戶／服務人員欄位 |
| Contract context API | `subsystems/contract_integration/contract_context.py`、`contract_context_repository.py` | 沒有覆蓋訂單資訏-1／2全欄，也沒有兩種文件的exact target model |
| external signing | `api/routes/contract_external_signing.py` | representative unsigned document不足代替client/staff target，也未接currently selected order preview |
| controlled file | release 1004/1005、current workflow | storage/digest/download可重用；不擁有契約欄位公式 |

Template inventory：客戶契約 worksheet `客戶契約`、185 rows／7 columns／112 merged cells；服務人員契約 worksheet `工作表1`、97 rows／8 columns／109 merged cells。客戶mapping約45欄，服務人員mapping約25欄，後者仍有6個帳務格位標為pending。

## 3. Owner mapping 邊界

- Contract Signing：template identity/version/hash、document target/version、unsigned PDF command、signing session/completion。
- Orders：case identity、terms、contract identity與案件lifecycle facts。
- Scheduling／Assignments：exact staff assignment、official dates與service tuple。
- Client／Staff／BeClass：各自身分、聯絡、申請／調查資料。
- Client Finance／Payroll：訂金、期款、費用／薪資及帳戶資料的canonical source；Contract renderer不重算。
- Controlled Files：opaque file identity、MIME、size、digest、staging/apply/download authorization。
- PDF adapter：已填XLSX轉PDF；不自行補值、計價或改法律條款。
- React：typed API／PDF blob預覽；不直接SQL、組合root facts或暴露storage locator。

## 4. 必須先收旂的規格缺口

1. `TPL-AUTH-01`：確認上述兩個XLSX是current正式template，還是只作舊版參考；若只參考，必須提供current replacement identity。
2. `FIELD-MAP-01`：客戶契約45欄與服務人員契約25欄的canonical owner path/type/version/requiredness。
3. `FIN-FIELD-01`：服務人員契約6個pending帳務格位與客戶契約訂金／期款／銀行欄位的owner、公式、masking/visibility。
4. `INFO12-01`：`tpl_info_01/02` 欄位如dietary/allergy/cooking/feeding/holiday/multiple-birth/parking等的typed source；不得用legacy raw column或placeholder。
5. `TARGET-01`：client contract與per-assignment staff contract的document target identity、current/superseded version與multi-staff selection。

推薦（未採用）：兩份XLSX作current visual/content baseline，但所有動態欄位必須取得owner typed source；mandatory欄位沒有root fact時fail closed，不留空、不作假，也不自動沿用上一筆訂單。

## 5. Acceptance

- `CPDF-A1`：切換case後，舊案request/preview/blob已失效，新案只顯示自己的client/staff contracts。
- `CPDF-A2`：兩個approved template都產生非空、可讀、全頁`application/pdf`；preview bytes=download bytes。
- `CPDF-A3`：mandatory mapping全部有typed source；missing/stale/cross-case/multi-assignment-unselected均fail closed。
- `CPDF-A4`：PDF在DB lock外render；stage/preview/apply保持version/digest/idempotency；UI不顯示path/URL/storage locator/full digest。
- `CPDF-A5`：同key同payload replay；同key不同payload conflict；render timeout/oversize/non-PDF/magic/EOF/digest drift零假成功。
- `CPDF-A6`：`pdfinfo`與逐頁`pdftoppm`驗證頁數、中文、合併儲存格、法律條款、付款/服務資料、簽章區、頁尾，且零裁切/重疊/空白頁。
- `CPDF-N1`：formula-like template content只literal render，不執行公式；HTML/XLSX/raw HTTPS/signed-return不可冒充unsigned PDF。

## 6. Scope／non-goals／safe stop

In scope：canonical facts projection、XLSX→PDF、controlled-file persistence、typed preview/download API、React full-document preview、case/assignment isolation、visual/security regression。

Out of scope：改寫法律條款、新的金額公式、direct provider send、production/NAS deployment、將Browser顯示當template Authority。

Safe stop：template/mapping hash、owner source、case/assignment identity、mandatory field、renderer output、digest、permission或controlled-file readback任一未知，就不顯示「完整契約」、不下載、不寫入。

```yaml
convergence:
  status: NOT_READY
  blockers:
    - TPL-AUTH-01: user must confirm the two XLSX templates are current authority or references
    - FIELD-MAP-01: domain owners must close all mandatory typed source mappings
    - FIN-FIELD-01: finance/payroll owner formulas and sensitive-field visibility are unresolved
    - INFO12-01: order information 1/2 typed projections are incomplete
    - TARGET-01: client/per-assignment staff document target identity must be fixed
```

Terminal status: `AUTHORITY_REQUIRED`。本文未達`SPEC_READY`，不得進task-pack或實作。

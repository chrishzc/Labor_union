# 完整客戶／服務人員契約預覽與 PDF 規格缺口

- `spec_gap_id`: `PROV-20260828-full-contract-preview-pdf`
- `declared_status`: `approved_mapping_compilation_in_progress`
- `authority_status`: `MAPPING_AUTHORIZED`
- `terminal_status`: `OWNER_SOURCE_GAPS_REMAIN`
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

## 4. 2026-08-31 人工裁決與 current mapping 結果

1. `TPL-AUTH-01`：`RESOLVED`。兩份XLSX是current template的靜態法律文字、section／label、visual layout、
   merged-cell結構、signature area與static content baseline；不擁有動態business fact或公式。
2. `TARGET-01`：`RESOLVED`。client target=`case_no + client scope`；staff target=
   `case_no + exact assignment/segment + staff scope`。版本沿用`contract_document_version`；多位staff未選
   exact assignment時fail closed。
3. `FIELD-MAP-01`：`PARTIAL_CURRENT_TYPED_SOURCE`。hash-bound inventory固定為客戶45格與staff25格；
   current typed source唯一的格位直接收斂，缺source／requiredness未定者維持unresolved。
4. `FIN-FIELD-01`：`PARTIAL_OWNER_SOURCE_GAP`。Contract Signing／renderer不得新增或重算金額；只接受
   Client Finance／Payroll／Staff Payables current typed derived value。完整帳務／銀行值只可進核准PDF與具權限
   的internal review；log、receipt、evidence不得保存不必要的完整帳號或個資。
5. `INFO12-01`：`OWNER_SOURCE_GAP`。raw `survey_details`、legacy column、placeholder與template formula都不構成
   typed source；缺少current owner projection時格位fail closed。

逐格mapping見§4.1與§4.2；每列的`version/snapshot`固定為同一document command保存的
`contract_document_versions.facts_snapshot_sha256`，且產生前必須由current owner Query重新讀取；缺少可重建的
owner snapshot時該列視為unresolved。
`full`表示核准PDF與具權限reviewer顯示完整正常業務值。`unresolved`一律不得留假值、沿用上一案或從raw
column猜測。

### 4.1 客戶契約45格 current mapping

| Cell | Template field | Canonical owner | Current typed source | Type | Requiredness | Visibility | Missing behavior |
|---|---|---|---|---|---|---|---|
| F1 | 訂單單號 | Orders | `ContractContextView.order.case_no` | text | required | full | fail closed |
| B7 | 簽約日期 | Contract Signing | unresolved：無current typed signed-date source | date | unresolved | full | fail closed |
| B8 | 客戶名稱 | Client | `ContractContextView.client.name` | text | required | full | fail closed |
| A9 | 預產期 | Client | unresolved：current context無typed due-date | date | unresolved | full | fail closed |
| C10 | 服務人員 | Staff／Scheduling | `ContractContextView.staff.name`，綁exact assignment | text | required | full | fail closed |
| B24 | 預定服務開始日期 | Orders commitment | unresolved：不得把Orders lifecycle date當commitment date | date | required | full | fail closed |
| D24 | 預定服務結束日期 | Orders commitment | unresolved：不得把Orders lifecycle date當commitment date | date | required | full | fail closed |
| F24 | 希望服務天數 | Orders | `ContractContextView.order.service_days` | integer | required | full | fail closed |
| B25 | 雇主單價 | Client Finance／Orders terms | unresolved：無current typed owner derived value | money | unresolved | full | fail closed |
| F25 | 服務總時數 | Scheduling／Orders | unresolved：不得在renderer計算 | decimal hours | unresolved | full | fail closed |
| B28 | 補助時數 | Government Subsidy／Orders | unresolved：無current typed contract projection | decimal hours | conditional unresolved | full | fail closed |
| E28 | 服務時段 | Client／Orders | `ContractContextView.client.service_time` | text | required | full | fail closed |
| D29 | 服務單價 | Payroll／Scheduling | `ContractContextView.assignment.hourly_rate` | money | conditional on exact assignment | full | fail closed |
| B30 | 自費天數 | Client Finance | unresolved：不得以total service days代替 | integer | conditional unresolved | full | fail closed |
| D30 | 每日服務時數 | Orders | `ContractContextView.order.service_hours_per_day` | decimal hours | required | full | fail closed |
| F30 | 費用合計 | Client Finance | unresolved：無current typed derived value | money | required | full | fail closed |
| F31 | 特殊休假 | Scheduling／Orders | unresolved：無current typed contract projection | text | conditional unresolved | full | fail closed |
| E33 | 政府案件編號 | Orders | `ContractContextView.order.case_no` | text | required | full | fail closed |
| B34 | 訂金金額 | Client Finance | unresolved：無current typed term amount | money | conditional unresolved | full | fail closed |
| C34 | 訂金日期 | Client Finance | unresolved：現有accounting source仍是raw mapping，尚非contract typed projection | date | conditional unresolved | full | fail closed |
| E34 | Email | Client | unresolved：current contract context未公開typed email | text | conditional unresolved | full | fail closed |
| B35 | 第一期款 | Client Finance | unresolved：無current typed term amount | money | conditional unresolved | full | fail closed |
| C35 | 第一期應收日期 | Client Finance | unresolved：無current typed term date | date | conditional unresolved | full | fail closed |
| B36 | 第二期款 | Client Finance | unresolved：無current typed term amount | money | conditional unresolved | full | fail closed |
| C36 | 第二期應收日期 | Client Finance | unresolved：無current typed term date | date | conditional unresolved | full | fail closed |
| D36 | 月嫂匯款帳號 | Staff Payables | unresolved：現有accounting source尚非contract typed projection | account text | conditional unresolved | full in approved PDF only | fail closed |
| B37 | 樓層費用 | Orders terms | `ContractContextView.order.floor_fee` | money | conditional | full | fail closed |
| C37 | 樓層費入帳日 | Client Finance | unresolved：不得以deposit date代替 | date | conditional unresolved | full | fail closed |
| B38 | 雇主自費合計金額 | Client Finance | unresolved：無current typed derived value | money | required | full | fail closed |
| E39 | 每日服務時數 | Orders | `ContractContextView.order.service_hours_per_day` | decimal hours | required | full | fail closed |
| B40 | 補助薪資 | Payroll／Government Subsidy | unresolved：無current typed contract projection | money | conditional unresolved | full | fail closed |
| D40 | 雇主退款銀行代號 | Client Finance | unresolved：current accounting source尚非contract typed projection | bank code | conditional unresolved | full in approved PDF only | fail closed |
| E40 | 雇主退款銀行帳號 | Client Finance | unresolved：current accounting source尚非contract typed projection | account text | conditional unresolved | full in approved PDF only | fail closed |
| B41 | 服務方式 | Client／Orders | unresolved：不得把`service_type`自動改義為template service mode | text | unresolved | full | fail closed |
| C41 | 寶寶資訊 | Client | `ContractContextView.client.baby_info` | text | conditional | full | fail closed |
| D41 | 生產方式 | Client | unresolved：current contract context無typed delivery type | closed text | conditional unresolved | full | fail closed |
| E41 | 居住型態 | Client | unresolved：current contract context無typed residence type | closed text | conditional unresolved | full | fail closed |
| F41 | 其他備註 | Client | `ContractContextView.client.notes` | text | conditional | full | fail closed |
| B43 | 服務地址 | Client | `ContractContextView.client.address` | text | required | full | fail closed |
| A48 | 服務時段 | Client／Orders | `ContractContextView.client.service_time` | text | required | full | fail closed |
| B178 | 甲方姓名 | Client | `ContractContextView.client.name` | text | required | full | fail closed |
| E178 | 甲方電話 | Client | `ContractContextView.client.phone` | text | required | full | fail closed |
| B180 | 甲方通訊地址 | Client | `ContractContextView.client.address` | text | required | full | fail closed |
| B181 | 乙方月嫂姓名 | Staff／Scheduling | `ContractContextView.staff.name`，綁exact assignment | text | required | full | fail closed |
| B185 | 立約簽署日期 | Contract Signing | unresolved：無current typed signed-date source | date | required | full | fail closed |

### 4.2 服務人員契約25格 current mapping

| Cell | Template field | Canonical owner | Current typed source | Type | Requiredness | Visibility | Missing behavior |
|---|---|---|---|---|---|---|---|
| F1 | 案件編號 | Orders | `ContractContextView.order.case_no` | text | required | full | fail closed |
| C4 | 服務人員姓名 | Staff／Scheduling | `ContractContextView.staff.name`，綁exact assignment | text | required | full | fail closed |
| B5 | 雇主姓名 | Client | `ContractContextView.client.name` | text | required | full | fail closed |
| B6 | 預計開始日期 | Scheduling | `ContractContextView.assignment.assigned_start_date` | date | required | full | fail closed |
| D6 | 服務天數 | Orders | `ContractContextView.order.service_days` | integer | required | full | fail closed |
| B7 | 服務開始日期 | Scheduling | `ContractContextView.assignment.assigned_start_date` | date | required | full | fail closed |
| D7 | 服務結束日期 | Scheduling | `ContractContextView.assignment.assigned_end_date` | date | required | full | fail closed |
| G7 | 服務天數 | Scheduling | unresolved：無assignment-specific typed day count | integer | required | full | fail closed |
| B8 | 服務時段 | Client／Orders | `ContractContextView.client.service_time` | text | required | full | fail closed |
| B9 | 休假方式 | Client／Orders | unresolved：不得把`service_type`自動改義為休假方式 | text | unresolved | full | fail closed |
| B10 | 服務單價 | Payroll／Scheduling | `ContractContextView.assignment.hourly_rate` | money | required | full | fail closed |
| E8 | 胎數 | Client／Case Import | unresolved：raw `survey_details`不是typed projection | integer | conditional unresolved | full | fail closed |
| F8 | 生產方式 | Client | unresolved：current contract context無typed delivery type | closed text | conditional unresolved | full | fail closed |
| H8 | 居住型態 | Client | unresolved：current contract context無typed residence type | closed text | conditional unresolved | full | fail closed |
| D15 | 服務區域 | Client／Orders | `ContractContextView.client.city` | text | required | full | fail closed |
| B24 | 服務地址 | Client | `ContractContextView.client.address` | text | required | full | fail closed |
| B94 | 服務人員姓名 | Staff／Scheduling | `ContractContextView.staff.name`，綁exact assignment | text | required | full | fail closed |
| B96 | 服務人員電話 | Staff | `ContractContextView.staff.phone` | text | required | full | fail closed |
| B13 | 補助費用 | Payroll／Staff Payables | unresolved：無current typed derived value | money | conditional unresolved | full | fail closed |
| C13 | 補助費用日期 | Staff Payables | unresolved：無current typed contract date | date | conditional unresolved | full | fail closed |
| B15 | 自費金額 | Payroll／Staff Payables | unresolved：無current typed derived value | money | conditional unresolved | full | fail closed |
| C15 | 自費金額日期 | Staff Payables | unresolved：無current typed contract date | date | conditional unresolved | full | fail closed |
| F10 | 費用合計 | Payroll／Staff Payables | unresolved：無current typed derived value | money | required | full | fail closed |
| B19 | 總計 | Payroll／Staff Payables | unresolved：無current typed derived value | money | required | full | fail closed |
| A97 | 契約當天日期 | Contract Signing／BusinessClock | unresolved：command snapshot date尚無typed field | date | required | full | fail closed |

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
  status: OWNER_SOURCE_GAPS_REMAIN
  blockers:
    - FIELD-MAP-01: unresolved rows require current owner typed sources and requiredness
    - FIN-FIELD-01: finance/payroll/payables contract projections are incomplete; renderer formulas forbidden
    - INFO12-01: raw survey_details has no approved typed projection
    - PUBLIC-API-ENTRY: preview/download endpoints still require explicit public-entry Authority
```

Terminal status: `OWNER_SOURCE_GAPS_REMAIN`。`TPL-AUTH-01`與`TARGET-01`已解除；已唯一的rows可直接採用，
但不得以局部mapping實作「完整契約」。涉及缺少owner source、requiredness或新增public preview/download entry時
維持`BOUNDARY_REQUIRED`，不得由Contract renderer補公式或旁路讀raw欄位。

---
doc_type: decision-and-closure-record
declared_status: repository-local-complete
date: 2026-09-01
owner: contract-signing / orders / scheduling / client-finance
---

# 完整客戶／服務人員契約自動套值與列印

## 最新人工裁決

- 輸出方式是既有瀏覽器「列印／另存 PDF」，不要求另建 server-side PDF endpoint。
- 「自動」是指欄位值由 current typed owner facts 套入，工會人員不得手動改值或改欄位對照。
- 客戶契約綁定案件；服務人員契約綁定 exact assignment。同案多人不得猜 representative staff。
- 現行 owner model 不存在的 legacy funding split 欄位標為 `not_applicable` 並自動留白；尚未形成的時間性 owner fact 只能條件式留白，不得編造數值。

## Current implementation

| Boundary | Current owner |
|---|---|
| typed owner projection | `infrastructure/mysql/contract_full_preview_repository.py` |
| zero-write exact-target Preview | `subsystems/contract_signing/full_contract_preview.py` |
| authenticated API | `POST /api/v1/orders/{case_no}/contract-signing/client/preview`、`POST /api/v1/orders/{case_no}/contract-signing/staff-segments/{segment_id}/preview` |
| browser rendering／print | `ui/pages/form_management/shared.py`、`tab3_contract_management.py` |
| approved mappings | `db/templates/contracts/contract_client_copy.json`、`contract_staff_service.json` |

Preview 回傳 cell-keyed `field_values`、blockers、template／owner fingerprints 與 `ready_to_print`。UI 僅將這些值套入既有 Excel mirror，內嵌 `window.print()` 供使用者列印或另存 PDF；不再保留重複的 server-PDF route、PDF download client 或 React download component。

簽約寫入流程與預覽共用同一份 client typed projection，避免舊 `_client_template_facts` SQL 與新版 mapping 再次漂移。簽約命令只補其擁有的 `contract_signed_date`，不重算 Finance、Scheduling 或 Payroll facts。

## Field applicability

- `due_date`：只有 legacy `due_month` 明確為 `YYYY/MM/DD` 才可套值；month-only 不推測日期。
- `staff_name`／`total_hours`：只有 current owner 已形成單一可識別 assignment／typed total 才套值；pre-assignment 或多人情境自動留白。
- 服務人員契約 `service_unit_price`／`staff_payable_total`：只有 official assignment rate／Staff Payables obligation 已存在才套值。
- B13／C13／B15／C15：現行模型沒有補助／自費拆分，固定不適用並留白。

## Verification

- focused Contract Signing：81 tests passed（typed projection、mapping blockers、renderer、API、UI client、browser-print HTML oracle、manual client workflow）。
- React：185 files／1202 tests passed；production build passed。
- real MySQL `lu_test_1`：Task 96 Scheduling lane C 完成雙服務人員契約、客戶契約、正式 assignment、actual-start、leave substitution、Payroll／Staff Payables lineage 與 fresh readback。
- browser-print oracle 證明 typed cell value 優先、raw fallback 不會穿透、HTML 會 escape，且保留 `window.print()`。

## External ceiling

本 closure 不宣稱真 NAS、verified LIFF、LINE provider send、production 或 preserve-data upgrade。這些依 Task 96 current register 個別標示為 `not_run`／deferred；不影響本項 repository-local 自動套值與列印完成判定。

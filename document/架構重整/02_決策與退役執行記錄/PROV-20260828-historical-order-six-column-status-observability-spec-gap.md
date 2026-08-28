# Historical Orders 六欄狀態判定與可觀測契約

- `spec_gap_id`: `PROV-20260828-historical-order-six-column-status-observability`
- `authority_status`: `CONFIRMED-2026-08-28`
- `spec_status`: `SPEC_READY`
- `implementation_status`: `completed`
- `owner`: Orders
- `authority`: 2026-08-28 使用者明確要求六欄歷史訂單匯入恢復判斷 `0／1／2`。

## 1. 問題與根事實

canonical workbook 固定為前六欄：`client_name`、`case_no`、`start_date`、`end_date`、
`status`、`staff_name`。Orders source profile v1 的 status 根事實固定為：

| source status | Orders asserted status |
|---|---|
| `0` | `訂單取消` |
| `1` | `訂單完成` |
| `2` | `洽談中` |
| 空白／其他 | 無 asserted status；建立既有 typed review evidence |

live drift 有兩項：

1. row fingerprint 使用 `str(raw_status or "")`，numeric `0` 因 falsy 被正規化成空字串，
   無法與缺值區分；Preview stale、replay與source identity完整性因此不可靠。
2. Preview／Apply receipt 只有總採納筆數，沒有 `0／1／2／invalid` 的可核對分布；UI無法證明
   六欄 parser 對每一種狀態的判定。

## 2. Required behavior

- `HOS-R1`: row source fingerprint 必須保存 status 的canonical source token；numeric `0`與空白
  必須不同，且不得改寫其他五欄或原始workbook content digest。
- `HOS-R2`: parser 必須接受numeric／文字的 `0／1／2`，以及Excel常見的`0.0／1.0／2.0`；
  其他值維持invalid，不推測中文或其他生命週期。
- `HOS-R3`: Preview與Apply receipt必須回傳strict `status_counts`：`cancelled_0`、
  `completed_1`、`discussion_2`、`invalid_or_blank`。四者總和必須等於`source_row_count`。
- `HOS-R4`: React資料匯入卡顯示四項判定數量；不得在前端重算status或修改Orders。
- `HOS-R5`: Apply仍沿用既有row-atomic Orders Q/P/A、fresh version、event、receipt與outbox；
  不新增schema、不觸發現行通知／帳務、不提供generic status editor。
- `HOS-R6`: same key＋same workbook replay回相同status counts；same key＋different workbook維持conflict。

## 3. Acceptance

| ID | Acceptance |
|---|---|
| `HOS-A1` | 六欄三列 `0／1／2` Preview回counts各1、invalid 0；逐列asserted status為取消／完成／洽談中。 |
| `HOS-A2` | 相同其餘五欄的status `0`與空白，其row fingerprint不同；空白列為invalid review。 |
| `HOS-A3` | 真`lu_test_*` MySQL Apply後三個既有Order分別回讀取消／完成／洽談中，並各有exact lifecycle event／receipt。 |
| `HOS-A4` | API Pydantic、React Zod與adapter拒絕counts不守恆；Browser可見四項counts。 |
| `HOS-A5` | replay counts相同且row counts不增加；different payload conflict零新增。 |

## 4. Boundaries

- 不改DB schema、migration、release、Client／Scheduling／Finance／Staff Payables owner roots。
- 不解析第七欄起的月嫂資料，不重開雙月嫂契約。
- 不以UI輸入target status；UI只顯示server-owned Preview／receipt。
- 不修改`union_db`或production target；runtime只使用具唯一identity的`lu_test_*`資料。

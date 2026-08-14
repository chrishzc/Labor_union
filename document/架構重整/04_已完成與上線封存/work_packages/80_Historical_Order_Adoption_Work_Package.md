---
doc_type: work-package
declared_status: superseded
date: 2026-08-13
owner: Orders / Scheduling / Payroll
priority: P0
---

> 歷史封存版本：2026-08-13 的 Preview-only 版本已被 active
> `80_Historical_Order_Adoption_Work_Package_Completed_20260814.md` 取代；不得以本檔授權實作。

# 80 Historical Order Adoption Work Package

## 1. 人工裁決與 business scenario

2026-08-13 人工確認：歷史訂單檔只用來補登既有 HCM 案件的來源狀態與月嫂配對證據，
避免已完成／取消的舊案件仍停在預設「洽談中」，並為日後帳務回溯提供可追溯根事實。
它不建立找不到的 Client／Order，也不得重新開放已退役的
`scripts/import_historical_orders.py` direct-SQL writer。

配對既有案件固定使用 `case_no + 客戶姓名` 精確相符；找不到時回 `unmatched_case`，
不寫 Domain root、不建立警示。來源狀態 v1 只接受 `0→訂單取消`、`1→訂單完成`、
`2→洽談中`；空白或其他值進 durable review。實際開始／結束日期永遠允許 `NULL`，
Excel 五碼日期依 workbook 的 1900／1904 date system 轉換；無效非空值只省略該欄並 review，
不得阻擋同列合法狀態採納。

來源可有兩位月嫂。月嫂空白、找不到或姓名不唯一都不阻擋狀態採納，只保存配對 evidence
與 review。單一月嫂且來源起訖日可唯一視為該人的區間時，可建立 completed
`case_staff_assignments`；多月嫂只有共同起訖日、沒有每人各自區間時，不建立 assignment、
不猜測分段。沒有 assignment-owned 正式服務日及費率快照時不得猜算薪資，只標記
`payroll_rebuild_blocked`，待補足根事實後再呼叫既有 typed Payroll rebuild。

## 2. Architecture 與 transaction boundary

- Orders 擁有 asserted historical lifecycle event、目前 status／nullable actual dates、version 與 receipt。
- Scheduling 擁有正式 assignment；Historical Adoption 只透過 purpose-specific borrowed writer，
  不寫 `orders.staff_id`、不建立 `staff_schedule`。
- Payroll 仍只讀 assignment-owned official service days 與 rate snapshot；本包不反推金額。
- Preview 零寫入。Apply 每一 source row fresh lock `case_no + client_name`、重建 candidate、
  驗證 fingerprint 後，以單一 outer Unit of Work 寫 Order projection、event、assignment／evidence、
  review、outbox 與 receipt。
- 相同 source identity＋fingerprint replay 原 receipt；相同 identity＋不同 fingerprint fail closed。
- 既有非「洽談中」狀態若與來源不同，保留 current fact 並 review；歷史來源不得覆寫較新的狀態。
- 日期只補 DB 空值；既有非空日期衝突時保留 current fact並 review。

## 3. Source profile v1

- 必要欄位：客戶姓名、案件編號、status；sheet 名稱不限，只接受唯一符合欄位契約的 sheet。
- 可選欄位：開始日期、結束日期、第一／第二月嫂姓名，以及各月嫂獨立起訖日。
- 六欄 legacy layout 仍可讀：`client_name, case_no, start_date, end_date, status, staff_name`。
- 未知欄忽略；重複必要欄、多個符合 sheet、空 workbook 固定 fail closed。
- 原始 workbook 不寫 DB；receipt／review 只保留 digest、row、masked identity、issue code 與 bounded facts。

## 4. Change inventory

| 類型 | 變更 | 資料效果 | replay／rollback |
|---|---|---|---|
| schema-only | Historical Order receipt／pairing evidence／review／outbox | 新增不可變採納證據 | source identity＋fingerprint replay；code rollback 保留證據 |
| schema-only | 無新增 Order／Staff 欄位 | 沿用 lifecycle event、orders version、case_staff_assignments | expected version guard |
| system-seed | 無 | 無 | 不適用 |
| business-row-backfill | 無自動 backfill | operator 明確 Apply 才逐列採納來源 | 預設 Preview；逐列 receipt 可安全重跑 |
| destructive | 無 | 不刪除、不覆寫非空衝突 | 不適用 |

## 5. Write set

- `document/架構重整/01_規格基線/01_Orders_Domain.md`
- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md`
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- 本文件與同目錄 `README.md`
- `domains/orders/historical_adoption.py`
- `subsystems/orders/historical_adoption_workflow.py`
- `subsystems/orders/historical_order_workbook.py`
- `infrastructure/mysql/historical_order_adoption_repository.py`
- `scripts/imports/adopt_historical_orders.py`
- `db/schema_parts/190_historical_order_adoption.sql`
- `db/schema.sql`、WP80 release manifest／descriptor、canonical migration catalog
- WP80 focused／disposable MySQL／release tests與 evidence

## 6. DB gate

| Gate | 狀態 | 證據／條件 |
|---|---|---|
| Scope | PASS | 本文件及 2026-08-13 人工「開始執行」 |
| Change inventory | PASS | 第 4 節；無 seed／自動 backfill／destructive |
| Static release | PASS | metadata／manifest focused `36 passed`；validation manifest verifier valid |
| Descriptor | PASS | WP80 descriptor test涵蓋4表與immutable triggers |
| Read-only plan | PASS | runner解析latest WP80並列出`190_historical_order_adoption.sql` |
| Engine verification | BLOCKED | WP80 MySQL E2E `1 passed`；preserve candidate先被既有185／186 partial baseline阻擋 |
| Developer acceptance | NOT_RUN | 不在現有 union_db 執行；交付後由 operator Preview／Apply |

目前總結：`DB_CHANGE_NOT_READY`。

## 7. Acceptance

1. Preview 對 242-row 真實形狀輸出守恆 manifest，零寫入。
2. 只有 `case_no + client_name` 精確匹配才可採納；未匹配不寫入、不警示。
3. 0／1／2 mapping、blank／unknown review 永久回歸。
4. 1900／1904 serial、字串日期、空值及無效日期行為明確。
5. 單月嫂可建立 completed assignment；雙月嫂無各自區間只留 evidence。
6. staff missing／ambiguous、日期 issue 不阻擋合法 status；current conflict 不被覆寫。
7. Apply 寫 projection、event、receipt、evidence、review／outbox於同一交易；失敗全回滾。
8. replay、idempotency mismatch、stale、partial schema／drift fail closed。
9. Payroll 缺 official days／rate 時只回 blocker，不猜測金額或建立 obligation。
10. 新 CLI 預設 Preview，Apply 需明確 target allowlist 與確認旗標；replacement parity、release、
    disposable MySQL 與 source-scan 通過後直接移除舊 `scripts/import_historical_orders.py`、fixture caller
    與 entry inventory，不保留永久退役殼。

## 8. Out of scope

- 管理端 upload UI、API 與 durable upload storage。
- 以姓名建立 Client／Order／Staff，或以共同日期猜測兩位月嫂的服務分段。
- 反推每日正式服務日、費率、收付款、補助或自動建立任何金額。
- 修改既有 union_db；正式／開發資料 Apply 由 operator 在 release gate 通過後明確執行。

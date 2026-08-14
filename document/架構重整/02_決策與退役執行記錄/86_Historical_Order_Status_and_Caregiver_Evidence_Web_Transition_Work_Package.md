---
doc_type: work-package
declared_status: in-progress
date: 2026-08-14
owner: Orders / Global Management UI
priority: P0
---

# 86 訂單狀態與月嫂歷史配對 Web 過渡匯入 Work Package

## 1. 人工裁決與 business scenario

歷史來源檔與舊模組名稱可保留 `historical_orders` 作為來源追溯，但管理端顯示名稱與業務責任為
「訂單狀態與月嫂歷史配對」。在完整資料重建與實測前，操作員必須能由資料匯入中心先 Preview、
再 Apply 既有訂單的歷史狀態、配對月嫂 evidence 與實際服務日期；不可回退至 retired direct-SQL
writer，也不可讓 Streamlit 呼叫 CLI。

本包是 WP80 的 Web transition 子包，也是 WP83 的獨立 Orders card。它不改變 Orders Domain 的
歷史採納語意，不建立新 Client／Order，也不替多月嫂猜測個別服務區間。

## 2. Scope

1. 在「📥 資料匯入中心」新增一張「訂單狀態與月嫂歷史配對」卡；僅接受其明確 source profile
   的 `.xlsx`，不依檔名或 sheet 名猜測類型。
2. 新增 Orders-owned typed HTTP Preview／Apply endpoint、strict request／view、bounded UI client；
   endpoint 只呼叫既有 `HistoricalOrderAdoptionWorkflow`／application port，絕不 import 或 subprocess
   `scripts.import_historical_orders.py` 或 `scripts.imports.adopt_historical_orders`。
3. Preview 零寫入，顯示來源筆數、可採納、unmatched、review、正式 assignment 候選與多月嫂
   evidence-only counts。Apply 必須用 preview fingerprint、workbook digest 與穩定 idempotency key。
4. Apply 每列 fresh-lock Order，唯一匹配為 `case_no + client_name`；0／1／2 採納歷史 asserted
   status，空白／未知值進 review。unmatched case 是零 mutation、零 anomaly 的 terminal outcome。
5. `actual_start_date`／`actual_end_date` 永遠容許 `NULL`，Excel 1900／1904 serial 必須轉成西元
   日期。只要來源有月嫂姓名與案件編號，就保留歷史配對 evidence；只有每位月嫂有唯一服務區間
   才建立正式 `case_staff_assignments`，多月嫂缺個別區間只保存 evidence，不猜日期、排班、薪資
   或帳務。
6. UI 必須顯示 typed receipt、replay、conflict、review／anomaly 導向；source profile mismatch、
   multi-sheet ambiguity、unknown status、fingerprint stale 與 infrastructure failure 都 fail closed。

## 3. 過渡入口與退役邊界

- `scripts.import_historical_orders.py` 已退役，維持拒絕寫入。
- `scripts.imports.adopt_historical_orders` 保留為 operator-only maintenance adapter：預設 Preview，
  Apply 必須明確 `--apply --confirm-database`。它不是 UI backend，也不是永久一般操作入口。
- 本包驗收完成後，管理端日常入口改為 Web card；CLI 的最終移除需在完整資料重建、web Apply
  replay／rollback 與 operator cutover receipt 均完成後，另行裁決，不在本包自動刪除。

## 4. Out of scope

- 不新增或變更 Orders／Assignments schema、status state machine、Payroll、Finance、排班或通知規則。
- 不對真實來源檔、正式 production DB 或既有非隔離資料庫 Apply。
- 不替 Client／Staff BeClass、HCM 或 Finance card 實作功能；它們仍由 WP73／77／83 各自承接。
- 不將歷史 evidence 轉換為當期 service schedule、付款、薪資、追償或自動帳務。

## 5. Write set

- `15_正式規格索引與裁決總表.md`、`01_Orders_Domain.md`、WP80、WP83、本文件與本目錄 `README.md`
- Orders historical adoption application／repository 的必要 typed port（只修本包 API adapter 所需邊界）
- `api/routes/`、`api/schemas/`、`api/dependencies/` 的 Orders historical import 精確檔案與 `api/main.py`
- `ui/api_clients/`、`ui/pages/09_data_import.py`、navigation 的 Orders card 精確檔案
- 去敏 fixture／manifest、module／subsystem／API client／UI 與 disposable MySQL focused tests
- entrypoint review queue 與只保存 digest／counts 的 evidence receipt

若發現既有 WP80 release 不足以表達已核准的 evidence 或 receipt，先觸發 DB scope gate；不得在本包
順手加入 DDL 或 backfill。

## 6. Acceptance

1. Preview 對現有 Order、Assignment、Finance／Payroll projection、outbox 皆零寫入；Apply 的每列
   terminal outcome 守恆，且由單一 Orders outer UoW 擁有 commit。
2. 同 key＋同 digest terminal replay；同 key＋不同 digest 在任何 row mutation 前 conflict；中斷後
   matching retry 可安全 resume，不建立重複 event、assignment 或 receipt。
3. 有姓名＋案件編號的月嫂來源 evidence 被保存；日期可空。僅在每位月嫂都有唯一區間時建立正式
   assignment；雙月嫂缺個別區間的 fixture 證明零 assignment／零日期猜測。
4. `0`／`1`／`2`、空值、未知 status、1900／1904 日期、unmatched、existing current conflict、
   malformed sheet／header 都有 focused contract evidence；unmatched 固定零 mutation、零 anomaly。
5. disposable MySQL 證明 Preview、Apply、exact replay、conflict、rollback、existing Order preservation
   與 assignment/evidence projection；若 schema gate 未通過，結果只能為 `DB_CHANGE_NOT_READY`。
6. 實際啟動 API／Streamlit，使用去敏 `.xlsx` 從資料匯入中心完成 Preview、Apply、review、replay、
   conflict 與 typed error 顯示驗收；Chrome 專項驗收依 WP83 completion gate 執行。
7. `scripts/launchers/update_local_database.bat` 的 preview／candidate／verify，在任何本包所需 release
   完整收斂後皆通過；之後才允許完整重建測試 DB 的受控真實資料實測。

## 7. Dependencies／completion gate

- 依賴：Orders formal spec、WP80 typed workflow／release evidence、WP83 card composition、已完成的
  WP73 HCM card pattern。
- 本包只在第 6 節全部通過後完成；不因 parser、CLI Preview 或 UI 骨架存在而封存。
- WP80 仍擁有 Orders historical adoption 的 Domain／schema／disposable evidence；本包只擁有 Web
  transition。兩包必須共同更新 evidence，避免形成第二套語意。

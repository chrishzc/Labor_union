---
doc_type: work-package
declared_status: completed
date: 2026-08-13
owner: Case Import / Orders / Finance Import / Global Management UI
priority: P0
---

# 83 資料匯入中心與 Web Apply Work Package

## 1. 人工裁決與 business scenario

2026-08-13 人工確認：管理端需有單一「資料匯入中心」，以各類別獨立卡片上傳現實與歷史
workbook。每張卡都先 Preview、再 Apply，顯示 typed receipt 與 review／anomaly 導向；不得由
Streamlit 直接呼叫 script、SQL 或跨 Domain writer。

HCM 與銀行流水固定由 Web upload。Client／Staff BeClass 在 LIFF current writer 尚未完成
end-to-end 驗收前，可作為 temporary authenticated Web upload；LIFF 穩定後必須退役 temporary
card、API 與 entrypoint。歷史訂單只補既有 Order 的 historical status／配對 evidence。

## 2. Scope

1. 新增「資料匯入中心」導航頁與 typed category cards：HCM 案件、Client BeClass、Staff
   BeClass、歷史訂單狀態／配對、銀行流水／帳務歷史。
2. 每卡必須獨立處理檔案、來源意圖、sheet contract、Preview、Apply、固定 idempotency key、
   success／replay／review／conflict receipt 與異常中心導向；不可共用模糊 payload。
3. HCM Web upload 先完成 WP73 的 source intake、temporary cleanup、workbook replay／conflict
   與 Case Import review 邊界。
4. 將既有歷史訂單與 Finance Import typed API 接入卡片；Client／Staff temporary card 只能在
   後端已收斂為 typed application 後啟用。

歷史訂單卡的實際 Web transition、歷史月嫂配對 evidence 與可空實際服務日期由 WP85 執行；
`historical_orders` 只作來源追溯，畫面名稱固定為「訂單狀態與月嫂歷史配對」。
5. 完整 release 必須可由 `scripts/launchers/update_local_database.bat` 對本機既有資料庫安全
   升級；之後才以完整重建測試 DB 進行真實資料 UI 實測。

## 3. Out of scope

- 不以本包決定 Staff profile 的永久 canonical owner。
- 不把 LIFF、browser 或 File Watcher 變成 direct DB writer。
- 不在未有 disposable MySQL evidence 前對真實來源資料或既有 `union_db` Apply。
- 不把 Finance anomaly 的單筆人工修正放進一般匯入卡。

## 4. Write set

- `15_正式規格索引與裁決總表.md`、`17_External_Integration_LINE_Access正式規格.md`、本文件與本目錄 `README.md`
- WP73／WP77／WP80 直接需要的 source、schema、release metadata、API、UI client、pages、navigation、entry queue 與 focused tests
- Finance Import UI／API 只限 upload idempotency、multi-sheet contract、台新／永豐／歷史格式 Preview／Apply evidence
- 一鍵本機資料庫升級 launcher、其 migration metadata／tests，以及只保存去敏 counts／digest 的 evidence

任何新增 Domain root、非 additive DDL、真實資料 backfill、production deployment 或 temporary
entry retirement，必須另有明確裁決。

## 5. Acceptance

1. UI 只顯示 typed category card，卡片不使用 raw dict／直接 SQL／script direct writer。
2. 每卡 Preview 零寫入；Apply fresh-validate，輸出 strict typed receipt；unknown／multi-match
   sheet 與違反欄位契約固定 fail closed。
3. 相同 command key＋相同 digest replay；同 key＋不同 digest conflict；上傳回應遺失的 retry
   不得建立重複 roots 或 batch。
4. review rows 不阻擋同檔可接受 rows；receipt counts 守恆並可導向異常中心。
5. HCM、Client／Staff BeClass temporary、歷史訂單、台新、永豐與歷史帳務各有 focused
   contract evidence；實際 Apply 必須有 disposable MySQL evidence。
6. `update_local_database.bat` 在完整 release 對本機舊資料 schema 的 preview／candidate／verify
   均通過；full rebuild 後 UI 實測順序為 HCM、Client、Staff、歷史訂單、帳務。
7. Client／Staff LIFF end-to-end 完成後，temporary Web upload 有可驗證的 removal trigger，未完成
   前不得宣稱永久入口。

## 6. Completion gate

本包與 WP73 均須通過 API／Streamlit 實際啟動與 Chrome 或人工明確允許的內建瀏覽器 upload、invalid review、replay、conflict
驗收；在完整重建 DB 與各類實際資料受控實測前不得封存。

### 6.1 2026-08-14 更新後的唯一達成條件

本 Work Package 是本輪資料匯入工作的唯一整體終點。只有下列全部成立，才可將「資料匯入中心」
標記 completed 並依 archive gate 封存：

1. HCM、Client BeClass temporary、Staff BeClass temporary、訂單狀態與月嫂歷史配對、
   銀行流水／帳務歷史五張獨立卡都只呼叫其 owning Domain 的 typed API；不得保留「後續類別」
   placeholder 或由 UI／API 呼叫 legacy script。
2. 每一張卡都有該 bounded source profile 的 Preview／Apply、stable idempotency、same-key replay、
   different-digest conflict、髒列隔離／review、typed error 與異常中心導向證據；Finance 的 upload
   staging 與正式 posting Preview／Apply 必須明確分開，不得宣稱上傳為零寫入。
3. 每一 lane 均有 focused 與 disposable MySQL evidence；HCM、Client、Staff、歷史訂單、
   Finance 的實際 Chrome flow 都需驗證 upload、invalid review、replay、conflict 與可讀 typed result。
4. canonical release 以 `update_local_database.bat` 完成 preview／candidate／verify；完整重建的
   隔離測試 DB 依 HCM → Client → Staff → 歷史訂單 → 帳務順序完成受控實際來源驗證，並保存去敏 receipt。
5. Client／Staff temporary card 的 LIFF removal trigger 仍保持可驗證；LIFF 尚未 end-to-end 驗收前，
   不得提前移除 temporary card，也不得把它宣稱為永久 owner。

WP85 只證明第 1 項中的歷史訂單卡，不能單獨結束或代表資料匯入中心完成。HCM／Client BeClass
任一方成功提交後，Case Import 只針對該案件重新計算來源對應與一般 Matching 條件；這是 intake 的
既有責任，不新增欄位專屬流程、狀態機、outbox 或 schema。

## 7. 2026-08-14 completion

五個 lane 已依 owning typed API 完成 focused、disposable MySQL 與去敏 workbook 驗收。內建瀏覽器
實際上傳 `3.client_beclass.xlsx` 後，UI 顯示一列 `review_required` 的 typed Preview；Apply／replay
在隔離 MySQL 執行，未對開發者目前資料庫寫入。HCM、Staff、歷史訂單的去敏 workbook 結果分別
由 WP73、WP77、WP85 completion receipt 承接；Finance 的三種真實格式 sample、root-fact posting
與 UI/API Preview parity 均通過。

本包沒有新增 schema；canonical read-only plan 顯示 WP88 v4 的 61～194 artifacts 全部 `exact`。
警示中心 UI、Correct／Reject 與轉介 command 明確不在本輪 completion 範圍，留由 WP86／WP88
successor 執行，不阻擋匯入中心 completion。完整證據見
`../../03_追蹤清單與證據/evidence/2026-08-14_wp83_data_import_center_closeout_receipt.md`。

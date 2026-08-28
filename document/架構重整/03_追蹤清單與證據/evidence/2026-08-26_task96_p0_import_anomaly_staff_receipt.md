# Task 96 P0 import, anomaly, and staff receipt

- Current IDs：`CUR-P0-HISTORICAL-IMPORT-01`、`CUR-P0-ANOMALY-RECOVERY-01`、`CUR-P0-STAFF-QUERY-01`
- 驗證日期：2026-08-26
- 原始結論：歷史匯入、異常 UI safety 與 Staff acceptance 均通過。
- Current disposition（2026-08-26 使用者新裁決）：歷史匯入與 Staff 為 `completed`；
  `CUR-P0-ANOMALY-RECOVERY-01` 重開為 `in-progress`。原驗收只證明歷史 alert 不會假裝有
  Finance／generic 修復，沒有證明使用者具備可完成的人工 remediation，不能當作新範圍完成。
  未操作 `union_db`、production、schema、migration、replacement 或 `--switch`。

## Browser 與 MySQL acceptance

- 歷史訂單 workbook：在本機 React Import UI 以
  `scratch/task96-p0/historical-review-7d0a170bdfda.xlsx` 完成 Preview 與 Apply。Preview 為
  source `1`、adoptable `0`、unmatched `0`、review `1`、conflict `0`；Apply receipt 顯示需檢查 `1`。
- outbox consumer 投遞 `1` 筆後 readback：`HISTORICAL-ORDER-001` 的
  `source_identity=historical-order-review:9a019b5a-2527-4da6-919d-977aea733224`，歷史訂單仍為
  `洽談中`、`lifecycle_version=0`、assignment `0`；兩個 import-warning tracking task 均為 `open`。
  這是 Orders owner review，不是自動修復或 Finance action。
- 本機 Brave Chrome 顯示 anomaly card `匯入資料／歷史訂單匯入待人工確認`。Drawer 僅提供回到
  歷史訂單匯入流程核對來源列的指引；未出現 generic unavailable fallback、累計偵測次數、帳務資料更正
  或 Finance fallback surface。
- Staff Browser：初始 200 筆後按「載入下一頁」得到第 201 筆，再搜尋
  `CUR-P0-STAFF-LATE-7d0a170bdfda`，唯一命中 staff id `201`。因此 cursor continuation 命中不再侷限於
  初始頁。

## Focused verification

- `ui_react`: `npm test -- --run src/tests/anomalies_detail_referral_flow.test.tsx`：`6 passed`。
- `ui_react`: anomalies focused regression（real-data、no-fake-mutation、finance-correction、adapter）：`39 passed`。
- `ui_react`: `npm run lint`：passed（既有 warnings）；`npm run build`：passed（既有 large-chunk warning）。
- MySQL readback：`scratch/task96-p0/verify_acceptance_state.py`；其輸出僅保留在 ignored scratch，避免將
  test identity 或原始資料寫入追蹤文件。

## DDH 運作記錄

初始以 E4 兩條 read-only verification lanes 投影；其中一條完成 UI boundary 建議，另一條未形成可整合
deliverable，且第一版 plan assertion 不適用於實作 deliverable。因此不將其視為已通過的 DDH parallel
integration，將剩餘工作重投影為 E2 單一整合 lane。最終 patch 與驗收均由同一整合 lane 完成；詳見 ignored
`scratch/task96-p0-ui-ddh/lifecycle-state-r1-corrected.json`、`terminal-r1-corrected.json`。

## Superseded anomaly acceptance

歷史 alert 的 Chrome card／Drawer UI safety 驗收仍為有效的負向證據：它沒有 false Finance action、
fake occurrence count 或 generic unavailable fallback。然而它只叫操作者回到匯入流程，沒有 owner
Preview／確認／Apply／receipt／recheck，也沒有讓 immutable review predicate 合法消失的狀態。因此使用者
於 2026-08-26 明確要求「所有異常都應該要有人工修正的功能」後，此 evidence 不再支持
`CUR-P0-ANOMALY-RECOVERY-01` completed；正式的跨 Domain remediation contract 與 Orders 實作另行列管。

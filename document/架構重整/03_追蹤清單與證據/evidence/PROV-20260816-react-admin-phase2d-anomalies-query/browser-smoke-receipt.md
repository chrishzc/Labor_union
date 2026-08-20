# Browser Smoke Receipt — Phase 2D Anomalies Query

**Document Code**: `PROV-20260816-react-admin-phase2d-browser-smoke-receipt`  
**Timestamp**: 2026-08-16 fresh Chrome audit  
**Status**: `PASS_AFTER_PHASE2D_H_API_RESTART`

## Latest Phase 2D-H audit

後端候選已修正原severity public-contract gap。port 8000舊程序被精確重啟為專案`.venv` FastAPI後，
同一已登入Chrome tab重新mount兩個query family：100筆anomaly與Import Warning皆進DOM，schema mismatch與
retry UI消失，100個claim全部disabled。下節保留的是修正前歷史root-cause證據。

## True runtime result

在使用者已完成 password→TOTP 的真實 Chrome Session 中開啟 React Anomalies 頁面：

- Import Warning tasks：GET 成功，真資料可在 DOM 顯示。
- Anomalies summaries：GET 有 payload，但 strict decoder 對 100 筆資料逐筆拒絕空白 `severity`；
  DOM 顯示 schema mismatch，而非異常卡片。
- 未讀取、記錄或輸出任何 bearer token、帳密或 TOTP。

先前 happy-dom 元件測試不是 G7 Network→DOM 證據，已撤銷 `LOCAL_VALIDATED` 判定。前端 strict
decoder 的 fail-closed 行為正確；不可為了讓畫面顯示而接受空字串或自行猜 severity。

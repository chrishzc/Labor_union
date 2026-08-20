# Part 04 操作清單

1. 以受控測試帳號登入，確認頁面顯示 synthetic staff key 對應的 typed summary。
2. Preferences 執行 Query → Preview → Apply → receipt → re-query；修改內容後舊 Preview 必須失效。
3. Availability 執行 create 與 cancel 的 Query → Preview → Apply → receipt → re-query；不得由畫面計算天數、overlap、buffer 或 eligibility。
4. Lifecycle 分別執行 retirement 與 reactivation 的 Query → Preview → Apply → receipt → re-query；state、version、fingerprint 全由 server 決定。
5. 對 timeout/network/503 觀察 `outcome_unknown`；只有相同 payload 與 Idempotency-Key 可重試，re-query 失敗顯示 `observation_failed`。
6. 嘗試清單標示為 unavailable 的 mutation 控制項，確認原生 disabled，沒有 alert、confirm 或假成功訊息。
7. 記錄 API Network、DOM、DB/UoW、receipt 與 re-query 結果；未具備真實環境時保持 `NOT_RUN`。

# Part 14 操作清單

1. 載入 synthetic warning task，確認欄位級 warning 與 tracking status 由 typed API 提供。
2. 開啟 warning transition Preview，確認畫面不先改變狀態且後端證明零寫入。
3. 輸入非空 reason 執行 Apply；確認 server receipt、outbox observation 與 re-query 結果一致。
4. 重放相同 idempotency key，確認結果可重播；stale、timeout 與 enqueue failure 必須明確顯示。
5. 確認 Claim、Resolve、source correction 與 provider send controls 維持 unavailable/disabled。

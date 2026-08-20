# Part 09 操作清單

1. 以固定 business clock 載入 current calendar，分別記錄有資料、空範圍、abort 與 typed error。
2. 以 linked leave request 與 replacement request 執行 Preview；確認 Preview 零寫入且半組、stale 版本被 server 阻擋。
3. 在核准環境執行 Apply，確認單一 outer-UoW、receipt、re-query 與 LINE intent lineage；不得以前端推導替代。
4. 查詢 holiday policy horizon 與版本；確認 cache miss/version mismatch 顯示 unavailable 或 typed blocker。
5. 記錄每一步 Network、DOM、DB/UoW 與 receipt evidence；未具備真實環境時保持 `NOT_RUN`。

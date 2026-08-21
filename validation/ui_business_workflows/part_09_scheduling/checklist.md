# Part 09 操作清單

1. 以固定 business clock 載入 current calendar，分別記錄有資料、空範圍、abort 與 typed error。
2. 既有 development DB 只執行 Holiday GET 與 zero-write Preview；保存 Network／DOM evidence，禁止 Apply。
3. 以本工作包 owned disposable DB 執行 Holiday Query→Preview→Apply→receipt→post-commit re-query；只在
   re-query 為 `observed` 後顯示完成，並保存 owned rows before/after 與 scoped cleanup receipt。
4. 用相同 payload 與 stable idempotency key驗證same-key replay；不同 payload 使用相同key必須typed conflict。
5. stale expected version、conflict與rollback分別驗證零partial write；未執行的browser variant明列`NOT_RUN`。
6. outcome-unknown只允許以相同payload／idempotency identity恢復；不得以前端樂觀成功替代server receipt。
7. linked leave/substitution維持其獨立scenario與outer-UoW evidence，不以Holiday receipt替代。

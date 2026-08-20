# Phase 4C-Q open findings

- `OPEN-H01`：rules／config／publication route response model仍是 raw dict；client strict decode只是隔離，不是backend hardening完成。
- `OPEN-H02`：Rich Menu publish-preview會寫 `line_rich_menu_publish_previews` 並commit；名稱與Global Preview零寫入衝突。
- `OPEN-H03`：current notification-rules可能沒有 revision；UI必須顯示empty，不得使用prototype `RULES`。
- `OPEN-H04`：publish/retry/upload/delete會建立job、喚醒worker或觸發provider/outbox，全部out of scope。
- `OPEN-H05`：真browser controlled session/data evidence尚未執行，不得稱entry cutover ready。
- `OPEN-H06`：publication route最多先取100筆再於Python切頁，`total`不是完整資料集；本波只顯示loaded scope。
- `OPEN-H07`：publication detail path未限制`ge=1`；client先拒絕，backend hardening仍待處理。
- `OPEN-H08`：既有 React tests仍輸出多筆 `act(...)` warning，需另案清理測試同步語意。
- `OPEN-H09`：既有 Orders page test會意外嘗試連線`localhost:3000`；雖目前 suite exit 0，仍不是可信的
  zero-network test，需由 Orders owner修正完整 mock／fail-closed fetch。
- `OPEN-H10`：production bundle超過500 kB；屬效能／載入策略議題，不在本 query-only write set。

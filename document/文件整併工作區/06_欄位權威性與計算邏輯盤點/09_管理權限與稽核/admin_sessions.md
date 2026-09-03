# `admin_sessions` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 權限功能續盤：跳過待確認；本輪不處理登入 Session、續期、撤銷與權限治理。
- 分類：`09_管理權限與稽核`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：跳過待確認（權限治理）
- 根事實展開：跳過待確認（權限治理）
- 規格反查：跳過待確認（權限治理）

- Schema：`db/schema.sql`
- Service／API：`services/admin_auth_service.py`、`api/routes/admin_auth.py`、`api/dependencies/admin_auth.py`
- 父表關係：`admin_users`
- 子表關係：無。
- live 驗證公式：Session 有效 iff token hash 命中、`revoked_at IS NULL`、`expires_at > UTC_TIMESTAMP()` 且 admin user 仍 enabled。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | Session 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 登入成功建立 Session 的事實。 | 保留作內部 row 定位；不對前端當認證憑證。 | DB／Admin Auth Service | 登入成功 | 不變 | 無。 | 已確認：SSOT 鍵 |
| `admin_user_id` | `BIGINT NOT NULL`、FK `admin_users.id`、ON DELETE CASCADE | Session 所屬管理員。 | actor 關聯事實 | 登入驗證成功後取 `admin_users.id`。 | authenticated admin row。 | 哪一個管理員取得此 Session。 | 保留；登入 transaction 內由 Server 寫入，caller 不得指定。依已確認規則管理員帳號只停用、不硬刪除。 | Admin Auth Service | 登入成功 | 建立後不變 | Schema CASCADE 與「管理員帳號不硬刪除」目標規則不一致，但本輪權限治理暫不處理。 | 已確認：保留管理員 FK |
| `session_token_hash` | `CHAR(64) NOT NULL UNIQUE` | 高熵 bearer token 的 SHA-256；原始 token 只在登入成功時回傳一次。 | 認證憑證驗證值 | `SHA256(token_urlsafe(48))`。 | Server CSPRNG 產生的 raw token。 | 持有 raw token 的 client 是否對應此 Session。 | 保留唯一 hash；DB 不保存 raw token，所有查詢只雜湊 caller bearer token 後比對。 | Admin Auth Service | 登入成功 | 建立後不變 | 若 raw token 外洩，hash 無法阻止其在到期或撤銷前被使用。 | 已確認：保留 token hash |
| `expires_at` | `DATETIME NOT NULL` | Session 到期時間；可由 refresh 延長。 | Session 時效權威欄位 | login／refresh 時為 `Server UTC now + clamp(ADMIN_SESSION_MINUTES, 5, 1440)`。 | Server UTC clock、Session policy。 | 此 Session 被允許使用到何時。 | 保留；只有 Auth Service 可建立或續期，前端不得傳入時間。驗證使用 DB UTC clock。 | Admin Auth Service | login／refresh | 可續期，revoked 後不可再改 | policy 來自環境變數，建立列沒有保存當時採用的分鐘數，但 expires_at 已保存結果。 | 跳過待確認（權限治理） |
| `last_seen_at` | `DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP` | 最近一次成功驗證或 refresh 的時間；每次受保護 API 驗證都 UPDATE。 | 使用活動投影／待確認必要性 | login 時 Server UTC now；每次 `get_admin_session` 與 refresh 更新為 UTC now。 | 成功驗證請求。 | 最近一次使用 Session 的請求時點。 | 現況未被任何 Session 判斷、API 或 UI 讀取；是否保留待權限治理時確認。 | Admin Auth Service | 每次 authenticated request／refresh | Session 存續期間持續更新 | 每次 GET 也造成 DB write；若無 idle-timeout 或管理 UI 使用，欄位沒有獨立用途。 | 跳過待確認（權限治理） |
| `revoked_at` | `DATETIME NULL` | Session 被登出或強制撤銷的時間。 | 撤銷事件事實 | revoke 時 `COALESCE(revoked_at, UTC_TIMESTAMP())`。 | logout／revoke command、DB UTC clock。 | 此 Session 是否已被明確撤銷及首次撤銷時點。 | 保留；NULL 表示未撤銷，非 NULL 即永久失效。重複 revoke 不改寫首次時間。 | Admin Auth Service | logout／強制撤銷 | 首次寫入後不變 | 目前只有當前 Session logout API，尚未看到管理員列出並撤銷其他 Session 的 UI。 | 跳過待確認（權限治理） |
| `created_at` | `DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP` | Session 建立時間。 | 技術建立時間 | DB default。 | DB INSERT。 | 登入成功建立 Session row 的時點。 | 保留並統一解讀為 UTC，不代替 admin_users.last_login_at。 | DB／Admin Auth Service | 登入成功 | 不變 | DB session timezone 必須維持 UTC 語意。 | 跳過待確認（權限治理） |

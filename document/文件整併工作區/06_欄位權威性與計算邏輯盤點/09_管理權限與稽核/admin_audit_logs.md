# `admin_audit_logs` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`09_管理權限與稽核`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成（權限與防竄改保證跳過待確認）

- Schema：`db/schema.sql`
- Writer：`api/main.py::audit_authenticated_mutations`、`services/admin_auth_service.py::record_admin_audit`
- 父表關係：`admin_users`
- 子表關係：無。
- live 邊界：記錄 FastAPI 中已取得 `admin_principal` 的 POST／PUT／PATCH／DELETE；preview 路由排除。middleware 在業務 response 產生後，以獨立 DB transaction 盡力寫入；失敗只印出 log，不回滾原操作。
- 跨表邊界：Data Browser 資料列修改另由 `audit_logs` 在同一業務 transaction 內保存 before／after hash；兩張表目前不是同一種稽核保證。
- 已確認目標規則：已驗證的管理端狀態變更，不允許出現「操作成功但沒有持久稽核紀錄」。DB 異動須與 audit／durable outbox 共享可靠 transaction 邊界；檔案或外部設定異動須先建立 durable audit intent，再執行變更並記錄結果。無法建立稽核證據時不得回報成功。
- 權限與防竄改保證：跳過待確認。目前只能確認 production code 沒有提供更新／刪除 `admin_audit_logs` 的 Service／API；本輪不裁決 DB 權限、hash chain、數位簽章或外部唯讀儲存。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 管理操作紀錄技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | audit row 建立事實。 | 保留作稽核紀錄定位鍵。 | DB／Admin Audit Service | 寫入 audit | 不變 | 無。 | 已確認：SSOT 鍵 |
| `admin_user_id` | `BIGINT NULL`、FK `admin_users.id`、現況 ON DELETE SET NULL | 執行管理 mutation 的已驗證管理員；僅明確系統／歷史 migration 事件可為 NULL。 | 操作 actor 關聯事實 | 正式人工操作為 `request.state.admin_principal.id`。 | Server 驗證的 admin principal。 | 通過 Session 驗證並實際執行命令的管理員帳號。 | 正式管理 mutation 必須有 Server principal，前端不得自填；管理員帳號只停用、不硬刪除，FK 目標語意為限制刪除，避免歷史 actor 被清空。 | Admin Auth／Audit Service | 已驗證 mutation | 寫入後不變 | 現況 ON DELETE SET NULL 允許刪除帳號後把歷史 actor ID 清空。 | 已確認：保留 actor FK，帳號只停用不硬刪除 |
| `action` | `VARCHAR(100) NOT NULL` | 管理操作的受控動作代碼。 | 操作類型事實 | 由 Server route 的稽核契約固定指定；不允許 generic fallback。 | API route metadata。 | 實際執行的管理命令。 | 正式 mutation 必須有明確 action；缺少 metadata 視為稽核契約不完整，拒絕執行或回報成功，不再使用 `api.mutation`。 | API route／Audit middleware | mutation command | 寫入後不變 | 現況 fallback 會把不同操作壓成同一代碼，無法辨識實際命令。 | 已確認：受控 action 必填，移除 generic fallback |
| `resource_type` | `VARCHAR(100) NULL` | 被操作資源的受控類型。 | 操作目標分類事實 | 由 Server route 的稽核契約固定指定。 | API route metadata。 | 實際被修改的業務資源種類。 | 每個正式 mutation 必填；整體集合操作仍須使用集合資源類型。不得由 caller 自填。 | API route／Audit middleware | mutation command | 寫入後不變 | 現況未設定時為 NULL，難以依資源查詢。 | 已確認：正式 mutation 必填受控 resource_type |
| `resource_id` | `VARCHAR(255) NULL` | 被操作單一資源的識別鍵。 | 操作目標識別事實 | 由 Server 從已驗證 path parameter 或執行結果產生。 | API route 執行結果／path parameter。 | 實際被修改資源的 ID／設定鍵。 | 單一資源操作必填；整體集合操作才可為 NULL。不得接受 request body 自報。 | API route／Audit middleware | mutation command／result | 寫入後不變 | 部分 route 未設定；多資源操作需由 resource_type 與 details 說明範圍。 | 已確認：依資源粒度由 Server 產生 |
| `request_path` | `VARCHAR(500) NULL` | 實際 API request path。 | HTTP 技術事實 | `request.url.path`。 | FastAPI Request。 | 收到管理命令的 endpoint path。 | 保留作技術追蹤；不得包含 query string、token 或其他秘密，不作業務判斷來源。 | Audit middleware | mutation request | 寫入後不變 | 路徑可能包含業務 ID，需依敏感性管理讀取權限。 | 已確認：保留技術 request path |
| `http_method` | `VARCHAR(10) NULL` | HTTP method。 | HTTP 技術事實 | `request.method`。 | FastAPI Request。 | 管理命令使用的 HTTP method。 | 保留作技術追蹤，不代替 action，也不作業務判斷來源。 | Audit middleware | mutation request | 寫入後不變 | 同一 method 可代表多種不同命令。 | 已確認：保留技術 method |
| `result_status` | `INT NULL` | API response HTTP status。 | HTTP 結果事實 | `response.status_code`。 | FastAPI Response。 | 對 caller 回傳的技術結果。 | 保留為回應事實；不得直接推定業務 transaction 是否完整提交。未完成請求也必須有對應的失敗稽核結果。 | Audit middleware／Audit Service | mutation outcome | 寫入後不變 | 現況 middleware 只在正常取得 Response 時執行；未轉成 Response 的例外可能完全沒有 audit row。 | 已確認：保留技術結果，不作業務 commit 證據 |
| `ip_address` | `VARCHAR(64) NULL` | API Server 觀測到的直接連線 peer IP。 | 網路連線技術事實 | `request.client.host`。 | ASGI server connection。 | 與 API server 建立連線的直接 peer 位址。 | 保留作網路技術資訊，不作管理員身分或授權證據；不直接信任 caller 提供的 forwarded header。只有未來建立明確 trusted-proxy 設定後，才另行解析原始 client IP。 | Audit middleware | mutation request | 寫入後不變 | Nginx／反向代理部署時通常只會記到 proxy IP。 | 已確認：保留 direct peer IP，不先加入 proxy 解析 |
| `details_json` | `JSON NULL` | Server route 建立的非敏感結構化操作摘要。 | 可選稽核內容快照 | 通過 Audit Service 敏感鍵與大小檢查後序列化；空值不寫。 | API route 的受控 audit metadata。 | 操作理由、影響數量或必要的非敏感變更摘要。 | 保留；不得保存完整 request payload。統一阻擋密碼、token、完整銀行帳號等敏感鍵並限制內容大小。 | API route／Audit Service | mutation command／outcome | 寫入後不變 | 現況無共用敏感資料檢查或大小限制，完全依賴各 route 自律。 | 已確認：保留受控非敏感摘要 |
| `created_at` | `DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP` | audit row 持久化時間。 | 技術紀錄時間 | DB UTC default。 | DB INSERT。 | durable audit row／outbox 實際建立的時點。 | 保留並統一解讀為 UTC；不等同業務 mutation 的發生或 commit 時點。 | DB／Audit Service | 建立 audit evidence | 不變 | 現況 audit 在 response 後另開 transaction，時間晚於業務操作且可能完全缺失。 | 已確認：沿用技術建立時間規則 |

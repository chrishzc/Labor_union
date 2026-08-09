# `audit_logs` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`09_管理權限與稽核`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成（`actor`、`role` 權限治理跳過待確認）
- 根事實展開：已完成（`actor`、`role` 權限治理跳過待確認）
- 規格反查：已完成（`actor`、`role` 權限治理跳過待確認）

- Schema：`db/schema_parts/99_data_browser_admin_audit_logs.sql`
- Writer：`services/data_browser_admin_schema_service.py`、`services/data_browser_admin_audit_log_service.py`
- 父表／子表關係：無實體 FK；以 `table_name + pk_value` 指向被修改資料列。
- live 邊界：只保存 Data Browser 單列 PATCH。資料列 UPDATE、after snapshot 查詢與 audit INSERT 共用同一 DB transaction；audit 失敗會回滾資料修改。
- 與 `admin_audit_logs` 的差異：本表保存資料列 before／after hash 與 changed fields；`admin_audit_logs` 記錄一般管理 API 命令。兩者目前不應互相冒充。
- 權限欄位：`actor`、`role` 的治理本輪跳過待確認。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | Data Browser PATCH audit 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | audit event 建立事實。 | 保留作 audit row 定位鍵。 | DB／Data Browser Audit Service | PATCH transaction | 不變 | 無。 | 已確認：SSOT 鍵 |
| `action` | `VARCHAR(64) NOT NULL` | 動作代碼；live writer 永遠寫 `DATA_BROWSER_PATCH`。 | 單值常數／長期考慮移除 | 常數 `DATA_BROWSER_PATCH`。 | 表格與唯一 writer 的固定用途。 | 此表每一列都代表 Data Browser PATCH。 | 不具獨立資訊，長期考慮移除；其他管理操作進入 `admin_audit_logs`，不擴張本表。 | Data Browser Audit Service（過渡期） | PATCH transaction | 不變 | 單一 writer／單一事件類型下，每列重複相同字串。 | 已確認：單值常數，長期考慮移除 |
| `table_name` | `VARCHAR(64) NOT NULL` | 被修改的白名單資料表。 | 操作目標事實 | 取通過 `ALLOWED_TABLES` 驗證的 path table。 | Data Browser PATCH command。 | 實際被 UPDATE 的資料表。 | 保留；只接受 Server 白名單通過的 canonical table name。 | Data Browser Admin Service | PATCH transaction | 不變 | 無實體 FK，但動態表名已 fail-closed 驗證。 | 已確認：保留操作目標資料表 |
| `pk_value` | `VARCHAR(255) NOT NULL` | 被修改資料列的主鍵值，統一字串化。 | 操作目標事實 | `str(row_id)`；主鍵欄位本身由 `TABLE_PRIMARY_KEYS[table_name]` 決定。 | 已驗證 path row id。 | 實際被 UPDATE 的資料列識別值。 | 保留並與 table_name 合併解讀；不得單獨當全域 ID。 | Data Browser Admin Service | PATCH transaction | 不變 | 沒有保存 pk column name，需依 table schema／TABLE_PRIMARY_KEYS 解讀。 | 已確認：保留操作目標主鍵值 |
| `changed_fields` | `JSON NOT NULL` | 本次 PATCH 實際修改的欄位及修改後新值。 | 變更命令輸入快照 | `json.dumps(validated_updates)`；不保存整列 before／after snapshot。 | 通過 editable-column 白名單並實際套用的 updates。 | 管理員要求且 DB 成功寫入的新值。 | 保留；只保存實際修改欄位及新值。密碼、token、完整銀行帳號等不得開放 Data Browser 修改，也不得進入本欄。個資讀取權限與保存期限留待權限治理。 | Data Browser Admin Service／Audit Service | PATCH transaction | 不變 | 仍會保存姓名、電話、地址等被修改的新值，需在後續權限治理限制讀取與保存。 | 已確認：保留實際變更欄位及新值 |
| `actor` | `VARCHAR(128) NOT NULL` | 執行 PATCH 的管理員 username；舊預設為 admin_ui／admin。 | 操作 actor 字串快照／權限治理跳過 | API caller 傳 `principal.username`；Service 仍提供字串預設值。 | authenticated admin principal 或舊 caller label。 | 誰執行資料列修改。 | 權限治理本輪跳過；不得把 caller 自填字串當正式身分。 | Data Browser API／Audit Service | PATCH transaction | 不變 | 無 admin user FK；Service 預設值可能產生非真實 actor。 | 跳過待確認（權限治理） |
| `role` | `VARCHAR(64) NOT NULL` | PATCH 當下的管理員角色字串快照。 | actor role 快照／權限治理跳過 | API caller 傳 `principal.role`；Service 仍預設 admin。 | authenticated admin principal 或舊 caller label。 | 操作當下 actor 的授權角色。 | 權限治理本輪跳過；只可作當時角色快照，不作後續授權來源。 | Data Browser API／Audit Service | PATCH transaction | 不變 | 無受控 enum／FK；預設 admin 不在現行 ROLE_LEVELS。 | 跳過待確認（權限治理） |
| `request_id` | `VARCHAR(128) NOT NULL` | 名稱稱 request ID，但 live route 未傳 HTTP correlation；Service 每筆 audit row 自行產生新 UUID。 | 重複事件識別／長期考慮移除 | `uuid.uuid4()`；與一筆 audit row 一對一。 | Data Browser Audit Service。 | 已由 `id` 唯一識別的同一 audit event。 | 不具獨立資訊，長期考慮移除。若未來確有單一 request 修改多列需求，再由 API 層建立真正 correlation ID。 | Data Browser Audit Service（過渡期） | PATCH transaction | 不變 | 目前不是 HTTP request ID、沒有 UNIQUE constraint，也沒有 production reader。 | 已確認：重複識別欄位，長期考慮移除 |
| `before_hash` | `CHAR(64) NOT NULL` | UPDATE 前整列 snapshot 的 SHA-256。 | 衍生完整列 fingerprint／長期考慮移除 | `SHA256(canonical_json(before_snapshot))`。 | `SELECT ... FOR UPDATE` 的原始 row。 | 修改前每一個資料欄位值。 | 不具獨立資訊，長期考慮移除；目前沒有 reader／UI 驗證連續性，也無法由 hash 還原修改前內容。若未來需要完整歷史或防竄改能力，應另行設計 before／after snapshot 或可驗證事件鏈。 | Data Browser Audit Service（過渡期） | PATCH transaction | 不變 | hash 依 Python `default=str` 的序列化結果；其他 writer 可繞過本表，且目前不會主動偵測鏈中斷。 | 已確認：衍生 fingerprint，長期考慮移除 |
| `after_hash` | `CHAR(64) NOT NULL` | UPDATE 後整列 snapshot 的 SHA-256。 | 衍生完整列 fingerprint／長期考慮移除 | `SHA256(canonical_json(after_snapshot))`。 | 同 transaction 重新 SELECT 的 row。 | 修改後每一個資料欄位值。 | 不具獨立資訊，長期考慮移除；目前沒有 reader／UI 驗證下一次 `before_hash` 是否相等，也無法由 hash 還原修改後內容。若未來需要完整歷史或防竄改能力，應另行設計 before／after snapshot 或可驗證事件鏈。 | Data Browser Audit Service（過渡期） | PATCH transaction | 不變 | 其他 writer 若繞過此 Service，連續性會中斷但不會主動告警；本欄本身不是防竄改證據。 | 已確認：衍生 fingerprint，長期考慮移除 |
| `changed_fields_hash` | `CHAR(64) NULL` | Schema 預留的 changed_fields hash；live Service 不寫入，也不讀取。 | 未使用衍生欄位／長期考慮移除 | 現況恆為 NULL。即使未來計算，也只能由 `changed_fields` 推導。 | 無 live writer。 | `changed_fields`。 | 不具獨立資訊，長期考慮移除；不得把欄位存在誤認為 production 已提供歷史還原、防竄改或完整性驗證。 | 無 live owner | 無 | 維持 NULL | Schema 暗示具備 hash，但 production 完全沒有該保證。 | 已確認：未使用衍生欄位，長期考慮移除 |
| `occurred_at` | `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | PATCH audit event 寫入時間。 | 直接技術事件時間 | Service INSERT 使用 `NOW()`；Schema default 亦可寫入。 | DB clock。 | audit INSERT 與資料 UPDATE 同 transaction 的時點。 | 保留並統一保存 UTC；由 Server／DB 自動產生，禁止 UI／caller 指定。 | DB／Data Browser Audit Service | PATCH transaction | 不變 | 現況 DB 連線未固定 session timezone，`NOW()` 不一定明確代表 UTC，屬待重整的實作漂移。 | 已確認：保留，統一 UTC 且禁止 caller 指定 |

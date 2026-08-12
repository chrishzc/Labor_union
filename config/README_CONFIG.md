# LINE／LIFF 可編輯設定規格

本目錄保存 LINE 設定的**初始 bootstrap JSON**。自重構第 5 階段起，正式執行時的唯一資料來源是 MySQL `line_configuration_revisions`；Web／UI 不應直接讀寫本目錄，也不應再把 JSON 檔當成 runtime 設定。

正式設定流程：

```text
config/*.json（只提供第一次初始化）
  → scripts/bootstrap_line_configuration.py --apply
  → MySQL 版本化設定
  → /api/v1/line/configurations/{kind}
```

初始化前可只驗證 JSON，不寫 DB：

```powershell
.venv\Scripts\python.exe scripts\bootstrap_line_configuration.py
```

Stage 5 migration 套用完成後，才可用 `--apply` 寫入目前仍缺少的 revision-0 設定；已有正式 revision 的種類不會被 JSON 覆蓋。舊 `/api/config/*` 路由仍暫時保留給尚未於階段 9 移植的管理 UI，相容期內不得作為新功能的寫入入口。

Canonical 設定 API：

```text
GET  /api/v1/line/configurations/{kind}
POST /api/v1/line/configurations/{kind}/preview
PUT  /api/v1/line/configurations/{kind}
```

`kind` 可為 `message_templates`、`message_schedules`、`rich_menus`、`liff` 或 `customer_service`。修改須帶 expected revision、idempotency key、correlation ID 與修改原因；衝突會回 409，不會靜默覆蓋。

## 設定檔

### `message_templates.json`

統一管理 Webhook 回覆、主動推播、排程推播與私人客服常用回覆。

- `id`：程式使用的穩定識別碼。
- `category`：`webhook_reply`、`push`、`scheduled_push` 或 `customer_service`。
- `message_type`：`text` 或 `flex`。
- `content`：文字或 Flex JSON。
- `variables`：可替換參數，例如 `{bind_url}`。
- `usage`：允許使用此範本的功能。

API：

```text
GET    /api/config/message-templates
PUT    /api/config/message-templates
POST   /api/config/message-templates
GET    /api/config/message-templates/{template_id}
PUT    /api/config/message-templates/{template_id}
DELETE /api/config/message-templates/{template_id}
POST   /api/config/message-templates/{template_id}/preview
```

### `line_menu.json`

管理多組 Rich Menu 的尺寸、顏色、按鈕區域及 LINE Action。

- `audience_role`：明確對應 `customer`、`staff` 或 `union_staff`。
- `appearance.image_mode`：`generated` 使用設定產圖；`uploaded` 使用受控媒體資產。
- `appearance.image_asset_id`：上傳圖片對應的 MySQL `media_assets.id`。

Action 支援：

- `message`：點擊後向官方帳號傳文字。
- `uri`：開啟固定 URL。
- `uri`＋`uri_source: liff`：開啟目前設定的 LIFF。
- `postback`：傳送 postback data。

API：

```text
GET    /api/config/line-menus
GET    /api/config/line-menus/state
PUT    /api/config/line-menus
POST   /api/config/line-menus
GET    /api/config/line-menus/{menu_id}
PUT    /api/config/line-menus/{menu_id}
DELETE /api/config/line-menus/{menu_id}
POST   /api/config/line-menus/{menu_id}/preview
POST   /api/config/line-menus/{menu_id}/publish
POST   /api/v1/line/rich-menus/preview
POST   /api/v1/line/rich-menus/{menu_id}/images
GET    /api/v1/line/rich-menus/publications
GET    /api/v1/line/rich-menus/publications/{publication_id}
POST   /api/v1/line/rich-menus/publications/{publication_id}/retry
```

儲存與發布分開。修改 JSON 不會立即更動 LINE；發布接口會建立持久化工作並喚醒 Worker，
一次只發布指定 Menu。設定更新須帶 `If-Match` revision，舊畫面會收到 409。

圖片上傳會檢查實際 JPEG／PNG 格式、尺寸與檔案大小，再重新編碼為 JPEG。圖片本體位於
`MEDIA_STORAGE_ROOT`（正式環境建議 NAS 或受控磁碟），MySQL `media_assets` 保存路徑、
MIME、大小、尺寸與 SHA-256；不將圖片 BLOB 存入 MySQL，也不提交 Git。

### `liff_settings.json`

管理 LIFF 共用主題、入口選擇頁、舊客戶綁定頁、新客戶登記頁及動態問題。

- `gateway` 使用 `actions` 管理入口卡片文字、圖示與相對路徑／HTTPS 連結。
- `bind` 與 `registration` 使用 `fields` 管理表單欄位。
- `system_field: true` 是後端必要欄位，API 禁止刪除、停用或改變必要型別。
- 自訂問題使用 `system_field: false`，可由前端新增、修改、排序與刪除。
- 選擇題必須提供 `options`。
- 自訂答案保存至既有 `beclass_records.survey_details` JSON，不必每次修改 DB schema。
- `liff_settings_history.json` 最多保存 20 個修改前快照，供管理介面人工還原。
- Runtime API 只輸出啟用中的頁面、欄位與入口，並以 ETag／revision 防止載入舊設定。

API：

```text
GET    /api/config/liff
GET    /api/config/liff/runtime?page={page_id}
GET    /api/config/liff/state
POST   /api/config/liff/validate
GET    /api/config/liff/history
POST   /api/config/liff/rollback/{revision}
PUT    /api/config/liff
PUT    /api/config/liff/theme
PUT    /api/config/liff/pages/{page_id}
POST   /api/config/liff/pages/{page_id}/fields
PUT    /api/config/liff/pages/{page_id}/fields/{field_id}
DELETE /api/config/liff/pages/{page_id}/fields/{field_id}
```

除公開讀取與 Runtime API 外，管理接口均需管理員權限及內部服務金鑰。修改與還原必須帶
`If-Match` revision；其他管理員先儲存時會回 409，不會靜默覆蓋。

### `customer_service.json`

目前只保存私人客服的靜態設定：服務時間、狀態顯示、閒置時間及固定回覆。聊天訊息、客服指派、已讀狀態與標籤不應存 JSON，後續應存 MySQL。

API：

```text
GET /api/config/customer-service
PUT /api/config/customer-service
```

## 訊息管理中心（5.2）

前端讀取訊息範本與內容 revision：

```text
GET /api/config/message-templates/state
```

新增、修改、刪除時會把 revision 放入 `If-Match` Header。內容已被其他人更新時回傳 409，
前端必須重新載入。草稿預覽使用：

```text
POST /api/config/message-templates/preview
```

啟用中的 `message_schedules.json` 若仍引用某個範本，該範本不可停用或刪除。JSON 寫入採
同程序鎖與原子檔案替換；目前正式架構為單一 FastAPI 程序，未來多程序時應改用集中式
設定儲存或分散式鎖。

### `message_schedules.json`

管理新好友 D+1、D+2、D+3 等排程。排程只引用 `message_templates.json` 中已啟用的範本 ID，顯示時區預設為 `Asia/Taipei`。

```text
GET /api/config/message-schedules
GET /api/config/message-schedules/state
PUT /api/config/message-schedules
```

`state` 會同時回傳設定與 SHA-256 revision；管理前端更新時以 `If-Match` 帶回 revision，
若設定已被其他人更新會回傳 409，避免覆蓋新版。後端會檢查 IANA 時區、時間格式、
重複天數及啟用中的範本是否存在；儲存排程不會立即補發或修改歷史任務，只影響之後建立的任務。

`restart_on_refollow=true` 表示使用者解除封鎖或重新加入時，取消既有尚未發送的 onboarding
任務並依當次 follow 事件重新建立；設為 `false` 時沿用首次建立的穩定冪等規則。

### `rich_menu_ids.json`

由 Rich Menu 發布器寫入的 LINE 平台 ID，不是前端可編輯設定。

重新綁定待審資料不再存放於 `config`。月嫂驗證與客戶重新綁定均保存在 MySQL `line_confirmation_requests`，`config` 目錄只保存可由管理介面維護的靜態設定。

## 圖片與附件儲存

重構 Schema 已建立 `line_media_objects` 保存 LINE 媒體中繼資料，並以 `line_domain_outbox` 可靠排程下載；Rich Menu 發布則以內容雜湊保存產生圖片。圖片本體位於 `MEDIA_STORAGE_ROOT` 指向的 filesystem 或 NAS，DB 不保存大型 BLOB。

若後續要讓非 LINE 功能共用媒體，可另由 Media domain 建立跨功能 `media_assets`，建議欄位如下：

```text
id
category            rich_menu / line_user_upload / contract / other
owner_type          line_user / menu / case / message
owner_id
storage_provider    local / nas / s3
storage_key
original_filename
mime_type
file_size
sha256
line_message_id
created_at
expires_at
deleted_at
```

不建議將圖片二進位直接存 MySQL BLOB。建議優先順序：

1. 正式地端環境：NAS 或受控專用媒體目錄，DB 只保存 storage key 與中繼資料。
2. 未來雲端環境：S3 相容物件儲存，例如 Cloudflare R2、AWS S3 或 MinIO。
3. 開發環境：專案外的 writable media 目錄，避免把用戶照片提交 Git。

LINE 用戶照片應在 Webhook 收到 message ID 後下載至受控儲存區，再建立 `media_assets` 紀錄；不要長期依賴 LINE 暫時下載網址。

## 安全注意事項

- 第五階段 5.1 已加入資料庫管理員登入、短時效 Session、角色權限與操作稽核。
- `/api/config` 的管理讀取至少需要 `line_viewer`；新增、修改、刪除與發布需要 `line_manager`。
- 公開 LIFF 頁使用 `GET /api/config/liff/runtime`；`GET /api/config/liff` 維持舊版相容，其餘 LIFF 管理接口受保護。
- 正式環境由 LIFF 傳送 ID Token，FastAPI 使用 `LINE_LOGIN_CHANNEL_ID` 向 LINE 驗證後才採用 token 中的使用者 ID；不信任瀏覽器自行提交的 `line_user_id`。
- API 只操作固定白名單檔案，不能由前端傳入任意檔案路徑。
- Rich Menu 發布會呼叫 LINE API，應限制為管理員操作。
- 月嫂驗證查詢及角色管理底層接口仍需使用 `X-Legacy-Shared-Key`；Web/UI 經由後端 Client 呼叫，不把金鑰交給瀏覽器。

相關環境變數：

```env
LEGACY_SHARED_KEY=<固定長隨機值>
API_BASE_URL=http://127.0.0.1:8000
ADMIN_SESSION_MINUTES=30
ENABLE_ADMIN_AUTH=true
ALLOWED_ORIGINS=http://localhost:8501,http://127.0.0.1:8501
MEDIA_STORAGE_ROOT=.local_media
MEDIA_STORAGE_PROVIDER=local
LINE_LOGIN_CHANNEL_ID=<LIFF 所屬的 LINE Login Channel ID>
LIFF_REQUIRE_ID_TOKEN=true
LINE_REVIEW_STALE_HOURS=24
```

`ENABLE_ADMIN_AUTH=false` 僅能在 `APP_ENV=development/dev/local/test` 略過帳號登入；正式環境
即使誤設為 `false` 仍會強制驗證。略過登入不會關閉 `X-Legacy-Shared-Key`。

## 工會工作人員統一待審接口

月嫂資格驗證與舊客戶重新綁定可由同一個工作人員佇列取得：

```text
GET  /api/line/staff/review-requests
GET  /api/line/staff/review-requests?request_type=client_rebind
GET  /api/line/staff/review-requests?request_type=staff_verification
POST /api/line/staff/review-requests/{request_type}/{request_id}/approve
POST /api/line/staff/review-requests/{request_type}/{request_id}/reject
```

以上接口一律要求：

```http
X-Legacy-Shared-Key: <LEGACY_SHARED_KEY>
```

`client_rebind` 的 approve 會更新客戶 LINE 綁定，reject 會保留原綁定並通知申請者。`staff_verification` 的 approve 會直接將 LINE 角色切換為 `staff` 並綁定月嫂選單，reject 則保留原角色並通知申請者。兩種請求共用 MySQL `line_confirmation_requests`，不產生月嫂驗證碼。

舊版 `/api/line/rebind_requests`、`approve`、`reject` 接口暫時保留相容性，但現在同樣要求內部 API Key。

開發環境可設定：

```env
ENABLE_REBIND_CONSOLE_REVIEW=true
```

開發時，Webhook提交月嫂身分或重新綁定申請後，會向專案根目錄`start_fastapi_ngrok.py`在`127.0.0.1`建立的臨時入口推送一次通知，終端隨即接受`y`核准、`n`拒絕，不會固定輪詢待審API。啟動器只在啟動時補查一次既有待審資料。此功能由`ENABLE_LINE_REVIEW_CONSOLE`控制，正式環境`APP_ENV=production`時強制停用。

正式 Web/UI 使用具管理員 Session 與角色權限的新接口：

```text
GET  /api/v1/line/review-requests/summary
GET  /api/v1/line/review-requests
GET  /api/v1/line/review-requests/{request_id}
POST /api/v1/line/review-requests/{request_id}/approve
POST /api/v1/line/review-requests/{request_id}/reject
```

清單與詳細資料至少需要 `line_agent`；核准／拒絕需要 `line_manager`。兩組接口最後都呼叫 `services/line_review_service.py`，因此交易鎖、資料衝突檢查、LINE 任務與狀態結果一致。`LINE_REVIEW_STALE_HOURS` 只控制管理頁逾時提醒門檻，不會自動拒絕或核准申請。

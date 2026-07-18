# LINE／LIFF 可編輯設定規格

本目錄保存可由 Web 或 UI 管理端透過 FastAPI 修改的靜態設定。前端不應直接讀寫檔案，而應串接 `/api/config` API；後端會使用 Pydantic 驗證並以原子替換方式寫入 JSON。

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

Action 支援：

- `message`：點擊後向官方帳號傳文字。
- `uri`：開啟固定 URL。
- `uri`＋`uri_source: liff`：開啟目前設定的 LIFF。
- `postback`：傳送 postback data。

API：

```text
GET    /api/config/line-menus
PUT    /api/config/line-menus
POST   /api/config/line-menus
GET    /api/config/line-menus/{menu_id}
PUT    /api/config/line-menus/{menu_id}
DELETE /api/config/line-menus/{menu_id}
POST   /api/config/line-menus/{menu_id}/preview
POST   /api/config/line-menus/{menu_id}/publish
```

儲存與發布分開。修改 JSON 不會立即更動 LINE；呼叫 `publish` 才會執行 `line/setup_rich_menus.py`。

圖片上傳 API 暫未建立。JSON 的 `appearance.image_path` 只保存圖片位置。

### `liff_settings.json`

管理 LIFF 主題、頁面文字及動態問題。

- `system_field: true` 是後端必要欄位，API 禁止刪除。
- 自訂問題使用 `system_field: false`，可由前端新增、修改、排序與刪除。
- 選擇題必須提供 `options`。
- 自訂答案後續可保存至既有 `survey_details` JSON，不必每次修改 DB schema。

API：

```text
GET    /api/config/liff
PUT    /api/config/liff
PUT    /api/config/liff/theme
PUT    /api/config/liff/pages/{page_id}
POST   /api/config/liff/pages/{page_id}/fields
PUT    /api/config/liff/pages/{page_id}/fields/{field_id}
DELETE /api/config/liff/pages/{page_id}/fields/{field_id}
```

### `customer_service.json`

目前只保存私人客服的靜態設定：服務時間、狀態顯示、閒置時間及固定回覆。聊天訊息、客服指派、已讀狀態與標籤不應存 JSON，後續應存 MySQL。

API：

```text
GET /api/config/customer-service
PUT /api/config/customer-service
```

### `message_schedules.json`

管理新好友 D+1、D+2、D+3 等排程。排程只引用 `message_templates.json` 中已啟用的範本 ID，顯示時區預設為 `Asia/Taipei`。

```text
GET /api/config/message-schedules
PUT /api/config/message-schedules
```

後端會檢查時間格式、重複天數及範本是否存在；儲存排程不會立即補發歷史任務，只影響之後建立的任務。

### `rich_menu_ids.json`

由 Rich Menu 發布器寫入的 LINE 平台 ID，不是前端可編輯設定。

重新綁定待審資料不再存放於 `config`。月嫂驗證與客戶重新綁定均保存在 MySQL `line_confirmation_requests`，`config` 目錄只保存可由管理介面維護的靜態設定。

## 圖片與附件儲存建議（後續工作）

目前 `db/schema.sql` 沒有圖片、附件或媒體資料表。本次不修改 DB。

後續建議建立共用 `media_assets` 表，Rich Menu 圖片與 LINE 用戶照片共用，以欄位分類：

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

1. 正式環境：S3 相容物件儲存，例如 Cloudflare R2、AWS S3 或 MinIO。
2. 地端環境：NAS 或專用媒體目錄，DB 只保存路徑與中繼資料。
3. 開發環境：專案外的 writable media 目錄，避免把用戶照片提交 Git。

LINE 用戶照片應在 Webhook 收到 message ID 後下載至受控儲存區，再建立 `media_assets` 紀錄；不要長期依賴 LINE 暫時下載網址。

## 安全注意事項

- 目前設定 API 尚未加入管理員登入；正式開放給前端前必須加上權限保護。
- API 只操作固定白名單檔案，不能由前端傳入任意檔案路徑。
- Rich Menu 發布會呼叫 LINE API，應限制為管理員操作。
- 月嫂驗證查詢及角色管理接口需使用 `X-Internal-API-Key`；正式前應再接管理員登入與角色權限。

## 工會工作人員統一待審接口

月嫂資格驗證與舊客戶重新綁定可由同一個工作人員佇列取得：

```text
GET  /api/line/staff/review-requests
GET  /api/line/staff/review-requests?request_type=client_rebind
GET  /api/line/staff/review-requests?request_type=caregiver_verification
POST /api/line/staff/review-requests/{request_type}/{request_id}/approve
POST /api/line/staff/review-requests/{request_type}/{request_id}/reject
```

以上接口一律要求：

```http
X-Internal-API-Key: <INTERNAL_API_KEY>
```

`client_rebind` 的 approve 會更新客戶 LINE 綁定，reject 會保留原綁定並通知申請者。`caregiver_verification` 在申請時即產生六位數驗證碼；approve 會向工作人員回傳既有驗證碼，仍需由月嫂本人在 LINE 輸入，reject 則取消驗證碼並通知申請者。兩種請求共用 MySQL `line_confirmation_requests`。

舊版 `/api/line/rebind_requests`、`approve`、`reject` 接口暫時保留相容性，但現在同樣要求內部 API Key。

開發環境可設定：

```env
ENABLE_REBIND_CONSOLE_REVIEW=true
```

`start_line_bot.py` 會透過統一待審 API 取得重新綁定申請，並在終端接受 `y` 核准、`n` 拒絕。正式環境 `APP_ENV=production` 時此功能強制停用。

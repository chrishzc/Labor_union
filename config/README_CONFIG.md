# LINE／LIFF 設定

`config/` 只保存初始 bootstrap JSON 與 repository-owned defaults。正式 runtime 設定的權威來源是 MySQL 的版本化 LINE configuration；React 管理端與 worker 都不得直接把本目錄當成 current state。

## Data flow

```text
config/*.json
  → scripts/bootstrap_line_configuration.py --apply
  → MySQL versioned configuration
  → typed FastAPI Query／Preview／Apply
  → React 管理端或 LINE worker
```

只驗證 bootstrap JSON，不寫入資料庫：

```powershell
.\.venv\Scripts\python.exe scripts\bootstrap_line_configuration.py
```

只有目標資料庫缺少初始 revision 時才使用 `--apply`。既有正式 revision 不得被 repository JSON 靜默覆蓋。

## Bootstrap files

- `message_templates.json`：訊息範本初始值。
- `message_schedules.json`：排程推播初始值。
- `line_menu.json`：Rich Menu 定義初始值。
- `liff_settings.json`：LIFF 頁面、欄位與主題初始值。
- `customer_service.json`：客服靜態設定初始值。
- `rich_menu_ids.json`：平台 publication identity 的相容資料；不是人工編輯的正式設定。

## Canonical configuration API

```text
GET  /api/v1/line/configurations/{kind}
POST /api/v1/line/configurations/{kind}/preview
PUT  /api/v1/line/configurations/{kind}
```

`kind` 為 `message_templates`、`message_schedules`、`rich_menus`、`liff` 或 `customer_service`。

Mutation 必須帶 current revision、idempotency identity、correlation identity 與原因。Revision 不一致時回傳 typed conflict，不得 last-write-wins。

## Rich Menu and media

Rich Menu 儲存與發布是不同操作。設定 mutation 只更新 versioned configuration；發布由 typed Preview／Apply 建立 durable task，再由 LINE worker 執行外部效果。

圖片本體放在 `MEDIA_STORAGE_ROOT` 指向的受控 filesystem／NAS；MySQL 只保存 storage identity、MIME、尺寸、大小與 digest。不得把使用者媒體或 provider credential 提交到 Git。

## LIFF

公開 LIFF runtime 只讀取啟用中的 current revision。系統必要欄位不能由 UI 刪除、停用或改變必要型別；自訂欄位則依 typed schema 驗證。

瀏覽器提交的 LINE user identity 不具權威性。正式環境必須驗證由 LINE Login channel 簽發的 ID token，再使用已驗證 subject。

## React administration

Current 管理端只有 `ui_react/`。設定畫面透過 typed API client 讀寫 FastAPI；不存在 Streamlit 管理頁、`ui/app.py`、8501 origin 或 console-based UI rollback。

本機允許來源預設為：

```env
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

正式環境須改為實際 HTTPS 管理端 origin。

## Security boundary

- Secret、channel token、cookie 與 private key 不得寫入本目錄。
- 管理 Query 與 mutation 必須經 current admin session 驗證。
- Provider publication 是外部副作用，必須由明確 Apply 與 durable worker 執行。
- API 僅操作已定義的 configuration kind 與受控 media identity，不接受任意 filesystem path。
- Production 不接受本機 shared-key 或 auth bypass。

## Current environment variables

```env
LINE_CHANNEL_ID=
LINE_CHANNEL_SECRET=
LINE_CHANNEL_ACCESS_TOKEN=
LINE_LOGIN_CHANNEL_ID=
LINE_LIFF_ID=
LINE_PUBLIC_BASE_URL=
MEDIA_STORAGE_ROOT=.local_media
MEDIA_STORAGE_PROVIDER=local
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

其他 current runtime 設定以 `.env.example` 與正式 LINE／Access 規格為準。

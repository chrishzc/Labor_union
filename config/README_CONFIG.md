# 系統外部設定檔 (JSON Config) 使用說明

本資料夾 (`config/`) 包含了系統中可以讓管理員直接修改的外部設定檔。這些檔案採用 JSON 格式，您可以使用任何純文字編輯器（如記事本、VS Code）打開並修改。
**修改存檔後，大部分設定將會即時生效，不需重啟伺服器。**

---

## 1. 🎨 前端網頁外觀設定 (`liff_settings.json`)
此檔案控制了使用者開啟「產婦服務登記表單 (LIFF)」時的網頁外觀與文字。

### 📡 管理 API 接口
前端管理後台可透過以下 API 進行設定存取與修改：
- **GET** `/api/config/liff`：取得目前網頁外觀設定
- **PUT** `/api/config/liff`：傳送 JSON 結構儲存並覆寫外觀設定

### 重要參數說明：
- **`theme_colors.primary`**: 主要按鈕與強調元素的顏色。
- **`theme_colors.background_gradient`**: 網頁背景的漸層顏色。
- **`typography.title_size`**: 網頁大標題的文字大小 (預設 `20px`)。
- **`texts.form_title`**: 網頁最上方的大標題。
- **`texts.success_desc`**: 使用者成功送出表單後，畫面上顯示的提示文字（支援 `<br>` 換行標籤）。

### 常用的顏色代碼 (Hex Color) 參考：
| 顏色風格 | Primary (主色) | Background Gradient (背景漸層) |
| :--- | :--- | :--- |
| **經典工會藍 (預設)** | `#4a90e2` | `linear-gradient(135deg, #eef2f7 0%, #d9e2ec 100%)` |
| **溫暖櫻花粉** | `#ff85a2` | `linear-gradient(135deg, #fff0f3 0%, #ffe4e8 100%)` |
| **質感薄荷綠** | `#42b883` | `linear-gradient(135deg, #e8f7f0 0%, #d1efe1 100%)` |
| **沉穩曜石黑** | `#333333` | `linear-gradient(135deg, #f5f5f5 0%, #e0e0e0 100%)` |

> 💡 **提示**：若想尋找其他顏色代碼，可以至 Google 搜尋「Color Picker」，挑選喜歡的顏色後複製其 HEX 碼 (包含 `#` 號) 貼上即可。

---

## 2. 📱 LINE 圖文選單設定 (`line_menu.json`)
此檔案控制了 LINE 官方帳號下方的「圖文選單 (Rich Menu)」按鈕文字與底圖顏色。包含 `default_menu` (一般用戶) 與 `caregiver_menu` (月嫂專區) 兩個區塊。

### 📡 管理 API 接口與自動更新
前端管理後台可透過以下 API 進行設定存取與修改：
- **GET** `/api/config/line_menu`：取得目前圖文選單設定
- **PUT** `/api/config/line_menu`：傳送 JSON 結構儲存並覆寫圖文選單設定。
  > ⚡ **自動化生效機制**：當呼叫 PUT API 儲存成功後，系統將會在背景自動觸發執行 `setup_rich_menus.py` 腳本。LINE 官方帳號的選單會在幾秒內自動更新，不需工程師介入！

### 重要參數說明：
- **`background_color`**: 選單的背景底色。
- **`buttons[].text`**: 顯示在圖片按鈕上的文字。
- **`buttons[].color`**: 按鈕文字的顏色。

> ⚠️ **注意**：如果您是手動在伺服器上修改此檔案 (沒有透過 API)，修改後請務必請工程師或管理員執行以下指令，選單才會更新：
> ```bash
> uv run python scripts/setup_rich_menus.py
> ```

---

## 3. 💬 機器人自動回覆文案 (`webhook_replies.json`)
此檔案管理了當用戶在 LINE 中觸發特定行為時，機器人主動推播的文字訊息。

### 📡 管理 API 接口
前端管理後台可透過以下 API 進行設定存取與修改：
- **GET** `/api/config/webhook_replies`：取得目前自動回覆設定
- **PUT** `/api/config/webhook_replies`：傳送 JSON 結構儲存並覆寫自動回覆設定

### 重要參數說明：
- **`caregiver_switch_success`**: 當月嫂輸入「我是月嫂」且切換成功時的回覆。
- **`esc_success`**: 當輸入「esc」退回一般用戶時的回覆。
- **`bind_link_msg`**: 當用戶輸入「查詢訂單」時，彈出的綁定連結引導文案。
- **`register_success`**: 新用戶填完表單後，系統在 LINE 中回傳案件編號的恭喜訊息。

### 特殊變數替換 (請勿刪除)：
在此檔案中，您會看到一些用大括號 `{}` 包起來的英文字，這是系統自動帶入資料的「變數」，修改文案時**請保留它們**：
- `{bind_url}`：系統會自動替換成用戶專屬的 LIFF 綁定網址。
- `{name}`：系統會自動替換成客戶或月嫂的真實姓名。
- `{case_no}`：系統會自動替換成 `clients.case_no` 案件編號。
- `{status_code}`：系統會自動替換成錯誤代碼。

### 如何換行？
在 JSON 檔案中，請使用 `\n` 來代表換行。
例如：`"第一行\n第二行"`，在 LINE 裡面就會呈現為：
```
第一行
第二行
```

---

## 4. 🗂️ 重新綁定申請暫存檔 (`rebind_requests.json`)
此檔案用於暫存使用者「要求重新綁定 LINE 帳號」的申請。當舊客戶的資料已經被另一個 LINE 帳號綁定時，他們可以在前端申請重新綁定，申請記錄會暫存於此。

### ⚠️ 前端工程師注意事項：
**請勿直接讀寫此檔案**。由於可能發生併發衝突，請務必使用後端提供的 API 來存取與操作申請紀錄：

1. **取得所有待確認名單**
   - **Method**: `GET`
   - **Endpoint**: `/api/line/rebind_requests`
   - **Response**: 回傳 JSON 陣列，包含 `request_id`, `client_name`, `old_line_user_id`, `new_line_user_id` 等資訊。

2. **管理員核准申請**
   - **Method**: `POST`
   - **Endpoint**: `/api/line/rebind_requests/approve`
   - **Payload**: `{"request_id": "req_..."}`
   - **Action**: 後端會自動寫入資料庫覆蓋、從 JSON 刪除暫存，並推播成功訊息給客戶。

3. **管理員拒絕申請**
   - **Method**: `POST`
   - **Endpoint**: `/api/line/rebind_requests/reject`
   - **Payload**: `{"request_id": "req_..."}`
   - **Action**: 後端會從 JSON 刪除該暫存，並推播拒絕訊息給客戶。

---
### 🚨 編輯 JSON 的注意事項
1. 所有的文字與參數都必須被**雙引號 `"`** 包起來。
2. 每一行結尾必須有**逗號 `,`** (除了該區塊的最後一行)。
3. 如果修改後系統發生異常，請檢查是否不小心刪除了雙引號或逗號，可使用線上工具 (如 JSONLint) 檢查格式是否正確。

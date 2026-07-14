# API 與外部系統整合規格書

本規格書基於 [[自動化系統設計規格書(總覽)]]、[[設計規格書 (LINE)]] 與 [[設計規格書(Streamlit UI)]]，定義地端後端 (FastAPI) 與管理端 UI (Streamlit) 之間、以及與外部第三方平台（LINE Platform、BeClass、好好簽 Breezysign）之介面對接標準與 API 詳細 Payload 格式。

---

## 1. 安全防護與身份驗證規範

為了確保地端私有資料與外部 API 對接的安全性，系統採行以下驗證機制：

### 1.1 內部 API 驗證 (FastAPI <--> Streamlit UI)
* **機制**：所有內部管理端 API 皆須在 HTTP Header 中攜帶安全金鑰。
* **Header 格式**：`X-API-Key: ${ADMIN_API_TOKEN}`。
* **安全性**：`ADMIN_API_TOKEN` 由地端 `.env` 檔案配置，未帶金鑰或金鑰錯誤時，API 拒絕連線並回傳 `HTTP 401 Unauthorized`。

### 1.2 LINE Webhook 簽章驗證 (FastAPI <--> LINE Platform)
* **機制**：FastAPI Webhook 服務必須驗證請求是否真正來自 LINE 官方伺服器。
* **驗證步驟**：
  1. 取得 Request Header 中的 `x-line-signature`。
  2. 使用地端儲存的 `LINE_CHANNEL_SECRET` 對整個 Request Body（Raw Bytes）進行 HMAC-SHA256 運算。
  3. 將計算出的 Signature 進行 Base64 編碼，比對是否與 `x-line-signature` 一致。不一致時回傳 `HTTP 400 Bad Request`。

### 1.3 外部 Webhook 存取權限 (FastAPI <--> BeClass / 好好簽)
* **機制**：第三方平台發送 Webhook 到地端時，需在 Path 中攜帶動態產生的 UUID Token 或是驗證 Header，以防止惡意探針與重放攻擊。
* **端點範例**：`/api/v1/webhooks/beclass?token=${BECLASS_WEBHOOK_TOKEN}`。

---

## 2. 內部 RESTful API 規格 (FastAPI 與 Streamlit 溝通)

內部 API 預設基礎 URL：`https://localhost:8000/api/v1` (Nginx 本地轉發)。

### 2.1 儀表板與異常資料隔離 (Dashboard & Anomalies)

#### (1) 取得未處理異常資料列表
* **端點與方法**：`GET /anomalies`
* **Request Headers**：`X-API-Key: ******`
* **Response (200 OK)**：
  ```json
  {
    "status": "success",
    "count": 2,
    "data": [
      {
        "id": 1,
        "case_no": "115000001",
        "source_platform": "beclass",
        "anomaly_type": "PHONE_FORMAT_ERROR",
        "invalid_data": { "phone": "0912-34" },
        "created_at": "2026-06-29 15:00:00"
      }
    ]
  }
  ```

#### (2) 取得特定異常資料的原始 JSON
* **端點與方法**：`GET /anomalies/{id}`
* **Response (200 OK)**：
  ```json
  {
    "status": "success",
    "data": {
      "id": 1,
      "raw_payload": {
        "項次": 1,
        "查詢序號": 28755000,
        "查詢序號(案件編號)": "115000001",
        "姓名": "陳小姐",
        "行動電話": "0912-34",
        "地址": "新竹市東區和平街"
      }
    }
  }
  ```

#### (3) 手動修正異常資料並存入客戶表
* **端點與方法**：`POST /anomalies/{id}/resolve`
* **Request Body**：
  ```json
  {
    "corrected_fields": {
      "phone": "0912345678"
    }
  }
  ```
* **Response (200 OK)**：
  ```json
  {
    "status": "success",
    "message": "Anomaly resolved. Data written to clients table."
  }
  ```

#### (4) 忽略特定異常事件
* **端點與方法**：`POST /anomalies/{id}/ignore`
* **Response (200 OK)**：
  ```json
  {
    "status": "success",
    "message": "Anomaly status set to ignored."
  }
  ```

---

### 2.2 客戶與訂單管理 (Clients & Orders)

#### (1) 查詢訂單列表
* **端點與方法**：`GET /orders`
* **Query Parameters**：`status=洽談中` (可選)
* **Response (200 OK)**：
  ```json
  {
    "status": "success",
    "data": [
      {
        "id": 12,
        "case_no": "113000012",
        "name": "林小姐",
        "phone": "0988123456",
        "project_status": "洽談中",
        "due_month": "113/10/30",
        "service_days": 24
      }
    ]
  }
  ```

#### (2) 更新訂單狀態 (特別包含取消功能)
* **端點與方法**：`POST /orders/{id}/status`
* **Request Body**：
  ```json
  {
    "project_status": "訂單取消",
    "cancel_reason": "客戶因家庭因素決定自行照顧"
  }
  ```
* **Response (200 OK)**：
  ```json
  {
    "status": "success",
    "message": "Order status updated to 訂單取消."
  }
  ```

---

### 2.3 月嫂行事曆與排班管理 (Staff Schedules)

#### (1) 取得特定月嫂之排班日程時間軸
* **端點與方法**：`GET /caregivers/{caregiver_id}/schedule`
* **Response (200 OK)**：
  ```json
  {
    "status": "success",
    "caregiver_id": 5,
    "name": "陳大姐",
    "weekly_rest_days": ["Sunday"],
    "schedules": [
      {
        "id": 101,
        "type": "booking",
        "client_name": "林小姐",
        "start_date": "2026-08-10",
        "end_date": "2026-09-05",
        "status": "confirmed"
      },
      {
        "id": 102,
        "type": "buffer",
        "client_name": "林小姐 (緩衝期)",
        "start_date": "2026-09-06",
        "end_date": "2026-09-12",
        "status": "soft_hold"
      },
      {
        "id": 103,
        "type": "leave",
        "reason": "請假出國",
        "start_date": "2026-09-15",
        "end_date": "2026-09-20",
        "status": "approved"
      }
    ]
  }
  ```

#### (2) 新增月嫂排班日程 (請假/手動預排)
* **端點與方法**：`POST /caregivers/{caregiver_id}/schedule`
* **Request Body**：
  ```json
  {
    "schedule_type": "leave",
    "start_date": "2026-09-15",
    "end_date": "2026-09-20",
    "reason": "請假出國",
    "ignore_warnings": false
  }
  ```
* **Response (200 OK / 409 Conflict)**：
  * *成功寫入*：`200 OK`，回傳成功。
  * *衝突阻擋 (Hard Block)*：`409 Conflict` (如與實派案件或固定休假重疊)：
    ```json
    {
      "status": "error",
      "error_code": "SCHEDULE_CONFLICT_HARD",
      "message": "此請假期間與 8/18-8/25 的林小姐實派案重疊，禁止排班。"
    }
    ```
  * *衝突警告 (Soft Warning)*：`409 Conflict` (與預排或緩衝期重疊)：
    ```json
    {
      "status": "warning",
      "error_code": "SCHEDULE_CONFLICT_SOFT",
      "message": "此請假期間與王小姐預排案的7天緩衝期重疊。是否忽略警告強行排班？"
    }
    ```

---

### 2.4 雙向確認媒合流程 (Smart Matching)

#### (1) 篩選合格月嫂列表
* **端點與方法**：`POST /matching/search-caregivers`
* **Request Body**：
  ```json
  {
    "case_no": "115000001",
    "filter_no_conflict": true,
    "filter_region": true,
    "filter_special_skills": ["大寶餐專長"]
  }
  ```
* **Response (200 OK)**：
  ```json
  {
    "status": "success",
    "candidates": [
      {
        "caregiver_id": 5,
        "name": "陳大姐",
        "phone": "0922111333",
        "regions": ["竹北市", "東區"],
        "skills": ["葷食", "大寶餐專長"],
        "rating": 9.5
      }
    ]
  }
  ```

#### (2) 一鍵傳送「接案意願詢問」至月嫂 LINE
* **端點與方法**：`POST /matching/ask-intent`
* **Request Body**：
  ```json
  {
    "case_no": "115000001",
    "caregiver_id": 5,
    "custom_notes": "週六需要配合加班半天"
  }
  ```
* **Response (200 OK)**：
  ```json
  {
    "status": "success",
    "message": "LINE message queued to caregiver. matching_record entry created with pending status."
  }
  ```

#### (3) 一鍵傳送「月嫂履歷卡片」至客戶 LINE
* **端點與方法**：`POST /matching/send-resume`
* **Request Body**：
  ```json
  {
    "case_no": "115000001",
    "caregiver_id": 5
  }
  ```
* **Response (200 OK)**：
  ```json
  {
    "status": "success",
    "message": "Resume card sent to client via LINE."
  }
  ```

#### (4) 一鍵傳送「電子合約簽署卡片」至雙方 LINE (好好簽 Breezysign 整合)
* **端點與方法**：`POST /matching/send-contract`
* **Request Body**：
  ```json
  {
    "case_no": "115000001",
    "caregiver_id": 5,
    "contract_details": {
      "start_date": "2026-08-10",
      "end_date": "2026-09-05",
      "daily_rate": 2000,
      "split_days": null,
      "custom_clauses": "透天服務需每日加收100元樓層費"
    }
  }
  ```
* **Response (200 OK)**：
  ```json
  {
    "status": "success",
    "breezysign_contract_id": "BS_CON_998273",
    "message": "E-Contract created in Breezysign. Signature cards sent to Client and Caregiver via LINE."
  }
  ```

---

## 3. LINE Webhook 與 Messaging API 對接規格

FastAPI webhooks 接口定義於 `POST /webhook`。

### 3.1 接收 LINE Webhook 事件

#### (1) 月嫂於 LINE 點擊「我願意接案」之 Postback 事件
* **LINE Webhook Payload 範例**：
  ```json
  {
    "destination": "Uxxxxxxxxxxxxxx",
    "events": [
      {
        "type": "postback",
        "replyToken": "nH7w4yWkg9QlIh1D6E6P8h3CIK85",
        "source": {
          "type": "user",
          "userId": "U_CAREGIVER_005_LINE"
        },
        "timestamp": 1462629479859,
        "mode": "active",
        "postback": {
          "data": "action=caregiver_accept&case_no=115000001&staff_id=5"
        }
      }
    ]
  }
  ```
* **地端處理邏輯**：
  1. Webhook 解析 postback data 參數：`action=caregiver_accept`、`case_no=115000001`。
  2. 搜尋 `matching_records` 資料表，將狀態更新為 `caregiver_accepted = 1`。
  3. 回傳 LINE 官方帳號訊息：「感謝您的回覆！我們已將您的意願同步給行政專員，待客戶確認後將會為您發送合約書。」

---

### 3.2 發送 LINE Flex Message 模板 (JSON 結構)

#### (1) 月嫂接案意願詢問 Flex 卡片 (發送給月嫂)
```json
{
  "type": "bubble",
  "header": {
    "type": "box",
    "layout": "vertical",
    "contents": [
      {
        "type": "text",
        "text": "月子專案媒合意願確認",
        "weight": "bold",
        "color": "#1DB954"
      }
    ]
  },
  "body": {
    "type": "box",
    "layout": "vertical",
    "contents": [
      {
        "type": "text",
        "text": "服務對象：林小姐 (新竹竹北市)",
        "size": "sm"
      },
      {
        "type": "text",
        "text": "預估期間：2026/08/10 起 24 工作日",
        "size": "sm"
      },
      {
        "type": "text",
        "text": "特殊備註：需做大寶餐、有寵物貓",
        "size": "sm",
        "color": "#FF5555"
      }
    ]
  },
  "footer": {
    "type": "box",
    "layout": "horizontal",
    "spacing": "sm",
    "contents": [
      {
        "type": "button",
        "style": "primary",
        "color": "#1DB954",
        "action": {
          "type": "postback",
          "label": "我願意接案",
          "data": "action=caregiver_accept&case_no=115000001&staff_id=5"
        }
      },
      {
        "type": "button",
        "style": "secondary",
        "action": {
          "type": "postback",
          "label": "無意願",
          "data": "action=caregiver_decline&case_no=115000001&staff_id=5"
        }
      }
    ]
  }
}
```

---

## 4. BeClass 報名問卷對接 Webhook 規格

當客戶填寫完成 BeClass 表單後，BeClass 發送 Webhook 至地端端點：`POST /api/v1/webhooks/beclass`。

### 4.1 Webhook Payload 格式
```json
{
  "form_id": "30525d069a79b3597af1",
  "query_no": "28755000",
  "case_no": "115000001",
  "submit_time": "2026-05-07 20:34:19",
  "personal_data": {
    "name": "陳小姐",
    "gender": "女",
    "email": "test_3059@example.com",
    "birth_year": 1998,
    "birth_month": 10,
    "birth_day": 22,
    "phone": "0912-34-5678",
    "tel": "03-5415899",
    "ext": "",
    "city": "新竹市",
    "zip_code": "300",
    "address": "新竹市東區和平街335號"
  },
  "questionnaire": {
    "月子餐點調理喜好/飲食習慣：": "葷食",
    "可以接受中藥補品：□茶飲 □藥飲 □藥膳": "Y",
    "2．餐飲含酒比例：": "無法接受",
    "3．料理用油：(可接受種類)": "□苦茶油(前兩週)、□麻油(後兩週)",
    "特殊照護時應注意事項：": "大寶1歲需協助照顧",
    "提供服務人員轎車停車位": "有"
  }
}
```

### 4.2 後端處理與 Data Pipeline 觸發
1. **驗證與清洗**：對 `personal_data.phone` 等核心欄位進行強校驗，若格式不合規，寫入 `data_anomaly_events`，狀態設為 `pending`。
2. **寫入 BeClass 記錄**：若校驗通過，將 `personal_data` 核心欄位寫入 `beclass_records`，並將整個 `questionnaire` 轉為 JSON 字串存入 `survey_details`。
3. **推播排程**：在 `line_push_tasks` 插入 `REMIND_REGISTRATION` 的 `pending` 任務，通知客戶「提醒登記與契約」完成填表之確認訊息。

---

## 5. 好好簽 (Breezysign) API 電子合約整合規格

為了自動化合約簽署，地端後端需與台灣的好好簽 (Breezysign) API 進行整合。

### 5.1 創建合約文件 (Create Contract)
* **API 端點**：`POST https://api.breezysign.com/v1/documents`
* **Headers**：
  * `Authorization: Bearer ${BREEZYSIGN_API_TOKEN}`
  * `Content-Type: application/json`
* **Request Body**：
  ```json
  {
    "template_id": "BS_TEMPLATE_UNION_METH",
    "document_name": "HC115628 到宅坐月子服務合約書",
    "variables": {
      "client_name": "陳小姐",
      "caregiver_name": "陳大姐",
      "start_date": "2026-08-10",
      "end_date": "2026-09-05",
      "daily_rate": "2000",
      "extra_clauses": "透天服務需每日加收100元樓層費"
    },
    "signers": [
      {
        "role": "client",
        "name": "陳小姐",
        "email": "test_3059@example.com",
        "phone": "0912345678",
        "sign_auth_type": "sms"
      },
      {
        "role": "caregiver",
        "name": "陳大姐",
        "email": "c_5873@example.com",
        "phone": "0922111333",
        "sign_auth_type": "sms"
      }
    ]
  }
  ```
* **Response (201 Created)**：
  ```json
  {
    "document_id": "BS_CON_998273",
    "status": "pending_signature",
    "signing_urls": {
      "client": "https://breezysign.com/s/9a12b3c4d5",
      "caregiver": "https://breezysign.com/s/5f6g7h8i9j"
    }
  }
  ```

---

### 5.2 監聽合約簽署狀態 Webhook

當客戶與月嫂完成線上簽章時，好好簽會發送 POST Webhook 到 FastAPI 的對接端點：`POST /api/v1/webhooks/breezysign`。

#### (1) Webhook Payload (合約簽署完成)
```json
{
  "event_type": "document.completed",
  "document_id": "BS_CON_998273",
  "completed_at": "2026-06-29T15:30:00Z",
  "download_url": "https://breezysign.com/download/BS_CON_998273.pdf"
}
```

#### (2) 地端自動化排班回寫邏輯
當後端接收到合約 `document.completed` 狀態時，執行以下事務 (Transaction)：
1. 更新 `orders` 表的合約狀態為 `已簽訂`，並寫入合約 PDF 下載連結。
2. 讀取對應月嫂的主表及休假偏好 (`weekly_rest_days`)。
3. 計算服務天數，自 `start_date` 開始遞增，排除固定休假日，得出實派結束日。
4. 在 `staff_bookings` (已被預約/排班區間表) 寫入實派排班紀錄。
5. 在該服務期結束日後，自動寫入 7 天的橘色緩衝預留期。

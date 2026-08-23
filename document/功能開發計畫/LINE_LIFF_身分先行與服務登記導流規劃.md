# LINE LIFF 身分先行與服務登記導流規劃規範

## 一、 文件狀態與責任範圍
- **文件狀態**：`proposed`
- **所屬模組**：LINE Ingress & LIFF Onboarding (模組一)
- **核心目標**：實現「身分先行核對 ➔ 自動帶入問卷 ➔ DB 暫存待綁定 ➔ 例外自動通報」的一體化導流閉環。

---

## 二、 `gateway.html` 業務主線與使用者路徑

### 1. 雙主線入口設計
* **路線一【已申請政府平台】**：進入身分先行核對流程（輸入姓名與手機）。
* **路線二【尚未申請政府平台】**：彈出市府申請須知，外連至「新竹市政府月子服務平台」登記，並提醒填寫完畢後回到 LINE 填寫 60 題問卷。

---

## 三、 身分先行核對與 3 種狀態分流機制

用戶於第一步輸入「產婦姓名 (name)」與「行動電話 (phone)」後，後端即時比對 `clients` 資料庫：

| 狀態類型 | 資料庫判定條件 | 畫面提示與系統動作 | 後續處理流程 |
| :--- | :--- | :--- | :--- |
| **狀態 A<br/>(舊客完全命中)** | 查得 `case_no` 且歷史已有 BeClass 需求記錄 | 提示「身分綁定成功！您的案件編號為【{case_no}】」 | 無需重複填寫問卷，自動升級為【客戶專屬選單】。 |
| **狀態 B<br/>(政府建檔待填問卷)** | 查得政府案件 `case_no`，但尚無 60 題問卷資料 | 提示「身分驗證成功！已對接政府案件【{case_no}】，請繼續填寫服務需求問卷」 | 自動預填姓名、電話與 `case_no`，無縫跳轉 `register.html`，送出問卷 100% 自動歸戶至既有正式案件。 |
| **狀態 C<br/>(名冊未同步/新申請)** | 暫時查無資料 | 提示「已為您建立臨時檔案，請直接填寫服務需求問卷，專員將於後台為您手動核對」 | 自動預填姓名與電話，跳轉 `register.html`。送出後寫入 `provisional_registrations` 暫存池，後台專員匯入政府名冊後一鍵核定。 |

---

## 四、 例外防呆與工會人工協處機制 (Retry Protection)

1. **第一次比對失敗**：前端提示「請確認姓名與電話是否與當時登記一致」，允許重新輸入。
2. **第二次比對仍失敗**：
   - 系統自動於 `customer_service_tickets` 建立一筆待辦工單（類別：`binding_failed_assistance`，狀態：`waiting`）。
   - 工會管理後台即時收到告警通知，由行政專員主動聯繫客戶協助排查。

---

## 五、 Eraser.io 流程圖對照
- **圖表連結（current read-only audit）**：`https://app.eraser.io/workspace/87vWpXgxRJMD2prPgXgO?diagram=9vI_ssJZUHa59Yw7LXc0d&layout=canvas`
- **Diagram ID**：`9vI_ssJZUHa59Yw7LXc0d`
- **Last verified**：2026-08-21（Eraser MCP）；僅更新外部圖表 identity，不把圖中文字升格為正式規格或實作授權。舊 ID `1XwrLwQvzREt3gYfwac2` 與 `0dXMFM1JaK-mi8Ayl_sB` 僅供追溯。

# 證據紀錄：04-變更控制鎖定與唯讀防護驗證 (Mutation Lock & Query-Only Evidence)

> **SUPERSEDED / STALE EVIDENCE**：本檔保存早期稽核歷史，測試數、工具鏈與完成判斷不得再引用。
> Current authority: `evidence-summary.md` and `verification-receipt.md`（Phase 2A status remains `blocked`）。

**證據代碼 (Evidence ID)**: `PROV-20260816-PHASE2A-EVID-04-MUTATION-LOCK`  
**所屬工作包 (Work Package)**: `PROV-20260816-react-admin-phase2a-orders`  
**執行時間 (Timestamp)**: `2026-08-16T12:17:55+08:00`  
**執行者 (Actor)**: Worker G4 (Verification & Evidence Ledger Writer)  

---

## 1. 變更控制項鎖定核心原則 (Invariant 2: GET Query Only)

依據 Phase 2A 核心規範：
1. **唯讀查詢原則 (GET Query Only)**：Phase 2A 僅遷移查詢端點，所有涉及狀態寫入、業務推進、日程確認、履歷推播、訂金鎖定與退款結案之變更控制項，必須維持既有 UI 佈局，但明確設定為 `disabled` 狀態，並附加 `title` 提示說明不可用原因（如 `[查詢模式] ...`）。
2. **零假變更 (Zero Fake Mutations)**：禁止在前端使用 `alert()`、`confirm()`、`setOrders()` 模擬寫入成功，禁止前端私自進行退款試算、排班覆蓋率計算或日程日期推算。
3. **完整 UI 層級保留 (Preserve UI Hierarchy)**：保留 Orders 4 大抽屜、Tracker 雙分頁、7-stage 管線與 11 步驟 SOP 視覺格位，不刪減任何按鈕或輸入框。

---

## 2. 22 個變更控制項清單與鎖定狀態 (Mutation Controls Inventory)

| 編號 (ID) | 控制項名稱 / 標籤 | 所在元件 / 抽屜 | 元素型別 | 鎖定狀態 (`disabled`) | 提示文字 (`title`) | 零假變更驗證 |
| :---: | :--- | :--- | :---: | :---: | :--- | :---: |
| **M01** | `+ 新建訂單` | `OrdersPage` 頂部操作列 | `<button>` | `true` | `[查詢模式] 建立新訂單功能將於 Phase 2B 開放` | PASSED |
| **M02** | `🔄 重啟訂單` | `OrdersPage` 頂部操作列 | `<button>` | `true` | `[查詢模式] 重啟訂單功能將於 Phase 2B 開放` | PASSED |
| **M03** | `實際服務開始日` | Drawer 1 (確認服務日期) | `<input type="date">` | `true` | `[查詢模式] 日期修改需透過後端工作流 API` | PASSED |
| **M04** | `排休與請假摘要` | Drawer 1 (確認服務日期) | `<input type="text">` | `true` | `[查詢模式] 排休請假調整需透過後端工作流 API` | PASSED |
| **M05** | `📢 發送精算日程表` | Drawer 1 (確認服務日期) | `<button>` | `true` | `[查詢模式] 精算日程表推播功能將於 Phase 2B 開放` | PASSED |
| **M06** | `📞 電話補登客戶確認` | Drawer 1 (確認服務日期) | `<button>` | `true` | `[查詢模式] 客戶確認照會寫入需透過正式工作流` | PASSED |
| **M07** | `📞 電話補登月嫂確認` | Drawer 1 (確認服務日期) | `<button>` | `true` | `[查詢模式] 月嫂確認照會寫入需透過正式工作流` | PASSED |
| **M08** | `🚀 轉入正式服務履約` | Drawer 1 (確認服務日期) | `<button>` | `true` | `[查詢模式] 轉入正式履約需透過後端狀態機推進` | PASSED |
| **M09** | `📅 更新日程` | Drawer 1 (確認服務日期) | `<button>` | `true` | `[查詢模式] 日程變更需透過後端工作流` | PASSED |
| **M10** | `➕ 加入月嫂至意願池` | Drawer 2 (媒合工作台) | `<button>` | `true` | `[查詢模式] 意願池名單調整將於 Phase 2B 開放` | PASSED |
| **M11** | `✖ 重設配對池` | Drawer 2 (媒合工作台) | `<button>` | `true` | `[查詢模式] 重設配對池將於 Phase 2B 開放` | PASSED |
| **M12** | `💬 發送 訂單資訊-1` | Drawer 2 (媒合工作台) | `<button>` | `true` | `[查詢模式] LINE 意願徵詢推播將於 Phase 2B 開放` | PASSED |
| **M13** | `📄 發送 訂單資訊-2` | Drawer 2 (媒合工作台) | `<button>` | `true` | `[查詢模式] 訂單完整資訊推播將於 Phase 2B 開放` | PASSED |
| **M14** | `📨 傳送已勾選月嫂履歷給客戶` | Drawer 2 (媒合工作台) | `<button>` | `true` | `[查詢模式] 履歷交付推播將於 Phase 2B 開放` | PASSED |
| **M15** | `🔒 產生並建立等待訂金鎖` | Drawer 2 (媒合工作台) | `<button>` | `true` | `[查詢模式] 訂金鎖定寫入需透過後端交易 API` | PASSED |
| **M16** | `核取月嫂履歷勾選框` | Drawer 2 (媒合工作台) | `<input type="checkbox">` | `true` | `[查詢模式] 唯讀檢視` | PASSED |
| **M17** | `審核與計算結案退款` | Drawer 3 (履約與結案) | `<button>` | `true` | `[查詢模式] 結案計算由後端端點即時投影，不開放前端試算` | PASSED |
| **M18** | `套用正式結案單據` | Drawer 3 (履約與結案) | `<button>` | `true` | `[查詢模式] 結案套用需透過後端狀態機交易` | PASSED |
| **M19** | `補登預收訂金扣抵` | Drawer 3 (履約與結案) | `<button>` | `true` | `[查詢模式] 訂金扣抵由後端合約帳務自動彙整` | PASSED |
| **M20** | `更新合約簽署狀態` | Drawer 3 (履約與結案) | `<button>` | `true` | `[查詢模式] 合約狀態更新需透過正式 API` | PASSED |
| **M21** | `確認執行取消` | Drawer 4 (取消試算) | `<button>` | `true` | `[查詢模式] 取消案件需透過後端取消工作流 API` | PASSED |
| **M22** | `🔄 手動重發` (通知) | `OrderTrackerPage` (LINE 分頁) | `<button>` | `true` | `[查詢模式] LINE 訊息手動重發將於 Phase 2B 開放` | PASSED |

---

## 3. 靜態與動態防護測試驗證 (Verification Results)

### 3.1 靜態程式碼審查 (Static Source Code Audit)
- 搜尋 `OrdersPage.tsx` 與 `OrderTrackerPage.tsx`：
  - `alert(` 出現次數：`0`
  - `confirm(` 出現次數：`0`
  - `prompt(` 出現次數：`0`
  - `calculateRefund` / 前端自算退款出現次數：`0`
  - 假寫入 `setState` 假裝資料新增/修改：`0`

### 3.2 自動化整合測試 (`src/tests/orders_no_fake_mutation.test.ts`)
- 5 個專屬對抗測試案例：
  1. `M1 & M2: +新建訂單 與 🔄重啟訂單 按鈕為 disabled 且點擊無 alert/confirm` -> **PASSED**
  2. `M3-M9: Drawer 1 (確認服務日期) 之輸入與推進按鈕皆為 disabled` -> **PASSED**
  3. `M10-M20: Drawer 2 (媒合工作台) 之加入、重設、推播與鎖定按鈕皆為 disabled` -> **PASSED**
  4. `M21: Drawer 4 (取消試算) 之執行取消按鈕為 disabled` -> **PASSED**
  5. `M22: OrderTrackerPage 之手動重發通知按鈕為 disabled` -> **PASSED**

---

## 4. 驗證結論 (Conclusion)

所有 22 個變更控制項完全受控鎖定，UI 原貌完整保留，零假變更、零前端假試算，嚴格遵守 Phase 2A 唯讀查詢防護要求。

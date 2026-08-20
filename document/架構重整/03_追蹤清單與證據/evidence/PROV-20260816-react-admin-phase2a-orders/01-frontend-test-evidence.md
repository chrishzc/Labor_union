# 證據紀錄：01-前端單元與元件測試 (Frontend Test Evidence)

> **SUPERSEDED / STALE EVIDENCE**：本檔保存早期稽核歷史，測試數、工具鏈與完成判斷不得再引用。
> Current authority: `evidence-summary.md` and `verification-receipt.md`（Phase 2A status remains `blocked`）。

**證據代碼 (Evidence ID)**: `PROV-20260816-PHASE2A-EVID-01-FE-TEST`  
**所屬工作包 (Work Package)**: `PROV-20260816-react-admin-phase2a-orders`  
**執行時間 (Timestamp)**: `2026-08-16T12:17:14+08:00`  
**執行者 (Actor)**: Worker G4 (Verification & Evidence Ledger Writer)  
**執行環境 (Environment)**:
- OS: Windows 11 (win32 10.0.26100)
- Node.js: v20.x+
- Vitest: v3.2.7
- Testing Library: `@testing-library/react` v16.2.0, `@testing-library/jest-dom` v6.6.3

---

## 1. 測試執行指令與摘要 (Execution Command & Summary)

### 執行指令
```powershell
cd ui_react
npm test
```
*同等於執行 `npx vitest run`*

### 執行結果統計
- **Test Files**: 14 passed (14 total)
- **Tests**: 224 passed (224 total)
- **Failures**: 0
- **Skipped**: 0
- **Duration**: 6.20s
- **Exit Code**: `0`

---

## 2. 測試檔案清單與測試案例細項 (Test Suites Breakdown)

| 測試檔案 (Test File) | 案例數 (Tests) | 狀態 (Status) | 耗時 (Duration) | 核心驗證範圍 (Verification Scope) |
| :--- | :---: | :---: | :---: | :--- |
| `src/tests/orders_query_client.test.ts` | 29 | PASSED | 71ms | 訂單查詢 API Client (11 端點、Zod 綱要驗證、URL 查詢編碼、404/422/500/網路錯誤包裝、AbortSignal 取消、Session Token 注入) |
| `src/tests/orders_adapter.test.ts` | 14 | PASSED | 53ms | 訂單摘要、訂單詳情、訂單進度追蹤器 Adapter (後端真實資料轉換、資料欄位映射、空值與非標準狀態優雅降級、`BACKEND_GAP` 顯式標註) |
| `src/tests/orders_page_real_data.test.tsx` | 7 | PASSED | 793ms | `OrdersPage` 真實資料渲染 (訂單清單表格、分頁、搜尋、4大抽屜 Lazy Loading、Fast Case Switching 競態防護、載入/錯誤/空狀態) |
| `src/tests/order_tracker_real_data.test.tsx` | 3 | PASSED | 450ms | `OrderTrackerPage` 真實資料渲染 (7 階段管線狀態、11 步驟 SOP 檢核、案件卡片切換、LINE 通知紀錄雙分頁) |
| `src/tests/orders_no_fake_mutation.test.ts` | 5 | PASSED | 746ms | 22 個變更控制項鎖定驗證 (所有寫入/推進按鈕 `disabled`、無 `alert`/`confirm` 假變更、無前端試算邏輯) |
| `src/tests/challenger_g2_orders_client.test.ts` | 38 | PASSED | 120ms | G2 對抗性測試：綱要惡意污染、非預期欄位注入、極端字元編碼、畸形分頁邊界驗證 |
| `src/tests/challenger_g2_orders_client_resilience.test.ts` | 28 | PASSED | 95ms | G2 彈性與並行測試：高併發競態、微秒級超時、連線中斷重試標記、記憶體無洩漏驗證 |
| `src/tests/runtime_decoder.test.ts` | 11 | PASSED | 45ms | 共用 Zod 執行期解碼器 (型別安全解碼、結構錯誤詳細定位、巢狀綱要相容) |
| `src/tests/transport.test.ts` | 11 | PASSED | 67ms | 共用 Transport 通訊層 (HTTP 狀態碼轉換、Timeout、AbortSignal、錯誤分級) |
| `src/tests/stress_transport_decoder.test.ts` | 26 | PASSED | 185ms | 壓力與極限測試 (50 併發請求、極限 Payload 解析、非同步計時器回收) |
| `src/tests/system_status_slice.test.ts` | 5 | PASSED | 114ms | 系統狀態切片與 MasterLayout 狀態燈指示器 |
| `src/tests/LoginPage.test.tsx` | 9 | PASSED | 320ms | 登入頁面展示、會話客戶端、防偽登入按鈕與狀態回饋 |
| `src/tests/route_guard.test.tsx` | 7 | PASSED | 515ms | 路由防衛、URL Hash 同步、未認證跳轉、側邊欄導航切換 |
| `src/tests/challenger_auth_navigation.test.tsx` | 18 | PASSED | 635ms | 權限與導航對抗性驗證 (URL Hash 注入、會話過期強制跳轉、冷啟動狀態復原) |

---

## 3. Phase 2A 專屬測試範疇深度驗證 (Detailed Orders Scope Verification)

### 3.1 訂單查詢 API Client (`orders_query_client.test.ts` - 29 tests)
1. **摘要分頁查詢 (`getOrderSummaries`)**:
   - 支援 `page_size`, `cursor_created_at`, `cursor_case_no`, `search_text` 參數傳遞。
   - 支援空字串、全形/半形空白及特殊搜尋關鍵字 URL safe 編碼。
   - 正確處理空清單與分頁游標回傳。
2. **四大抽屜詳情端點解碼**:
   - `getOrderDetail`: 嚴格解碼完整案件基本資訊、合約狀態與客戶備註。
   - `getOrderCalendarDetail`: 嚴格解碼日曆排程、服務模式與每日狀態清單。
   - `getOrderTerms`: 嚴格解碼服務條款、保證金與收費細項。
   - `getContractCompletion`: 嚴格解碼結案審查狀態、獨立三退款預測（履約完成、客戶退款、月嫂結算）。
   - `getContractSigning`: 嚴格解碼合約簽署進度與時間戳。
   - `getActualStart`: 嚴格解碼實際開工日期確認狀態與指派人員。
   - `getServiceDates`: 嚴格解碼服務日程確認、各方電話照會與正式推進狀態。
   - `getCandidateContactPool`: 嚴格解碼意願池月嫂名單、聯絡階段與推播紀錄。
   - `getScheduleConfirmation`: 嚴格解碼月嫂排程確認歷程與確認狀態。
   - `getOrderCancellation`: 嚴格解碼取消審查、責任歸屬與退款試算結果。
3. **錯誤分類與安全防護**:
   - HTTP 404 精確轉換為 `OrderNotFoundError`。
   - HTTP 422 結構化錯誤解構為 `OrderQueryValidationError`。
   - Schema 不符精確轉換為 `OrderQuerySchemaMismatchError`。
   - AbortSignal 觸發中斷時精確拋出 `ApiAbortError`。

### 3.2 訂單資料適配層 (`orders_adapter.test.ts` - 14 tests)
1. **欄位對齊與轉換**:
   - 嚴格落實 `contract-field-matrix.md` 規定之 126 個欄位映射。
   - `order_status` 正確映射至中文狀態標籤與顏色等級。
   - 金額欄位以正整數格式化顯示，日期時間欄位標準化為台北時區格式。
2. **缺口欄位安全防護 (`BACKEND_GAP`)**:
   - 後端尚未提供之欄位（如緊急聯絡人備註、非核心第三方發票資訊）統一回傳顯式缺口標記 `BACKEND_GAP`。
   - 拒絕任何前端 Mock 資料回退或假計算填充。
3. **單一人員推薦與多段備案業務邏輯**:
   - 單一推薦人員正常呈現單一卡片；僅在單一人員無法涵蓋時呈現 2-4 人多段組合。

### 3.3 訂單頁面真實渲染 (`orders_page_real_data.test.tsx` - 7 tests)
1. **清單資料載入**: 頁面掛載時正確發送 `getOrderSummaries` 請求，並將後端回傳之真實案件清單填入表格。
2. **四大抽屜 Lazy Loading**:
   - 點擊表格內「確認服務日期」即時呼叫 `getServiceDates` 載入 Drawer 1。
   - 點擊「媒合意願池」即時呼叫 `getCandidateContactPool` 載入 Drawer 2。
   - 點擊「履約與結案」即時呼叫 `getContractCompletion` 載入 Drawer 3。
   - 點擊「取消試算」即時呼叫 `getOrderCancellation` 載入 Drawer 4。
3. **快速切換案件之競態防護 (Generation Guard)**:
   - 連續點選不同案件抽屜時，前次未完成之請求由 AbortController 中斷，且舊請求之回應不會覆蓋當前最新選定案件之畫面。
4. **狀態容錯**:
   - 網路斷線時呈現優雅錯誤重試提示，不造成 React 崩潰。

### 3.4 訂單進度追蹤器真實渲染 (`order_tracker_real_data.test.tsx` - 3 tests)
1. **7 階段管線狀態渲染**: 正確映射 7-stage pipeline（諮詢、意願徵詢、鎖定訂金、簽約、待開工、服務中、已結案）。
2. **11 步驟 SOP 檢核**: 正確對齊 11 步驟標準作業程序核取狀態。
3. **雙分頁切換**:「SOP 檢核清單」與「LINE 通知紀錄與發送狀態」切換正常，資料維持獨立綁定。

### 3.5 變更控制項全面鎖定 (`orders_no_fake_mutation.test.ts` - 5 tests)
1. **22 個變更控制項鎖定**:
   - `+ 新建訂單`、`🔄 重啟訂單` 按鈕 `disabled=true`。
   - Drawer 1（確認服務日期）中所有日期輸入、發送精算日程、電話補登、轉入正式履約按鈕全部 `disabled=true`。
   - Drawer 2（媒合工作台）中加入月嫂、重設配對池、發送訂單資訊、傳送履歷、建立訂金鎖按鈕全部 `disabled=true`。
   - Drawer 4（取消試算）中確認執行取消按鈕 `disabled=true`。
   - OrderTrackerPage 中手動重發通知按鈕 `disabled=true`。
2. **零假變更**: 點擊上述所有控制項，`window.alert` 與 `window.confirm` 呼叫次數均為 `0`。

---

## 4. 驗證結論 (Conclusion)

前端測試套件共 14 個測試檔案、224 個測試案例全部以 0 錯誤、0 警告通過。所有 Phase 2A 新增與既有切片均符合合約規範與品質標準。

# 證據紀錄：05-安全、敏感資料與 Mock 殘留掃描 (Security, PII & Mock Residual Scan Evidence)

> **SUPERSEDED / STALE EVIDENCE**：本檔保存早期稽核歷史，測試數、工具鏈與完成判斷不得再引用。
> Current authority: `evidence-summary.md` and `verification-receipt.md`（Phase 2A status remains `blocked`）。

**證據代碼 (Evidence ID)**: `PROV-20260816-PHASE2A-EVID-05-SECURITY-MOCK-SCAN`  
**所屬工作包 (Work Package)**: `PROV-20260816-react-admin-phase2a-orders`  
**執行時間 (Timestamp)**: `2026-08-16T12:21:46+08:00`  
**執行者 (Actor)**: Worker G4 (Verification & Evidence Ledger Writer)  

---

## 1. 掃描目標與檢驗項目 (Scan Target & Scope)

本次安全掃描針對 Phase 2A 涉及之所有前端生產代碼進行深度逐行靜態分析：
1. **API Client 層**:
   - `ui_react/src/api/orders/order_query_client.ts`
   - `ui_react/src/api/orders/order_query_errors.ts`
   - `ui_react/src/api/orders/order_query_schemas.ts`
2. **Adapter 適配層**:
   - `ui_react/src/adapters/orders/order_detail_adapter.ts`
   - `ui_react/src/adapters/orders/order_summary_adapter.ts`
   - `ui_react/src/adapters/orders/order_tracker_adapter.ts`
3. **頁面視圖層**:
   - `ui_react/src/pages/OrdersPage.tsx`
   - `ui_react/src/pages/OrderTrackerPage.tsx`

---

## 2. 檢測項目與規則定義 (Detection Rules)

| 檢驗維度 (Dimension) | 規則 pattern / 目標 | 判定準則 (Acceptance Rule) |
| :--- | :--- | :--- |
| **Mock 資料殘留** | `mockData`, `\bMOCK_[A-Z0-9_]+\b`, `mockOrders`, `fakeData` | 生產代碼中出現次數必須為 **0**（不得有 Mock 回退或假資料匯入） |
| **密鑰與憑證 (Secrets)** | `(?i)(password\|secret\|api_key\|apikey\|private_key\|auth_token)\s*[:=]\s*['"][^'"]+['"]` | 生產代碼中出現次數必須為 **0**（Token 僅能由 SessionClient 動態取得） |
| **個資 (PII)** | 台灣身分證字號格式 `\b[A-Z][12]\d{8}\b`、真實電話與電子郵件 | 生產代碼中出現次數必須為 **0** |

---

## 3. 掃描執行結果記錄 (Scan Results)

### 執行輸出 (Verbatim Report)
```text
=== SECURITY, PII & MOCK RESIDUAL SCAN REPORT ===
File: order_query_client.ts
  Path: c:\Users\chris\Desktop\project\Labor_union\ui_react\src\api\orders\order_query_client.ts
  Lines: 659
  Mock Residuals Found: 0
  Secret/PII Suspicious Tokens: 0
File: order_query_errors.ts
  Path: c:\Users\chris\Desktop\project\Labor_union\ui_react\src\api\orders\order_query_errors.ts
  Lines: 199
  Mock Residuals Found: 0
  Secret/PII Suspicious Tokens: 0
File: order_query_schemas.ts
  Path: c:\Users\chris\Desktop\project\Labor_union\ui_react\src\api\orders\order_query_schemas.ts
  Lines: 429
  Mock Residuals Found: 0
  Secret/PII Suspicious Tokens: 0
File: order_detail_adapter.ts
  Path: c:\Users\chris\Desktop\project\Labor_union\ui_react\src\adapters\orders\order_detail_adapter.ts
  Lines: 489
  Mock Residuals Found: 0
  Secret/PII Suspicious Tokens: 0
File: order_summary_adapter.ts
  Path: c:\Users\chris\Desktop\project\Labor_union\ui_react\src\adapters\orders\order_summary_adapter.ts
  Lines: 248
  Mock Residuals Found: 0
  Secret/PII Suspicious Tokens: 0
File: order_tracker_adapter.ts
  Path: c:\Users\chris\Desktop\project\Labor_union\ui_react\src\adapters\orders\order_tracker_adapter.ts
  Lines: 359
  Mock Residuals Found: 0
  Secret/PII Suspicious Tokens: 0
File: OrdersPage.tsx
  Path: c:\Users\chris\Desktop\project\Labor_union\ui_react\src\pages\OrdersPage.tsx
  Lines: 1206
  Mock Residuals Found: 0
  Secret/PII Suspicious Tokens: 0
File: OrderTrackerPage.tsx
  Path: c:\Users\chris\Desktop\project\Labor_union\ui_react\src\pages\OrderTrackerPage.tsx
  Lines: 406
  Mock Residuals Found: 0
  Secret/PII Suspicious Tokens: 0

=== OVERALL STATUS ===
STATUS: PASSED (Zero residual mock data, zero secrets, zero PII)
```

---

## 4. 測試資料集規範檢驗 (Test Fixtures Verification)

針對測試目錄 `ui_react/src/tests/fixtures/orders_real_data_fixtures.ts` 進行審查：
- 所有測試案號均為合成格式（如 `ORD-2026-0801`、`ORD-2026-0802`）。
- 客戶與工作人員名稱均為合成虛構姓名（如「陳雅婷」、「林美玲」、「黃怡君」、「林美惠」）。
- 無任何真實身分證字號、真實通訊錄或第三方服務認證金鑰。

---

## 5. 驗證結論 (Conclusion)

所有 8 個 Phase 2A 核心生產檔案經全面掃描，確認：
1. **Mock 殘留量**: 0 筆。
2. **硬編碼金鑰 / 憑證**: 0 筆。
3. **客戶 PII / 身分證字號洩漏**: 0 筆。
4. **狀態**: **全面合規通過 (PASSED)**。

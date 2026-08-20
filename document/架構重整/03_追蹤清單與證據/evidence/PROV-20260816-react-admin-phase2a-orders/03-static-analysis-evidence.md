# 證據紀錄：03-靜態分析、建置與檔案編碼驗證 (Static Analysis, Build & Encoding Evidence)

> **SUPERSEDED / STALE EVIDENCE**：本檔保存早期稽核歷史，測試數、工具鏈與完成判斷不得再引用。
> Current authority: `evidence-summary.md` and `verification-receipt.md`（Phase 2A status remains `blocked`）。

**證據代碼 (Evidence ID)**: `PROV-20260816-PHASE2A-EVID-03-STATIC-ANALYSIS`  
**所屬工作包 (Work Package)**: `PROV-20260816-react-admin-phase2a-orders`  
**執行時間 (Timestamp)**: `2026-08-16T12:21:07+08:00`  
**執行者 (Actor)**: Worker G4 (Verification & Evidence Ledger Writer)  
**執行環境 (Environment)**:
- OS: Windows 11 (win32 10.0.26100)
- Node.js: v20.x+
- TypeScript: v5.6.3
- Vite: v5.4.21
- ESLint: v9.x / `@typescript-eslint`

---

## 1. ESLint 程式碼品質與規範檢查 (ESLint Linter)

### 執行指令
```powershell
cd ui_react
npm run lint
```

### 執行輸出 (Verbatim Output)
```text
> labor-union-ui@1.0.0 lint
> eslint .
```

### 結果分析
- **Exit Code**: `0`
- **Errors**: 0
- **Warnings**: 0
- **合規性**: 符合 ESLint 與 TypeScript 靜態規則，無任何未使用的變數、隱式 `any` 或語法違規。

---

## 2. TypeScript 編譯與 Vite 生產打包 (Production Build)

### 執行指令
```powershell
cd ui_react
npm run build
```

### 執行輸出 (Verbatim Output)
```text
> labor-union-ui@1.0.0 build
> tsc -b && vite build

vite v5.4.21 building for production...
transforming...
✓ 83 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.97 kB │ gzip:   0.60 kB
dist/assets/index-DahKdmEP.css   34.74 kB │ gzip:   6.00 kB
dist/assets/index-BKuK0SKx.js   466.68 kB │ gzip: 128.60 kB
✓ built in 1.61s
```

### 結果分析
- **Exit Code**: `0`
- **TypeScript 專案參照編譯 (`tsc -b`)**: 通過，無型別定義衝突或遺漏。
- **打包產出 (Build Artifacts)**:
  - HTML: `dist/index.html` (0.97 kB)
  - CSS: `dist/assets/index-DahKdmEP.css` (34.74 kB / gzip: 6.00 kB)
  - JS: `dist/assets/index-BKuK0SKx.js` (466.68 kB / gzip: 128.60 kB)
- **模組轉換**: 83 個模組全部成功轉換與打包，無語法解析或路徑解析錯誤。

---

## 3. Git Diff 空白與衝突標記檢查 (Git Diff Whitespace Check)

### 執行指令
```powershell
git --git-dir="D:\project\Labor_union\.git" --work-tree="D:\project\Labor_union" diff --check
```

### 執行結果
- **Exit Code**: `0`
- **空白違規 (Whitespace Errors)**: 0
- **未解析衝突標記 (Conflict Markers)**: 0
- **行尾序列一致性**: 正常，無異常混雜控制字元。

---

## 4. 嚴格 UTF-8 編碼與零 BOM 驗證 (Strict UTF-8 & BOM Validation)

對 `ui_react/src/api/orders/`, `ui_react/src/adapters/orders/`, `ui_react/src/pages/`, `ui_react/src/tests/` 範圍內共 **46 個檔案** 進行逐位元二進位讀取、嚴格 UTF-8 解碼與 BOM / 空字元檢驗。

### 驗證結果清單

| 分類 / 目錄 (Category) | 檔案名稱 (File Path) | 大小 (Bytes) | 字元數 (Chars) | BOM 標記 | 空字元 (\x00) | UTF-8 解碼狀態 |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **API Client** | `api/orders/order_query_client.ts` | 22,639 | 22,065 | False | 0 | **PASSED** |
| **API Client** | `api/orders/order_query_errors.ts` | 6,051 | 5,599 | False | 0 | **PASSED** |
| **API Client** | `api/orders/order_query_schemas.ts` | 18,443 | 18,403 | False | 0 | **PASSED** |
| **Adapters** | `adapters/orders/order_detail_adapter.ts` | 18,373 | 16,950 | False | 0 | **PASSED** |
| **Adapters** | `adapters/orders/order_summary_adapter.ts` | 7,550 | 6,744 | False | 0 | **PASSED** |
| **Adapters** | `adapters/orders/order_tracker_adapter.ts` | 11,752 | 9,950 | False | 0 | **PASSED** |
| **Pages** | `pages/OrdersPage.tsx` | 60,374 | 56,500 | False | 0 | **PASSED** |
| **Pages** | `pages/OrdersPage.css` | 3,786 | 3,786 | False | 0 | **PASSED** |
| **Pages** | `pages/OrderTrackerPage.tsx` | 18,270 | 17,626 | False | 0 | **PASSED** |
| **Pages** | `pages/OrderTrackerPage.css` | 4,026 | 4,026 | False | 0 | **PASSED** |
| **Pages** | `pages/LoginPage.tsx` | 9,131 | 8,695 | False | 0 | **PASSED** |
| **Pages** | `pages/LoginPage.css` | 4,337 | 4,337 | False | 0 | **PASSED** |
| **Pages** | `pages/AccountManagementPage.tsx` | 28,707 | 26,832 | False | 0 | **PASSED** |
| **Pages** | `pages/AccountManagementPage.css` | 1,748 | 1,748 | False | 0 | **PASSED** |
| **Pages** | `pages/AnomaliesPage.tsx` | 21,812 | 19,525 | False | 0 | **PASSED** |
| **Pages** | `pages/AnomaliesPage.css` | 2,551 | 2,551 | False | 0 | **PASSED** |
| **Pages** | `pages/DataBrowserPage.tsx` | 14,004 | 13,017 | False | 0 | **PASSED** |
| **Pages** | `pages/DataBrowserPage.css` | 1,598 | 1,598 | False | 0 | **PASSED** |
| **Pages** | `pages/DataImportPage.tsx` | 16,183 | 14,603 | False | 0 | **PASSED** |
| **Pages** | `pages/DataImportPage.css` | 1,287 | 1,287 | False | 0 | **PASSED** |
| **Pages** | `pages/FinancePage.tsx` | 36,363 | 33,516 | False | 0 | **PASSED** |
| **Pages** | `pages/FinancePage.css` | 2,405 | 2,405 | False | 0 | **PASSED** |
| **Pages** | `pages/LineManagementPage.tsx` | 44,219 | 40,421 | False | 0 | **PASSED** |
| **Pages** | `pages/LineManagementPage.css` | 1,375 | 1,375 | False | 0 | **PASSED** |
| **Pages** | `pages/ReportsPage.tsx` | 22,574 | 20,479 | False | 0 | **PASSED** |
| **Pages** | `pages/ReportsPage.css` | 2,469 | 2,469 | False | 0 | **PASSED** |
| **Pages** | `pages/SchedulingPage.tsx` | 66,173 | 62,234 | False | 0 | **PASSED** |
| **Pages** | `pages/SchedulingPage.css` | 7,880 | 7,880 | False | 0 | **PASSED** |
| **Pages** | `pages/StaffPage.tsx` | 39,462 | 36,517 | False | 0 | **PASSED** |
| **Pages** | `pages/StaffPage.css` | 1,996 | 1,996 | False | 0 | **PASSED** |
| **Tests** | `tests/orders_query_client.test.ts` | 35,144 | 33,948 | False | 0 | **PASSED** |
| **Tests** | `tests/orders_adapter.test.ts` | 13,999 | 13,307 | False | 0 | **PASSED** |
| **Tests** | `tests/orders_page_real_data.test.tsx` | 6,804 | 6,459 | False | 0 | **PASSED** |
| **Tests** | `tests/order_tracker_real_data.test.tsx` | 3,302 | 2,996 | False | 0 | **PASSED** |
| **Tests** | `tests/orders_no_fake_mutation.test.ts` | 8,843 | 8,182 | False | 0 | **PASSED** |
| **Tests** | `tests/challenger_g2_orders_client.test.ts` | 22,496 | 22,412 | False | 0 | **PASSED** |
| **Tests** | `tests/challenger_g2_orders_client_resilience.test.ts` | 19,629 | 18,765 | False | 0 | **PASSED** |
| **Tests** | `tests/runtime_decoder.test.ts` | 5,179 | 4,833 | False | 0 | **PASSED** |
| **Tests** | `tests/transport.test.ts` | 8,800 | 8,376 | False | 0 | **PASSED** |
| **Tests** | `tests/stress_transport_decoder.test.ts` | 25,562 | 24,324 | False | 0 | **PASSED** |
| **Tests** | `tests/system_status_slice.test.ts` | 6,312 | 6,008 | False | 0 | **PASSED** |
| **Tests** | `tests/LoginPage.test.tsx` | 6,748 | 6,014 | False | 0 | **PASSED** |
| **Tests** | `tests/route_guard.test.tsx` | 5,223 | 4,667 | False | 0 | **PASSED** |
| **Tests** | `tests/challenger_auth_navigation.test.tsx` | 16,931 | 15,649 | False | 0 | **PASSED** |
| **Tests** | `tests/setup.ts` | 820 | 768 | False | 0 | **PASSED** |
| **Tests** | `tests/fixtures/orders_real_data_fixtures.ts` | 10,202 | 9,830 | False | 0 | **PASSED** |

### 統計總結
- **總檢查檔案數**: 46 份
- **解碼失敗 (Decode Failures)**: 0
- **BOM 標記檢出 (BOM Detected)**: 0
- **異常空字元 (Null Bytes)**: 0
- **狀態**: **100% 全部通過**

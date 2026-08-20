# Orders／OrderTracker Query Page-Slice Evidence Matrix（Draft）

> 狀態：Draft／不可作為授權。此矩陣只描述 page surface 與驗收證據位置，不建立欄位級 gap，也不取代後端 Pydantic schema。執行前須由 Integration Owner 依最新 base、live schema 與實際 diff 再凍結。

| Stable ID | React surface | 允許的 server source | 目前 source disposition | 預期 UI evidence | 禁止行為 |
|---|---|---|---|---|---|
| `ORD-QRY-001` | Orders summary list；OrderTracker initial list | `GET /api/v1/orders/summaries` → `OrderSummaryPageView` | Existing typed GET；保留 | Network 200、列表 DOM、empty／error／reload | 依 status 推導七階段或額外逐筆預抓 |
| `ORD-QRY-002` | Orders／Tracker selected order detail | `GET /api/v1/orders/{case_no}` → `OrderDetailView` | Existing typed GET；保留 | Drawer Network 200、server 欄位可追溯 | 把缺失欄位補成 false／0／pending |
| `ORD-QRY-003` | Orders service-date Drawer calendar area | `GET /api/v1/orders/{case_no}/calendar-detail` → `OrderCalendarDetailView` | Existing typed GET；保留可提供欄位 | calendar slot DOM 與 unavailable sentinel | 前端自算日期／buffer |
| `ORD-QRY-004` | Orders terms／contract Drawer | `GET /api/v1/orders/{case_no}/terms` → `OrderTermsQueryView` | Existing typed GET；保留 | terms DOM、typed error | 把 terms 當作簽署完成或付款完成 |
| `ORD-QRY-005` | Form-management context slot（若 surface 實際使用） | `GET /api/v1/orders/{case_no}/form-management-context` → `FormManagementCaseContextView` | Existing typed GET；按需一次 | request budget + context DOM | 預抓／從其他 Domain 猜表單狀態 |
| `ORD-QRY-006` | Actual-start／date Drawer read projection | `GET /api/v1/orders/{case_no}/actual-start` → `ActualStartQueryView` | Existing typed GET；保留 | actual-start DOM | 用 current date 或 order status 推導 |
| `ORD-QRY-007` | Contract completion slot | `GET /api/v1/orders/{case_no}/contract-completion` → `ContractCompletionQueryView` | Existing typed GET；保留 | completion blockers／typed unavailable | 呼叫 `/contract-signing` 或猜簽回 |
| `ORD-QRY-008` | Matching Drawer assignment-owned section | `GET /api/v1/orders/{case_no}/assignment-plan` → `AssignmentPlanQueryView` | Existing typed GET；只顯示 assignment-owned projection | assignment section DOM | candidate pool、recommend staff、正式推薦故事 |
| `ORD-SLOT-UNAVAILABLE-001` | Cancellation Drawer、unsupported matching／signing slots | 無本包 allowlist request | 保留既有 slot，顯示 stable unavailable | visible DOM sentinel + 0 network request | hidden、假退款、假推薦 |
| `ORD-NO-DERIVATION-001` | Orders filter／Tracker stage/SOP/settlement | 無可用 single typed projection | 不可由前端計算 | static scan + negative test | `mapOrderStatusToWorkflowStage`、stage index、fixed LINE timestamps |
| `ORD-MUTATION-PRESERVE-001` | Service Dates Confirm／Controlled Reopen | Phase 2B mutation client／store／adapter | 本包不修改 | focused regression only | 改 mutation state machine、headers、receipt、re-query |

## Required receipts（execution phase）

| Receipt | Minimum proof |
|---|---|
| `contract-matrix.md` | 八項 endpoint、Pydantic source、Zod schema、surface disposition |
| `candidate-change-inventory.md` | exact diff、0 backend、0 DB、0 mutation-file change |
| `verification-receipt.md` | focused/full Vitest、lint、build、strict scan、request-budget tests |
| `browser-smoke-receipt.md` | 真 TOTP session、去敏 Network↔DOM、GET allowlist、unavailable sentinel、0 non-GET |
| `open-findings.md` | 只記錄尚未提供的 server projection；不得以 fake data 關閉 |

## Draft gate status

| Gate | Status | Note |
|---|---|---|
| Scope／write-set draft | PASS | 只規劃 Orders／OrderTracker React query slice |
| Contract freeze | NOT_RUN | 待 exact approval 與 execution fresh read |
| Code/test verification | NOT_RUN | 本次只建立文件，未修改或執行 production/tests |
| Browser GET evidence | NOT_RUN | 待核准後真實登入與既有 DB query-only observation |
| DB change | PASS（0） | 不建立 DB、不 migration、不 seed、不 mutation |

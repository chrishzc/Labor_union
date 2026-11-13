# Module: react-application-shell

## Parent
- domain: `global`
- subsystem: `application-shell`

## Responsibility
組成React應用程式的hash navigation、session/auth shell、nested ErrorBoundary，以及開發伺服器的公開Host與API proxy邊界。預設crash畫面只提供closed recovery，不顯示render exception message；不得擁有任何Domain business rule、root fact或mutation workflow。

## Implementation
- composed page: `ui_react/src/pages/DatabaseBackupPage.tsx` — `#database-backup` in 稽核與系統；backup execution/time/version/status belong to Global migration §9.5. Shell owns navigation only.
- composed page: `ui_react/src/pages/ContractTemplatesPage.tsx` — `#contract-templates` in 稽核與系統；模板保存、啟用及檔案驗證歸 Contract Signing。
- primary: `ui_react/src/App.tsx`
- entry: `ui_react/src/main.tsx` — mounts the Access-owned `FirstRootSetupGate` before `App`, including cached-session and development-bypass composition; root status and bootstrap belong to Access authentication-session.
- primary: `ui_react/src/components/ErrorBoundary.tsx`
- shared presentation: `ui_react/src/components/Drawer.tsx`、`ui_react/src/components/Drawer.css` — all sizes share customer-roster width (desktop min(1400px,94vw), mobile full width); preserve focus trap and unsaved-navigation protection, and return focus to the ongoing-case search when a saved case has left its original row.
- shared presentation: `ui_react/src/components/useSaveValidation.tsx` — 儲存前必填檢查、紅字警告與欄位定位；不擁有業務規則或送出操作。
- shared presentation: `ui_react/src/components/UnsavedChanges.tsx`、`ui_react/src/components/UnsavedChanges.css` — 管理端表單提供草稿差異與原儲存狀態，shell 在切頁／Hash／登出前攔截，Drawer 與各 local navigation 在卸載前共用差異提示；儲存依 Global §2.4 單擊送出，內部使用既有 owner Preview／Apply，不要求人工預覽／核對。
- primary: `ui_react/src/components/MasterLayout.tsx`
- shared presentation: `ui_react/src/components/ManagementPageHeader.tsx`、`ui_react/src/components/ManagementPageHeader.css` — 桌面管理頁共用帳務中心的標題與說明字級、字重、色彩及間距，對齊 MasterLayout 內容區起點。
- presentation: `ui_react/src/pages/NotificationTasksPreviewPage.tsx`、`ui_react/src/pages/NotificationTasksPreviewPage.css` — authenticated `#notifications` 通知事項入口，位於右上系統狀態旁。讀取 LINE 工作台的共用 owner-backed Query，操作轉接原功能；notification presentation 與 LIFF 映射歸 `external-integration/line/mobile-assignment-review`，Shell 不擁有待辦狀態或 writer。
- composed page: `ui_react/src/pages/ClientRegistryPage.tsx`
- composed page: `ui_react/src/pages/ClientRosterPage.tsx`
- primary: `ui_react/vite.config.ts`
- presentation transport: `ui_react/src/api/shared/application_fetch.ts` — optional build-time `/test` public prefix applied by shared transport and direct fetch consumers; no auth／body／business rule changes. `VITE_PUBLIC_PATH_PREFIX` defaults empty, keeping local `/admin/` and root API paths.
- retired page: `ui_react/src/pages/FileSettingsPage.tsx` — 2026-10-30 退役，不再於稽核與系統導航或 App render branches 中掛載。

- retired page: `ui_react/src/pages/line_management/AlertGroupSecurity.tsx` — 2026-10-30 移除 line-security 導航、hash alias 及 render branch；狀態改在既有管理員 LIFF 待辦工作台。

## Contracts
- MasterLayout 內容區以按 currentPage 重置的 ErrorBoundary 包住頁面及頁級 Staff provider；頁面 render／lazy-load 失敗保留導覽，失敗頁卸載清除其 busy 登記。HTTP 5xx 不清除登入，401 沿既有 Session 失效契約。
- `ui_react/vite.config.ts` 的 `WINDOWS_REMOTE_BUILD=1` 關閉 Vite envDir discovery，Windows managed artifact 僅採明確 process build settings，不讀 `.env*`；一般開發模式設定載入不變。建置以 `manualChunks` 切分穩定第三方套件（`vendor-react`、`vendor-icons`、`vendor-utils`），並由 `ui_react/src/App.tsx` 對次要／低頻管理頁面採 `React.lazy`＋`Suspense` 動態分塊載入，保留每日核心工作台同步載入。
- 已登入的案件、客戶、財務、帳務通知設定與 LINE 三個工作頁（`line-management`、`line-notifications`、`line-interface`）掛載 Staff-owned `StaffIdentityProvider`，以 current Staff id 共用公會編號標籤與人員選單排序；頁面切換／登出卸載，無跨 session 身分快取。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — Global UI shell、recovery與closed error presentation。
- `document/架構重整/01_規格基線/25_Access_Control_Production_Cutover與External_Security_Alert正式規格.md` — session/auth boundary。

## Verification
- layout_status: `custom_current`
- integration_root: `ui_react/src/tests/challenger_auth_navigation.test.tsx`
- integration_root: `ui_react/src/tests/react_entrypoint_registry.test.ts`
- integration_root: `ui_react/src/tests/setup.ts` — Vite-configured shared React test environment, DOM cleanup and browser API doubles; no business oracle.
- integration_root: `ui_react/src/tests/domains/global/subsystems/application-shell/modules/react-application-shell/`
- routing: `.arch-map/tests/domains/global/subsystems/application-shell/modules/react-application-shell.md`

## Change triggers
Reconcile when React shell navigation、session/auth composition、ErrorBoundary recovery、closed crash presentation或higher-boundary test location changes。

## Registry entry transition
- 同頁點選「待辦看板」傳遞明確返回請求，由案件工作區沿既有關閉流程回到清單並清除案件深連結；進行中或結果未明的操作不被卸載，稍後解鎖也不自動跳走。
- Canonical `#clients` exposes one 客戶清單 with editable case-detail Drawer; independent 名冊資料 and 變更歷程 tabs are merged. Case／field deep links open the selected Drawer, with case history at the bottom; the virtual-account import tab remains. Legacy `#client-roster`、`#data-browser`／`#databrowser` redirect to `#clients`.
- Data Import no longer composes the six-source Data Browser tab; the archived server API remains read-only for compatibility.
- LINE 專區收斂為四個左側入口：`#line-management`（客服與營運：客服案件、身分與授權、案件群組）、`#line-notifications`（通知與寄送：通知與發送、寄送與異常）、`#line-interface`（LINE 介面設定：圖文選單、表單、LINE 流程圖、引導動作；引導動作深連結為 `#line-interface?tab=guidance`）、`#line-ai-events`（AI 客服工作室，含模型設定分頁）。舊 `#line-llm`／`#line-llm-settings`、`#line-studio`／`#line-liff-studio` 與 `#line-management?tab=push_queue|delivery|richmenu|message_flow|liff` 相容導向對應新頁。

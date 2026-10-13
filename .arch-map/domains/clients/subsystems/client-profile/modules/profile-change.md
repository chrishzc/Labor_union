# Module: profile-change

## Parent
- domain: `clients`
- subsystem: `client-profile`

## Implementation
- `domains/clients/profile.py`
- `subsystems/client_profile/`
- `infrastructure/mysql/client_profile_repository.py`
- `infrastructure/mysql/client_profile_binding_port.py`
- `api/dependencies/client_profile.py`
- `api/routes/client_profile.py`
- `api/schemas/client_profile.py`
- `subsystems/client_profile/registry_query.py`
- `subsystems/client_profile/case_inspection_export.py` — 案件總覽及固定關聯明細 XLSX，保留明細 grain，不重算 owner facts。
- `infrastructure/mysql/client_case_inspection_repository.py` — 以名冊篩選取得案件，固定欄位關聯 Query，無 writer。
- `infrastructure/mysql/client_registry_query_repository.py`
- `api/dependencies/client_registry.py`
- `api/routes/client_registry.py`
- `api/schemas/client_registry.py`
- `api/main.py` — bounded router composition only
- `line/static/profile_update.html`
- `ui_react/src/api/client_registry/`
- `ui_react/src/pages/ClientRegistryPage.tsx`
  - 支援案件／欄位 hash 深連結；管理端 `due_month`／`reject_reason` 走既有 Client Profile Preview／Apply，不擴張 applicant 欄位。
  - `service_type` 使用文字輸入與 Client Profile writer 保存非空原文（最多 100 字），不提供固定選單、不轉換別名，不重算 Orders 結束日。
- `ui_react/src/components/HcmIntakeProfileRepairPanel.tsx` — 由 current HCM review 指定本案可編輯欄位，組合既有 Client Profile Preview／Apply，正式回讀後才刷新警示。
- `ui_react/src/pages/ClientRosterPage.tsx`
- `ui_react/src/components/OrderTermsUnavailableNote.tsx` — 名冊編輯與唯讀詳情共用服務條件提示；日期／天數缺件以 Orders completion Preview 的 actual missing fields 顯示，查詢失敗不推定空值，錯誤代碼置於技術資訊。
- `ui_react/src/components/ClientRosterColumnFilter.tsx` — Excel 式表頭篩選；只讀 allowlisted 全名冊選項，不在單頁上過濾。
- `ui_react/src/components/client_roster_filter_columns.ts` — 表頭與已套用摘要共用欄位標籤、型別及格式。
- `ui_react/src/components/CaseArchitectureBootstrapRepairPanel.tsx` — 僅組合 Case Import-owned bootstrap Q/P/A，完成後重讀名冊 owner facts。

## Dependencies
- inbound: `case-import/hcm-current-workbook-import` — Client Profile email-only 命令 fresh-lock 空白資格並保存 version／事件／receipt；借用 workbook outer UoW，無自有 commit。
- Client-owned `clients.phone` 接受手機／含區碼的市話；Client Profile 與 HCM 匯入共用 `domains/clients/profile.py` 的格式規則與正規化。欄位、writer、版本及 BeClass 獨立聯絡欄位保持既有契約。
- Client-owned `clients.email` 保存 HCM email，管理端 Q/P/A 與名冊／唯讀詳情顯示「HCM Email」；BeClass effective `email` 獨立顯示「BeClass Email」。LIFF applicant 範圍不擴張。
- outbound: `case-import/case-architecture-bootstrap` — `client_finance_bootstrap_required` 時提供明示 Preview／Apply 修復入口；Client Profile／名冊 Query 不自行建立 financial roots。
- outbound: `orders/order-terms` — 名冊 Query 讀取保存條件與版本，不使用 mutation Preview 判定查閱資格；`order_terms_start_date_required`／`order_terms_service_days_required` 或 bootstrap status 缺件時，名冊組合既有 Orders-owned 契約條件 Preview／Apply，成功後重新查詢 Case Import bootstrap status。

## Entrypoints
- `GET /api/v1/admin/registries/clients` — bounded selector with optional query, BeClass effective multi-birth-count, order-status, cooking and allowlisted sort filters; the registry editor exhausts its case-number cursor, while the read-only roster uses offset pagination across all supported sorts.
- `GET /api/v1/admin/registries/clients/filter-options` — authenticated, paginated distinct values for allowlisted roster columns. Typed column filters share the same server predicate across roster pagination and order-accounting export.
- `GET /api/v1/admin/registries/clients/{case_no}`
- `GET /api/v1/admin/registries/clients/{case_no}/change-history` — 依時間／流程順序讀取主要人工變更事件保存的原因，不重複列出同次操作的衍生 projection events。
- `GET /api/v1/admin/registries/clients/export/order-accounting` — 依客戶名冊 current filters 匯出每案件一列的 HCM／Orders／Client Finance XLSX。
- `GET /api/v1/admin/registries/clients/export/case-inspection` — 同名冊 filters 的全部案件；九個工作表分別保存案件摘要、保存資料、派案、排班、客戶義務／流水／分配、月嫂義務／付款分配。authenticated registry reader，固定欄位、不提供 raw table export。
- `POST /api/v1/admin/registries/clients/{case_no}/profile/{preview|apply}`
- Client registry case mapping enters through canonical `orders.case_no -> clients.id`; Client Profile remains the only writer.

## Verification
- layout_status: `custom_current`
- layout_basis: Backend contract tests own Client Profile and BeClass query/mutation boundaries; the mirrored React root owns the case-centered registry editing and bounded read-only roster interaction.
- test_root: `tests/domains/clients/subsystems/client-profile/modules/profile-change/`
- test_root: `ui_react/src/tests/domains/clients/subsystems/client-profile/modules/profile-change/`

## Change triggers
- Reconcile when allowlist、binding evidence、profile/request version、event／receipt／outbox、public route or LIFF readback changes.

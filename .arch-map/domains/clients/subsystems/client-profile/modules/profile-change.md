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
- `infrastructure/mysql/client_registry_query_repository.py`
- `api/dependencies/client_registry.py`
- `api/routes/client_registry.py`
- `api/schemas/client_registry.py`
- `api/main.py` — bounded router composition only
- `line/static/profile_update.html`
- `ui_react/src/api/client_registry/`
- `ui_react/src/pages/ClientRegistryPage.tsx`
- `ui_react/src/pages/ClientRosterPage.tsx`
- `ui_react/src/components/CaseArchitectureBootstrapRepairPanel.tsx` — 僅組合 Case Import-owned bootstrap Q/P/A，完成後重讀名冊 owner facts。

## Dependencies
- outbound: `case-import/case-architecture-bootstrap` — `client_finance_bootstrap_required` 時提供明示 Preview／Apply 修復入口；Client Profile／名冊 Query 不自行建立 financial roots。
- outbound: `orders/order-terms` — bootstrap status 回報 `missing_start_date` 時，名冊先組合 Orders-owned 契約條件 Preview／Apply，成功後重新查詢 Case Import bootstrap status。

## Entrypoints
- `GET /api/v1/admin/registries/clients` — bounded selector with optional query, BeClass effective multi-birth-count, order-status, cooking and allowlisted sort filters; the registry editor exhausts its case-number cursor, while the read-only roster uses offset pagination across all supported sorts.
- `GET /api/v1/admin/registries/clients/{case_no}`
- `GET /api/v1/admin/registries/clients/{case_no}/change-history` — 依時間／流程順序讀取主要人工變更事件保存的原因，不重複列出同次操作的衍生 projection events。
- `GET /api/v1/admin/registries/clients/export/order-accounting` — 依客戶名冊 current filters 匯出每案件一列的 HCM／Orders／Client Finance XLSX。
- `POST /api/v1/admin/registries/clients/{case_no}/profile/{preview|apply}`
- Client registry case mapping enters through canonical `orders.case_no -> clients.id`; Client Profile remains the only writer.

## Verification
- layout_status: `custom_current`
- layout_basis: Backend contract tests own Client Profile and BeClass query/mutation boundaries; the mirrored React root owns the case-centered registry editing and bounded read-only roster interaction.
- test_root: `tests/domains/clients/subsystems/client-profile/modules/profile-change/`
- test_root: `ui_react/src/tests/domains/clients/subsystems/client-profile/modules/profile-change/`

## Change triggers
- Reconcile when allowlist、binding evidence、profile/request version、event／receipt／outbox、public route or LIFF readback changes.

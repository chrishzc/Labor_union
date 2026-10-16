# Module: line-identity-workspace

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
React 身分綁定、待審核、待配對三任務工作區；只呈現 owner-backed query 與既有角色限定 Preview／Apply／fresh readback，不擁有 binding、review、pairing 或 provider root facts。

## Implementation
- primary: `ui_react/src/components/LineIdentityWorkbench.tsx`
- presentation: `ui_react/src/components/LineIdentityWorkbench.css`
- composition: `ui_react/src/pages/LineManagementPage.tsx` — 只替換 binding 工作面。
- client: `ui_react/src/api/line_identity/line_identity_client.ts`
- schema: `ui_react/src/api/line_identity/line_identity_schemas.ts`

## Contracts
- `document/架構重整/01_規格基線/23_LINE身分管理與解除正式規格.md` §8 2026-10-15 React 介面裁決。
- depends_on: `line-identity-management`, `line-identity-review-presentation` — canonical role/query/command contracts。
- LINE 管理頁其他 tabs、舊 standalone review／maintenance／pairing 元件與其直接 consumer 不退役。

## Verification
- UI coverage: `ui_react/src/tests/domains/external-integration/subsystems/line/integration/line_identity_workbench.test.tsx`；沿用上層 LINE integration 歸屬。
- Parent regression: `ui_react/src/tests/line_management_page_real_data.test.tsx`。

## Boundaries
不以 UI 過濾／示範資料替代 server query；raw LINE ID、provider ID、fingerprint 不進一般畫面。Apply 只走既有 typed client，結果不明先讀取最新狀態。

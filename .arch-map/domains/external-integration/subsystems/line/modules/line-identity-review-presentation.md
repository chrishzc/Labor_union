# Module: line-identity-review-presentation

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
呈現LINE-owned身分人工審核的既有list／detail／Preview／Confirm／Apply／receipt／fresh readback。一般畫面以審核對象、決定、狀態與closed結果說明操作；typed error code、provider detail及readback工程術語不得穿透。不得改寫role-scoped binding、審核決定、provider delivery或receipt語意。

## Implementation
- primary: `ui_react/src/components/LineIdentityReviewWorkbench.tsx`

## Contracts
- `document/架構重整/01_規格基線/23_LINE身分管理與解除正式規格.md` — LINE identity review與role-scoped binding owner規則。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/line_identity_review_workbench.test.tsx`
- routing: `.arch-map/tests/domains/external-integration/subsystems/line/modules/line-identity-review-presentation.md`

## Change triggers
Reconcile when LINE identity review presentation、Preview／Confirm／Apply gating、fresh review readback、closed error或focused test location changes。

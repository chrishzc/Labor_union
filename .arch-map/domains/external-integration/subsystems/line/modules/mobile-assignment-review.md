# Module: mobile-assignment-review

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
以persisted-human Session/capability及role-scoped LINE current fact驗證mobile actor，薄轉接既有Scheduling
Assignment Plan Query／Preview／Apply／readback；不建立mobile business state、approval root或writer。

## Implementation
- `api/routes/line_mobile_admin.py`
- `api/dependencies/line_identity.py`
- `line/static/mobile_admin.html`
- `line/static/identity.html`
- `line/static/gateway.html`

## Verification
- layout_status: `custom_current`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_legacy_static_surfaces.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_liff_entrypoint.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_mobile_admin_review_pagination.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_static_mutation_ui.py`

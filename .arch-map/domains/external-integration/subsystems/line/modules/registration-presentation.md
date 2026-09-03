# Module: registration-presentation

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
提供 LINE LIFF 客戶需求調查頁面的呈現與零寫入本地輸入驗證；表單只透過既有 registration Preview／Apply typed endpoint 送出資料，不擁有 provisional registration、案件、補助或銀行資料的業務事實。

## Implementation
- primary: `line/static/register.html`
- entrypoints:
  - `/line-registration`
  - `/api/v1/line/identity/registration/preview`
  - `/api/v1/line/identity/registration/apply`

## Dependencies
- outbound: `case-import` — 只經既有 typed registration Preview／Apply contract 建立或讀取 provisional registration。
- outbound: `external LINE LIFF runtime` — 已驗證身分的瀏覽器 transport；不得以 query string user ID 作身分證明。

## Contracts
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` §2、§4 — LIFF 身分與需求調查的 transport boundary。
- `document/架構重整/01_規格基線/29_LINE服務說明、客服互動與選單角色正式規格.md` §4 — registration Preview 零正式寫入，Apply 交由 current owner contract。

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_liff_entrypoint.py`

## Change triggers
Reconcile when registration page、local input validation、Preview／Apply entrypoint、LIFF identity boundary 或 focused static contract test changes。

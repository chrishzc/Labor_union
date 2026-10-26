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

一般文字、按鈕與成功提示套用目前 LIFF 設定；正式結果狀態及申請編號由實際回執顯示。

## Dependencies
- outbound: `case-import` — 只經既有 typed registration Preview／Apply contract 建立或讀取 provisional registration。
- outbound: `external LINE LIFF runtime` — 已驗證身分的瀏覽器 transport；不得以 query string user ID 作身分證明。

## Contracts
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` §2、§4 — LIFF 身分與需求調查的 transport boundary。
- `document/架構重整/01_規格基線/29_LINE服務說明、客服互動與選單角色正式規格.md` §4 — registration Preview 零正式寫入，Apply 交由 current owner contract。
- Apply 成功呈現待工會核准及申請編號；未核准時 client／beclass IDs 為 null，不宣稱完成綁定或已建立正式客戶。

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/modules/registration-presentation/contract/test_line_registration_presentation.py`

## Change triggers
Reconcile when registration page、local input validation、Preview／Apply entrypoint、LIFF identity boundary 或 focused static contract test changes。

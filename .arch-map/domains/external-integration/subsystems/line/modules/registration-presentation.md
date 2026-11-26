# Module: registration-presentation

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
提供 LINE LIFF 客戶需求調查頁面的呈現與零寫入本地輸入驗證（含一般與非市民共用之 `單胞胎／雙胞胎` 必填閉鎖單選，非市民移除舊「寶寶資訊」文字欄與 `LINE ID` 輸入並同步帶入 `baby_info`）；表單只透過既有 registration Preview／Apply typed endpoint 送出資料，不擁有 provisional registration、案件、補助或銀行資料的業務事實。

## Implementation
- primary: `line/static/register.html`
- 非市民頁面共用表單 presentation，以 server-owned body marker 切換 HCM＋BeClass 合併必填及 typed payload；不由 query string 決定正式身分。
- entrypoints:
  - `/line-registration`
  - `/line-non-citizen-registration`
  - `/api/v1/line/identity/studio-preview/gateway`
  - `/api/v1/line/identity/studio-preview/non-citizen-registration`
  - `/api/v1/line/identity/registration/preview`
  - `/api/v1/line/identity/registration/apply`

一般文字、按鈕與成功提示套用目前 LIFF 設定；正式結果狀態及申請編號由實際回執顯示。

## Dependencies
- outbound: `case-import` — 只經既有 typed registration Preview／Apply contract 建立或讀取 provisional registration。
- outbound: `external LINE LIFF runtime` — 已驗證身分的瀏覽器 transport；不得以 query string user ID 作身分證明。

## Contracts
- `.arch-map/requirements/20_LINE客服與月嫂自助服務正式規格.md` §5.2 — LIFF 設定與非市民登記入口。
- `.arch-map/requirements/29_LINE服務說明、客服互動與選單角色正式規格.md` §2 — Gateway 與非市民登記入口；Preview 不建立正式資料，Apply 送待審申請，由需求 #17B §§3.1–3.2 定義正式核准與復原。
- 非市民 LIFF 的服務方式只顯示「週休 1 日／週休 2 日」；後台手動新案保留「連續服務」。生產方式、居住型態及固定每日服務時段仍與後台對齊。多選問卷欄標示「可複選」，不改 Preview／Apply 的送件與正式核准責任。業務規則以 `.arch-map/requirements/17B_Case_Import與非市民Redis待審正式規格.md` §3.1 為準。
- Apply 成功呈現待工會核准及申請編號；未核准時 client／beclass IDs 為 null，不宣稱完成綁定或已建立正式客戶。

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/modules/registration-presentation/contract/test_line_registration_presentation.py` — 既有靜態案例核對初始化失敗分支會顯示錯誤，並停用表單所有控制項。

## Change triggers
Reconcile when registration page、local input validation、Preview／Apply entrypoint、LIFF identity boundary 或 focused static contract test changes。

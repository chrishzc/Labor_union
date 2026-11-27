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

## Implementation status
- 候選版本 `9dd304bc70b1922058b9bb5d854ca37b3bec5365` 已移除非市民正式頁與表單工作室唯讀預覽的存摺圖片控制項、本地圖片驗證及上傳動作。正式送件明傳 `registration_kind="non_citizen"` 並省略 `passbook_image_id`；銀行文字欄位與原驗證保留，一般市民維持圖片必填及原上傳流程。後端共用 schema、Preview／Apply 與核准收尾的實作見 [Case Import provisional-registration](../../../../case-import/subsystems/case-import/modules/provisional-registration.md#current-implementation)，驗收依 Case Import `NC-PASSBOOK-01～04`。

## Contracts
- [LINE §5.2](../../../../../requirements/20_LINE客服與月嫂自助服務正式規格.md#52-手機審核中心db-版控-liff-設定與非市民入口契約) — LIFF 設定、非市民入口及正式頁／表單工作室預覽邊界。
- [Case Import §3.1](../../../../../requirements/17B_Case_Import與非市民Redis待審正式規格.md#31-非市民進件與配號nc-entrync-formnc-approvalnc-numbernc-stat) — `NC-FORM-01～02` 表單契約；[§5](../../../../../requirements/17B_Case_Import與非市民Redis待審正式規格.md#5-驗收標準) 定義 `NC-PASSBOOK-01～04`。
- [服務閘道 §2](../../../../../requirements/29_LINE服務說明、客服互動與選單角色正式規格.md#2-服務閘道gateway與登記入口規則) 定義 Gateway 與非市民登記入口；送件及正式核准以 Case Import §§3.1–3.2 為權威，後端接線由 [provisional-registration](../../../../case-import/subsystems/case-import/modules/provisional-registration.md#handoff-boundaries) 承接，不引用知識庫 §4 作 registration 契約。
- 非市民 LIFF 的服務方式只顯示「週休 1 日／週休 2 日」；後台手動新案保留「連續服務」。生產方式、居住型態及固定每日服務時段仍與後台對齊。多選問卷欄標示「可複選」，不改 Preview／Apply 的送件與正式核准責任。業務規則以 `.arch-map/requirements/17B_Case_Import與非市民Redis待審正式規格.md` §3.1 為準。
- 收件成功、可離頁提示及原申請重送依 [Case Import §3.1](../../../../../requirements/17B_Case_Import與非市民Redis待審正式規格.md#送件欄位與原申請查詢)。

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/modules/registration-presentation/contract/test_line_registration_presentation.py` — Chromium 驗證非市民正式頁、工作室預覽及市民表單的實際 DOM 與送件序列；既有靜態案例保留初始化失敗時停用控制項等檢查。

- 候選 `9dd304bc…` 的[專項 CI](https://github.com/chrishzc/Labor_union/actions/runs/45854012939/job/140027497325) 已執行並通過 41 個表單／API 案例及 1 個隔離 MySQL 案例，包含正式頁與工作室無圖片入口、非市民零上傳、市民圖片規則及銀行文字驗證。Chromium 使用合成 LIFF／API 回應；不代表正式環境已部署或真實 LINE provider 已驗收。

## Change triggers
Reconcile when registration page、local input validation、Preview／Apply entrypoint、LIFF identity boundary 或 focused static contract test changes。

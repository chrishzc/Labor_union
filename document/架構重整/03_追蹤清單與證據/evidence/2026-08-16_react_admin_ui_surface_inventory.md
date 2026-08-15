---
doc_type: ui-surface-inventory
declared_status: current-read-only-evidence
date: 2026-08-16
owner: global-admin-web-presentation
base_ref: 538c836acfe13e0288a82ab29a5f7c3cc4eae853
---

# React 管理端 UI Surface Inventory

## 1. 用途與證據邊界

本文件保存 Desktop React prototype 的完整可見 UI surface，供 React 遷移計畫逐 action 裁決。
它不是業務規格、實作授權、backend readiness 或 production acceptance；畫面文案、local state、
mock data、`alert()` 與前端公式不得升格為 root fact 或 canonical state machine。

- Source root：`C:/Users/chris/Desktop/project/Labor_union/ui_react/src/`
- 盤點範圍：11 個導航頁、Login、App Shell、共用 Drawer、所有 page-local Drawer／Modal／Tab／
  inline form／二級操作／條件顯示與 disabled gate。
- 方法：逐檔展開 component tree、fields、badges、actions、conditional render、local handlers 與
  mock source；再以 `KEEP | ADAPT | REPLACE | RETIRE | DECISION_REQUIRED` 記錄 backend disposition
  候選。候選不是正式裁決，仍受正式規格、entrypoint governance 與 Part activation gate 約束。
- 驗證方式：source／Graphify／`rg` 唯讀盤點；沒有執行 npm、pytest、browser mutation 或 DB tooling。

## 2. 全域定量與共同發現

- Desktop 有 11 個導航頁；整個 `src/` 沒有 `fetch(`、Axios 或 `/api/v1/` 呼叫，真實 React API
  coverage 為零。
- Orders 有 4 個 Drawer；Order Tracker 有 1 個雙 Tab Drawer；其餘頁面有 12 個 Drawer，合計
  17 個 Drawer。另有 Orders add-staff inline modal、Scheduling add-holiday modal 與多個 inline form。
- 非 Orders 頁面共有 130 個 `<button>`、35 個 input、8 個 select、5 個 textarea、51 個 alert、
  6 個 confirm、1 個 prompt；Shell 另有 6 個 button，共用 Drawer 另有 close button。
- 非 Orders 頁面未找到 `disabled` 或 `aria-disabled`；多數 validation 只在 click handler 以 alert
  阻擋。Orders 雖有少數 disabled 條件，仍有大量理由空白、stale、double-submit 與錯誤順序缺口。
- App 只以 local boolean 作 auth guard，無 router、deep link、URL、session restore 或真 principal。
- 共用 Drawer 可由 Escape、backdrop、X 或 footer 關閉，但沒有 `role="dialog"`、`aria-modal`、
  focus trap／restore、body scroll lock 或 dirty draft confirmation。

## 3. Orders 與 Order Tracker

### 3.1 Component tree

```text
OrdersPage
├─ Header：+新建訂單（alert placeholder）
├─ 8 個 stage filters
├─ Order cards
│  ├─ identity/stage/contact/address/date/time/cooking/floor fee
│  ├─ deposit/contract/caregiver/match/lock/blocker badges
│  └─ terms / matching / date / cancel / settlement-only reopen
├─ Date-confirmation Drawer [wide]
│  ├─ actual-start/rest fields、holiday overrides、computed snapshot
│  ├─ send schedule、customer/staff confirmation
│  └─ active-assignment action（gatePassed only）
├─ Matching-workbench Drawer [xl]
│  ├─ candidate pool + add modal + reset collapsible
│  ├─ Info-1/Info-2 send/resend + manual willingness
│  ├─ resume selection/send
│  └─ customer decision + waiting lock
├─ Contract Drawer [wide]
└─ Cancellation/refund Drawer [wide]

OrderTrackerPage
├─ sticky 7-stage stepper
├─ stage sections + order cards + blockers
└─ SOP/Notification Drawer [wide]
   ├─ SOP tab：11 checklist rows
   └─ Notification tab：outbox records + failure replay
```

### 3.2 Orders 主頁與四個 Drawer

- Header、stage filters、cards：`pages/OrdersPage.tsx:448-623`。卡片顯示 id、stage、客戶、完整電話、
  地址、日期、實際開始日、時段三欄、下廚、樓層費、訂金、合約總額、月嫂、match score、waiting
  lock 與 blocker。「新建訂單」只有 alert；媒合按鈕只在 intake stage disabled。
- Date Drawer：`pages/OrdersPage.tsx:626-833`。actual-start 與 rest note 為文字輸入；中秋／國慶
  checkbox 沒有 state／handler；結束日、30 日、+5 休息日與 buffer range 為硬編碼；send 始終 enabled；
  雙方確認可由電話補登；只有 local `gatePassed` 顯示轉正式服務按鈕。
- Matching Drawer：`pages/OrdersPage.tsx:835-1365`。包含加入月嫂 modal、重設理由、候選卡、Info-1／
  Info-2、send/resend、人工意願、履歷勾選、客戶決策與 waiting lock。候選卡沒有完整 availability／
  qualification gate；多個理由欄空白時按鈕仍 enabled；Info-2 沒有 Info-1 prerequisite。
- Contract Drawer：`pages/OrdersPage.tsx:1367-1427`。只有條款、月嫂合約、訂金、客戶合約三類
  read-only evidence；沒有文件 preview/send/download/retry/repair。
- Cancellation Drawer：`pages/OrdersPage.tsx:1429-1508`。Apply 始終 enabled 且只 alert。退款公式在
  `pages/OrdersPage.tsx:400-440` 由前端依 stage 推算；active case 硬編已服務 15 天與 NT$5,000
  penalty，contract/date case 固定扣訂金 20%。所有公式必須從正式 UI 移除。

### 3.3 Tracker、11 步 SOP 與通知

- Tracker 以 7 個 local stage 顯示 intake、matching、client review、contract/deposit、date confirmation、
  active、settlement；卡片另顯示 `waitingFor`、`missingFields` 與 date confirmation：
  `pages/OrderTrackerPage.tsx:7-198`。
- SOP Drawer：`pages/OrderTrackerPage.tsx:200-311`。每列只有 step、status、timestamp、notes，沒有
  row action。11 步定義位於 `api/mockData.ts:230-241`：進件、候選、LINE 詢問、月嫂意願、履歷、
  月嫂契約、訂金、客戶契約、日期確認、正式服務、完工／尾款／薪資。
- Notification Tab：`pages/OrderTrackerPage.tsx:313-366`。雖標示「只顯示此訂單」，兩筆資料固定且
  不依 selected order；manual replay 只有 alert，沒有 reason、idempotency、loading、receipt 或結果。
- `drawerTab` 不隨訂單切換 reset，存在把上一筆訂單的 tab context 帶到下一筆的風險。

### 3.4 Orders disposition 候選

| Surface | 候選 disposition |
|---|---|
| Filters／cards／SOP | `ADAPT` 為 bounded Query 與跨 Domain read model；React 不推導 target stage |
| Candidate pool／willingness | `ADAPT`；候選聯繫、正式 plan、delivery、customer decision 分開 |
| 正式推薦 | 內部 shortlist 可多位；一般只正式推薦一位。只有 server 證明單一月嫂無法覆蓋全部正式日期時，才允許 2–4 位連續、不重疊 segments 作為一個整體正式推薦；不是多位競爭候選供客戶拼選 |
| Date Drawer | `REPLACE` local 計算；改用 server Query／Preview／Apply 與 typed confirmation projections |
| Contract Drawer | `ADAPT` 到 Contract Signing typed view 與文件操作；delivery 不等於簽回 |
| Cancellation／refund | `REPLACE` 全部前端公式；由 Orders／Client Finance Preview→Apply→receipt |
| Reopen／new order | 在正式 owner、entrypoint、state machine 確認前為 `DECISION_REQUIRED` |
| Notification tab | `REPLACE` static rows；建立 order-scoped delivery timeline 與受控 replay flow |

### 3.5 已人工確認的 Orders 決策

1. 一般情況只正式推薦一位月嫂；只有 server 以 confirmed service dates、fresh availability 與完整
   coverage evidence 證明單一月嫂無法覆蓋全部日期時，才允許 2–4 位月嫂的連續、不重疊分段
   方案作為一個整體正式推薦。客戶不能同時收到多位競爭候選並自行拼選。
2. `service_completed`、`client_finance_settled`、`staff_payout_reconciled` 是三個 owner projection，
   不得合成單一可寫 status 或一鍵共同 Apply。
3. 緊急聯絡電話缺漏只顯示 warning，允許繼續媒合；warning 必須由 server typed view 提供，React
   不得自行由 nullable field 推導。

## 4. Scheduling

- Source：`pages/SchedulingPage.tsx:97-174,390-1310`。
- 四個 tabs：甘特檔期投影、突發請假代班、國定假日、請假 Inbox；一個 wide 精算 Drawer；一個
  新增假日 modal。
- 甘特頁有案件 select／清除、月份三鍵、搜尋、四 filter、六 legend、service／buffer／leave／
  waiting bars、ghost projection 與快速 lock。月份三鍵無 handler；ghost quick-lock 為 alert。
- 請假代班有 request cards、代班／順延 radio、代班人 select、Apply；Inbox 有受理轉排班與以
  native prompt 退件。假日 table 可即時 toggle rest/special-pay、delete、add。
- 精算 Drawer 包含 order、actual-start、Sunday、批次／單筆 custom rest、holiday overrides、
  service/rest/end/buffer outcomes 與 Save Apply；結果均由 local state 推算。
- 候選：保留甘特資訊架構與 Preview outcome；`ADAPT` inbox／leave flow；`REPLACE` local date/payroll／
  quick-lock mutation；retired rest-date mutation 不得復活；假日 policy、lock 語意與管理權限為
  `DECISION_REQUIRED`。

## 5. Staff

- Source：`pages/StaffPage.tsx:29-105,200-846`。
- 三 tabs：名冊資格、媒合偏好、不可服務期間；一個履歷證照 Drawer；一個新增不可服務 inline form。
- 名冊卡顯示 status、區域、年資、問卷、備註、技能、良民證／體檢；有證照警示、離職 confirm、
  「新增人員」alert。Drawer 顯示背景、問卷、notes、三種文件狀態與 masked bank info，但沒有附件
  upload control。
- 偏好包含 min/max days、daily hours、只讀 cooking chips、notes；不可服務包含 long leave／paused、
  range、reason、cancel。
- 候選：`KEEP/ADAPT` 名冊、偏好、availability、retirement views；`REPLACE` local save/cancel/retire；
  staff master create/edit、證照 owner、銀行資訊權限為 `DECISION_REQUIRED`。

## 6. Finance

- Source：`pages/FinancePage.tsx:68-180,240-791`。
- 五 tabs：客戶收款、月嫂應付、退款、政府補助、銀行 facts；四個 Apply Drawer。
- Tables 顯示 receipt、payout、refund、subsidy 與 bank allocation 狀態；另有 XLSX、adjustment、bank
  import 二級入口。
- 四 Drawer 分別顯示 obligation/bank match、薪資與帳戶、退款拆分、補助代墊規範；沒有 input、
  Preview、confirm、receipt 或 disabled gate，直接 local success。
- 候選：保留 bounded tabs／detail presentation；`REPLACE` 所有直接 success 為各 owner 的
  Preview→Apply→receipt；generic export／adjustment／import alert 為 `RETIRE/REPLACE` 候選；操作角色、
  清冊交接、帳號 masking 與 subsidy recovery UX 為 `DECISION_REQUIRED`。

## 7. Anomalies

- Source：`pages/AnomaliesPage.tsx:5-38,130-457`。
- KPI、七 domain filters、四 status filters、severity/status cards、open-only claim 與 recovery Drawer。
- Drawer 顯示 overview、root-fact evidence、suggested deep-link、resolve reason；resolved 時隱藏 form。
- 候選：保留分類、evidence 與 resolved conditional；`ADAPT` typed claim／deep-link／resolve；`REPLACE`
  local alerts；claim lease、reopen、哪些 anomaly 可人工 resolve 為 `DECISION_REQUIRED`。

## 8. LINE Management

- Source：`pages/LineManagementPage.tsx:61-213,221-858`。
- 六 tabs：tickets、rich menu、identity binding、notification rules、FAQ、order groups；一個 rule Drawer。
- Rich Menu 有三 role preview 與 12 個非互動 menu tiles、兩個 read-only LIFF URL；binding 有 invite／
  unbind；rules editor 使用 uncontrolled `defaultValue` 且 Save 不回寫；FAQ 只讀；groups 只有空狀態。
- 候選：`ADAPT` typed Customer Service／Identity；`REPLACE` publish/invite/rules/FAQ/groups fake actions；
  notification catalog、Rich Menu version/rollback、FAQ lifecycle、group scope 與 LIFF config owner 為
  `DECISION_REQUIRED`。

## 9. Data Import

- Source：`pages/DataImportPage.tsx:17-83,87-344`。
- 六 category cards：HCM、HCM historical、BeClass、Staff historical、Historical Order、bank statement；
  共用一個 Drawer。每卡 Preview／Apply 都只開同一 Drawer。
- Drawer 以 filename text 代替 file input，使用 random fingerprint／固定 sample；dirty-row correction／
  override 只有 alert；`APPLY` 輸錯時按鈕仍 enabled。
- 候選：保留 domain-separated cards 與 Preview/dirty-row presentation；`REPLACE` generic workbench、random
  result 與 manual override；歷史入口、dirty-row authority、background job 與 active import catalog 為
  `DECISION_REQUIRED`。

## 10. Data Browser

- Source：`pages/DataBrowserPage.tsx:5-28,142-327`。
- 六 source tabs、search/count、snapshot table、一個 immutable JSON Drawer；唯一二級操作是 Copy JSON。
- 候選：保留 read-only metadata/raw split；`ADAPT` allowlisted typed query 與 redaction；mock archive names、
  PII copy/download、source correction 是否獨立入口為 `DECISION_REQUIRED`。

## 11. Reports

- Source：`pages/ReportsPage.tsx:55-216,323-626`。
- 四 KPI、三 sheet tabs、單一 XLSX alert。三 sheets 分別是案件受理／審核、補助、服務中／工時；
  無 date/filter/export parameters。
- 候選：現有 named reports 可 `ADAPT`；generic weekly workbook 與 hard-coded KPI 為 `REPLACE/RETIRE`
  候選；三 sheets 是否 current scope、統計口徑、PII、下載權限為 `DECISION_REQUIRED`。

## 12. Account、Login 與 Shell

### 12.1 Account

- Source：`pages/AccountManagementPage.tsx:30-220,230-658`。
- 四 tabs：users、TOTP guide、audit、jobs；兩 Drawers：Add User、TOTP setup。
- User cards 顯示 enabled、username/email/login/IP/TOTP/session；有 Bind TOTP、revoke session、enable／
  disable。TOTP Drawer 顯示 fake QR 與明文 demo secret；jobs 為固定 health cards。
- 候選：`ADAPT` password auth、audit、system/job queries；`REPLACE` account/TOTP/session mutations；TOTP、
  user lifecycle、same-capability policy、session admin 與 jobs placement 為 `DECISION_REQUIRED`。

### 12.2 Login

- Source：`pages/LoginPage.tsx:10-59,68-209`。
- Stage 1 有 username/password/show/remember/forgot；只驗非空，password 預填 bullet 字元；remember 無
  state，forgot 只 alert。Stage 2 任意六位數即登入；沒有 loading、disabled、lockout 或 typed error。
- 候選：保留登入卡 presentation；`ADAPT` 真 password session；`REPLACE` local success；TOTP、remember、
  password reset、reload/new-tab session policy 為 `DECISION_REQUIRED`。

### 12.3 App Shell／Drawer

- Source：`App.tsx:18-44`、`components/MasterLayout.tsx:25-149`、`components/Drawer.tsx:4-50`。
- 11 pages 以 conditional mount 切換；section switch 自動回第一頁；system status 固定 Online、notification
  固定 3、profile click 直接 logout。
- 候選：保留三區導覽／slim sidebar 視覺；`REPLACE` local auth/navigation與硬編碼 status；route map、
  deep-link、reload、新分頁、logout、drawer unsaved-close 與 accessibility 為 `DECISION_REQUIRED`。

## 13. Phase 0 action inventory gate

每一個 button、form、link、download、upload、polling、replay 與 automatic refresh 必須在後續
machine-checkable inventory 建立一筆 action identity，至少記錄：

- actor／capability、business scenario、page／drawer／tab、positive/negative example；
- Query／Preview／Apply／external intent／presentation-only 分類；
- owner、SSOT、root facts、derived views、state transition、completion criteria；
- accounting impact、external delivery、outer UoW、version／fingerprint／idempotency／receipt；
- current route→application→Domain→repository/UoW→tests chain；
- disposition、replacement、entrypoint compatibility、rollback／forward-written-data compatibility；
- loading／empty／error／stale／conflict／timeout／abort／replay／partial-failure UI states；
- browser/API/DB oracle 與 acceptance scenario identity。

任何 `DECISION_REQUIRED`、raw dict、message parsing、unknown owner、fake success、前端業務公式或缺少
replacement 的 `RETIRE` 均不得進入 production React write set。

## 14. 尚待人工確認

1. Orders summary 的主 badge 顯示哪個 owner projection；是否需要只讀的「營運結案」聚合標籤。
2. Emergency contact 的 owner、stable warning code、masking、repair entry 與明確不受阻 actions。
3. Auth reload／new-tab 是否接受 memory-only bearer 重新登入；TOTP／remember／reset 是否進產品範圍。
4. 各頁 mutation 的 operator/capability；尤其 Finance、Subsidy、Scheduling、Staff lifecycle、LINE publish。
5. Data Import 六 category、Reports 三 sheets、Data Browser 六 sources 的 current canonical catalogs。
6. Router/deep-link、Streamlit compatibility window、forward-written data、entry replacement 與 rollback policy。
7. Global PII、upload/download、browser cache、external adapter test isolation 與 Drawer accessibility／dirty-close policy。

## 15. DB gate

本 inventory 沒有 DB write set；所有 DB gate 為 `NOT_RUN`。任何後續 slice 若出現 schema、seed、
backfill 或 migration，必須另立 Work Package 並完整執行七項 DB gate。總結：`DB_CHANGE_NOT_READY`。

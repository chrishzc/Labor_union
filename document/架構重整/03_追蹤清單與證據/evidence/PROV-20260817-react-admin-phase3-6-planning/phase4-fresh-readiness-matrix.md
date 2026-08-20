# Phase 4 fresh readiness matrix（2026-08-17）

本文件是目前工作樹的唯讀 evidence，不構成 production、外部副作用或資料庫變更授權。判定以正式
規格、active Work Package 狀態、live route/client/page與focused tests交叉比對；畫面存在或backend
route存在不等於可接線。

| Surface／capability | Current status | Exact disposition |
|---|---|---|
| HCM current workbook | `completed-preview-only / apply-blocked` | 真檔multipart Preview已接；Apply仍受outer-UoW、terminal receipt/re-query與warning disposition gate阻擋 |
| HCM historical overwrite | `retired` | 不得復活whole-row overwrite |
| BeClass／Staff historical／Historical Orders | `not-connected` | 卡片維持locked；先完成各自public contract，再建立bounded client |
| Finance Import／Bank Facts | `not-connected` | backend有既有能力，但React無client；Phase4A Finance Import hardening仍proposed |
| FinancePage | `mock-unsafe` | 五組local資料與核銷／出款／退款／補助假成功仍存在；不得用build PASS冒充real-data |
| Client Finance | `backend-public-contract-gap` | `client_payments.py`仍有raw dict／auth缺口；legacy mutation 410不能當successor |
| Staff Payout | `typed-backend / react-missing` | backend workflow較完整，但React bounded client、adapter與flow tests均缺 |
| Accounts Payable | `backend-public-contract-gap` | preview缺admin auth且公開完整銀行／身分資訊，hardening前不得接React |
| Subsidy Reports | `backend-authority-gap` | raw response、auth/masking及root-fact authority未閉合 |
| LINE Customer Service／Identity | `real-data-local-validated / runtime-blocked` | typed query與兩條mutation已接；缺fresh controlled browser data |
| LINE Rules／Rich Menu | `query-only-local-validated` | 四個GET已接；save/delete/publish/retry維持disabled |
| LINE Delivery Tasks | `backend-public-contract-gap` | route仍raw dict並含敏感payload/provider資訊；React client不存在 |
| Knowledge FAQ | `mock / backend-public-contract-gap` | React仍硬編FAQ；backend query raw且application在Query後commit |
| LINE Order Groups | `query-partial / mutation-owner-gap` | 後台create/release不可由現有provider group流程推導 |

## Safe dependency order

1. 先核准並完成backend public-contract／outer-UoW successors。
2. 每一bounded domain凍結Pydantic success/error contract後，才建立React client與adapter。
3. `DataImportPage.tsx`、`FinancePage.tsx`、`LineManagementPage.tsx`各自只能有一位presentation writer。
4. 第一個會產生warning task的Import Apply前，Anomaly／Import Warning disposition必須能查詢與處置。
5. 所有finance／provider mutation必須走Preview→Apply→receipt→re-query；禁止local state與`alert()`成功。

## Authority result

本輪查得尚未完成的Phase 4A／4B／4C backend與React successor Work Packages仍為`proposed`，
Phase 4B-S-H為`blocked`；HCM Preview與LINE rules／menu Query的既有local-validated成果不等於
Apply／Mutation、真browser或entry cutover ready。未取得各自exact人工核准並通過全部前置前，只能維持
fail-closed UI與read-only evidence，不得開始production writer。

## DB gate

Scope `PASS`（唯讀inventory）；Change Inventory、Static Release、Descriptor、Read-only Plan、Engine
Verification、Developer Acceptance均`NOT_RUN`；結論`DB_CHANGE_NOT_READY`。

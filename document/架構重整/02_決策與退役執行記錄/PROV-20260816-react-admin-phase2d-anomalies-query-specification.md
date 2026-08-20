---
doc_type: implementation-specification
declared_status: approved
identity: PROV-20260816-react-admin-phase2d-anomalies-query
date: 2026-08-16
owner: Anomalies / React Integration
domain: Anomalies
subsystem: Alert Query / Import Warning Tracking / React Presentation
authority: human-approved
---

# React 管理端 Phase 2D：Anomalies／Import Warning 真實唯讀接線規格

## 0. 目的與成功邊界

保留既有 `AnomaliesPage` 的 KPI、兩層篩選、異常卡片與修復 Drawer 視覺結構，將六筆內嵌
假異常、local claim／resolve 與跳轉 alert 換成真實 API Query、嚴格 runtime decoder 與明確
`unavailable` 狀態。

本波只做 Query：

1. canonical anomaly summary 清單；
2. import warning current tasks 清單；
3. server 已提供的 staff-calendar／import-center navigation metadata；
4. loading、empty、typed error、abort、stale-response discard 與重新整理。

本波不啟用 claim、resolve、warning transition、projector retry、definition scan 或任何 owning Domain
Preview／Apply。人工 resolve 只代表工作進度且不代表根因已修正；在 Phase 3 mutation 工作包核准前，
相關原有控制位置必須保留但 native disabled。

## 1. Business scenario

已通過帳密 Challenge 與 TOTP 的工會人員進入「異常與退款處理中心」，需要：

- 看見目前 canonical anomaly projection，而不是六筆固定範例；
- 分辨 `blocking`、`warning` 與 open／claimed／resolved；
- 看見 import warning 的 field-level task，不把同一來源的多欄警示合併成一筆可整案放行的假操作；
- 從 server 提供的 neutral navigation metadata 前往排班或對應匯入中心；
- 在 backend 尚未提供 strict typed 顯示摘要、timeline 或 recovery context 時，看見原位 unavailable，
  而不是 raw JSON、前端猜測或 mock fallback。

## 2. 權威與不變量

- Global：`01_規格基線/00_Global_共同契約.md`。
- Domain：`01_規格基線/06_Anomalies_Domain.md`。
- 最新銀行／帳務異常邊界：`22_銀行流水匯入與帳務異常處理正式規格.md`。
- React 遷移主計畫：`document/功能開發計畫/React管理端遷移與UI真實業務流程驗收計畫.md`。
- UI inventory：`03_追蹤清單與證據/evidence/2026-08-16_react_admin_ui_surface_inventory.md`。

不可破壞的不變量：

1. source Domain 根事實是異常 predicate SSOT；Alert／UI status 不是 Domain gate。
2. Query 唯讀，不 scan、不 claim、不 resolve、不刷新 projector、不寫 tracking event。
3. generic anomaly workflow 與 import warning tracking 是兩套不同狀態機，不得只靠中文 label 合併。
4. `resolved` 只是人工作業進度；根條件仍存在時可 reopen。
5. import warning 是 field-level occurrence；UI 分組不改變 occurrence identity。
6. HCM／BeClass／Historical／Finance 的實際修正只能回 owning Domain typed Preview／Apply。
7. frontend 不解析 `display_snapshot`、`timeline`、`root_fact_snapshot` 或 raw details 推導標題、原因、
   金額、日期、blocker 或 action。
8. 只有 server receipt 才能顯示 mutation 成功；本波沒有 mutation receipt。

## 3. 本波核准 HTTP contract

### 3.1 Anomaly summaries

`GET /api/v1/anomalies`

固定 query：

- `active_only`: UI filter 決定；預設 `true`。
- `limit`: `1..200`，預設 100。
- `offset`: 非負整數。
- `include_snapshot`: **固定 `false`**。

只允許消費 `BaseResponse[list[AnomalySummaryView]]` 的下列欄位：

| JSON path | Type | UI disposition |
|---|---|---|
| `fingerprint` | 64-hex string | internal selection identity，不進 log／文案 |
| `definition_code` | non-empty string | 顯示 stable code |
| `source_domain` | non-empty string | allowlisted presentation label；unknown 顯示「其他」 |
| `source_identity` | string | `INTERNAL_ONLY`；本波不得直接 render |
| `source_version` | integer >= 0 | Drawer 顯示版本 |
| `severity` | `warning | blocking` | map 到既有 Warning／Critical 視覺 |
| `predicate_active` | boolean | 顯示 active/inactive，不推 Domain blocker |
| `workflow_status` | `open | claimed | resolved` | generic anomaly workflow badge |
| `workflow_version` | integer >= 0 | Drawer 顯示版本 |
| `display_snapshot` | `null` | 因 `include_snapshot=false`；非 null 固定 decode failure |
| `staff_calendar_navigation` | nullable `{staff_id, target_date}` | 可顯示前往排班入口，不自動 Apply |

禁止本波 client 呼叫 `include_snapshot=true`。`display_snapshot` 目前是 `dict[str, Any]`，不屬可穿透
render 的 typed contract。

### 3.2 Import warning tasks

`GET /api/v1/import-warning-tracking/tasks`

query：`active_only`、`limit 1..200`、`offset >= 0`。

允許消費 `ImportWarningTaskView` 全部已宣告欄位：

- `occurrence_identity`
- `owning_lane`
- `logical_code`
- `field_path`
- `masked_subject`
- `issue_codes: string[]`
- `tracking_status`
- `tracking_version >= 1`
- nullable `evidence_reference`
- `display_message`
- nullable allowlisted `navigation_action`

`tracking_status` 必須限定為：
`open | awaiting_external_confirmation | response_recorded | reimport_requested | closed | auto_resolved`。

`navigation_action` 只允許後端 Pydantic enum；frontend map 到已存在的 hash page：

| navigation_action | React hash |
|---|---|
| `hcm_import_center` | `#data-import` |
| `historical_order_import_center` | `#data-import` |
| `client_beclass_import_center` | `#data-import` |
| `staff_beclass_import_center` | `#data-import` |
| `finance_import_recovery_center` | `#data-import` |

不得把 `owning_lane` 或 message 當 URL，也不得附帶 raw source payload。

### 3.3 明確排除的現有 routes

| Route | 本波 disposition | 原因 |
|---|---|---|
| `GET /api/v1/anomalies/{fingerprint}` | `BACKEND_GAP` | timeline 與 display snapshot 含 raw dict |
| `GET /api/v1/anomaly-recovery/{fingerprint}` | `BACKEND_GAP` | root fact／workflow timeline 仍為 raw dict |
| `GET .../actions/{action_key}` | `OUT_OF_SCOPE` | Phase 3/4 owning Domain recovery |
| anomaly claim／resolve | `OUT_OF_SCOPE` | mutation；需 version/idempotency/receipt flow |
| warning referral | `OUT_OF_SCOPE` | 本波 tasks 已含 neutral navigation；error envelope 尚未完整 Global typed |
| warning preview／apply | `OUT_OF_SCOPE` | Phase 3 mutation |
| scan／projector retry | `OUT_OF_SCOPE` | operator maintenance mutation |

任何 Writer 不得因 route 已存在就擴張 client 方法。

## 4. Presentation contract

### 4.1 必須保留

- page header／subtitle；
- 四張 KPI 卡；
- category filter bar；
- status pills；
- anomaly cards；
- diagnostic/recovery Drawer；
- root evidence、guided recovery、resolve form 的原 UI 槽位。

### 4.2 真實資料呈現

- KPI 只統計目前已載入的 generic anomaly summaries；文案改為「目前載入」，不得冒充全庫總數。
- import warning 使用獨立區塊與自己的 tracking-status badge；不得併入 generic claimed/resolved KPI。
- anomaly card 至少顯示 definition code、source domain label、severity、workflow status、predicate state。
- server 未提供 typed title／description／masked related entity 時，原位置顯示
  `後端尚未提供 typed 顯示摘要`；不得從 definition code 或 source identity 生成業務描述。
- Drawer 可由 summary 開啟，顯示 safe scalar metadata；root evidence、timeline、available actions 原位顯示
  `後端 typed detail/recovery contract 尚未開放`。
- `staff_calendar_navigation` 存在時可顯示 anchor 到 `#scheduling`，並顯示 server staff id／date；
  不存在時不產生假 navigation。
- import warning `navigation_action` 存在時可顯示 anchor 到 `#data-import`。

### 4.3 Category presentation map

只做技術 owner label，不推導業務狀態：

- `case_import | finance_import` → 匯入資料
- `line | line_integration | matching` → 媒合推播
- `scheduling | assignments` → 排班調度
- `client_finance` → 客戶帳務
- `staff_payables | payroll` → 月嫂薪資
- `government_subsidy` → 政府補助
- 其他 → 其他

既有 category pills 保留並新增「其他」。未知 domain 不得被丟棄或硬塞到任一既有分類。

### 4.4 Query state

每個 query family 使用獨立 discriminated union：

`idle | loading | ready | empty | error | loading_more`。

- 首次載入同時發出兩個 GET，但錯誤互相隔離；Anomalies 成功不因 Import Warning 失敗而消失。
- page unmount／reload／filter supersession 必須 AbortController + generation guard。
- stale response 不得覆蓋較新 filter/result。
- 相同 offset 不重複 append；重複 identity 且 payload 不同時 fail closed，不採 first/last wins。
- response length 等於 limit 時顯示「載入更多」；短於 limit 才標 end-of-list。
- retry 只重試失敗的 query family。

## 5. Mutation safety

本波所有既有 mutation controls 必須：

- 原位置存在；
- 使用 native `disabled`；
- 具 stable `data-control-id`；
- 無 onClick fake handler；
- 點擊測試證明 0 non-GET request、0 alert、0 confirm、0 local business-state change。

至少包括：

- `anomalies.card.claim`
- `anomalies.drawer.resolve`
- `anomalies.drawer.resolve-reason`
- import-warning transition／override（若 UI slot 存在）

Drawer close、filters、status pills、reload、load-more 與 hash navigation 是 presentation control，非 mutation。

## 6. Strict client rules

1. 每次 request 即時讀取 current memory Session token；module load 不快取。
2. caller 不能覆寫 `Authorization`；token 缺失須在 request 前 fail closed。
3. new Anomalies client 自有 strict envelope schema；不得使用 shared decoder 的 defaults／optional envelope。
4. production client/schema/adapter 禁止：
   `z.any`、`z.unknown`、`z.record`、`.passthrough()`、`.catch()`、`.default()`、`.coerce()`、
   `.preprocess()`、`.transform()`、`as any`、`unknown as`。
5. server-required key 必須 required；nullable 不等於 optional。
6. unknown envelope/nested field、missing required、wrong primitive、invalid enum、null violation 全部
   轉成 `ApiDecodeError`，不得降級成 empty/unavailable。
7. typed 401／403／409／503 依 live endpoint status matrix處理；不得依中文 message 分支。
8. fingerprint、source identity、token、correlation id 不進 DOM、console、snapshot 或 receipt。

## 7. Out of scope

- 修改 backend production route/schema/application/Domain/repository。
- claim／resolve／warning transition／recovery Preview／Apply。
- 直接顯示 raw snapshot、timeline、source payload 或完整 PII。
- 修改 shared transport/runtime decoder/Auth、App router、其他十頁。
- DB schema、migration、seed、backfill、fixture reset。
- Streamlit retirement、entry cutover、launcher、CORS、deployment、external LINE。
- 重新設計既有 UI hierarchy。

## 8. Completion definition

只有以下全部成立才可標 `completed-local-validated`：

1. contract matrix逐欄凍結，且 raw/BACKEND_GAP 明確；
2. 兩個 GET clients strict decode 與 negative tests通過；
3. production dependency closure 不再觸及 `mockData.ts` 或內嵌六筆假異常；
4. KPI/filter/card/Drawer/import-warning 區塊以 server DTO sentinel 驗證；
5. mutation controls native disabled且 0 non-GET；
6. full frontend、lint、build、focused backend tests、UTF-8、write-set audit通過；
7. 真 Chrome 以已完成 Phase 2C Session 發出兩個 GET，並以 Network→DOM 證明 success 或合法 empty；
8. 無真實 mutation、無 DB、無 external side effect。

## 9. DB gate

| Gate | Status | Reason |
|---|---|---|
| Scope gate | PASS | query-only React/API contract test，0 DB write |
| Change inventory | NOT_RUN | 無 DB change |
| Static release gate | NOT_RUN | 無 migration release |
| Descriptor gate | NOT_RUN | 無 schema object |
| Read-only plan gate | NOT_RUN | 不執行 DB tooling |
| Engine verification gate | NOT_RUN | 不需 DB engine mutation evidence |
| Developer acceptance gate | NOT_RUN | 不操作 developer DB |

總結：`DB_CHANGE_NOT_READY`；本規格不授權任何 DB 變更。

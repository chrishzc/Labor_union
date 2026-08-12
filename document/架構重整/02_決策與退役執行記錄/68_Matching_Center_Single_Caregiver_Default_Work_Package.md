---
doc_type: work-package
declared_status: in-progress
date: 2026-08-12
owner: Orders / Assignments / Scheduling / Matching / LINE Integration
scope: Single-caregiver default matching, typed candidate coverage, confirmed service dates, customer and caregiver schedule delivery and confirmation, and formal-assignment gate
write_set: [document/架構重整/01_規格基線/01_Orders_Domain.md, document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md, document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md, domains/orders/, domains/scheduling/, subsystems/orders/, subsystems/scheduling/, subsystems/line/, api/, ui/pages/order/, ui/pages/scheduling/, infrastructure/mysql/, db/schema_parts/, db/migration_releases/, tests/]
acceptance: Single-caregiver is the default, multi-caregiver remains an explicit fallback, candidate coverage is typed, confirmed service dates produce versioned customer and caregiver schedule snapshots, and formal assignment is blocked until both required confirmations pass.
out_of_scope: Automatic schedule delivery, automatic reminders or expiry escalation, payroll or finance formula changes, and removal of multi-caregiver capability.
---

# 68 Matching Center Single-Caregiver Default Work Package

## 文件狀態

- 文件類型：`work-package`；由功能開發計畫轉入正式架構執行記錄。
- 功能狀態：`In-progress`
- 實作狀態：`partial-implementation`
- 優先級：`P0／與「休假代班天數精算與行事曆差異預覽修復」並列目前最高優先`
- 建立日期：2026-08-10
- 更新日期：2026-08-12
- Owner：`Orders／Assignments／Scheduling／Matching／LINE Integration`
- 主要 Subsystem：`Matching Candidate Query`、`Matching Plan／Contact State`、`Confirmed Service Dates`、`Schedule Confirmation`、`Reliable LINE Delivery`、`Multi-caregiver Fallback`
- 實作授權：`authorized-by-2026-08-12-user-direction`；第 14 節所列業務裁決均已確認。

本計畫是獨立功能開發計畫，不屬於 Import ADR。production code、schema 與 pytest 必須在本文件的
Global → Domain → Subsystem → Module、資料來源、週次定義與傳送語意取得人工確認後才能開始。

## 1. 已確認目標

1. 「月嫂配對中心 → 智慧配對與指派」預設採單月嫂模式。
2. 初始畫面不顯示案件分段數、分段日期或多月嫂組合選項。
3. 保留原本單月嫂配對版面與操作模式。
4. 保留並清楚顯示訂單資訊寄送紀錄、可靠發送狀態與月嫂意願。
5. 多月嫂仍是必要時使用的備案能力，不從 Domain 移除，但不得混入單月嫂預設流程。
6. 新增「傳送預計服務日期表」按鈕，傳送訂單預計服務日期的週表。
7. 週表至少顯示總週數、每週日期與每週服務天數。
8. 表格由後端正式 Orders／Scheduling facts 產生；Streamlit 不自行計算日期、週數或工作日。
9. 已確認的正式服務日期 projection 產生後，系統只提醒人員手動傳送日期表，不自動發送 LINE。
10. 日期建立、修改或重算都不得直接發送；人員必須檢視最新內容並按下按鈕。
11. 移除沒有獨立操作價值的「檢視案件詳情」配對子頁；必要案件摘要固定顯示在配對工作區頂端。
12. 多月嫂備案不再顯示 raw「最新檔期」表格；候選選項直接顯示該月嫂在本案服務期間內可支援的日期。
13. 可支援日期必須由後端 Scheduling Query 回傳，Streamlit 不得自行用 raw intervals 推導或拼接業務結果。
14. 建立配對方案時仍須 fresh-read 最新檔期；移除表格不代表放寬 availability／occupancy gate。
15. 月嫂配對中心不得顯示「正式根狀態／確認建立正式案件架構」等內部 bootstrap 操作；一般案件在進入
    配對前就必須具備完整 roots，歷史缺口改由受控 migration／異常處理入口修復。

## 2. 現況與根因

以下為 2026-08-10 current working tree 的只讀證據，不是永久規格：

| 切片 | 現況 | 問題 |
|---|---|---|
| 配對子頁 | 已有「檢視案件詳情／智慧配對與指派／多月嫂配對方案（備案）」 | Domain 能力已有單／多月嫂概念 |
| 檢視案件詳情 | 只把已選案件的案號、客戶、服務期間與身分資格以 raw mapping 顯示 | 與上方案件選擇及配對流程重複，沒有獨立操作；資訊形狀也不適合作為正式 UI |
| 智慧配對 renderer | `_render_single_caregiver_matching()` 直接呼叫 `_render_multi_segment_matching()` | 單月嫂頁一開始就出現 `服務分段數 [1,2,3,4]`、分段日期與多月嫂 controls |
| 單月嫂 eligibility | 已有完整服務期間的單月嫂 eligibility check | 結果沒有成為單月嫂預設 UX 的唯一候選入口 |
| 多月嫂候選標籤 | selectbox 只顯示 `#staff_id｜姓名` | 使用者無法在選擇時判斷該月嫂可支援哪些日期 |
| 最新檔期結果 | `segment_candidates` 以 `segment_index／staff_id／start_date／end_date` raw dataframe 顯示 | 表格是內部資料形狀，重複列多、沒有姓名及本案日期覆蓋摘要，使用者難以理解 |
| 檔期刷新 | 日期輸入後需按「重新查詢最新檔期」，候選與 raw table 分開顯示 | 查詢時點及目前候選是否對應最新輸入不清楚，容易選到 stale UI 結果 |
| 案件架構 bootstrap | 配對中心無條件呼叫 `ensure_case_architecture_ready()`；未 ready 時直接顯示「正式根狀態」、初始化原因與 Apply 按鈕 | 這是 legacy case adoption／資料修復命令，不是月嫂配對業務；內部架構術語與跨 Domain root 建立不應暴露在一般頁面 |
| bootstrap mutation | Apply 會建立 Client Finance account／payment terms、Payroll account／policy snapshot、Scheduling aggregate 與 bootstrap event | 高影響跨 Domain 初始化被錯放在配對頁；使用者可能在不了解資料政策時建立正式根事實 |
| 聯繫流程 | matching plan segment 可發送訂單資訊-1／資訊-2 | 由 reliable delivery queue 發送，應沿用 |
| 寄送紀錄 | contact state 顯示 info-1／info-2 delivery status | 不應因 UI 重整遺失 |
| 月嫂意願 | segment-owned willingness，支援 LINE 回覆與人工補登 | 不應退回 legacy `matching_records` writer |
| 履歷發送 | 月嫂願意後可發送履歷給客戶，歷史由 matching plan 擁有 | 單月嫂補寄能力需保留 |
| 日期表 notification | 尚無正式 notification kind／intent／card／button | schema enum 目前只有 `caregiver_info_1`、`caregiver_info_2`、`customer_profiles` |

根因不是多月嫂 Domain 本身，而是 Presentation 把單月嫂頁直接重用多月嫂 renderer。修正時不得為了
畫面簡化而刪除 matching plan、segment、communication version、delivery task 或 willingness roots。

## 3. Global → Domain → Subsystem → Module

### 3.1 Global

Global 不變量：

- 一般配對先嘗試一位月嫂完整承接全部預計服務期間；
- 多月嫂只作明確備案，不在單月嫂初始畫面要求使用者分段；
- UI 不以日期區間自行猜測服務日，也不直接傳 LINE；
- 所有傳送動作先保存 immutable intent／snapshot，再由 reliable delivery task 發送；
- 寄送紀錄、意願、customer decision 與 waiting-deposit lock 都綁定同一 active matching plan version；
- 日期表傳送失敗不改變月嫂意願、訂單狀態、指派或檔期；
- stale plan／stale schedule 不得發送過期日期表；
- confirmed planned-service-date projection 只產生 internal `manual_send_required` decision，不建立 LINE delivery task；
- 日期建立、修改、重算或重新確認均不得直接產生 outward message；
- 單月嫂 UX 調整不得破壞未來正式多月嫂 assignment ownership；
- 移除「檢視案件詳情」只退役重複的 Presentation 入口，不刪除 Orders／Matching Query 或案件根事實；
- 月嫂可支援日期由 Scheduling 根事實與 occupancy policy 衍生，候選標籤只是 typed query view；
- Query 顯示的可支援日期不是檔期鎖定，也不是建立 matching plan 的成功保證；Apply 仍 fresh-check；
- 不得為了縮短選項文字隱藏 coverage gap，亦不得把未覆蓋日期推測為可服務；
- 一般 Matching UI 不擁有 case bootstrap／migration command，也不得建立 Finance、Payroll 根事實；
- 新建／匯入案件必須在 owning command 的單一交易中建立必要 roots，不能延後到首次開啟配對頁；
- 歷史案件缺 root 是資料遷移／異常修復問題，必須從受控 operator entry 處理並留下 receipt。

### 3.2 Domain ownership

| Domain | 擁有 | 不擁有 |
|---|---|---|
| Orders | case、正式 order terms、預計服務起點／服務天數與 lifecycle roots | 月嫂候選、LINE delivery、UI table formatting |
| Scheduling／Assignments | planned service dates projection、月嫂 availability、matching plan／segment、正式 assignment ownership | Client／Order root、LINE provider transport |
| LINE／Delivery | recipient identity、message payload、delivery task／status／retry | 配對與服務日期業務規則 |
| Access Control | matching read／send／override capability 與 actor | 配對方案或日期計算 |
| Streamlit Presentation | typed view、選擇、按鈕、loading／result | 日期、週次、候選、意願與發送規則 |

### 3.3 Subsystems

1. Single Caregiver Candidate Query
2. Matching Plan／Contact State
3. Planned Service Schedule Query
4. Expected Service Schedule Notification
5. Reliable LINE Delivery
6. Multi-caregiver Fallback
7. Matching Workspace Summary Query
8. Caregiver Case-period Coverage Query

### 3.4 Modules

- `SingleCaregiverEligibilityPolicy`
- `SingleCaregiverCandidateRanker`
- `PlannedServiceDateProjector`
- `ServiceWeekGrouper`
- `ExpectedServiceScheduleViewBuilder`
- `ExpectedServiceScheduleCardBuilder`
- `MatchingScheduleNotificationFingerprint`
- `MatchingContactStateProjector`
- `MultiCaregiverFallbackVisibilityPolicy`
- `MatchingWorkspaceSummaryViewBuilder`
- `CaregiverCasePeriodCoverageProjector`
- `CaregiverAvailabilityRangeGrouper`

## 4. 目標 UI

### 4.1 智慧配對與指派預設流程

```text
選擇洽談中案件
→ 顯示案件與預計服務摘要
→ 查詢可完整承接的單一月嫂
→ 選擇一位月嫂
→ 建立單月嫂 matching plan（一個 segment）
→ 發送訂單資訊並收集配對意願
→ 顯示寄送紀錄與月嫂意願
→ 願意後發送履歷給客戶
→ 客戶接受後進 waiting-deposit lock
→ 訂單管理確認正式服務日期
→ Preview 並人工發送客戶完整日期表與月嫂 segment 日期表
→ 客戶與目標月嫂確認 current snapshot
→ 建立正式指派／正式排班
```

初始畫面不得出現：

- `服務分段數`；
- 第 1～4 段開始／結束日；
- 多位月嫂選擇器；
- 自動平均切分日期；
- 「多月嫂共同完成」備註。

單月嫂 plan 在 Domain 仍可用一個 segment 表示，以沿用現有寄送紀錄、意願與後續 conversion；UI 不把
segment implementation detail 暴露給一般使用者。

### 4.2 建議版面

```text
月嫂配對中心

[案件摘要：案號／客戶／預計開始日／預計結束日／服務天數／服務方式]

1. 推薦可完整承接的月嫂
   [推薦月嫂清單與可承接完整期間證據]

2. 選擇月嫂並建立配對方案
   [月嫂選擇] [建立單月嫂配對方案]

3. 聯繫與確認意願
   月嫂姓名｜完整服務期間｜目前意願
   [發送訂單資訊-1] [發送訂單資訊-2] [傳送預計服務日期表]

   寄送紀錄：資訊-1／資訊-2／日期表各自的 queued、sent、failed
   月嫂意願：待回覆／願意／無意願
   [人工補登意願]

4. 月嫂願意後傳送履歷給客戶
5. 客戶接受後鎖定等待訂金檔期
```

### 4.3 配對工作區導覽與案件摘要

移除「檢視案件詳情」子頁及其 radio option。月嫂配對中心只保留：

1. `智慧配對與指派`（預設單月嫂）；
2. `多月嫂配對方案（備案）`。

原子頁內對配對有用的資料不能一起消失，改由兩個工作流程共用的固定案件摘要顯示：

```text
案件 #115000015｜客戶：徐○雯
服務期間：2026-12-06～2026-12-20｜15 天｜服務方式：...
目前配對狀態：尚未建立／聯繫中／等待意願／已鎖定
```

- 摘要使用 typed Matching Workspace View，不 render Python mapping／JSON；
- 只顯示配對決策需要的最小資料，不重製完整訂單詳情頁；
- 需要檢視完整案件資料時，提供既有正式訂單頁 deep link，不在配對中心維護第二份詳情；
- 退役 `_render_matching_order_summary()` 前須完成 caller inventory、navigation replacement 與 focused regression；
- 從異常中心或其他入口 deep link 時，必須落在明確的單月嫂或多月嫂工作流程，不能指向已移除子頁。

### 4.4 多月嫂候選的可支援日期顯示

多月嫂備案保留分段能力，但移除 `segment_candidates` raw dataframe。每一段的月嫂 selectbox
直接顯示該月嫂在整張訂單服務期間內的可支援日期，讓管理人員在選擇當下理解 coverage。

建議選項格式：

```text
王○○｜本案可支援 12/06～12/10、12/13～12/20（13／15 天）
陳○○｜本案可支援 12/06～12/20（全期 15／15 天）
林○○｜目前區段無法完整承接；缺 12/09、12/10
```

日期很多時，後端先把連續日期整理成 ranges；不可由 Streamlit 收集 raw rows 後自行計算。候選
typed view 至少包含：

```text
CaregiverCasePeriodCoverageView
- staff_id
- staff_display_name
- case_period_start
- case_period_end
- required_service_dates[]
- supported_service_dates[]
- supported_ranges[]
  - start_date
  - end_date
  - service_day_count
- supported_day_count
- required_day_count
- full_case_coverage
- selected_segment_start
- selected_segment_end
- full_selected_segment_coverage
- uncovered_segment_dates[]
- source_scheduling_version
- coverage_fingerprint
```

UI 行為：

- 月嫂姓名與可支援日期出現在同一個選項，不要求先看另一張表再回頭對照 staff id；
- 完整覆蓋目前分段的候選排在前面；無法完整覆蓋該段者預設不可選，但可顯示缺口原因；
- 連續日期顯示為區間，不連續日期拆成多個區間；每一區間仍以正式 service dates 計數；
- segment 日期或數量變更時，舊候選立即失效，重新 Query 後才可選擇；
- 不再顯示「重新查詢最新檔期」加 raw dataframe 的兩段式操作；候選查詢隨已提交的分段條件刷新，
  並清楚顯示 loading、查詢時間與版本；
- 正式建立 matching plan 前，後端 Apply 必須重新檢查最新 availability、active lock、assignment
  occupancy 及版本；Query 後被其他案件占用時固定回 conflict，不得沿用畫面快取強行建立；
- 完全沒有可行候選時，直接列出未覆蓋日期及可執行方向，不顯示空白表格。

「可支援」只表示目前 Scheduling 根事實下沒有已知衝突，不表示月嫂已同意接案；月嫂意願仍須走
既有聯繫與回覆流程，不能由 availability 推導為 willing。

### 4.5 多月嫂備案

- 「智慧配對與指派」永遠不渲染 segment count controls；
- 多月嫂 renderer 只存在於獨立備案 workflow；
- 初始 render 不自動跳至多月嫂備案；
- 從異常中心導航時，除非 action 明確表示多月嫂備案，仍落在單月嫂頁；
- 建議只有在單月嫂完整期間候選為零時，顯示「沒有月嫂可完整承接」與「前往多月嫂備案」；
- 是否允許管理員在仍有單月嫂候選時手動開啟多月嫂備案，列為人工決策。

### 4.6 移除配對頁的案件架構 bootstrap

畫面中的「此案件尚未完成正式根狀態／確認建立正式案件架構」不是配對狀態，而是系統在架構
切換期間為 legacy 案件設計的 first-use adoption／bootstrap 工具。它會依預設政策建立跨 Domain
根事實，因此不得出現在一般月嫂配對流程。

目標流程：

```text
新案件建立／核准匯入
→ 同一正式 command 建立 Orders、Scheduling、Client Finance、Payroll 必要 roots
→ 完成 invariant 與 receipt
→ 案件才進入可配對 Query

歷史案件缺少必要 roots
→ reconciliation／anomaly projection
→ 從受權限保護的 operator migration／recovery 入口 Preview
→ 人員核對來源政策後 Apply
→ receipt／audit
→ 修復完成後才重新出現在可配對清單
```

Matching UI 的處理規則：

- 移除對 `ensure_case_architecture_ready()` 的直接呼叫與 bootstrap 表單 renderer；
- 不顯示「正式根狀態、架構、世代、bootstrap」等內部術語；
- 一般可配對案件的 Query 只回傳 roots 完整且 invariant 通過的案件；
- 缺 root 的案件不得讓使用者在配對頁臨時建立 Finance／Payroll facts；
- 若案件由 deep link 進入後才發現不完整，回 typed `matching_case_not_ready`，不 render mutation
  controls；由異常中心提供受控處理入口與來源證據；
- 不能只是把表單藏起來後讓後續 matching command 500；所有 Query／Apply 都要有 server-side
  readiness gate 與可追蹤 blocker；
- bootstrap API 是否保留為 operator-only maintenance entry，須依 Entry Point Governance 盤點所有
  caller 後裁決；本項只確認它不能由 Matching UI 暴露。

## 5. 預計服務日期表

### 5.1 業務目的

客戶與月嫂在正式指派前，需要確認已由訂單管理確認的服務日期。客戶查看整張訂單，月嫂查看自己的
segment，避免只看起訖日期而誤判休假、工作密度或正式承接內容。

日期表是配對溝通 snapshot，不是正式 assignment／staff schedule，也不會鎖定檔期。後續 order terms
變更時舊訊息保留為歷史；重新發送必須產生新 snapshot／intent。

### 5.2 SSOT 與根事實

日期表只能使用：

- Orders 已確認的預計服務開始日；
- contracted service days；
- service mode／核准休息規則；
- Scheduling planned service-date projection；
- order／schedule／matching plan versions。

不得使用：

- UI 以 `start + service_days - 1` 猜出的日期；
- `clients.due_month`；
- 未完成確認的 planned service-date projection；
- 月嫂個人 UI 暫存草稿；
- 已取消或 stale matching plan；
- `orders.staff_id` legacy convenience field。

若 planned service dates 尚未產生、數量不等於 contracted service days、日期重複或 terms stale，按鈕
disabled，後端回 typed blocker，不允許 UI fallback。

### 5.3 Typed view

```text
ExpectedServiceScheduleView
- case_no
- plan_id
- segment_id
- order_version
- schedule_version
- schedule_fingerprint
- expected_start_date
- expected_end_date
- total_service_days
- total_weeks
- week_grouping_policy
- weeks[]
  - week_number
  - period_start
  - period_end
  - service_dates[]
  - service_day_count
```

守恆式：

```text
total_service_days
  = SUM(weeks[].service_day_count)
  = COUNT(DISTINCT all weeks[].service_dates)

weeks[].service_dates 必須排序、互斥且都落在該週 period 內。
```

### 5.4 週次定義（已確認）

採 calendar week：每週星期日開始、星期六結束。日期表第一週與最後一週可不足七日，但每個
service date 只能屬於一個週次，週次順序依 period start 升冪排列。

範例：預計開始日為 2026-08-05，則：

| 週次 | 週期 | 本週預計服務日期 | 本週服務天數 |
|---|---|---|---|
| 第 1 週 | 08/02～08/08 | 由 confirmed service dates 列出 | N |
| 第 2 週 | 08/09～08/15 | 由 confirmed service dates 列出 | N |

`week_grouping_policy` 固定版本化為 `calendar_week_sunday_to_saturday_v1`，並納入 snapshot fingerprint。

### 5.5 傳送按鈕與流程

按鈕名稱固定為：`傳送預計服務日期表`。

放在該月嫂 contact container，與「發送訂單資訊-1／2」並列。正式服務日期 projection 尚未完成確認時，
按鈕 disabled 並說明缺少的前置條件；確認完成後，顯示「日期表待人工傳送」提醒並啟用按鈕。

提醒與發送必須分離：

```text
confirmed_planned_service_dates
→ 建立／更新 internal manual-send-required decision
→ UI 顯示待辦提醒與最新日期表 Preview
→ 不建立 notification intent
→ 不建立 LINE delivery task
→ 人員確認收件人與內容後按下傳送按鈕
→ 才建立 immutable intent／snapshot／delivery task
```

按下後：

```text
fresh-read active matching plan／segment／order terms／planned dates
→ 驗證 expected communication version、schedule version、recipient LINE binding
→ 建立 ExpectedServiceScheduleView
→ 產生 payload snapshot＋fingerprint
→ append matching notification intent
→ enqueue reliable LINE delivery task
→ commit
→ UI 顯示 queued／sent／failed
```

任何日期調整只更新 authoritative dates、schedule fingerprint 與 Preview：

- 尚未傳送：維持 `manual_send_required`，不得自動送出；
- 已傳送且內容未變：維持 `sent_current`；
- 已傳送後日期內容改變：標記 `sent_outdated`，提醒人員評估是否重送；
- 人員未按下按鈕：不論修改幾次，都不得建立新的 outward delivery；
- 重送必須產生新 snapshot／intent，舊訊息與舊 delivery receipt 保留為歷史。

新增 notification kinds：

- `customer_expected_service_schedule`：order-level 完整日期表；
- `caregiver_expected_service_schedule`：segment-level 月嫂日期表。

月嫂日期表是 segment-level notification：

- recipient 必須是該 segment 的月嫂 LINE identity；
- 不建立 willingness interaction token，也不自動改變月嫂意願；
- 不要求月嫂已回覆願意才能傳送；
- 同一 schedule fingerprint＋同一 plan version＋同一 idempotency key replay 回原 intent；
- schedule／plan stale 時拒絕；管理員 fresh preview 後可發新版本；
- delivery failure 只影響本次日期表寄送狀態，不回滾 matching plan 或其他已送訊息。

客戶日期表是 order-level notification；recipient 必須是該訂單目前有效客戶 LINE identity，內容包含
全部 segments。客戶 delivery 與各月嫂 delivery 各自保存 intent、task、attempt 與 receipt，任一方
發送失敗不得偽造成另一方成功。

日期表人工傳送 readiness 至少包含：

```text
not_ready
manual_send_required
sent_current
sent_outdated
blocked
```

每個 recipient confirmation state 至少包含：

```text
pending
confirmed
rejected
invalidated
manually_confirmed
manually_revoked
```

order-level gate 只有在客戶完整日期表為 confirmed／manually_confirmed，且目標正式 assignment 所屬
月嫂的 segment 日期表為 confirmed／manually_confirmed，並全部指向 current confirmed service-date
version 與同一 snapshot lineage 時才是 `passed`；其他狀態一律為 `blocked`。

上述狀態是後端依已確認的正式服務日期 projection、schedule fingerprint 與最後成功傳送 snapshot 衍生的 typed
view；Streamlit 不得自行比較日期或 session state 來推導。

### 5.6 訊息內容

LINE 訊息至少顯示：

- 案件識別（使用核准、隱私安全的 display identity）；
- 預計服務期間；
- 總服務天數；
- 總週數；
- 每週週次、日期範圍、具體服務日期與服務天數；
- 「此為預計日期；若訂單條款調整，工會將另行通知」；
- snapshot version／sent time 不必直接顯示給月嫂，但必須留在 intent audit。

不得在訊息中暴露不必要的客戶身分證、電話、地址、銀行或內部價格資料。

## 6. 寄送紀錄與月嫂意願

### 6.1 保留原模式

每位月嫂仍顯示：

- 訂單資訊-1 delivery status；
- 訂單資訊-2 delivery status；
- 新增的預計服務日期表 delivery status；
- 月嫂意願：pending／willing／unwilling；
- LINE 回覆或人工補登來源；
- 人工補登原因；拒絕時必填，確認、撤回或一般修正時可選填；
- plan communication version。

UI 重整不得清空或搬移既有 matching notification intents、delivery tasks、response events 或 legacy
歷史投影。取消方案後寄送與意願歷史仍保留；新方案使用新 plan/version。

### 6.2 狀態互不混用

- `sent` 只表示 provider delivery 成功，不表示月嫂願意；
- `willing` 是月嫂回覆／人工補登根事實，不由三個按鈕發送成功推導；
- 日期表 `failed` 不把已存在 willingness 改回 pending；
- 月嫂 unwilling 後，若新方案仍選同人，必須建立新 plan／明確人工理由，不覆寫舊 response event；
- customer resume／decision 不與 caregiver notification status 共用欄位。

## 7. 交易、idempotency、retry 與 conflict

- `ConfirmServiceDates` 由 Orders outer Unit of Work 擁有；它透過 borrowed Scheduling port 產生／驗證
  planned service-date candidate，追加 confirmed service-date event／version、audit、outbox 與 receipt 後單次 commit。
- 日期表 Preview 是唯讀 Query；Send command 由 Matching communication outer Unit of Work 擁有，原子寫入
  parent snapshot、recipient snapshot、notification intents、delivery tasks 與 receipt。
- 客戶／月嫂 LINE confirmation 由 canonical inbox consumer 呼叫 Matching confirmation command；每一筆回覆
  append immutable confirmation event，再更新 current projection，不直接寫 assignment 或 schedule。
- 正式 assignment Apply 仍由 Scheduling outer Unit of Work 擁有；鎖定 current confirmed service-date version、
  parent／recipient snapshot 與 confirmation projection 後驗證 gate，失敗零寫入。
- notification intent、payload snapshot、interaction（若有）、delivery task、projection 在單一 outer UoW commit；
- 日期表不開 willingness interaction，因此不新增可回覆 token；
- provider/network failure 由 delivery task bounded retry，不重新建立 intent；
- same key＋same fingerprint 回原 receipt；same key＋different snapshot 409；
- plan version、order terms version 或 schedule fingerprint stale 固定 409，要求 fresh preview；
- recipient 無 LINE binding 回 typed blocker，不轉人工 recipient、不用其他月嫂 identity；
- active plan 被取消、訂單不再洽談中或月嫂已不屬於 segment 時禁止發送；
- UI timeout 後 query intent／delivery status，不換 idempotency key重送。

### 7.1 Snapshot lineage

- 一次 Send 建立一個 order-level parent snapshot，identity 至少包含 case、confirmed service-date version、
  order／schedule／matching-plan versions、完整 service dates、week policy 與 fingerprint。
- 客戶 snapshot 引用 parent 並包含完整日期表；每個月嫂 snapshot 引用同一 parent、segment identity 與該
  segment service dates。所有子 snapshot 的日期聯集必須等於 parent dates，且不同 segment 不得重複 ownership。
- confirmation event 必須引用 recipient snapshot identity，不接受只帶 case number、plan id 或 UI 顯示版本的回覆。
- 日期、Terms、plan、segment、recipient binding 或 schedule version 改變時，舊 parent 及全部子 snapshot
  保留歷史但 current projection 改為 `invalidated`；不得把舊確認搬到新 snapshot。

### 7.2 拒絕與人工調整

- LINE 使用者選擇拒絕後，interaction 進入 `awaiting_rejection_reason`；收到非空白文字才追加正式 rejected event。
- interaction timeout、取消或無效文字不產生 rejected event，current confirmation 維持 pending 並顯示待補理由。
- 工會人工補登拒絕同樣必填非空白理由；人工確認／撤回原因可選填。
- 人工確認可在保留原 rejected event 的前提下，使 current projection 成為 `manually_confirmed`；後續同一
  snapshot 的有效 LINE 回覆仍追加事件，最後一筆合法事件決定 current projection。
- 撤回人工確認追加 `manually_revoked` event，結果為 gate blocked；不得刪除或恢復覆寫前事件。

## 8. Typed errors

| Code | 行為 |
|---|---|
| `single_caregiver_full_coverage_unavailable` | 顯示沒有單人可完整承接，提供多月嫂備案入口 |
| `planned_service_schedule_unavailable` | 缺正式 planned dates；按鈕 disabled，導向 terms／schedule補正 |
| `planned_service_schedule_invariant_failed` | 日期數量／重複／範圍不守恆；阻擋發送並告警 |
| `planned_service_date_confirmation_required` | 正式服務日期 projection 尚未確認；只顯示前置條件，不允許傳送 |
| `matching_plan_stale` | 409；重讀 active plan |
| `planned_service_schedule_stale` | 409；重新取得日期表 Preview |
| `matching_segment_recipient_mismatch` | 403／409；不得發給其他 LINE identity |
| `caregiver_line_binding_required` | 422；顯示需先完成 LINE 綁定 |
| `customer_line_binding_required` | 422；顯示需先完成客戶 LINE 綁定；仍允許人工補登確認 |
| `schedule_confirmation_rejection_reason_required` | 422；拒絕理由為空白，維持 pending |
| `schedule_confirmation_snapshot_stale` | 409；回覆或人工調整指向非 current snapshot |
| `schedule_confirmation_gate_required` | 409；客戶或目標月嫂尚未確認 current snapshot，正式指派零寫入 |
| `matching_schedule_delivery_unavailable` | intent 已 commit則查 delivery／retry，不重建 plan |
| `matching_schedule_idempotency_conflict` | 409；同 key 不同 snapshot |

## 9. Schema／API 影響

需要 additive migration／contract update：

- `MatchingNotificationKind` 新增 `caregiver_expected_service_schedule`；
- `MatchingNotificationKind` 新增 `customer_expected_service_schedule`；
- `matching_notification_intents.notification_kind` enum／target CHECK 接受新 segment-level kind；
- notification target CHECK 接受 customer order-level 與 caregiver segment-level targets；
- 新增 versioned confirmed service-date event／receipt、parent／recipient schedule snapshots、append-only
  confirmation events 與 current confirmation projection；
- contact state typed segment view 增加 schedule notification delivery status；
- contact state typed view 增加 `manual_send_required`／`sent_current`／`sent_outdated` readiness；
- confirmed planned-service-date projection consumer 只更新 internal reminder/readiness，不 enqueue LINE task；
- API 新增 schedule Preview Query 與 send Command，或在既有 information endpoint 以新 typed kind 擴充；
- candidate Query view 增加月嫂 display name、required／supported service dates、display ranges、coverage count、
  uncovered dates、Scheduling version 與 coverage fingerprint；
- UI 必須透過 dedicated Matching API client，不再在 render function 散落 raw `_request`／dict；
- LINE card builder 與 payload snapshot masking／size contract；
- LINE confirmation interaction 支援 confirm／reject→reason，並綁定 recipient snapshot identity；
- Orders 確認服務日期 Preview／Apply，以及 Scheduling formal-assignment Apply gate；
- release manifest、candidate schema verifier、preserved-data rehearsal。

不修改／不重建既有 notification intents；migration 只擴充 enum／projection，歷史 rows 保留。

## 10. 實作待辦

### P0：最高優先 UX 修復

- [ ] `MATCH-P0-01` 人工確認本文件架構與第 5.4 節週次政策；
- [ ] `MATCH-P0-02` 將單月嫂 renderer 與 multi-segment renderer 完全分開；
- [ ] `MATCH-P0-03` 智慧配對頁移除 segment count、分段日期與多月嫂 controls；
- [ ] `MATCH-P0-04` 恢復單月嫂候選→選擇→聯繫→意願→履歷→鎖定的原版面順序；
- [ ] `MATCH-P0-05` 保留並回歸 info-1／info-2 寄送紀錄、月嫂意願與人工補登；
- [ ] `MATCH-P0-06` 修正異常中心導航，預設不跳入多月嫂備案；
- [ ] `MATCH-P0-07` 定義多月嫂備案顯示條件與人工 override policy。
- [ ] `MATCH-P0-08` 移除「檢視案件詳情」子頁、radio option 與失效 navigation target；
- [ ] `MATCH-P0-09` 建立共用 typed 案件摘要，固定顯示在單／多月嫂工作區頂端；
- [ ] `MATCH-P0-10` 盤點 `_render_matching_order_summary()` caller，提供完整訂單 deep link 後退役 renderer；
- [ ] `MATCH-P0-11` 擴充候選 Query，回傳月嫂姓名、本案 required／supported dates、ranges、coverage count 與版本；
- [ ] `MATCH-P0-12` 多月嫂 selectbox 直接顯示姓名與本案可支援日期；
- [ ] `MATCH-P0-13` 移除 `segment_candidates` raw dataframe 與 staff-id 對照式操作；
- [ ] `MATCH-P0-14` 分段條件變動時使舊候選失效並刷新 typed Query，不保留 stale 選擇；
- [ ] `MATCH-P0-15` plan Apply fresh-check availability／lock／occupancy，證明 UI 簡化未放寬寫入 gate；
- [ ] `MATCH-P0-16` 無完整候選時顯示缺口日期與 typed reason，不顯示空白或內部欄位表格。
- [ ] `MATCH-P0-17` 從 Matching UI 移除 `ensure_case_architecture_ready()` 與 bootstrap mutation panel；
- [ ] `MATCH-P0-18` 配對案件 Query 只列出必要 roots 完整且 invariant 通過的案件；
- [ ] `MATCH-P0-19` 缺 root／partial root 改投影為 typed anomaly，提供受控 operator recovery deep link；
- [ ] `MATCH-P0-20` 新建與正式匯入案件驗證必要 roots 在 owning transaction 內建立，不依賴 first-use UI；
- [ ] `MATCH-P0-21` 依 Entry Point Governance 盤點 bootstrap API、order editor、case staffing 等其他 caller，
  分別裁決保留 operator-only、替換或退役，不因本頁移除而直接刪除共用 API。

### P1：預計服務日期表 Query

- [ ] `MATCH-P1-00` 在訂單管理新增確認服務日期 Preview／Apply，允許工會增刪或調整 candidate dates；
  Apply 保存 versioned confirmed service-date projection／receipt，不建立 assignment 或 staff schedule。
- [ ] `MATCH-P1-01` 定義 Planned Service Schedule SSOT 與 typed Query port；
- [ ] `MATCH-P1-02` 實作 `ServiceWeekGrouper` 與週／日守恆 validator；
- [ ] `MATCH-P1-03` 實作 `ExpectedServiceScheduleView`／fingerprint／version；
- [ ] `MATCH-P1-04` 缺日期、stale、重複或 day-count mismatch 時 fail closed，不由 UI fallback；
- [ ] `MATCH-P1-05` 建立不同開始星期、休假模式、跨月／跨年、最後不足一週的 Module tests。
- [ ] `MATCH-P1-06` 建立 confirmed-planned-service-dates→manual-send-required readiness policy；不得建立 delivery task。

### P2：可靠傳送

- [ ] `MATCH-P2-01` 新增 `caregiver_expected_service_schedule` Domain enum 與 typed command；
- [ ] `MATCH-P2-02` additive migration 擴充 notification enum／target CHECK／release descriptor；
- [ ] `MATCH-P2-03` 建立 privacy-safe LINE schedule card／message builder；
- [ ] `MATCH-P2-04` 同交易寫 intent、snapshot、delivery task、projection／receipt；
- [ ] `MATCH-P2-05` contact state 加入日期表 queued／sent／failed 狀態；
- [ ] `MATCH-P2-06` 驗證 replay、different-payload conflict、stale plan／schedule、recipient mismatch、retry。
- [ ] `MATCH-P2-07` 驗證日期修改只產生 `sent_outdated`／待辦提醒，不自動建立新 intent 或 task。
- [ ] `MATCH-P2-08` 建立 customer parent snapshot、caregiver segment child snapshots 與 lineage 守恆 validator。
- [ ] `MATCH-P2-09` 建立客戶／月嫂 confirm、reject→reason、人工確認／撤回的 append-only commands 與 projections。
- [ ] `MATCH-P2-10` 將 current 雙方確認 gate 接入 Scheduling 正式 assignment／schedule Apply。

### P3：UI 與整合驗收

- [ ] `MATCH-P3-01` 在單月嫂 contact container 新增「傳送預計服務日期表」；
- [ ] `MATCH-P3-02` UI 先顯示 typed 日期表 Preview，再允許傳送；
- [ ] `MATCH-P3-03` 使用 Matching bounded-domain API client／Pydantic views，不讓 raw dict 進 render；
- [ ] `MATCH-P3-04` 顯示日期表 delivery status，與 info-1／info-2／willingness 分欄；
- [ ] `MATCH-P3-05` Streamlit rerender／double-click／timeout 不重複發送；
- [ ] `MATCH-P3-06` 完成單月嫂 happy path、無完整候選、多月嫂 fallback、LINE 無綁定與 provider retry E2E。
- [ ] `MATCH-P3-07` 正式服務日期確認後顯示手動傳送提醒；未確認前按鈕 disabled。
- [ ] `MATCH-P3-08` 已送後改期顯示「舊日期表已過期」，由人員選擇是否重送。
- [ ] `MATCH-P3-09` 訂單管理可調整並確認服務日期；任何異動使舊日期表及雙方確認顯示失效／未確認。
- [ ] `MATCH-P3-10` 管理 UI 分別顯示客戶完整表與各月嫂 segment 的 delivery、confirmation、拒絕理由與人工事件。

## 11. 分層驗收

| 層級 | 必須證明 |
|---|---|
| Module | single-coverage policy、case-period ranges、coverage gaps、week grouping、date/day conservation、fingerprint、card masking |
| Subsystem | single plan/contact state、case-period coverage Query、case readiness／anomaly、schedule Preview／Send、replay、stale、retry、delivery projection |
| Domain | Orders terms→planned dates→one-segment matching plan→notification intent；多月嫂能力未受破壞 |
| Global | 登入 UI→ready 案件摘要→單／多月嫂候選日期→配對→三種月嫂訊息→意願→履歷→customer decision→waiting lock；一般頁無 bootstrap mutation |

最低驗收場景：

1. 進入智慧配對，第一畫面沒有服務分段數與多月嫂 controls；
2. 一位月嫂可完整承接，建立一個 segment 並保留完整 contact history；
3. 沒有完整承接候選，才顯示多月嫂備案入口，不自動跳頁；
4. info-1／info-2 原發送與意願更新流程行為不變；
5. 日期表總服務天數等於各週服務天數加總；
6. 跨月、跨年、休假與最後不足一週顯示正確；
7. 日期表發送成功後 contact state 可查 delivery status；
8. 日期表傳送不改變 willingness、order status、assignment 或 lock；
9. terms／planned dates 在 Preview 後改變，舊 send command stale；
10. provider failure 重試只產生一個 intent，成功後 UI 顯示 sent；
11. 取消方案後寄送與意願歷史仍存在；
12. 多月嫂備案仍能建立 2～4 segments，但不出現在單月嫂初始頁。
13. 確認正式服務日期 projection 只建立內部提醒，LINE delivery task 數量仍為零；
14. 連續修改日期多次皆不自動發送，只有最後一次人工按鈕操作建立一個新 intent；
15. 已成功傳送後修改日期，舊 snapshot 保留且 readiness 顯示 `sent_outdated`。
16. 配對中心不再出現「檢視案件詳情」子頁，但兩個配對流程頂端均有必要案件摘要；
17. 完整案件資料仍可透過正式訂單頁 deep link 查看，不建立第二份詳情 SSOT；
18. 多月嫂候選選項直接顯示月嫂姓名、可支援日期區間與覆蓋天數；
19. 畫面不再顯示 `segment_index／staff_id／start_date／end_date` raw 最新檔期表格；
20. 不連續可支援日期顯示為多個區間，缺口日期可被人員直接理解；
21. 改動分段日期後舊候選不可沿用；建立方案前發生新 occupancy 時 Apply 回 typed conflict 且零寫入。
22. 月嫂配對中心不再顯示正式根狀態、初始化原因、架構版本／世代或建立架構按鈕；
23. 新建／正式匯入且 roots 完整的案件可直接配對，不需 first-use bootstrap；
24. 缺 root 的歷史案件不進入一般配對清單，並在異常／operator recovery 入口具有來源證據與合法修復命令；
25. 直接以 deep link 開啟缺 root 案件時回 typed blocker，沒有 Finance／Payroll／Scheduling 部分寫入；
26. Matching UI 移除 bootstrap 後，其他核准 operator caller 與 API 的 disposition 有 entry-point evidence。
27. 訂單管理調整任一服務日期後，舊 confirmed service-date version 保留歷史但 current 失效，客戶與全部
    受影響月嫂狀態回到未確認；未重新 Preview、Send 並確認前，正式 assignment Apply 回 gate blocker。
28. 客戶確認完整 parent snapshot、每位月嫂只確認自己的 child snapshot；部分月嫂未確認時，只阻擋該
    月嫂對應的正式 assignment，不把其他人的確認推導為完成。
29. 客戶或月嫂拒絕必須完成理由輸入才形成 rejected event；空白、逾時或取消維持 pending。
30. 工會人工確認可覆蓋 current projection但保留拒絕事件；人工撤回與後續 LINE 回覆均追加事件並依最後
    一筆合法事件決定 current state。
31. 直接呼叫正式 assignment／schedule API 也必須驗證 current 雙方確認，不得只依 UI disabled 防守。

## 12. 完成定義

只有同時符合以下條件才可標記 Implemented：

- P0～P3 無必要未完成項；
- 智慧配對預設單月嫂，初始頁沒有分段 controls；
- 「檢視案件詳情」重複子頁已退出，必要摘要與正式訂單 deep link 可用；
- 多月嫂候選在選項中直接說明本案可支援日期，不再依賴 raw 最新檔期表格；
- 內部 case bootstrap／migration controls 已從 Matching UI 完全退出；正常案件不需要人員理解「正式架構」；
- 原寄送紀錄、月嫂意願、履歷與 waiting-lock 流程通過回歸；
- 日期表使用正式 planned service dates，週／日守恆；
- 日期表 notification 有 immutable intent、snapshot、delivery task、retry 與 UI status；
- 訂單管理確認服務日期、客戶 parent snapshot、月嫂 segment snapshots、雙方確認與正式 assignment gate
  具有完整 version、lineage、replay、stale、拒絕與人工調整證據；
- 多月嫂仍是獨立可用備案；
- Module／Subsystem／Domain／Global 證據可重跑且 `.venv\Scripts\python.exe -m pytest -W error` 通過。

## 13. 非目標

- 不刪除多月嫂 Domain／assignment 能力；
- 不以 `orders.staff_id` 恢復單月嫂權威；
- 不由 Streamlit 計算週次或服務日期；
- 不把日期表發送成功當成月嫂願意；
- 不在本項目修改薪資、補助、付款公式；
- 不恢復 legacy `/matches/{id}/send-*` writers；
- 不把預計日期表當成正式出勤或 assignment ownership。
- 不把正式服務日期 projection 確認、日期修改或排程重算當成自動發送指令。
- 不刪除正式訂單詳情頁或 Orders root facts；只移除配對中心內重複且無操作價值的子頁。
- 不把「可支援日期」當成月嫂意願、正式 assignment、檔期鎖定或承諾接案。
- 不讓 Streamlit 從 raw `segment_candidates` 計算 coverage ranges 或缺口。
- 不因移除 Matching UI bootstrap 就未經 caller inventory 刪除 operator API、歷史 receipt 或 migration evidence。
- 不把缺 root 的歷史案件靜默忽略；它們必須有 anomaly／operator recovery 追蹤，但不在一般配對頁修復。

## 14. 人工裁決紀錄

本節已完整記錄日期表及多月嫂流程的人工裁決；後續 production code、schema 與 pytest 以本節為準。

### 14.1 2026-08-11 已確認事項

- 移除配對中心內的「檢視案件詳情」子頁；必要摘要改在工作區固定顯示。
- 多月嫂頁移除難以理解的「最新檔期」raw 表格，改由各月嫂選項直接顯示本案可支援日期。
- 「正式根狀態／確認建立正式案件架構」屬內部 legacy adoption，不得出現在月嫂配對中心。
- 上述三項與單月嫂預設、寄送紀錄、月嫂意願及日期表手動傳送改善合併執行，彼此不衝突。

### 14.2 2026-08-12 日期表確認裁決

本節優先於前文所有將日期表視為單向月嫂通知、或以月嫂意願取代日期表確認的描述。

- `配對意願` 只表示月嫂是否有承接意願；它是提供工會人員判斷的資訊，不是正式 gate。工會人員可人工補登、修正或撤回，並須保留 actor、時間與來源；補登無意願時理由必填，其他調整原因可選填。
- `日期表確認` 是獨立的正式 gate。日期表的同一 immutable snapshot／fingerprint 必須同時取得客戶與該 active matching plan segment 月嫂的確認，才可通過 gate。
- 日期表發送對象為客戶與月嫂；兩者各有獨立 confirmation state、來源、時間與人工 override audit，不得共用或由其中一方的確認推導另一方已確認。
- 工會人員可依既有管理 command 手動標記、修正或撤回任一方確認；不新增角色權限 gate。補登拒絕時理由必填，確認、撤回或其他修正原因可選填，且不得覆寫原始客戶／月嫂確認事件。
- order terms、planned service dates、matching plan、recipient binding 或 schedule fingerprint 任一改變時，既有日期表確認固定失效；必須產生新 snapshot，重新取得客戶與月嫂確認。
- 日期表發送仍沿用既有 `Preview → 人員明確 Send command` 原則；已確認的正式服務日期 projection 是產生／送出日期表的前置條件，不授權日期建立、修改或重算時自動外送。此確認不等同於既有 `actual_start` Apply，後者會建立正式 assignment／排班，必須在日期表雙方確認 gate 通過後才可執行。
- 正式 gate 通過與否不得改寫月嫂配對意願、matching plan、訂單狀態或 waiting-deposit lock；gate 已裁決接入正式 assignment／staff schedule Apply，未通過時零寫入。

### 14.3 2026-08-12 執行政策裁決

- 日期表週次採 calendar week：每週星期日開始、星期六結束；跨週的日期表 snapshot 依此分組。
- 多月嫂備案只有在查無可完整承接的單月嫂時主動提示；管理員仍可從明確的次要入口手動開啟備案流程。
- 日期表雙方確認 gate 只阻擋「建立正式指派／正式排班」的 transition。
- gate 未通過時，仍可建立與調整 matching plan、向其他月嫂發送訂單資訊、收集或人工調整月嫂配對意願，以及建立或維持 waiting-deposit lock。
- 不得把日期表 gate 未通過解讀為禁止配對搜尋、候選聯繫或多月嫂備案；它只表示尚不可把任何候選轉為正式 assignment／staff schedule。

### 14.4 2026-08-12 日期表流程裁決

- 服務日期已確認後，工會人員必須先看日期表 Preview，再以明確 Send command 發送；不因日期確認、建立、修改或重算自動外送。
- 客戶與月嫂都透過各自的 LINE confirmation button 回覆；工會人員可在管理 UI 補登或調整確認結果。
- 日期表 Preview 直接讀取最新已確認的正式服務日期；不新增第二次「確認服務日期」按鈕或中介 command。
- 客戶或月嫂缺少 LINE 綁定時，日期表 Send command 必須 fail closed 並顯示 typed blocker；工會人員仍可人工補登該方確認。
- 初版只顯示未確認／已確認／已失效等狀態，不建立自動催辦、逾期或升級通知。
- 日期表所依的 terms、planned service dates、matching plan、recipient binding 或 fingerprint 改變時，客戶與月嫂確認一律失效；必須 Preview 並人工 Send 新版本後重新確認。
- 多月嫂方案中，客戶確認整張訂單的完整日期表；每位月嫂只確認自己 segment 的日期表。正式 assignment gate 必須檢查客戶確認與該 assignment 所屬月嫂的 segment confirmation 都對應同一 current snapshot lineage。
- 人工確認、撤回或修正不新增額外角色權限，也不強制填寫原因；仍記錄既有 actor、時間、來源與 snapshot identity。

### 14.5 2026-08-12 拒絕理由裁決

- 月嫂在配對意願回覆「無意願」時，LINE interaction 必須要求填寫拒絕理由；理由連同原始回覆事件保存，工會人工補登無意願時也必須提供理由。
- 客戶或月嫂在日期表確認回覆「拒絕」時，LINE interaction 必須要求填寫拒絕理由；工會人工補登拒絕時也必須提供理由。
- 日期表任一方拒絕時，該 current snapshot 不通過雙方確認 gate，正式指派／正式排班維持阻擋；工會可依理由調整日期後 Preview、Send 新版本，或以人工確認覆寫 current version。
- 拒絕理由是業務溝通與稽核資料，不得覆寫既有配對意願或日期表 snapshot；應保留 actor／recipient、時間、來源與對應 plan／segment／snapshot identity。

### 14.6 2026-08-12 服務日期確認 Owner 裁決

- 「確認服務日期」是訂單管理的新增 command，由 Orders owning workflow 擁有；月嫂配對中心不得自行確認、計算或建立日期表來源。
- command 對最新有效 Order Terms 與 Scheduling planned service-date projection 執行 Preview／Apply，確認後保存版本化的 confirmed service-date projection／receipt。
- 訂單管理的 Preview 先顯示系統依正式 Terms 與 Scheduling policy 產生的 candidate dates；工會人員可在
  該畫面直接增刪或調整日期。Apply 必須驗證日期唯一、排序、落在合法範圍、服務日數守恆及 occupancy
  規則，再保存 confirmed version。
- 確認服務日期只建立日期表可讀取的正式日期版本，不建立正式 assignment、staff schedule、Payroll impact 或 availability conversion。
- Matching UI 只可讀取該 confirmed version 產生日期表 Preview，並由人員明確 Send 給客戶與月嫂；若 dates、Terms 或 schedule version 改變，confirmed version 與所有對應確認均失效，必須回訂單管理重新確認服務日期。
- 正式 assignment／正式排班的 Apply 必須驗證目前 confirmed service-date version 存在，且客戶與所屬月嫂對同一 current snapshot lineage 均已確認；未通過時回 typed gate blocker 並零寫入。
- 工會修改任何已確認日期後，舊 confirmed version、parent／recipient snapshots 與雙方確認事件保留歷史，
  current confirmation projection 一律回到未確認／invalidated；必須重新 Preview、人工 Send 並取得客戶與
  月嫂對新版本的確認，才可再次通過正式 assignment／排班 gate。

## 15. 本次新增來源追溯（2026-08-11）

## 16. 實作追蹤與未完成阻塞（2026-08-12）

- 已落地：Orders confirmed-service-date Preview/Apply、版本化日期／receipt、日期修改使 current
  schedule snapshot 失效、後端 typed coverage、單月嫂預設 UI、日期表 snapshot／recipient event
  模型、管理端人工確認／拒絕、assignment server-side gate，以及缺 LINE binding 的 Send fail-closed。
- 已驗證 composition：canonical LINE worker 在 `scripts/run_line_worker.py` 將
  `LineMatchingPostbackApplication` 注入 `LineWebhookIdentityHandlers`；日期表 postback 與後續文字
  理由會透過同一 Unit of Work 進入 schedule-confirmation repository。
- 已完成 focused regression：confirmed dates、typed schedule client、snapshot enqueue、LINE
  postback／拒絕理由、target-segment assignment gate、typed coverage 與 canonical worker boundary
  均以 `-W error` 驗證（`30 passed`）；確認查詢另回傳最後事件的來源、UTC 時間與拒絕理由，管理 UI
  不再只能顯示狀態。
- 2026-08-12 內建瀏覽器驗證補正：單月嫂 UI 的 coverage view 已與 availability API schema 對齊；
  `coverage_day_count` 由正式 service dates 計算。development bypass 的 matching-plan command 使用
  canonical actor，且 UI 不傳 workflow 自行衍生的 `segment_order`。未確認服務日期時，日期表面板
  顯示具體 blocker，而非 Streamlit traceback 或泛用請求失敗。
- 尚未完成：matching-center schedule panel 的 Chrome UI 驗收、full-suite 既有失敗的獨立
  reconciliation，以及 archive gate。`declared_status` 維持 `in-progress`，本 Work Package 不可封存。
- 內建瀏覽器已補足 matching-center UI 驗收，但用同一新建測試方案繼續訂單管理日期確認時，既有
  operator bootstrap flow 未產生 receipt／error，無法建立 roots；此 `live-drift` 不在本 WP write set，
  但使同一案件無法完成 Send UI continuation。

### 16.1 Focused receipt

- `../03_追蹤清單與證據/evidence/2026-08-12_wp68_matching_schedule_confirmation_receipt.md`
  記錄 Chrome Order Management 服務日期 Preview／Apply、current version `2 → 3`、日期表 Send、
  recipient snapshot、雙方確認與 server-side assignment gate 的本機測試資料證據。

- `ui/pages/scheduling/matching_center.py`：目前三個子頁、raw summary renderer、多月嫂候選標籤、
  「重新查詢最新檔期」與 `segment_candidates` dataframe 的 live 證據。
- `api/routes/caregiver_segment_availability.py`：目前 candidate response 只有 segment index、staff id
  與日期區間，尚無姓名、required dates、coverage count 或 display ranges。
- `subsystems/scheduling/segmented_availability.py`：已能產生 free intervals／conflicts／complete combinations，
  可作 typed coverage view 的來源，但 UI 不得直接解讀其內部資料形狀。
- `ui/pages/order/case_architecture_bootstrap_panel.py`：目前直接顯示 root-state blocker、預設政策 Preview、
  初始化原因與跨 Domain Apply 按鈕。
- `subsystems/bootstrap/case_architecture_status.py`：此能力明確是 legacy case adoption status；ready 判斷
  要求 Client Finance、payment terms、Payroll、bootstrap event 與 Scheduling aggregate 同時存在。
- `infrastructure/mysql/case_architecture_bootstrap_repository.py`：Apply 實際建立 Finance／Payroll roots、
  bootstrap event 與 receipt，證明它不是一般唯讀案件提示。
- 2026-08-11 使用者提供之配對中心與最新檔期畫面；圖片只作需求證據，不提交可能含個資的副本。
- 2026-08-11 使用者提供之「正式根狀態／確認建立正式案件架構」畫面及人工裁決。

## 17. 2026-08-12 Candidate Contact Pool 補充裁決

單月嫂智慧配對可一次選擇多位「完整承接候選人」加入 case-owned Candidate Contact Pool。候選人不是正式 matching plan segment，不占用檔期，也不因被選取而成為日期表或正式指派的確認對象。

- 候選聯繫池逐人保存完整 coverage evidence、資訊-1／資訊-2 的 append-only 發送事件、發送時間、可靠 delivery 狀態、接案意願、拒絕理由與人工補登 actor／時間。
- 資訊-1／資訊-2 即為詢問配對意願的動作；移除沒有獨立資料效果的「聯繫與確認意願」按鈕。
- 加入候選及每次發送均 fresh-read availability；候選池不保證或鎖定檔期。
- 管理員只能從 `willing` 候選人選定一位，重新驗證 availability 後建立一個 segment 的正式單月嫂 plan。多人共同服務時才使用既有多月嫂備案 plan。
- 候選選定、撤回、plan supersede 或取消均不得刪除候選聯繫與意願歷史。日期表、客戶／月嫂雙方確認及正式指派 gate 只適用於正式 plan recipients。
---
doc_type: work-package
declared_status: completed
date: 2026-08-15
owner: Orders / Scheduling / LINE Integration
domain: Orders / Scheduling / LINE Integration
subsystem: Notification Catalog
implementation_authorization: approved-by-user-2026-08-15
write_set: domains/line notification policy; Orders/Scheduling/Client Finance/Case Import notification event adapters; subsystems/line notification workflow and worker guard; MySQL additive release; notification API and API tests; formal LINE contract; entrypoint queue; evidence/archive manifest
out_of_scope: Streamlit or React UI; real LINE provider acceptance; production DB application; unregistered future Domain event writers
---

# LINE 可配置通知規則後端工作包

## 文件狀態

- 文件類型：正式 LINE Notification Rule 後端工作包。
- 狀態：`completed`；2026-08-16 已完成可配置通知後端、月嫂寶寶日誌／餐食照片 root fact、API／worker 驗收與 developer-local schema replacement。實體 LINE provider acceptance 依 frontmatter `out_of_scope` 未執行。
- 優先級：`P0 規則配置架構與根事實盤點`；production 實作順位接在「休假代班天數精算與行事曆差異預覽修復」及「月嫂配對中心：單月嫂預設」之後。
- 事件白名單、condition grammar、schema write set 與「編輯 → 預覽 → 儲存啟用／刪除」command 已依第 5.12、6～10 節收斂；未知事件、predicate 或收件人一律 fail closed。
- 本文件只定義功能邊界、盤點方法與代辦；訊息文字仍以 LINE 管理頁核准版本為準。

## 1. 使用者需求

1. 訂單狀態或業務里程碑推進時，系統依規則自動推送 LINE 訊息給客戶、月嫂或兩者；
2. 沿用 LINE 管理頁已可維護的訊息範本，不把正式文字寫死在程式；
3. 補上「狀態／事件紀錄 → 規則判斷 → 建立發送任務 → 發送結果」完整鏈路；
4. 提供可配置的觸發、收件人、範本、時間、頻率與條件；新增規則不應要求修改程式；
5. 納入既有雛型，例如客戶資料少填／尚未填 BeClass 問卷；
6. 管理員能查明某一則訊息為何已發送、尚未發送、被抑制或發送失敗。

## 2. 現況盤點結論

### 2.1 已存在能力

- 訂單 canonical status 共有五個：`洽談中`、`訂單成立`、`服務中`、`訂單完成`、`訂單取消`；
- `order_lifecycle_state_events` 已能 append-only 記錄 trigger、before／after status、版本、事實快照與 idempotency key；
- LINE 已有 versioned message template、管理頁、預覽及 optimistic revision；
- LINE 已有 durable delivery task、attempt event、retry 與 sent／failed 狀態；
- 新好友加入後 D+1～D+3 排程已有可運作雛型；
- 配對中心已有資訊-1／資訊-2、寄送紀錄與月嫂意願的專用可靠傳送流程；
- 異常中心已有 `BECLASS-001`、`LINE-001`／`005`、`ORDER-001`～`004` 等偵測雛型。

### 2.2 尚未完成

- 現行 message schedule 只接受 `follow` trigger，尚不接受 order lifecycle／workflow event；
- 訂單事件寫入後，沒有 canonical outbox／consumer 將事件轉成 LINE notification intent；
- `BECLASS-001` 目前是「缺少問卷」警示，不等於已自動提醒客戶；
- `LINE-001`／`005` 是「無法通知」警示，不能當作已建立發送任務；
- committed bootstrap 範本只涵蓋身分綁定、新好友引導等內容；正式 DB 可能已有管理頁後續版本，因此需先匯出 DB current revision 做差異盤點；
- 沒有一份經人工核准的 trigger→recipient→template→delay→suppression 規則表；
- 沒有狀態事件與 delivery task 之間的 durable linkage，也無法完整回答「為何沒發」。

## 3. 第一性原理與核心裁決

### 3.1 狀態不是訊息

`orders.status` 只表示目前結果，不足以證明何時、為何進入該狀態，也無法證明通知是否已處理。自動通知必須由 immutable source event 驅動，不得以反覆掃描 current status 作為主要觸發方式。

### 3.2 通知觸發分成三類

1. **生命週期轉移**：例如 `洽談中 → 訂單成立`；
2. **工作流程里程碑**：例如月嫂正式指派、合約完成、服務日期變更；
3. **條件／時間提醒**：例如客戶尚未補齊資料、服務前三天提醒。

三類事件均需穩定 identity。current-state scanner 只可作 reconciliation／漏接補償，不可直接無條件重送。

### 3.3 歷史資料預設靜默

歷史匯入、migration backfill 或人工修復既有狀態時，預設 `notification_policy = historical_silent`：

- 保留歷史狀態與來源證據；
- 不把 113 年等歷史訂單當成今天剛進入該狀態；
- 不自動補發舊的成立、開始、完成或取消通知；
- 如確需補發，必須由管理員 Preview 後以明確 `manual_replay` command 執行並留下 reason／receipt。

### 3.4 訊息範本與觸發規則分離

- Message Template 擁有顯示文字、變數與訊息型別；
- Notification Rule 擁有事件、收件角色、時機、條件、抑制規則與 template reference；
- 修改範本不應改變已排定任務的 payload snapshot；
- 修改規則只影響規則生效版本之後的新 source event，除非人工執行重新評估。

## 4. Global → Domain → Subsystem → Module

### 4.0 本次可啟用的事件邊界

規則後端可管理所有已登錄 event／checkpoint／predicate，但只能對已有 owning-Domain committed event
adapter 的種類啟用。本工作包承接 Orders、Scheduling、Client Finance 與 Case Import 已存在的 committed
event／outbox adapter；未來其他 owner event writer 必須另立 Work Package。本工作包不以 current-state
polling、管理 API 或 LINE webhook 偽造業務事件。沒有已登錄 adapter 的規則可儲存及 Preview，儲存啟用
必須 fail closed。

### 4.1 Global

所有對外 LINE 主動通知必須可追溯到一個真實 source event 與一個已核准規則版本；同一事件、同一規則、同一收件人至多產生一個有效通知 intent。

Global invariants：

- 無 source event 不發送；
- 無有效 LINE binding 不猜收件人；
- 歷史匯入不自動推送；
- 同一 idempotency identity 不重複發送；
- 訂單取消或排程改變後，不發送已過期的未來提醒；
- 管理 UI 不自行判斷業務條件，只顯示 typed decision／delivery result。

### 4.2 Domain ownership

| Domain | 擁有責任 | 不擁有責任 |
|---|---|---|
| Orders | 訂單生命週期狀態與 state events | LINE 範本、provider delivery |
| Scheduling／Matching | 指派、服務日期、配對聯繫與意願事件 | 訂單 canonical status |
| Client／Staff Identity | 客戶、月嫂身分與有效 LINE binding | 通知業務時機 |
| LINE Integration | 規則版本、notification intent、payload snapshot、delivery／attempt | 推導訂單是否成立或資料是否完整 |
| Anomalies | 缺綁定、漏觸發、逾期與永久失敗投影 | 取代 source event 或 delivery receipt |

### 4.3 Subsystems

1. `Notification Catalog`：管理規則版本與有效期間；
2. `Source Event Adapter`：把各 Domain event 轉成 provider-neutral notification trigger；
3. `Notification Policy Evaluator`：判斷收件人、條件、延遲與 suppression；
4. `Notification Intent Workflow`：原子建立 intent、payload snapshot 與 delivery task；
5. `Delivery Worker`：沿用既有 LINE retry／attempt／terminal failure；
6. `Notification Reconciler`：找出漏建 intent、過期提醒與 orphan task；
7. `Notification Administration`：規則矩陣、Preview、紀錄與人工補發。

### 4.4 Modules

- `NotificationTrigger`
- `NotificationRule`
- `RecipientResolver`
- `NotificationPrerequisitePolicy`
- `NotificationSuppressionPolicy`
- `TemplateVariableBuilder`
- `NotificationIdempotencyKeyFactory`
- `StaleScheduledNotificationCanceller`
- `NotificationDecisionView`
- `NotificationTimelineQuery`

## 5. 應記錄與通知的狀態目錄草案

### 5.1 訂單 canonical status：確認為五個

| 狀態／事件 | 必須記錄 | 建議自動發送 | 建議收件人 | 初步業務規則 |
|---|---:|---:|---|---|
| 建立訂單並進入 `洽談中` | 是 | 不發通用狀態訊息 | — | 改由「登記成功／待補資料／配對聯繫」等具體事件處理 |
| `洽談中 → 訂單成立` | 是 | 不因 status transition 自動發送 | — | `FLOW-05` 只記錄；訂單資訊由 `FLOW-06` 人工按鈕發送 |
| `訂單成立 → 服務中` | 是 | 不發通用狀態訊息 | — | 改由 D-3、確認寶寶狀況及服務期間等具體規則處理 |
| `服務中 → 訂單完成` | 是 | 不發通用狀態訊息 | — | 改由結案前 D-5、滿意度調查等具體規則處理 |
| `任何有效狀態 → 訂單取消` | 是 | 否 | — | `FLOW-27` 只記錄取消結果並取消尚未送出的提醒，不建立 LINE 通知規則 |
| 訂單重新開啟／復原 | 是 | 否 | — | 保留 lifecycle event，不建立本版 LINE 通知規則 |
| before status = after status | 是 | 否 | — | 維持／阻擋決策只供 audit、異常與管理 UI，不應發送狀態推進訊息 |

因此「訂單狀態」本身是 **5 個**，但已確認不能把 status 與通知一對一綁定。成立、服務中、完成與取消只記錄 canonical transition；實際訊息由第 5.3～5.4 節已核准的具體業務事件觸發。

### 5.2 工作流程與條件提醒候選目錄

以下不是新的訂單 status，但需要獨立記錄與評估是否自動發送：

| 觸發事件 | 現況 | 建議收件人 | 建議行為 | 待確認事項 |
|---|---|---|---|---|
| 客戶服務登記／LINE 綁定成功 | 已有範本與 workflow | 客戶 | 保留既有即時通知 | 是否與建立訂單合併，避免連續兩則相似訊息 |
| 客戶尚未填 BeClass／少填資料 | `BECLASS-001` 偵測雛型 | 客戶 | 到期後提醒，補齊即取消尚未送出的後續提醒 | 「少填」是只缺整份問卷，或包含問卷內必要欄位 |
| 客戶 LINE 未綁定 | `LINE-001` 雛型 | 行政 | 建立異常，不建立客戶 delivery task | 綁定完成後是否立即補送尚有效訊息 |
| 候選月嫂資訊-1 | 已有專用手動傳送 | 候選月嫂 | 沿用 Matching intent／紀錄 | 是否納入自動化或維持人工選人後發送 |
| 候選月嫂資訊-2 | 已有專用手動傳送 | 候選月嫂 | 沿用 Matching intent／紀錄 | 前置條件必須是資訊-1已送且月嫂有意願 |
| 月嫂回覆願意／婉拒 | 已有意願紀錄 | 行政；是否通知客戶待定 | 寫回覆事件，不直接改訂單狀態 | 客戶是否需要即時知道候選階段結果 |
| 月嫂正式指派 | 部分已有 assignment facts | 客戶＋月嫂 | 發送雙方確認與聯絡／服務摘要 | 多月嫂時每位只能收到自己的 segment |
| 預計服務日期表首次確認 | 納入月嫂配對中心 P0 計畫 | 選定月嫂；客戶待定 | 人工按鈕或事件驅動 | 是否也自動傳客戶 |
| 正式服務日期／班表變更 | 有 scheduling root，未接通知 | 受影響客戶＋月嫂 | 只傳送差異與新版本；取消舊提醒 | 變動多少才發、臨時換班收件人 |
| 合約完成 | 有 contract event | 客戶；月嫂待定 | 告知下一步，不直接等同訂單成立 | 與訂金入帳的先後條件 |
| 訂金確認 | 有 finance／lifecycle facts | 客戶＋月嫂 | 由正式訂金確認事件發送一次 | 不從 bank import row 或 status current value 直接發送 |
| 服務前提醒（例如 D-3） | 舊規格曾出現概念，未形成正式規則 | 客戶＋月嫂 | 依正式服務日期排程 | 提前天數、發送時間、假日與異動重排 |
| 實際服務開始確認 | lifecycle 可記錄 | 客戶＋月嫂 | 只記錄狀態；由 D-3／服務期間的具體規則發送 | 預計開始日不等於實際開始 |
| 服務完成 | auto completion event 已存在 | 客戶＋月嫂 | 只記錄狀態；由結案前 D-5／滿意度規則發送 | 是否另需完成通知尚未提出 |
| 訂單取消 | cancellation event 已存在 | — | 記錄取消並立即取消未來通知；不建立本版 LINE 通知 | 不得由提醒逾期直接取消訂單 |
| 月嫂 LINE 未綁定 | `LINE-005` 雛型 | 行政 | 建立異常，不猜其他帳號 | 綁定後補送窗口 |

### 5.3 流程圖提取清單（待人工確認）

> 來源：使用者於 2026-08-10 提供的服務流程圖。以下只是逐節點提取，不代表已核准為訂單 status 或自動通知規則。圖例為紅色「客戶動作」、黃色「人工動作」、紫色「自動」；綠色另包含 API、資料庫更新及時間／期間節點。

#### 主流程

| ID | 流程圖節點 | 圖示分類 | 初步事件分類 | 圖上外部動作 | 是否納入自動通知 |
|---|---|---|---|---|---|
| `FLOW-01` | 客戶在政府網填表（產生訂單 ID） | 客戶動作 | 訂單來源事件 | — | **不納入 Notification Catalog v1** |
| `FLOW-02` | 電聯客戶（確認經驗） | 人工動作 | 人工接觸紀錄 | — | **不納入 Notification Catalog v1** |
| `FLOW-03` | 客戶加 LINE 官方帳號（標記訂單 ID），傳送歡迎訊息請客戶填寫 BeClass 表單 | 客戶動作 | LINE 綁定＋歡迎訊息 | API | **不納入 Notification Catalog v1** |
| `FLOW-04` | `[固定訊息]` 提醒登記與契約；若三天內客戶沒有填寫表單，每天發送提醒訊息 | 自動 | 缺表單／定時提醒 | API | **自動通知**；滿 3 天仍未填後開始每日提醒，最多 4 次，D+7 後轉 `FLOW-25` |
| `FLOW-05` | 客戶填寫 BeClass 表單，訂單成立 | 自動 | 表單完成＋訂單里程碑 | 資料庫更新 | **只記錄狀態**；本事件本身不自動發送 |
| `FLOW-06` | `[固定訊息]` 確認訂單資訊 | 自動 | 訂單資訊確認 | API | **人工按鈕通知** |
| `FLOW-07` | 詢問服務人員接案意願 | 人工動作 | 配對接觸 | — | **人工按鈕通知**；目前已有資訊-1／意願雛型 |
| `FLOW-08` | 傳送服務人員資料（PDF 履歷） | 人工動作 | 履歷傳送 | — | **人工按鈕通知**；目前已有履歷傳送雛型 |
| `FLOW-09` | `[固定訊息]` 確認合約內容 | 自動 | 合約確認通知 | API | **人工按鈕通知** |
| `FLOW-10` | `[固定訊息]` 簽名邀約（好好簽） | 自動 | 電子簽署邀請 | — | **人工按鈕通知** |
| `FLOW-11` | `[固定訊息]` 確認訂金收款；人工更新資料 | 人工動作 | 收款確認＋資料更新 | 資料庫更新 | **自動通知**；由正式收款確認事件觸發，不由銀行匯入列直接觸發 |
| `FLOW-12` | 用私人管理帳號拉群組；群組名稱＝市府訂單 ID | 人工動作 | LINE 群組建立 | API | **人工按鈕通知／動作**；需檢討私人帳號與正式系統邊界 |
| `FLOW-13` | `[固定訊息]` 請服務人員回傳動線與食材 | 自動 | 服務前資料請求 | API | **自動通知** |
| `FLOW-14` | `[固定訊息]` 確認食材並備課 | 自動 | 服務前確認 | API | **自動通知** |
| `FLOW-15` | 討論動線與時間 | 人工動作 | 人工協調紀錄 | — | **自動通知**；需再定義觸發時間與回覆完成條件 |
| `FLOW-16` | `[確認服務開始時間前 3 天]` | 時間節點 | 服務前 D-3 trigger | — | **只記錄狀態／時間條件**；作為後續通知 trigger，本身不發送 |
| `FLOW-17` | `[固定訊息]` 確認寶寶狀況 | 自動 | 服務前確認 | API | **自動通知** |
| `FLOW-18` | 討論餐食 | 人工動作 | 人工協調紀錄 | — | **自動通知**；需再定義觸發時間與回覆完成條件 |
| `FLOW-19` | `[服務期間]`（服務人員與雇主） | 期間節點 | 服務期間 | — | **只記錄狀態／期間條件**；不是單一可發送事件 |
| `FLOW-20` | `[固定訊息]` 提醒服務人員上傳寶寶日誌 | 自動 | 服務期間定時提醒 | API | **自動通知** |
| `FLOW-21` | `[固定訊息]` 提醒客戶結清尾款給服務人員 | 自動 | 尾款提醒 | API | **自動通知** |
| `FLOW-22` | `[結案前 5 天]` | 時間節點 | 結案前 D-5 trigger | — | **只記錄狀態／時間條件**；作為後續通知 trigger，本身不發送 |
| `FLOW-23` | `[固定訊息]` 滿意度調查 Google 表單（需帶入訂單 ID 與 Mail 給客戶） | 自動 | 滿意度調查 | API | **自動通知** |
| `FLOW-24` | `[固定訊息]` 推薦回購邀請 | 自動 | 行銷／回購邀請 | API | **不納入 Notification Catalog v1** |

#### 未填 BeClass 的取消分支

| ID | 流程圖節點 | 圖示分類 | 初步事件分類 | 圖上外部動作 | 是否納入自動通知 |
|---|---|---|---|---|---|
| `FLOW-25` | `[固定訊息]` 客戶 7 天後未填寫表單；超過 7 天處理案件時限，詢問是否取消訂單 | 自動 | 缺表單逾期＋取消確認 | API | **自動通知**；D+7 進入本流程，後續提醒間隔依序延長 1、2、3 天，最後仍無結果則建立人工電話關切警示 |
| `FLOW-26` | `[固定訊息]` 每天詢問是否取消訂單 | 自動 | 取消確認重複提醒 | API | **併入 FLOW-25**；改採 1、2、3 天遞增間隔，不再每日無限發送 |
| `FLOW-27` | 系統註記「取消訂單」 | 自動 | 訂單取消結果 | API | **不建立 LINE 通知規則**；取消仍須由 Orders lifecycle command 記錄，不得因提醒逾期自動取消 |

#### 依原流程圖顏色提取的分類

- 客戶動作：`FLOW-01`、`FLOW-03`；
- 人工處理／人工協調：`FLOW-02`、`FLOW-07`、`FLOW-08`、`FLOW-11`、`FLOW-12`、`FLOW-15`、`FLOW-18`；
- 自動或固定訊息候選：`FLOW-04`～`06`、`FLOW-09`～`10`、`FLOW-13`～`14`、`FLOW-17`、`FLOW-20`～`21`、`FLOW-23`～`26`；
- 時間／期間 trigger：`FLOW-16`、`FLOW-19`、`FLOW-22`；
- 已校正的取消結果節點：`FLOW-27`。

正式確認時，每一列需分別選擇：`只記錄`、`自動通知`、`人工按鈕通知`、`不納入`。不能因流程圖畫成紫色，就直接推論一定要由新系統自動發送。

### 5.4 已確認的 Notification Catalog 分類

#### 自動通知

`FLOW-04`、`FLOW-11`、`FLOW-13`、`FLOW-14`、`FLOW-15`、`FLOW-17`、`FLOW-18`、`FLOW-20`、`FLOW-21`、`FLOW-23`、`FLOW-25`。

- `FLOW-04`：滿 3 天仍未填 BeClass 後，開始每日發送登記提醒；
- `FLOW-04` 最多發送 4 次；D+7 評估時仍未填，就終止 `FLOW-04` 並轉入 `FLOW-25`；
- `FLOW-25`：D+7 進入取消確認流程；後續依序間隔 1、2、3 天提醒，`FLOW-26` 併入此規則；
- 遞增時間線已確認為：D+7 首次詢問，D+8、D+10、D+13 追蹤；
- `FLOW-25` 最後一次仍未完成 BeClass、也沒有明確取消決定時，停止自動通知並建立「人員電話聯絡客戶關切」警示；
- `FLOW-11`：由「訂金已正式確認」事件觸發，不能因匯入到疑似收款資料就直接通知；
- `FLOW-15`、`FLOW-18`：雖在原圖是人工討論節點，已裁決為自動通知；仍需補觸發時點、收件人與完成條件。

#### 人工按鈕通知／動作

`FLOW-06`、`FLOW-07`、`FLOW-08`、`FLOW-09`、`FLOW-10`、`FLOW-12`。

每次操作都必須有 Preview、收件人確認、固定 idempotency key、delivery receipt 及重複點擊防護。`FLOW-12` 同時包含建立 LINE 群組的外部副作用，不能只把它視為文字訊息發送。

#### 只記錄狀態／條件

`FLOW-05`、`FLOW-16`、`FLOW-19`、`FLOW-22`。

- `FLOW-05` 記錄 BeClass 完成事實；是否導致訂單成立仍應由 Orders 規則判斷；
- `FLOW-16`、`FLOW-22` 是相對日期 trigger；
- `FLOW-19` 是一段期間，不是單一 transition。

#### 不納入 Notification Catalog v1

- `FLOW-01`、`FLOW-02`、`FLOW-03`、`FLOW-24` 不建立本功能的 notification rule；
- `FLOW-27` 不建立 LINE 通知規則，但「取消訂單」仍是 Orders lifecycle 必須保存的 canonical transition。

#### BeClass 提醒狀態機

```text
waiting_for_beclass
  → D+3 still_missing
      → FLOW-04 reminder 1
      → FLOW-04 reminder 2
      → FLOW-04 reminder 3
      → FLOW-04 reminder 4
  → D+7 still_missing
      → FLOW-25 cancellation_confirmation
      → wait 1 day → follow-up
      → wait 2 days → follow-up
      → wait 3 days → final follow-up
  → still_no_resolution
      → human_phone_contact_required
```

任一階段收到 BeClass 完成事實時，取消尚未發送的 `FLOW-04`／`FLOW-25` tasks 並結束提醒。收到客戶明確取消意願時，只建立待人工確認的取消請求；系統不得直接變更 Orders 狀態。電話關切完成後，行政人員必須記錄處理結果與 reason，才能結束警示或另走正式取消流程。

### 5.5 不應自動對外發送的狀態

- lifecycle transition 被 blocker 阻擋；
- 同狀態重新評估；
- migration／historical import／backfill；
- LINE identity conflict；
- 尚未完成收件人角色確認；
- template 變數缺失、規則停用或 source version 已 stale；
- 技術 retry／worker lease 等內部狀態。

上述項目應寫 decision／audit，必要時投影行政異常，但不應讓客戶或月嫂收到內部技術訊息。

### 5.6 2026-08-15 人工確認：BeClass 未完成提醒邊界

Notification Catalog v1 的「少填資料」僅指**已綁定 LINE 的客戶尚未有有效 BeClass 完成事實**。
它走 `FLOW-04`／`FLOW-25` 的既定節奏。已提交表單但欄位缺漏、格式無效或身份關聯歧義，維持
異常中心追蹤與 owning 業面補正；不建立客戶自動推播。合約資料與服務資料也不納入本規則，待各自
owner 有正式 source event 與 command 後另立 Notification Rule。

### 5.7 2026-08-15 人工確認：FLOW-13 服務前動線與食材提醒

`FLOW-12` 是雙方群組的開始：在訂金正式確認（`FLOW-11`）後，人工建立並記錄以市府訂單 ID 命名的
LINE 群組。後續服務前雙方訊息不得改以個別私訊繞過這個邊界。

`FLOW-13` 是一次性服務前提醒，不是可由 LINE 對話自動判定完成的催收流程。收件人為 `FLOW-12` 已
成功建立、且明確對應該服務案及現行正式指派的客戶／月嫂雙方群組；觸發條件為該指派仍有效，且服務
開始日前三天（`FLOW-16`）。每一服務案／指派版本只建立一次投遞任務。投遞任務建立成功後即不再
提醒；LINE 回覆、已讀或聊天內容都不是完成事實。群組尚未建立、群組關聯不明或指派已變更時，必須
fail closed 並建立行政處理警示，不得改以私訊補發。

若未來要按「已回傳動線與食材」停止或加強催收，必須先由 Scheduling 建立可驗證的回傳資料及完成
事實，並以新的 owner event／Notification Rule 承接。

### 5.8 2026-08-15 人工確認：FLOW-14 食材與備課確認收件群組

`FLOW-14` 同樣投遞至 `FLOW-12` 已成功建立、且明確對應該服務案及現行正式指派的客戶／月嫂雙方
群組；不得改用任一方私訊。觸發條件為指派仍有效且服務開始日前三天（`FLOW-16`），每一服務案／
指派版本只建立一次投遞任務。投遞任務建立成功後即不再提醒；LINE 回覆、已讀或聊天內容不是完成
事實。群組不存在、關聯不明或指派版本已失效時，fail closed 並建立行政處理警示。

### 5.9 2026-08-15 人工確認：FLOW-15 動線與時間討論提醒

`FLOW-15` 是服務前 D-3 的一次性討論提醒。收件人為 `FLOW-12` 已成功建立、且明確對應該服務案
及現行正式指派的客戶／月嫂雙方群組；觸發條件為指派仍有效且服務開始日前三天（`FLOW-16`）。每一
服務案／指派版本只建立一次投遞任務。投遞任務建立成功後即不再提醒；LINE 回覆、已讀或聊天內容
不是完成事實。群組不存在、關聯不明或指派版本已失效時，fail closed 並建立行政處理警示。

### 5.10 2026-08-15 人工確認：FLOW-17 寶寶狀況確認提醒

`FLOW-17` 是服務前 D-3 的一次性確認提醒。收件人為 `FLOW-12` 已成功建立、且明確對應該服務案
及現行正式指派的客戶／月嫂雙方群組；觸發條件為指派仍有效且服務開始日前三天（`FLOW-16`）。每一
服務案／指派版本只建立一次投遞任務。投遞任務建立成功後即不再提醒；LINE 回覆、已讀或聊天內容
不是完成事實。群組不存在、關聯不明或指派版本已失效時，fail closed 並建立行政處理警示。

### 5.11 2026-08-15 人工確認：FLOW-18 餐食討論提醒

`FLOW-18` 是服務前 D-3 的一次性討論提醒。只有 Orders root 的 `requires_cooking` 已由正式
Orders Terms 事實確認為 `true` 時，才可建立投遞任務；`false` 與 `NULL`（未知、缺漏、矛盾或尚未
唯一配對）一律不發送。收件人為 `FLOW-12` 已成功建立、且明確對應該服務案及現行正式指派的客戶／
月嫂雙方群組；觸發條件為指派仍有效且服務開始日前三天（`FLOW-16`）。每一服務案／指派版本只建立
一次投遞任務。投遞任務建立成功後即不再提醒；LINE 回覆、已讀或聊天內容不是完成事實。群組不存在、
關聯不明或指派版本已失效時，fail closed 並建立行政處理警示。

### 5.12 2026-08-15 人工確認：通知規則改為後台可配置

本工作包不將 `FLOW-*` 的收件人、固定訊息、時間節點、發送頻率或狀態條件寫死在程式。後台操作固定
呈現為「編輯 → 預覽 → 儲存啟用／刪除」：編輯先形成不生效的草稿；預覽以去識別化事實顯示影響；
儲存啟用才發布新 revision；已啟用規則的「刪除」必須停止未來 evaluation，並取消所有尚未交給 LINE
provider 的舊 rule intent，確保舊訊息不再套用；保留歷史版本、intent 與 delivery receipt。provider 已
接受或已送達的訊息無法撤回，必須在時間軸明示。從未啟用、也沒有任何 inbound reference 的草稿才可
實體刪除。§5.7～§5.11 是已討論的**初始規則內容
範例**，未來可由發布新 revision 調整，不得以修改資料列或覆寫舊 receipt 改寫歷史。

規則可設定：

- 觸發節點：只能選擇已登錄、由 owning Domain 提供的 immutable event 或 service-time checkpoint；
- 收件人：客戶、現行有效指派月嫂、或已明確綁定該服務案的雙方 LINE 群組；
- 固定訊息：選擇已發布 template revision 與受允許變數，不能輸入任意 provider payload；
- 時機與頻率：立即、相對服務時間（如 D-3）、服務結束時、一次性或受上限約束的週期；
- 前置／停止條件：只能由白名單 root fact、事件或可驗證 existence predicate 組成，不能以 LINE 已讀、
  聊天內容或任意 SQL／自由文字判定；
- 變更範圍：只影響發布後的新 evaluation；已排程但尚未發送的 intent 是否取消，必須在 Publish Preview
  明示並留下 receipt。

`FLOW-20` 的業務語意成為此能力的代表案例：在某服務日的正式服務結束 checkpoint，僅當目前有效
assignment 的月嫂尚未有該服務日的寶寶日誌完成事實時，規則才符合。實際收件人、模板、延遲、頻率與
上限由後台發布的 rule revision 決定；資料未知、assignment／日誌關聯不唯一或群組關聯不明時一律
fail closed，寫入可處理的行政警示而非猜測發送。

此類警示使用 `LINE-006`（`line_notification`）：fingerprint 為 `case_no + notification_reason`，唯一 follow-up 是唯讀 `QueryLineNotificationTimeline`；不提供在異常中心直接重送或改寫通知。

## 6. Notification Rule typed contract

每條正式規則至少包含：

```text
rule_id
rule_version
enabled
source_domain
trigger_kind / source_event_code / checkpoint_code?
recipient_selector
template_revision_id
schedule_policy: immediate | relative_service_time | service_end | business_time
frequency_policy: once | recurring_bounded
condition_expression[]
suppression_policy[] / stop_expression[]
published_at / retired_at
effective_from / effective_until?
```

規則不得只保存中文名稱。觸發、收件人 selector、template revision、schedule、frequency、condition、
suppression 與停止條件都必須是穩定、白名單化的 machine-readable code；後台不能提供 SQL、任意
Python expression、任意 webhook payload 或直接送 LINE 的捷徑。

## 7. 根事實、衍生值與狀態機

### 7.1 根事實

- owning Domain immutable source event；
- notification rule revision；
- event evaluation decision；
- notification intent 與 payload snapshot；
- resolved recipient binding snapshot；
- delivery task 與 attempt events；
- suppression／cancellation／manual replay event；
- provider receipt 與 terminal error。

### 7.2 衍生值

- 某訂單通知時間軸；
- 已發／待發／失敗／被抑制數量；
- 下一則預計通知；
- 是否漏接通知；
- 可否人工補發。

UI 不得從 current order status 與 line task row 自行拼湊上述結果。

### 7.3 狀態機

```text
source_event observed
  → evaluated
      → suppressed
      → intent_created
          → scheduled
              → processing
                  → sent
                  → retryable_failed → scheduled
                  → terminal_failed
              → cancelled_stale
```

`sent`、`suppressed`、`terminal_failed`、`cancelled_stale` 是該 intent 的 terminal result；人工補發建立新的 manual replay intent，不改寫舊紀錄。

## 8. 交易、冪等、retry 與 conflict

1. Owning Domain 在寫 source event 的同一交易 append outbox；LINE consumer 不與 Orders transaction 共用資料庫業務判斷；
2. consumer 以 `source_event_identity + rule_id + rule_version + recipient_role + recipient_identity` 建 idempotency key；
3. 同 key、同 fingerprint 回原 receipt；同 key、不同 payload 為 conflict，禁止覆蓋；
4. intent、template snapshot、recipient snapshot、delivery task 在 LINE UoW 同一交易建立；
5. provider timeout／429／5xx 依既有 bounded retry；輸入缺資料、無綁定或 identity conflict 不做技術 retry；
6. 取消訂單、服務日期變更、換月嫂時，以 source linkage 取消仍 pending 的 stale future tasks；已 sent 訊息不得刪除，只能追加更正通知；
7. 規則刪除必須與 worker 取得 task 的 lease 互斥：刪除先取消尚未 provider-accepted 的 intent，worker
   在 provider request 前重讀 intent cancellation state；不能讓已刪除規則的 queued／retry task 穿透送出；
8. Reconciler 驗證「符合規則的 source events 是否都有 terminal decision」，只補建缺失 decision，不盲目重送；
9. 排程到期前再次驗證 source version／recipient binding／rule validity；stale 或已刪除時轉 `cancelled_stale`。

## 9. Typed errors 與 suppression reasons

### 9.1 Typed errors

- `notification_rule_not_found`
- `notification_rule_revision_conflict`
- `notification_source_event_not_found`
- `notification_source_event_conflict`
- `notification_template_unavailable`
- `notification_template_variables_missing`
- `notification_recipient_unresolved`
- `notification_recipient_conflict`
- `notification_intent_idempotency_conflict`
- `notification_source_stale`
- `notification_delivery_unavailable`
- `notification_audit_persistence_failed`

### 9.2 Suppression reasons

- `historical_source_silent`
- `same_status_evaluation`
- `transition_blocked`
- `rule_disabled`
- `recipient_not_applicable`
- `recipient_line_not_bound`
- `recipient_identity_conflict`
- `prerequisite_not_satisfied`
- `source_superseded`
- `already_delivered`

外部訊息不得包含內部 error code；管理 UI 則必須顯示 typed reason 與可採取的人工動作。

## 10. 後台 API 與未來管理介面

先提供獨立、typed 的 LINE Notification bounded-domain 後台 API；目前不投入 Streamlit 頁面。未來 React
管理介面使用此 API，並與「新好友自動通知」分開呈現。操作流程固定是「編輯 → 預覽 → 儲存啟用／刪除」：

1. **通知規則矩陣**：觸發事件、收件人、範本、時機、是否啟用、規則版本與刪除狀態；
2. **規則 Preview**：以去識別化 sample facts 顯示哪些人會收到哪則訊息；
3. **訂單通知時間軸**：source event、decision、task、attempt、sent／suppressed reason；
4. **待處理問題**：缺 LINE 綁定、identity conflict、範本缺變數、terminal failure；
5. **人工補發**：需要 capability、reason、preview、固定 idempotency key 與 receipt；
6. **變更影響預覽**：修改規則前顯示只影響新事件，或會取消哪些尚未送出的 future tasks。

React 或其他替換式前端只能使用獨立 LINE Notification bounded-domain API 與 typed views，不得讀 raw DB 或
自行判斷狀態。後台 UI 也不得暴露任意 SQL、任意條件式或直接 LINE provider 呼叫。

## 11. 實作待辦

### P0：可配置規則架構與 source-event registry

- [x] `LINE-AUTO-P0-01` 匯出 DB current message template／schedule revision，與 committed bootstrap config 比對；去敏指紋與裁決見 `03_追蹤清單與證據/evidence/2026-08-16_line_notification_catalog_configuration_inventory.md`。
- [x] `LINE-AUTO-P0-02` 列出所有 production order lifecycle event writers 與 trigger event；證據為 `order_lifecycle_state_events`／`orders_domain_outbox`，由 `order_lifecycle_impact_writer.py` 在同一交易寫入。
- [x] `LINE-AUTO-P0-03` 盤點 Matching、Scheduling、Contract、Client Finance、BeClass completeness 等 source events；Client Finance 有 `client_finance_outbox`，Scheduling 以 service-day checkpoint 與 rebuild notification outbox 承接，BeClass 仍只有綁定資料列、未納入本次啟用。
- [x] `LINE-AUTO-P0-04` 定義可配置 rule grammar：trigger／recipient／template／schedule／frequency／condition／suppression／stop 的白名單與型別；實作於 `domains/line/notification_rules.py`。
- [x] `LINE-AUTO-P0-05` 定義 service-time checkpoint、日誌存在判斷、群組關聯、`requires_cooking` 等可供 rule 使用的 root-fact predicate registry；Scheduling checkpoint 與日誌完成 root fact 已由 `204`／`205` 建立。
- [x] `LINE-AUTO-P0-06` 確認既有範本僅涵蓋綁定、客服與新好友引導；服務日提醒不得挪用，管理員必須先發布合適 template revision，見上述盤點收據。
- [x] `LINE-AUTO-P0-07` 確認歷史匯入永遠 silent，及人工補發的核准權限；裁決見 §3.3、§13.5。
- [x] `LINE-AUTO-P0-08` 產出並人工簽核 Notification Rule Catalog v1（可配置 rule definition，不要求預先逐條硬編碼）；裁決見 §5.12。

### P1：事件與規則架構

- [x] `LINE-AUTO-P1-01` 建立 provider-neutral `NotificationTrigger`／`NotificationRule`；實作為 `NotificationSourceEvent`、versioned rule definition 與 `NotificationDecision`。
- [x] `LINE-AUTO-P1-02` 為 Orders lifecycle、Client Finance deposit 與 Scheduling service-time checkpoint 定義 immutable outbox adapter；未知或未登錄 owner event 一律不投影，實作於 `subsystems/line/notification_source_adapters.py`。
- [x] `LINE-AUTO-P1-03` 建立 rule revision、effective period、recipient policy 與 suppression policy；規則預設 shadow，只有 `enabled=true` 才建立 task；群組必須為 active 且雙方 joined。
- [x] `LINE-AUTO-P1-04` 建立 historical／migration source classification；`historical_silent` 與 manual replay immutable source 已實作。
- [x] `LINE-AUTO-P1-05` 設計 additive schema、release descriptor 與 rollback／writer cutover 順序；涵蓋 `203`～`207`。

### P2：可靠觸發與發送

- [x] `LINE-AUTO-P2-01` 實作 source event consumer 與 Notification Policy Evaluator；目前啟用 Scheduling service-time checkpoint lane。
- [x] `LINE-AUTO-P2-02` 原子建立 decision、intent、snapshot 與 delivery task；同一 LINE UoW 完成，occurrence 有唯一鍵。
- [x] `LINE-AUTO-P2-03` 串接既有 delivery worker／attempt／retry；provider success 會同步標記 notification intent。
- [x] `LINE-AUTO-P2-04` 實作取消、改期、換月嫂時的 stale task canceller；Scheduling generation replacement 在同一交易寫 `scheduling_rebuild_notification_outbox`，LINE worker 只依被取代 assignment id 取消尚未送出的 service-day-log tasks；已 provider accepted 的紀錄保留。
- [x] `LINE-AUTO-P2-05` 實作 reconciliation，僅重跑已提交但尚無 decision 的 source-to-decision 投影，既有 intent 唯一鍵不會重送 provider；見 `subsystems/line/notification_reconciliation.py` 與 canonical worker。
- [x] `LINE-AUTO-P2-06` 將缺綁定、template／schedule 失效等不可自動修復原因投影為 `LINE-006`；異常中心只提供唯讀 timeline 導覽。

### P3：後台 API 與人工入口

- [x] `LINE-AUTO-P3-01` 新增規則 Query、Preview、Save/Enable、Delete、timeline 與 manual replay 的 typed backend API；不另設 Publish/Retire 狀態。
- [x] `LINE-AUTO-P3-02` 實作規則 revision conflict 與變更 Preview；
- [x] `LINE-AUTO-P3-03` 實作每案 notification timeline；
- [x] `LINE-AUTO-P3-04` 實作有權限、reason、preview、receipt 的人工補發；
- [x] `LINE-AUTO-P3-05` 為未來 React 管理介面提供 suppression／failure 原因與對應人工處理 typed view；不實作 Streamlit 頁面。

### P4：分階段啟用

- [x] `LINE-AUTO-P4-01` 先以 shadow mode 只產生 decision，不建立 provider delivery；規則需明確 `enabled=true` 才啟用。
- [x] `LINE-AUTO-P4-02` 以去識別化 service-time checkpoint、群組解析、日誌未完成與下廚條件案例驗證預期 decision／suppression；不含 UI 或 provider acceptance。
- [x] `LINE-AUTO-P4-03` 以 service-time checkpoint lane 做低風險 local enable characterization：duplicate source、missing recipient 與 stale assignment 均由 typed decision／cancellation 收斂。
- [x] `LINE-AUTO-P4-04` 已完成可啟用規則的 generic backend path；未登錄 owner event（例如 BeClass completion、未來 milestone）保持 rule 儲存／Preview 可見但 source projection fail closed，必須由 successor owner package 啟用。
- [x] `LINE-AUTO-P4-05` rule Delete 是 kill switch，會取消未 provider-accepted intent；worker pre-send reread、`LINE-006` 與 timeline API 提供監控／人工查詢。實體 LINE provider acceptance 依 frontmatter out_of_scope 未執行。

## 12. 分層驗收

### Module

- 規則匹配、收件角色、必要條件、suppression、idempotency 與 template variables；
- 五個 canonical status 與 same-status／blocked／historical case；
- D-N／business-time、timezone、改期與 stale 判斷。

### Subsystem

- source event→decision→intent→delivery task 單次建立；
- transaction rollback 不留下孤兒 intent／task；
- duplicate event、consumer crash、timeout、429／5xx、terminal failure；
- 取消／改期／換月嫂取消舊 future task；
- missing binding 不發送並建立正確異常。

### Domain

- 洽談中→成立→服務中→完成完整事件鏈；
- 任一階段取消；
- BeClass 缺資料→提醒→補齊→取消後續提醒；
- 正式指派與多月嫂 segment 不誤發他人資料；
- 歷史訂單匯入只留狀態與 silent decision，不發 LINE。

### Global

- 每則 outward message 都可追到 source event、rule revision、template snapshot、recipient snapshot 與 provider attempt；
- 同事件、同規則、同收件人不重複發送；
- shadow mode 與正式 mode 結果可對帳；
- production 無規則時 fail closed，不退回掃描 status 後直接發送。

## 13. 待人工確認

1. 已確認：僅「尚未有有效 BeClass 完成事實」；已提交欄位問題、合約資料及服務資料不納入本規則。
2. 已確認：`FLOW-13`～`18` 均以 `FLOW-12` 雙方群組為收件人、服務前 D-3 一次性發送；其中 `FLOW-18` 僅在 `requires_cooking=true` 時發送。LINE 對話不作為完成事實。
3. 已確認：`FLOW-20` 的「服務結束且尚未上傳寶寶日誌」是可配置 condition 的代表案例；頻率、時間、收件人與範本不硬編碼，改由發布後的 rule revision 決定。
4. `FLOW-21` 的尾款到期、月嫂願意／婉拒、正式指派與班表異動，均改由後台新增／發布相應 rule；實作前只須確認其 source event 與可用 predicate，不再逐條預設通知內容。
5. 已確認：所有 historical import／migration/backfill 預設 `historical_silent`；只能由人工 Preview 後的 `manual_replay` 建立新 intent，不能回寫或重送原來源事件。

本工作包的下一個架構確認點是：後台「編輯 → 預覽 → 儲存啟用／刪除」對應的 revision／安全刪除／
manual replay lifecycle、白名單 predicate registry，以及其 additive schema write set。確認後才能開始 production 實作與測試。

## 14. 2026-08-16 缺口收斂與阻斷條件

已實作的 Catalog 骨架以 schema part `203_line_notification_rule_catalog.sql` 保存不可變 source event、
decision 與可取消 notification intent；通知規則以 versioned configuration revision 保存。刪除規則時，
`LineNotificationRuleAdministration` 在同一 LINE UoW 先產生刪除 revision，再取消該規則所有尚未交給
provider 的 intent／delivery task；delivery worker 也會在呼叫 provider 前重讀 lease，避免刪除競態穿透。

現行可安全接入的 committed source 只有：

1. Orders `orders_domain_outbox` 的 lifecycle 事實；
2. Client Finance `client_finance_outbox` 的正式訂金確認事實。

以下是**業務根事實缺口**，不可由 Notification Catalog、自動輪詢或管理 API 偽造：

1. Scheduling 尚無每一服務日的 completed checkpoint outbox；
2. 寶寶日誌沒有可驗證、可關聯到服務日與指派的完成 root fact；
3. BeClass 只有表單／關聯寫入，沒有 case-level completion event outbox；
4. Scheduling rebuild 有 immutable event，但尚無 outbox snapshot，因此不能安全驅動 D-3 群組通知。

因此 `FLOW-20`、D-3 群組提醒與 BeClass 時間提醒在上述 owner command／outbox 建立、其 schema write set
與驗收經人工確認前固定 fail closed。這不是 LINE 技術重試可解的缺失；任何未知 source、predicate、
recipient 或關聯均只能產生 suppressed decision／行政警示，不能發送訊息。

## 15. 2026-08-16 月嫂寶寶日誌與餐食照片裁決

1. Rich Menu 的「寶寶日誌」只負責開啟月嫂 LIFF；它不是 webhook 寫入捷徑，也不傳 query-string user ID
   作為身分。
2. LIFF 必須以 server-side ID token 與已綁定月嫂身分驗證。後端只允許其提交自己仍有效指派的服務案／
   服務日；case、staff、assignment 或 service date 不符一律拒絕，不以姓名、群組或目前畫面猜測補正。
3. Scheduling 擁有每服務日的一筆 append-only 日誌完成事實、versioned receipt 與 committed outbox。
   日誌完成是 `FLOW-20` stop predicate；通知 Catalog 只消費此事件，不修改日誌。
4. 日誌內容由月嫂提交；若 Orders root `requires_cooking=true`，同一服務日必須至少有一張餐食照片才可
   完成。`false` 時不要求餐食照片；`NULL` 或無法唯一關聯時 fail closed，不宣告完成。
5. 照片 blob 不寫入 message payload 或 Scheduling row；以受控 object reference、content SHA-256、MIME、
   byte size 與日誌附件關聯保存。上傳失敗、內容型別不符、超過上限或外部儲存未確認時不建立完成事件。
6. 服務日 checkpoint 由 Scheduling worker 依已提交的 schedule/assignment snapshot 與 Orders 正式
   `service_end_time + service_end_day_offset` 產生；它是 owner event，不得以曆日 23:59 或 Notification
   Catalog 掃描 current status 偽造。服務時段不完整時固定 fail closed，不宣告服務已結束。日誌完成前的提醒
   頻率、時間與模板仍由 Notification Rule revision 配置。

### 15.1 月嫂操作入口與照片上傳邊界

1. 第一版入口沿用「排班資訊」月嫂 LIFF：月嫂由自己的正式服務日選擇「上傳寶寶日誌」，前端只帶
   `assignment_id` 與 `service_date` 到 Scheduling command；正式 case、月嫂、服務日與下廚需求仍由後端 fresh-read。
2. 未來可在月嫂 Rich Menu 新增「寶寶日誌」按鈕，但只能導向同一 LIFF。Rich Menu 圖片設計、Preview/Publish
   與 LINE provider 實際發布不屬本次後端驗收，未發布前不得聲稱已上線。
3. 餐食照片必須走已驗證月嫂的受控 media-intake，完成 object-store 保存、MIME／大小／內容雜湊驗證後才取得
   可提交的 media reference；不得把瀏覽器檔案名稱、base64 或任意 URL 當作照片。現有日誌 command 只接受
   已保存 reference，因此 direct LIFF multipart intake 是尚待實作的後端切片，不得以既有 webhook media 代替月嫂主動上傳。

## 16. 完成與封存裁決（2026-08-16）

- 規則 API、immutable source／decision／intent、日誌與 service-time checkpoint、stale cancellation、reconciliation、`LINE-006` 異常投影與 manual replay 已完成；API／worker focused tests 通過。
- `lu_test_dataset_contract_signing_v4` 已以 preserved-data candidate 驗證並同名替換，203～208 owned schema objects 均為 `exact`。
- `notification_rules` current revision 尚不存在，因此 production 預設 fail closed；日後管理員需先建立 template revision，再透過 Preview／Save 建立規則。這不是 backend 未完成或外送失敗。
- Rich Menu 圖片發布、React／Streamlit UI，以及實體 LINE provider acceptance 均在本工作包 `out_of_scope`；保留給後續 UI／provider rollout，不得被解讀為已上線。
- 新 owner event（BeClass completion、尾款、月嫂意願與其他未登錄 milestone）必須由各 owner successor package 提供 immutable outbox／predicate 後才可啟用，Catalog 不以輪詢或 guessed fact 補造。

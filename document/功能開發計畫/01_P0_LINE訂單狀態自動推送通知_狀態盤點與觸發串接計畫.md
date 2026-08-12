# LINE 訂單狀態自動推送通知：狀態盤點與觸發串接計畫

## 文件狀態

- 文件類型：新功能改善計畫；不屬於架構重整文件。
- 狀態：`Proposed／待人工確認通知目錄`。
- 優先級：`P0 狀態盤點與規格確認`；production 實作順位接在「休假代班天數精算與行事曆差異預覽修復」及「月嫂配對中心：單月嫂預設」之後。
- 本文件完成前不得開始 production code、schema migration 或 pytest 修改。
- 本文件只定義功能邊界、盤點方法與代辦；訊息文字仍以 LINE 管理頁核准版本為準。

## 1. 使用者需求

1. 訂單狀態或業務里程碑推進時，系統依規則自動推送 LINE 訊息給客戶、月嫂或兩者；
2. 沿用 LINE 管理頁已可維護的訊息範本，不把正式文字寫死在程式；
3. 補上「狀態／事件紀錄 → 規則判斷 → 建立發送任務 → 發送結果」完整鏈路；
4. 實作前先確認所有應記錄事件、收件人、發送時機與例外；
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

## 6. Notification Rule typed contract

每條正式規則至少包含：

```text
rule_id
rule_version
enabled
source_domain
trigger_kind
before_status? / after_status?
recipient_roles[]
template_id
send_timing: immediate | delayed | business_time
delay_policy?
prerequisites[]
suppression_policy[]
effective_from / effective_until?
```

規則不得只保存中文名稱。`trigger_kind`、recipient role、prerequisite 與 suppression reason 必須是穩定 machine-readable code。

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
7. Reconciler 驗證「符合規則的 source events 是否都有 terminal decision」，只補建缺失 decision，不盲目重送；
8. 排程到期前再次驗證 source version／recipient binding／rule validity；stale 時轉 `cancelled_stale`。

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

## 10. LINE 管理頁調整

在現有 LINE 管理頁新增「訂單自動通知」子頁，與「新好友自動通知」分開：

1. **通知規則矩陣**：觸發事件、收件人、範本、時機、是否啟用、規則版本；
2. **規則 Preview**：以去識別化 sample facts 顯示哪些人會收到哪則訊息；
3. **訂單通知時間軸**：source event、decision、task、attempt、sent／suppressed reason；
4. **待處理問題**：缺 LINE 綁定、identity conflict、範本缺變數、terminal failure；
5. **人工補發**：需要 capability、reason、preview、固定 idempotency key 與 receipt；
6. **變更影響預覽**：修改規則前顯示只影響新事件，或會取消哪些尚未送出的 future tasks。

Streamlit 只能使用獨立 LINE Notification bounded-domain API client 與 typed views，不得讀 raw DB 或自行判斷狀態。

## 11. 實作待辦

### P0：狀態與通知目錄人工確認

- [ ] `LINE-AUTO-P0-01` 匯出 DB current message template／schedule revision，與 committed bootstrap config 比對；
- [ ] `LINE-AUTO-P0-02` 列出所有 production order lifecycle event writers 與 trigger event；
- [ ] `LINE-AUTO-P0-03` 盤點 Matching、Scheduling、Contract、Client Finance、BeClass completeness 等 source events；
- [ ] `LINE-AUTO-P0-04` 逐列確認第 5 節 trigger、收件人、訊息、時機、前置條件與 suppression；
- [ ] `LINE-AUTO-P0-05` 定義「客戶少填資料」的完整欄位規則、到期點、提醒頻率與完成條件；
- [ ] `LINE-AUTO-P0-06` 確認哪些既有訊息範本可沿用、哪些需新增或合併；
- [ ] `LINE-AUTO-P0-07` 確認歷史匯入永遠 silent，及人工補發的核准權限；
- [ ] `LINE-AUTO-P0-08` 產出並人工簽核 Notification Catalog v1；未簽核不得進 P1。

### P1：事件與規則架構

- [ ] `LINE-AUTO-P1-01` 建立 provider-neutral `NotificationTrigger`／`NotificationRule`；
- [ ] `LINE-AUTO-P1-02` 為每個 owning Domain 定義 outbox contract，不以 current-state polling 取代事件；
- [ ] `LINE-AUTO-P1-03` 建立 rule revision、effective period、recipient policy 與 suppression policy；
- [ ] `LINE-AUTO-P1-04` 建立 historical／migration source classification；
- [ ] `LINE-AUTO-P1-05` 設計 additive schema、release descriptor 與 rollback／writer cutover 順序。

### P2：可靠觸發與發送

- [ ] `LINE-AUTO-P2-01` 實作 source event consumer 與 Notification Policy Evaluator；
- [ ] `LINE-AUTO-P2-02` 原子建立 decision、intent、snapshot 與 delivery task；
- [ ] `LINE-AUTO-P2-03` 串接既有 delivery worker／attempt／retry；
- [ ] `LINE-AUTO-P2-04` 實作取消、改期、換月嫂時的 stale task canceller；
- [ ] `LINE-AUTO-P2-05` 實作 reconciliation，偵測漏 decision 而非盲目補發；
- [ ] `LINE-AUTO-P2-06` 將缺綁定、identity conflict、永久失敗投影至異常中心。

### P3：管理頁與人工入口

- [ ] `LINE-AUTO-P3-01` 新增「訂單自動通知」子頁與 typed API client；
- [ ] `LINE-AUTO-P3-02` 實作規則矩陣、revision conflict 與變更 Preview；
- [ ] `LINE-AUTO-P3-03` 實作每案 notification timeline；
- [ ] `LINE-AUTO-P3-04` 實作有權限、reason、preview、receipt 的人工補發；
- [ ] `LINE-AUTO-P3-05` 顯示 suppression／failure 原因與對應人工處理入口。

### P4：分階段啟用

- [ ] `LINE-AUTO-P4-01` 先以 shadow mode 只產生 decision，不建立 provider delivery；
- [ ] `LINE-AUTO-P4-02` 用真實但去識別化案例比對人工預期結果；
- [ ] `LINE-AUTO-P4-03` 先啟用一種低風險事件，觀察 duplicate／missing／wrong recipient；
- [ ] `LINE-AUTO-P4-04` 逐規則啟用成立、開始、完成、取消與資料提醒；
- [ ] `LINE-AUTO-P4-05` 每次啟用均保留 kill switch、監控與人工查詢入口。

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

1. 「客戶少填資料」除整份 BeClass 未填外，是否包含已填問卷但缺必要欄位、合約資料或服務資料？
2. `FLOW-13`～`15`、`FLOW-17`～`18` 的確切收件人、觸發時間與「已完成、不再提醒」條件為何？
3. `FLOW-20` 寶寶日誌提醒是每天、每週或指定服務日；一天中幾點發送？
4. `FLOW-21` 尾款提醒的正式到期事實來源與提醒頻率為何？
5. 月嫂願意／婉拒是否要通知客戶，或只留在行政配對中心？
6. 正式指派、服務日期表及班表異動是否同時通知客戶與月嫂？
7. 是否確認所有 historical import／migration/backfill 預設不自動發送，只允許人工 Preview 後補發？

以上決策與 Notification Catalog v1 經人工確認後，才能開始 production 實作與測試。

# LINE 服務說明、客服互動與選單角色正式規格

## 1. 範圍與權威邊界

本文件為 LINE 官方帳號對話入口、四大 Rich Menu 角色選單（`default_menu`／`customer_menu`／`staff_menu`／`union_staff_menu`）、預約檢核閘道（Gateway）與 AI／常見問答 LIFF 知識庫之現行唯一正式規格。

- **上下游分工**：平台 Webhook 收件、投遞、客服工單與 `line_webhook_reply` 見 [`20_LINE客服與月嫂自助服務正式規格.md`](20_LINE客服與月嫂自助服務正式規格.md) 與 [`17A_LINE_Gateway_Inbox與通知投遞正式規格.md`](17A_LINE_Gateway_Inbox與通知投遞正式規格.md)；新案登記與非市民 14 天 Redis 待審儲存見 [`17B_Case_Import與非市民Redis待審正式規格.md`](17B_Case_Import與非市民Redis待審正式規格.md)；身分解除見 [`23_LINE身分管理與解除正式規格.md`](23_LINE身分管理與解除正式規格.md)。

## 2. 服務閘道（Gateway）與登記入口規則

1. **同一閘道兩步分流**。第一步顯示「新竹市民」與「非新竹市民」。第二步只顯示所選身分的兩個選項，並提供「返回選擇身分」。兩步選擇僅決定頁面導向，實際登記、身分與綁定結果由各目的地的既有流程核對。
   - **新竹市民 → 已在市府平台登記**。進入既有姓名與手機核對流程。資料完整且未綁定時完成綁定並排入選單更新。缺問卷或查無資料時，分別帶入已核對資料或姓名與手機轉入產婦問卷。核對錯誤只提示修正或明確點選「呼叫專員」。
   - **新竹市民 → 尚未在市府平台登記**。前往新竹市政府到宅月子媒合服務平台申請。
   - **非新竹市民 → 工會已建案，綁定 LINE**。手動建案及核准建案皆適用。沿用既有客戶綁定流程，以建案時的姓名與手機號碼核對。資料完整且未綁定時可完成綁定，免重填需求問卷。已綁定同一帳號時顯示已完成，需改綁時由客戶明確送出並由工會審核，核准前保留原綁定。查無資料、資料不完整或核對失敗時留在綁定頁，提示修正或聯絡工會。客服需求只在客戶明確呼叫專員後建立。
   - **非新竹市民 → 尚未申請**。開啟非市民自費申請專用 LIFF 頁。送出後顯示「申請已送出，待工會核准」。待審、核准建案及配號依 [非市民進件與待審規格 §3](17B_Case_Import與非市民Redis待審正式規格.md#3-非市民自費進件與專用-redis-7-待審隔離架構)。
   - **待審提示**。只在非新竹市民的第二步、兩個選項下方顯示「已送出申請，還在等工會審核？請等候審核結果，無須重複填寫。」這是固定提示，顯示時無須查詢個別申請。
2. **加入好友歡迎訊息退役（改由 LINE 官方帳號設定）**：系統不對 LINE `follow` 事件開啟身分流程、排程或發送歡迎訊息，加入好友歡迎訊息改於 LINE Official Account Manager 官方後台直接設定（避免重複發送或消耗推送額度）。原系統即時歡迎詞（`customer_onboarding_welcome`）、`D+1`～`D+3` 多日延遲引導排程與歡迎詞管理 API（`/api/v1/line/onboarding`）均已退役（API 回傳 `410 Gone`，資料庫設定歷史不刪除，管理端通知清單與公版目錄不再列入）；使用者於聊天室主動輸入客戶／月嫂／工會綁定關鍵字時，仍依 `line_webhook_reply` 回覆對應身分入口連結。

## 3. 服務說明與專用 AI 常見問答 LIFF

### 3.1 入口定位與退役頁清理

- **唯一常見問答入口**：Rich Menu「常見問答」與相關導流統一開啟專用 AI／FAQ LIFF（`?target=ai_assistant` / `/line-service-help?tab=ai`），呈現六大主題分類，共用 `service-menu` 回主選單 CTA。
- **分類導向**：原「服務流程介紹」（`service_flow`）與「費用與補助說明」（`fee_and_subsidy`）亦統一收斂導向 AI FAQ LIFF 主題頁；費用與補助固定使用現行政策分類說明「一般市民最高 40 小時／補助市民最高 120 小時（實際補助金額依本案服務資料計算）」，烹飪備料固定明示「由客戶購買並準備食材」。
- **訂單異動表單簡化**：`order_update` 改為純 URI 開啟頁，移除過去內嵌五顆快速動作按鈕及 `service_days` 直接調整欄位（改期統一走服務群組協議與月嫂提交流程）。
- **已退役訊息範本入口（11 個獨立範本與 `service-flow`／`service-payment` 皆回 `404`）**：`service-flow` 與 `service-payment` 之獨立查詢／預覽／編輯回傳 typed `404`（不刪除既有資料庫設定）；另以下 11 個無現行引用之 standalone 訊息範本編輯及公版預覽入口已自目錄移除並回傳 `404`：`staff_switch_fail`、`staff_menu_not_set`、`esc_success`、`esc_fail`、`bind_link_msg`、`register_success`、`bind_success_existing`、`bind_confirm_rebind`、`bind_fail_no_data`、`client_rebind_approved`、`staff_verification_requested`（bootstrap 與資料庫設定歷史不刪除，其他規則明確引用者仍沿該 rule ID 維護）。

## 4. 可發布知識庫目錄（Knowledge Catalog）

1. **題庫來源與種子資料**：基礎題庫定義於 `document/line/AI客服QA題庫.jsonl`（54 題核心問答）。`development` 環境啟動時自動進行冪等播種並預填可檢索索引；`production` 環境維持由管理員於介面手動觸發「播種／同步」與「審核發布」，禁止未經人工確認自動覆蓋線上知識版本。
2. **檢索與 `authoritative=false` 不變量**：
   - 先進行受保護的精確別名／題庫比對，僅針對已發布版本提供即時問答結果與引用來源。
   - 任何問答無法命中高信賴回答或超出題庫範圍時，一律回傳 `UNSUPPORTED` 並導回 AI FAQ 六大分類主題按鈕或顯示「聯絡專人服務」按鈕，**嚴禁聊天室自動觸發未受控自由生成回答或代行任何 Orders／Scheduling／Client 資料寫入**。
   - 嚴格區分 `author != reviewer != publisher` 發布檢核（非開發單人情境下不可由同一人越級自審自發）。

## 5. 四大角色圖文選單（Rich Menu Audiences）

為符合高齡友善操作與直觀辨識，全部 Rich Menu 統一採用 **`2500 x 1686` 高對比大字體規範**（主標字級 `138px`／副標或輔助說明 `48px`），**按鈕標籤一律壓縮至 6 個中文字以內**。四套選單與切換條件如下：

| 選單 ID | 適用身分（Role Context） | 四大按鈕固定標籤（≤ 6 字） | 動作／導向契約 |
|---|---|---|---|
| `default_menu` | `visitor`（未綁定訪客／待審新客） | `預約與登記`、`月嫂認證`、`常見問答`、`聯絡專人` | 預約與登記 → Gateway LIFF；月嫂認證 → `staff_binding` LIFF；常見問答 → `?target=ai_assistant`；聯絡專人 → Postback 明確呼叫專員 |
| `customer_menu` | `customer`（已綁定正式產婦／客戶） | `改個人資料`、`改訂單內容`、`常見問答`、`聯絡專人` | 改個人資料 → `profile_update` LIFF；改訂單內容 → `order_update` LIFF；常見問答 → `?target=ai_assistant`；聯絡專人 → Postback 明確呼叫專員 |
| `staff_menu` | `staff`（已綁定在職月嫂） | `我的訂單`、`我的排班`、`我的資料`、`我的薪資` | 我的訂單 → `staff_order_search` LIFF；我的排班 → `staff_schedule` LIFF；我的資料 → [月嫂更新個人資料](20_LINE客服與月嫂自助服務正式規格.md#月嫂更新個人資料)；我的薪資 → `staff_payout` LIFF |
| `union_staff_menu` | `union_staff`（已綁定工會後台人員） | `待辦工作台`、`客服中心`、`狀態追蹤`、`營運摘要` | 分別開啟 `line-mobile-admin` 對應視圖：`staff_review`、`customer_service`、`order_tracking`、`dashboard` |

- **雙角色與切換規則**：月嫂同時以產婦身分申請服務並完成二次驗證時，可於專用雙頁籤選單（`staff_customer_menu`）在「月嫂工作」與「我的月子」間切換視圖；當所屬產婦案件全數達到終結狀態（取消／完工結案歸檔）後，依 `R1-LIFECYCLE` 由 Orders closure outbox 驅動 LINE Identity 自動恢復為單一 `staff_menu`。
- **工會選單退役路由防呆**：`union_staff` 端原 `anomalies_center` 選單路徑自動重導至 `order_tracking`；`dashboard` 只消費經 server 遮罩且符合 [`34_營運報表與統計口徑正式規格.md`](34_營運報表與統計口徑正式規格.md) 口徑之本週營運摘要（`WeeklyOperationsReportQuery`／`operations-report.v4` 相容彙總），不揭露客戶或員工明碼個資。
- **身分退役回收**：工會於後台將月嫂辦理退役後，立即清除有效 `staff_id` 投影，並透過 Rich Menu saga 將其官方選單降級為 `customer_menu`（若具活躍客戶案）或 `default_menu`，同步回收 `staff_order_search`、`staff_schedule` 與 `staff_payout` 查詢授權。

## 6. 官方聊天室客服互動與狀態一致規則

1. 官方一對一聊天室不啟用自由對話 AI；使用者在未綁定／一般提問情境輸入任何一般語句時，一律只觸發自助引導卡片（走 `line_webhook_reply`），不建立客服工單。
2. 唯有明確點擊四選單「聯絡專人／聯絡工會人員」、輸入明確專員關鍵字或客訴事件進入點，方依 [`20_LINE客服與月嫂自助服務正式規格.md`](20_LINE客服與月嫂自助服務正式規格.md) §2 建立新工單（前單已 `resolved` 時強制建新單）或追加進行中工單；所有客服受理與結案訊息皆透過結構化事件留存可供查證。

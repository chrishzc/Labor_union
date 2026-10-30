# LINE 服務說明、客服互動與選單角色正式規格

## 1. 文件狀態與範圍

- 狀態：`consolidated-current-baseline`
- 收斂日期：2026-09-09
- 2026-09-16 使用者修訂：加好友引導只保留即時歡迎訊息；三日引導從現行需求與驗收移除，詳見 §4.1、§10.14。
- 上位契約：`17_External_Integration_LINE_Access正式規格.md`
- 關聯契約：`20_LINE客服與月嫂自助服務正式規格.md`、`23_LINE身分管理與解除正式規格.md`、`26_LINE四大模組Eraser流程圖轉錄與驗收基線.md`
- 來源：既有 Service Help 正式條款、已完成 migration 的歷史 QA／Rich Menu 規格，以及仍保留的 QA implementation-gap tracker 與 LINE 四大模組操作測試手冊；歷史來源只保留於 Git history，不另建 Authority。

本文件只補足「加好友的即時歡迎、使用者如何進入服務說明、回答如何發布啟用、何時轉人工、不同身分看到哪一類選單，以及本機 preview 的零外送邊界」。LINE identity、ticket root、delivery task、provider publication 與 M1～M4 transaction 仍由上位正式規格擁有。

## 2. Owner 與非目標

| Scope | Owner |
|---|---|
| Webhook、inbox、delivery task、attempt、provider result | `17` 的 LINE Integration |
| Service Help dispatch、Customer Service ticket／conversation／status | `20` |
| role-scoped binding、目前選定角色、replacement、revocation 與 default-menu reset | `23` |
| M1～M4 流程節點與跨模組 acceptance | `26` |
| 加好友歡迎、服務說明分類、核准回答 catalog、人工轉接與 menu audience | 本文件 |
| 具體業務金額、資格、進度、排班或帳務事實 | 對應 owning Domain |

不得由 FAQ、LLM、Rich Menu action、瀏覽器 local state 或客服文字直接寫 Orders、Scheduling、Finance、Staff、Access 或 LINE binding root。

## 3. 服務與問答入口、六類意圖及訂單修改分流

圖文選單左下的「AI 智慧問答」以 `?target=ai_assistant` 開啟同一整合頁 `/line-service-help?tab=ai`，可切換 AI 與常見問答；不再分占兩個選單格位。既有 `?target=faq` 仍開啟該頁的 FAQ 分頁。這是專用 LIFF 頁面，不啟動官方聊天室的自由文字 AI。

聊天室的「服務與問答」合併原「服務說明」與「常見問答」，是單一 guidance／dispatch entry，不是 unrestricted chatbot。舊文字「服務說明」、「常見問答」、「問答」與 `FAQ` 僅作同一入口的相容 alias，不得產生另一套卡片或語意。Current category 固定為：

1. `service_flow`／服務流程
2. `fee_and_subsidy`／收費與補助
3. `service_progress`／查詢服務進度
4. `profile_change`／修改登記資料
5. `human_contact`／聯絡工會人員
6. `other_question`／其他問題

處理規則：

- 服務流程：只可回覆已核准、版本化的流程說明與下一個安全入口。
- 收費與補助：只可使用已核准 wording；不得承諾個案最終金額、資格或核定結果。需要個案值時轉 owning API 或人工。
- 餐飲食材：月嫂料理所需食材由客戶或家人自行購買、事先準備並負擔費用；月嫂不負責外出採買、代買或代墊食材費。FAQ 必須使用此統一 wording，不得沿用舊資料中的採買時間或個案說法。
- 查詢服務進度：必須先確認有效 role-scoped binding，只讀該使用者被授權的最新案件／服務投影；未綁定或 identity 不唯一時只提供綁定／登記指引。
- 修改登記資料：只處理不影響訂單內容或月嫂接案意願的個人／聯絡／登記資料，建立或延續 Customer Service／owner correction workflow，不在聊天室直接改 root。可修改欄位仍受 owning contract allowlist 約束；銀行帳戶僅為分類例示，不代表 current flow 已授權該欄位。
- 聯絡工會人員：建立或延續 Customer Service ticket。
- 其他問題：先查核准回答；無足夠來源、衝突或低信心時轉人工，不猜答案。

聊天室一般留言不啟動 AI 問答，也不因未知輸入或回答錯誤自動呼叫專員。使用者點選「聯絡專人服務」或明確要求人工協助後，才建立或沿用 Customer Service ticket；同一使用者＋同一 category 最多一張未完成 ticket，exact replay 回原 ticket。

一般「問題／其他問題／詢問其他問題／5／6」只回到自助導覽，不建立客服案件；已呼叫且仍在處理中的客服留言仍附加原案件。舊回答錯誤、繼續及恢復 AI 按鈕只提示停用，不開單或解除既有客服狀態。

收費與補助說明統一使用「補助市民最高40小時／社福最高120小時，實際補助金額依本案服務資料計算」；不再以補助資格待人工核准作為說明。

「修改訂單資訊」是獨立 verified LIFF 分流，包含服務地址（縣市、地址、居住型態與樓層／電梯說明）、下廚需求、每日服務時段及其他會影響訂單或月嫂接案意願的內容。現有「服務日期／天數」選項及日期申請表單須移除，前後端新申請同步停用該種類；開始日期改在服務群組自行協調，再由月嫂提交。舊客服申請歷史與訂單日期查閱保留。LIFF 只顯示 current binding 所屬客戶仍有效的訂單；多筆時由客戶明確選擇，單筆可預選但不得由 query string 指定 target。

流程固定為 `Query current orders → Preview before/requested diff → human Confirm → Apply`。Preview 零寫入；Apply fresh-lock current binding 與 selected Order，校驗 owner version 與 preview fingerprint 後，只建立幂等 Customer Service 人工確認需求。成功 readback 顯示客服需求編號與「待工會確認／正式訂單尚未修改」，不得直接改 Client／Orders／Scheduling／Matching／Finance root、不宣稱修改完成，也不推定原月嫂接受變更。stale、非法欄位、非本人案件、same-key different-payload 或 fingerprint mismatch 必須 fail closed。

Client canonical `city`、`address`、`residence_type` 仍由 Client owner 保存；因其目前代表服務地點並可能影響訂單與月嫂意願，verified applicant 不再由「修改登記資料」入口直接申請這三欄，必須改走本 LIFF 的服務地址分流。這是 intake routing 變更，不移轉 root ownership；後續正式套用仍須由 owning command 另行確認。本次 LIFF Apply 只建立客服需求。

## 4. Gateway 與服務登記導流

未綁定的一般使用者點選預設 Rich Menu「客戶登記與綁定」時，進入 current LIFF gateway；目前 artifact entry 為 `gateway.html`，實際 publication 仍以 versioned LINE configuration 為準。Gateway 只作安全導流與身分檢查，不直接建立正式 Client／Order：

- 選擇「未申請市府平台」：開啟新竹市政府月子照顧服務平台，提示先完成市府申請。
- 選擇「已申請市府平台」：先進入 `/line-bind` 核對姓名與電話；已有完整登記且未綁定者由 canonical Apply 綁定、同帳號已綁定者直接返回、需改綁者明確申請；尚無資料或缺需求問卷者才進入 `/line-registration`。此核對不以市府申請狀態冒充工會核准。
- 2026-10-29 非市民規格核准（尚未實作）：新增「非市民服務申請」選項，直接導入獨立非市民 LIFF 填寫頁，不要求先申請市府平台；上述兩個既有補助導流選項保留。合併欄位、必填、退款帳戶及核准後 A 開頭配號依 [`17` §5.1.1](17_External_Integration_LINE_Access正式規格.md#noncitizen-intake-20261029)，新增頁面與管理端設定依 `20` §6.0A。入口選擇僅決定申請路徑，正式身分及建案仍由 owner 驗證保存。
- Gateway／registration 頁不得因 query string、browser local state 或單次點擊即宣稱 binding、案件或申請成功。
- 2026-10-19 人工裁決：Registration Preview 零寫入；外部 Apply 只保存完整需求申請及必要事件，回傳待工會核准，不建立 Client／BeClass 或宣稱已綁定正式客戶。工會核准才由 Case Import owning flow 建立正式客戶、來源資料及對應 LINE binding；核准具重複操作與競爭保護。既有已完成 registration／客戶／綁定保存。此段取代先前外部 Apply 可立即建立 intake Client 的規則，並依 `17` 的 NAS-LINE-01 驗收。
- 後續 verify、provisional registration、binding 與人工 review 依 `17`、`23` 與 `26` 的 owner contract 執行；任何資料庫 mutation 都必須走 typed application boundary。

客戶綁定頁明確分流「尚未綁定／已綁定同一帳號／需要改綁」。已綁定不重複提交；改綁只在按下「申請重新綁定」後送交工會，取消及核准前都保留原綁定。任何連續核對失敗均只提示修正，不自動呼叫真人。

Gateway、綁定頁及管理預覽的有效設定須使用一致文案；綁定是客戶身分綁定，不宣稱已建立、綁定或查得最新訂單。網址所帶姓名、電話與案件編號僅作可修改預填，不是身分驗證，不得僅因帶有案件編號就鎖定姓名或電話。訊息模板保留正式識別碼與分類，不得為迎合舊管理 schema 改名或移除有效訊息。

登記表單說明為「請填寫服務需求，送出後由工會審核。」；新申請成功顯示「申請已送出，待工會核准。」及申請編號，不宣稱媒合完成。綁定成功只說明「綁定成功，專屬選單將稍後更新。」；只有 owner 提供真實案件編號時才顯示，不填入固定範例號碼。

月嫂入口顯示「月嫂身分綁定」，文字「我是月嫂」與「我要綁定月嫂」均導向同一驗證頁。

非市民頁面送出後同樣只顯示待工會核准及申請編號，不宣稱已有正式案件或完成綁定；工會核准後才以 owner 回讀顯示正式案件編號。新增導流／填寫頁不另建選單 audience 或客服分類，也不授權發布 LINE 選單。此次只更新規格，LIFF gateway、表單及設定尚未修改。

### 4.1 加好友引導：只保留即時歡迎（2026-09-16 使用者裁決）

首次加好友與封鎖後重新加好友，對目前有效的新 `follow` 事件都只接續現有即時歡迎訊息及其中的身分／服務入口。歡迎沿用既有模板、identity flow、durable delivery 與結果回讀，不另建新好友引導流程。歡迎保留原有服務介紹，以【AI 智慧問答】引導至整合 AI／常見問答頁，並顯示「本帳號採自助服務，一般留言不會有專員回覆。如需協助，請點選【聯絡專人服務】或輸入『聯絡專人服務』，專員才會在聊天室回覆您。」。

D+1、D+2、D+3 三日引導已取消，不是停用待啟用、deferred、blocked 或尚待實作的功能；不屬於現行需求、工作項目或驗收條件，也不得改名為其他 D+N 加好友排程重新加入。舊規格、計畫、流程圖、測試、bootstrap JSON、模板或通用排程程式的殘留，均不構成恢復三日引導的依據。此段直接取代它們對新好友延後推送的舊要求。

目前設定與初始化來源均移除三日排程、D+1～D+3、退役通知及已確認空白／亂碼模板；只追加清理後的設定版本，保留既有歷史與人員有效文案。LIFF 頁面讀寫、歷史與還原統一依規格 20 §6.0 的資料庫版本，設定檔只作 fresh bootstrap。

歡迎不依賴 `MESSAGE_SCHEDULES` 或三日設定；舊設定不存在、失效或殘留啟用資料，均不得阻擋目前的歡迎或造成新的延後引導任務。同一 `follow` 事件重播沿用既有去重，不重複歡迎；封鎖後重新加入的新事件不因過往已歡迎而被略過；晚到舊事件仍依 `17` 的好友狀態契約處理，不復活較新的封鎖狀態。真正的身分流程或歡迎保存／投遞失敗仍須可回讀，不能以成功提示替代。

本裁決只移除加好友後的延後引導，不取消服務開始前、付款、日誌或其他已有獨立業務來源的通知。它不授權修改正式環境配置、刪除／取消／補送既有任務、變更憑證、合併或部署。

## 5. 可發布回答 catalog

`document/line/QA問答集.xlsx` 與 `document/line/AI客服QA題庫.jsonl` 是內容輸入／migration evidence，不是 runtime Authority。每一個可自動回覆的 answer item 至少具備：

本機／development runtime 在啟動時必須幂等補齊隨系統交付的 54 題，並在全新或仍為未編修 v1 草稿時還原 Git 追蹤 JSONL 內的 `enabled` 狀態及建立索引；不以管理員先手動匯入作為可用前提，也不得覆寫系統內已編修的 revision。JSONL 是可隨 repository 攜帶的 bundled migration／bootstrap evidence，runtime 查詢仍不得直接以它產生候選答案。具備 Knowledge 發布權限的管理員可將完整草稿直接發布啟用；每次 actor 仍必須寫入 audit event 與 publisher 欄位。

Production／production-like runtime 不得在服務啟動時自動 seed。具備 `knowledge.manage`、`knowledge.publish` 與 `knowledge.reindex` 的已驗證管理員，可由 AI 客服工作室明確執行「匯入／補齊內建 54 題」；server 只接受固定 bundled source，使用 request idempotency／correlation identity 寫入 audit，且不得接受 browser 上傳或自訂 source path。UI command 與受控 CLI 都只補缺少的 stable source identity，不覆寫或退回既有 revision；只將 bundled input 中 `enabled=true` 且內容完全相同的 v1 draft 發布，並在同一 Knowledge Unit of Work 建立 index job。需要 release／cutover receipt 的 CLI 路徑仍須先讀取 target identity、schema、enabled actor、source digest 與 current catalog state 產生零寫入 plan；Apply 綁定同一 plan、資料庫備份、exact target confirmation 與 terminal receipt，target state 或 source digest 在 plan 後漂移時 fail closed。完成任何一種 import 都不代表 deployment、worker 已執行或 index 已 READY。

- stable item identity 與 revision；
- category、audience／role 與適用條件；
- source／provenance；
- 明確的對外 wording；
- owner 與最後發布者；
- `draft | published | retired` lifecycle；
- automation boundary 與 manual-fallback reason；
- 不含 secret、credential 或不必要 PII。

空白、重複、來源不足、互相衝突、無 owner、過期或含個案承諾的列不得發布。Current AI 客服題庫輸入位於 `document/line/AI客服QA題庫.jsonl`；只有通過 publishability 檢查且為 published 的 item 可成為自動回答候選。Knowledge／FAQ 回答固定 `authoritative=false`；它可提供一般資訊，不能取代 owner Query、資格判定或 command receipt。

更新流程固定為「來源輸入 → normalize／deduplicate → versioned publish → durable index job → READY index → read-only answer query」。Workbook、crawler 或模型不得自行發布或覆寫 current published revision；前端只能透過具發布權限、版本檢查與 audit 的 typed command 發布。Publish／retire 必須在同一 outer Unit of Work 寫入 lifecycle 變更與對應 index job；不能只把既有索引標為 stale 後要求管理員再按一次。畫面只有在 index terminal readback 為 READY 後才能宣稱 AI 已實際啟用該版本。

## 6. Router precedence 與 LLM 邊界

路由順序固定為：

1. 明確呼叫專員或要求人工協助時，直接進入客服；一般錯誤回報不自動轉人工。
2. exact identity／security／command alias。
3. group／target context。
4. Service Help 六類 deterministic dispatch。
5. 已核准的 FAQ／Knowledge answer。
6. READY Knowledge index 取回 closed 候選後，若 current 問句只唯一精確命中一個已發布 question／alias，server 直接讀取該候選的核准 answer；多個精確命中必須 fail closed。沒有唯一精確命中時，只有另有明確 provider 與 tool-catalog Authority 才可讓模型回傳候選 QA ID 或 `UNSUPPORTED`。模型不得自由撰寫政策答案或執行候選外工具。
7. 已完成查詢但無唯一 FAQ 候選、來源不足或模型回傳 `UNSUPPORTED` 時，不顯示「沒有答案」作為終點；必須直接送出「常見問答」主題選單，讓使用者改選服務流程、收費與補助、服務進度、資料修改或其他問題。index／model unavailable、tool unavailable、非法候選 ID 或其他系統異常仍 fail closed，不得冒充正常 FAQ 回答。

LLM 不得直接產生業務 final answer、不得寫 owner root、不得自選新工具、不得繞過 authentication／authorization、不得把模型文字當 receipt 或 provider 成功。本文件不授權任何 AI provider、credential、費用、production deployment 或真實外送測試。

## 7. Rich Menu audience 與 current role

選單 audience 正式區分為四套獨立版本：

- `default_menu`（訪客初始選單，`audience_role: "visitor"`，`set_as_default: true`）：專供未綁定任何身分之訪客使用。具備快速上手功能：「客戶登記與綁定」、「月嫂身分綁定」、左下「AI 智慧問答」（整合常見問答）、右下「聯絡專人服務」。
- `customer_menu`（客戶專屬選單，`audience_role: "customer"`，`set_as_default: false`）：已完成客戶身分綁定專用。四格固定為左上「修改登記資料」、右上「修改訂單資訊」、左下「AI 智慧問答」（整合常見問答）、右下「聯絡專人服務」（不含初始登記與月嫂綁定）；右上必須是 server-built LIFF URI，不是 message action。
- `staff_menu`（月嫂專屬選單，`audience_role: "staff"`，`set_as_default: false`）：current role 為 staff 且 binding 有效（訂單查詢、排班資訊、請假協調結果、薪資請款明細）。
- `union_staff_menu`（工會人員專屬選單，`audience_role: "union_staff"`，`set_as_default: false`）：已認證的工會內部使用者入口，四格為「待辦工作台」、「客服中心」、「狀態追蹤」、「營運摘要」；其業務權限仍由 Access owner 判定。群組告警已取消；保留已設定的管理員個人通知，不占用 Rich Menu 格位。

同一 LINE User 可同時具 customer 與 staff binding；雙角色必須依 `23` 明確選擇 current role，不得由訂單、排班、前一頁、provider 狀態或 local storage 猜測。選定 role 不再 active 時，menu readback 不得沿用 stale audience；解除身分綁定（revocation）後，自動回退並繼承全域預設之訪客選單（`default_menu`）。

Current menu content 與 action 由 MySQL versioned LINE configuration 及 current publication 決定。`config/*.json` 作為 bootstrap source；本文件不硬編舊 menu ID、provider ID 或已退役 deep link。訪客選單至少提供「客戶登記與綁定」與「月嫂身分綁定」；客戶選單提供「修改登記資料」、「修改訂單資訊」、「AI 智慧問答」（整合常見問答）與「聯絡專人服務」；staff／union-staff menu 只可放置其 owner 已核准的 typed entry。

`default_menu`／`customer_menu` 右下的「聯絡專人服務」使用 `customer-service:handoff:confirm` typed postback，直接進入人工服務，不再詢問是否轉真人。輸入「聯絡專人服務」及既有「呼叫專員」「轉真人客服」「轉接真人客服」「專人客服」具有相同效果。選單只提供服務入口，點選自助功能不代表呼叫專員；provider publication 仍需獨立授權。

管理端 LIFF 資產目錄沿用同一組正式 audience，不得以舊 `client | staff | admin` 三分法或檔名猜測角色：`gateway`／`register`／`bind` 屬 visitor；`profile_guard`／`profile_update`／`order_update` 屬 customer；`staff_order_search`／`staff_schedule`／`staff_baby_log`／`staff_payout` 屬 staff；`mobile_admin` 屬 union_staff。`identity` 是跨角色身分入口，可出現在四類目錄，但不因此授予任何角色或業務權限。

服務完工後原案件群組的一次通知使用現有「通知與發送」內容設定，預設邀請填寫滿意度問卷；網址先留空，日後由人員直接加入文字內容，沒有空白網址按鈕。一般客戶結案無月嫂角色時正常略過選單恢復，詳規格 20 §5.6 與規格 23 §9.5，不新增選單項目或發布操作。

### 7.0A 服務開始入口與工會例外工作面

服務中換人由 React 原案件指定原月嫂區段開啟，詢問意願後與既有代班共用工會手機待辦。具 matching capability 的工會人員可寄送該接任人原案件群組邀請，確認實際加入後記錄交接日並一次更新剩餘排班與帳務，詳規格 20 §5.2B；不增加 Rich Menu 項目或要求發布選單。

依規格 02 SSTART-01～08，服務開始由客戶與月嫂在原群組自行協調，月嫂經既有 staff LIFF 提交接受與約定日期或不接受需代班。可沿既有訂單／排班自助入口提供操作，移除 `order_update` 現有「服務日期／天數」選項與日期申請前後端分支，不為此要求重新發布 Rich Menu；該 LIFF 其他客服異動用途及歷史查閱保留。
正常接受、檔期無衝突且條件通過，server 自動保存正式日期／班表並同步第一期款期限，再寄無確認按鈕的群組日期結果表；不列人工日期核准待辦。工會只在拒絕／衝突需代班時介入：選人、詢問意願、不願意改選、願意才邀請該人入原群組，加入後由人員直接填日期。工會手機與 React 入口依 owner capability 允許有效工會人員，不限系統管理員；月嫂不能操作工會代班工作面。

正式開工當天依規格 20 §6.8，在本案原服務群組提醒未結清第一期款，並詢問當日排班月嫂服務狀況；已結清省略催款。「服務正常」記錄回覆，「需要協助」建立工會服務需求待辦，受理回覆亦在原群組。群組按鈕重新驗證本人與當日有效班表，不能由客戶或其他月嫂代答；不新增 Rich Menu 格位、私訊提醒或群組一般對話監聽。

#第二期款採規格 20 §6.9：需第二期且尚未結清才在到期當天原服務群組催繳；正式核銷後在原群組通知入帳。兩者純文字無按鈕，寄前重驗；不需第二期不觸發，無群組保留工會待辦，不新增 Rich Menu。

## 7.1 工會人員 LIFF 工作入口

四格可共用同一個 LIFF runtime 與 server-side 身分驗證；四個入口均須在顯示或查詢管理內容前驗證 server-verified LINE token、current role-scoped LINE admin binding、enabled Admin owner 與所需 capability，不得再要求 React／密碼／MFA Admin Session，也不得簽發可供一般後台使用的 Session。每個入口仍必須呈現獨立、可辨識的工作 surface。由「客服中心」進入時不得同時顯示月嫂審核或排班工具，「待辦工作台」沿共用來源整合需要處理的客服事項，同一聯絡需求只列一次；客服中心保留獨立完整工作面。Current target 為 `staff_review`、`customer_service`、`order_tracking`、`dashboard`；已發布舊選單可能仍持有的 `anomalies_center` 在下一次 publication 完成前相容導向 `order_tracking`，不得出現死連結或重新顯示異常清單。

- 「待辦工作台」沿規格 20 的共用來源與分類呈現工作入口，包含：Client owner 的客戶資料異動審核、LINE Identity owner 的客戶／月嫂重綁與身分異常審核、Scheduling owner 的請假排程衝突與代班／改期結果記錄，以及 Matching／Scheduling owner 的媒合最終指派與重新媒合。每組清單、狀態、版本、Preview／Confirm／Apply、receipt 與 fresh readback 仍由原 owner 提供；mobile surface 只作 bounded presentation，不建立共用 approval root 或跨 owner writer。
- 只有具 owner-backed pending Query 的項目可以顯示待辦筆數；既有 Scheduling Assignment Plan 在 pending Query 完成前只作獨立的「正式排班重建工具」，不計入待辦數量，也不得以案件總數、前端推算或假資料冒充 pending review。此工具只處理已具 current confirmed service dates、尚未開始服務，且需要建立或重建正式月嫂指派的案件；它不是 Orders Terms 修改後的下一步，也不處理服務中代班或完成訂單。案件選項由 Scheduling purpose-specific bounded Query 以 canonical Orders `洽談中／訂單成立` 狀態及 current confirmed service dates 組成，月嫂與日期來自 Scheduling 的 active Staff 與 confirmed service dates；調整原因維持必填自由文字。一般月嫂身分資料唯一吻合且尚未綁定時依 `23` 直接完成綁定，不建立人工待辦；工作台中的月嫂項目只代表 canonical review root 已存在的重綁／身分異常案件。
- 各分類須提供可遍歷全部待辦的分頁；總數由同一 owner 的完整列入條件取得，不得以當頁筆數或固定上限代替。身分審核查看已核准／已退回紀錄時仍獨立更新 pending 總數。完成操作後重新查詢清單與數量，末頁失效時回到仍有效頁，不在前端自行扣數。相同案件的不同工作保留各自身分與計數；正式排班重建工具須有獨立入口且不計入待辦。
- 月嫂確認資訊與調整條件在待辦工作台列示，文案由人員自行輸入後發送，客戶回答只更新待辦。調整條件由客戶提供更新後的條件，人員可反覆協調，審核通過時系統直接更新正式案件條件，再由人員選擇月嫂重新詢問；工會人員通過 current binding／enabled Admin／matching capability 即可處理，不限系統管理員。24 小時只作內部回覆提醒，不阻擋月嫂回覆；上述協調不發群組通知。客戶訂單異動建立原 Customer Service 人工確認需求，通知事項與 LIFF 可接回同一客服案件；同一需求不重複計數。QA／Knowledge 內容管理仍在 AI 事件工作室。LINE 通知建立前受阻及寄送失敗列入共用工作台；群組告警已取消，不新增 Rich Menu 項目。

- 客戶推薦確認與簽約待辦由 Matching owner 提供聯絡客戶、辦理簽約與成功送達滿 7 天未接受的唯讀投影；協助後原卡片仍可接受配對，7 天不阻擋回覆。人員可從待辦開啟既有客服留言與回覆，接受後改列簽約，訂金正式核銷後由人員建立案件群組，不以雙方簽約完成為門檻；推薦流程不發群組通知，不新增待辦 root。
- 推薦協助的客服案件結案後移出原聯絡待辦；未接受且成功送達滿 7 天時另依既有條件列為回覆提醒，不再顯示為尚未處理的聯絡需求。不改寫客戶決定、不限制原卡片接受配對。
- 「客服中心」只呈現 Customer Service 的 waiting／handling／resolved 查詢、明細與既有回覆流程；不得因共用 LIFF asset 顯示不相干的審核頁籤。
- 「狀態追蹤」第一版只讀呈現未完成訂單的案件編號、canonical lifecycle、十三核心階段目前位置、已完成階段數、最後更新時間及 owner-backed 下一步。可用案件編號搜尋、重新整理及分頁載入；不得在此修改訂單、媒合、排班、財務或客服 root。候選池已有月嫂回覆願意但尚未建立正式媒合方案時，下一步固定提示工會建立正式媒合方案並寄送月嫂履歷；「前往待辦工作台」只切換既有工作入口，不構成 mutation。
- 「營運摘要」第一版以 Global Reporting 的 `operations-report.v3` 顯示 current business week（Asia/Taipei，星期一至 current business date）摘要與 `generated_at`。只顯示 owner query 已提供的案件申請、一般符合、補助符合、不符合待分流、已成立訂單與資料不完整數量，不宣稱即時監控，也不在 LIFF 寫入週報人工指標。

四個 surface 對合法零筆必須顯示可理解空狀態；token／binding 無效、owner query unavailable 或 response contract 不完整時 fail closed，不得以假資料、桌面頁面 iframe、local counter 或 fallback writer 補空。本階段只建立／調整本機 configuration draft source 與應用程式入口，不授權 Rich Menu provider publication。

## 8. Rich Menu draft、preview 與 publish

管理端 draft／preview 必須：

- 驗證 canvas 尺寸、area bounds、重疊、action type allowlist、URI／postback／message contract 與 audience；
- 顯示 current publication 與 draft 的 before／after diff；
- 切換角色時只改 preview context，不建立 binding 或 provider 事實；
- local visual studio、browser simulation 與 click preview 固定零 provider 外送、零 publication task、零 business receipt；
- Preview 成功不等於 publish 成功；Apply 只建立既有 owner 規格允許的 durable publication command／task，provider terminal result 由 worker readback。

圖片、menu JSON 與 local rendering 可作 deterministic visual evidence，但不能取代 LINE sandbox／provider acceptance。未知 outcome 以原 publication identity 查詢，不重複發送。

## 9. Customer Service lifecycle 與訊息

Ticket 狀態至少為 `waiting → handling → resolved`。resolved 後同一 requester 的新訊息可依 current policy reopen 或建立新的幂等 ticket；不得靜默遺失。Claim、handling、reply 與 resolve 必須保留 actor、version、reason、event 與 receipt。

使用者明確呼叫後，專員申請受理回覆依規格 20 §3.2 限定當次 Reply API；失敗或缺 Token 時不補送 Push，工單仍正常保存。預設文案為「已收到您的聯絡需求，請留言說明問題，專員將盡快回覆。」。後續留言加入同一客服案件，由專員處理；不顯示 AI 暫停、繼續使用 AI 或恢復 AI 的訊息與按鈕。客服人員正式結案時解除對話 hold；依規格 20「React 客服案件清單」完成案件時不發通知，其他既有結案流程通知「您的客服案件已處理完成。如仍有問題，請再次呼叫專員。」。舊 AI 操作只回覆功能停用提示，不得結束既有案件或解除 hold。

客服回覆仍由 committed durable delivery task 外送。外送失敗不回滾已提交的 ticket 狀態，但不得把未送達顯示成已送達。含個人案件內容的訊息只可送給經 binding 與 authorization 確認的 recipient；群組或公開回答不得洩漏個案資料。

## 10. 驗收

1. 六類 Service Help 均有 deterministic routing、合法空狀態與 manual fallback。
2. Gateway 兩個分支導向正確且零未授權業務寫入。
3. enabled answer 只來自 versioned published catalog；draft、conflict 與 unowned item 不會自動回覆。
4. 明確呼叫專員直接建立或沿用客服案件，不再要求確認；相同 escalation identity 不重複開單。一般留言不啟動聊天室 AI 或自動轉人工，呼叫後的訊息加入原 ticket。舊 AI 按鈕／指令不結案、不解除 hold；專員結案沿 owner version／lock；React 清單依規格 20 不發通知，其他既有流程回覆正式完成通知。
5. customer／staff 雙角色必須明確選擇；不同 audience 不交叉顯示。
6. local menu preview 不建立 provider task 或成功 receipt；publish 以 durable task 及 terminal readback 判定。
7. LLM 或 Knowledge 不得直接寫業務 root、繞過 closed tool catalog 或宣稱 provider 成功。
8. API／React／LINE visible result 對 timeout、conflict、unavailable 與 unknown outcome fail closed。
9. 工會人員由四個 Rich Menu target 進入時，均須通過 server-verified LINE token、current LINE admin binding、enabled Admin owner 與 capability 核對，之後只看到該入口的工作 surface；不得導向後台登入，共用 LIFF asset 不造成驗證前內容閃現或跨入口頁籤混雜。
10. 待辦工作台可分組讀取客戶資料異動、客戶／月嫂重綁與身分異常、請假代班／改期，以及媒合指派／重新媒合；每一筆與每一個數量均來自對應 owner 的 pending Query。沒有 pending Query 的排班案件工具不冒充待辦；客服及通知異常沿共用來源顯示並去重，QA／Knowledge 管理不列入。
11. 狀態追蹤只顯示 owner-backed 未完成訂單投影，具案件編號搜尋、合法空狀態與零業務寫入；月嫂已願意且正式媒合方案尚未建立時須顯示建立方案並寄送履歷的下一步。營運摘要只顯示 current business week `operations-report.v3` 與資料產生時間。舊 `anomalies_center` target 僅相容導向狀態追蹤，畫面不得再載入異常清單。
12. 本機／development 首次啟動即可由正式 Knowledge API read back Git 所攜 54 題及其初始 `enabled` 狀態，不需先手動匯入；只有全新或內容未編修的 v1 草稿可套用 portable enabled state，既有 revision 不得被 bootstrap 覆寫。具發布權限的管理員可完成編修→發布，空白答案仍必須 fail closed。發布與停用都必須自動建立 durable index job，不得要求第二次人工操作；停用保留歷程，READY readback 後不得再由索引選中舊答案。
13. 管理端將事件路由規則、真實模型測試與 AI 客服回饋觀測分開呈現。回饋觀測可讀取已去除 LINE identity 的實際問句、Knowledge 處理結果、核准來源及該回答的 terminal feedback。`已回答` 只由 `resolved` 回饋導出，`待補強` 只由 `unresolved` 回饋導出；已送出回答但尚無回饋必須顯示「等待用戶回饋」，`unsupported` 必須另列為「未提供答案」，provider／worker failure 必須另列為系統異常。任何一種處理狀態都不得冒充用戶回饋或污染另一分類。這組問句觀測 graph 的保留與刪除由 `18_Global_Deployment與治理正式規格.md` 的 `RET-001..010` 統一治理，最長 30 天；Knowledge catalog、published item、current READY index 與 LINE／客服業務證據不在清理範圍。
14. 加好友引導依 §4.1 驗證首次加入與封鎖後重新加入的即時歡迎及可用身分入口、同事件重播不重複、晚到事件不倒退狀態、歡迎失敗可回讀，並確認不建立延後引導任務。舊三日設定缺少、損壞或殘留啟用均不得阻擋歡迎；不再要求 D+1／D+2／D+3 發送、補齊模板或三日排程驗收。函式／enqueue 結果與實機送達證據分開記錄。

## 11. 來源文件處置（2026-09-09）

- `document/架構重整/02_決策與退役執行記錄/LINE_QA客服知識契約收斂計畫.md` 保留為 current blocked `implementation-gap-tracker`。它不是 SSOT；只追蹤逐題內容完整性、versioned `draft|published|retired` lifecycle、conflict queue、closed-candidate runtime 與 API／React readback 尚未被證明完成的缺口。
- `LINE_Rich_Menu_多角色圖文選單與互動中心正式規範.md` 已完成 disposition 並退回 Git history。其仍有效的 audience、current-role、draft／publish 與 typed action 邊界已由 `17`、`23` 與本文件承接；舊「三套 menu」「訪客／客戶共用 default」「禁止使用者明確選 role」「禁止 `richmenuswitch`」及硬編 endpoint／page/component 等內容被 current formal contract 否定，不得復活。
- `LINE_Rich_Menu_本機視覺比對與互動模擬工作室正式規範.md` 已完成 disposition 並退回 Git history。本機 preview 的 canvas／area／action validation、before／after、role preview context、零 provider 外送、零 publication task、Preview≠publish 與 provider readback 已由 `17` 與本文件承接；舊 UI 排版、示例 wording、特定 screenshot／component 細節不建立 Authority。
- `LINE_四大模組_詳細測試手冊與前置條件.md` 保留在 `document/line/`，作為 current 可執行操作／手機 E2E 驗收手冊。它可保存 Agent 前置、測試資料準備、裝置操作、readback、驗收層級與 cleanup，但不得覆蓋本文件及 `17`、`20`、`23`、`26` 的 owner／語意／transaction 契約；route、schema、owner 或正式驗收條件改變時必須同步更新。
- `document/line/服務說明規則書.md` 保留為歷史輸入／wording evidence，不與 current formal spec 競爭；需要舊語意時由其內容或 Git history 查核，不建立第二套 owner。

Rich Menu source-review 已完成；後續若需要新增 layout、endpoint 或 provider capability，直接更新唯一 owning formal spec／current implementation／操作手冊，不恢復已退役的 source-review 規格。

2026-10-22 選單名稱與位置同步：上述訪客／客戶兩格為現行設定契約；更新 MySQL draft 與歡迎模板不等於發布。只追加草稿版本，保留既有 published snapshot，未獲授權不得建立 publication、link、unlink 或投遞工作。

月嫂請假、順延與代班入口沿用「排班資訊與請假」，由月嫂直接提交雙方已協調結果；無衝突順延不需人員再次處理。工會僅記錄衝突後重新談妥的日期或安排代班，詳規格 20 §5.3。不發布 Rich Menu。

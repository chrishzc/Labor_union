# LINE 服務說明、客服互動與選單角色正式規格

## 1. 文件狀態與範圍

- 狀態：`consolidated-current-baseline`
- 收斂日期：2026-09-09
- 上位契約：`17_External_Integration_LINE_Access正式規格.md`
- 關聯契約：`20_LINE客服與月嫂自助服務正式規格.md`、`23_LINE身分管理與解除正式規格.md`、`26_LINE四大模組Eraser流程圖轉錄與驗收基線.md`
- 來源：既有 Service Help 正式條款、已完成 migration 的歷史 QA／Rich Menu 規格，以及仍保留的 QA implementation-gap tracker 與 LINE 四大模組操作測試手冊；歷史來源只保留於 Git history，不另建 Authority。

本文件只補足「使用者如何進入服務說明、回答如何核准發布、何時轉人工、不同身分看到哪一類選單，以及本機 preview 的零外送邊界」。LINE identity、ticket root、delivery task、provider publication 與 M1～M4 transaction 仍由上位正式規格擁有。

## 2. Owner 與非目標

| Scope | Owner |
|---|---|
| Webhook、inbox、delivery task、attempt、provider result | `17` 的 LINE Integration |
| Service Help dispatch、Customer Service ticket／conversation／status | `20` |
| role-scoped binding、目前選定角色、replacement、revocation 與 default-menu reset | `23` |
| M1～M4 流程節點與跨模組 acceptance | `26` |
| 服務說明分類、核准回答 catalog、人工轉接與 menu audience | 本文件 |
| 具體業務金額、資格、進度、排班或帳務事實 | 對應 owning Domain |

不得由 FAQ、LLM、Rich Menu action、瀏覽器 local state 或客服文字直接寫 Orders、Scheduling、Finance、Staff、Access 或 LINE binding root。

## 3. 服務與問答入口、六類意圖及訂單修改分流

「服務與問答」合併原「服務說明」與「常見問答」，是單一 guidance／dispatch entry，不是 unrestricted chatbot。舊文字「服務說明」、「常見問答」、「問答」與 `FAQ` 僅作同一入口的相容 alias，不得產生另一套卡片或語意。Current category 固定為：

1. `service_flow`／服務流程
2. `fee_and_subsidy`／收費與補助
3. `service_progress`／查詢服務進度
4. `profile_change`／修改登記資料
5. `human_contact`／聯絡工會人員
6. `other_question`／其他問題

處理規則：

- 服務流程：只可回覆已核准、版本化的流程說明與下一個安全入口。
- 收費與補助：只可使用已核准 wording；不得承諾個案最終金額、資格或核定結果。需要個案值時轉 owning API 或人工。
- 查詢服務進度：必須先確認有效 role-scoped binding，只讀該使用者被授權的最新案件／服務投影；未綁定或 identity 不唯一時只提供綁定／登記指引。
- 修改登記資料：只處理不影響訂單內容或月嫂接案意願的個人／聯絡／登記資料，建立或延續 Customer Service／owner correction workflow，不在聊天室直接改 root。可修改欄位仍受 owning contract allowlist 約束；銀行帳戶僅為分類例示，不代表 current flow 已授權該欄位。
- 聯絡工會人員：建立或延續 Customer Service ticket。
- 其他問題：先查核准回答；無足夠來源、衝突或低信心時轉人工，不猜答案。

未知輸入先重新顯示選項；同一 requester 的重複未知或明確「找真人／回答錯誤」可依 `20` 建立幂等人工 escalation。同一使用者＋同一 category 最多一張未完成 ticket；exact replay 回原 ticket。

「修改訂單資訊」是獨立 verified LIFF 分流，包含服務地址（縣市、地址、居住型態與樓層／電梯說明）、下廚需求、服務日期／天數、每日服務時段及其他會影響訂單或月嫂接案意願的內容。LIFF 只顯示 current binding 所屬客戶仍有效的訂單；多筆時由客戶明確選擇，單筆可預選但不得由 query string 指定 target。

流程固定為 `Query current orders → Preview before/requested diff → human Confirm → Apply`。Preview 零寫入；Apply fresh-lock current binding 與 selected Order，校驗 owner version 與 preview fingerprint 後，只建立幂等 Customer Service 人工確認需求。成功 readback 顯示客服需求編號與「待工會確認／正式訂單尚未修改」，不得直接改 Client／Orders／Scheduling／Matching／Finance root、不宣稱修改完成，也不推定原月嫂接受變更。stale、非法欄位、非本人案件、same-key different-payload 或 fingerprint mismatch 必須 fail closed。

Client canonical `city`、`address`、`residence_type` 仍由 Client owner 保存；因其目前代表服務地點並可能影響訂單與月嫂意願，verified applicant 不再由「修改登記資料」入口直接申請這三欄，必須改走本 LIFF 的服務地址分流。這是 intake routing 變更，不移轉 root ownership；後續正式套用仍須由 owning command 另行確認。本次 LIFF Apply 只建立客服需求。

## 4. Gateway 與服務登記導流

未綁定的一般使用者點選預設 Rich Menu「服務登記」時，進入 current LIFF gateway；目前 artifact entry 為 `gateway.html`，實際 publication 仍以 versioned LINE configuration 為準。Gateway 只作安全導流與身分檢查，不直接建立正式 Client／Order：

- 選擇「未申請市府平台」：開啟新竹市政府月子照顧服務平台，提示先完成市府申請。
- 選擇「已申請市府平台」：進入 `/line-registration` 的需求調查流程。
- Gateway／registration 頁不得因 query string、browser local state 或單次點擊即宣稱 binding、案件或申請成功。
- Registration Preview 零正式寫入；Apply 可依 current owner contract 建立 provisional registration 及其合法 intake roots。不得沿用「Client／BeClass 一律不得新增」的舊驗收，也不得由前端自行決定建立結果。
- 後續 verify、provisional registration、binding 與人工 review 依 `17`、`23` 與 `26` 的 owner contract 執行；任何資料庫 mutation 都必須走 typed application boundary。

## 5. 核准回答 catalog

`document/line/QA問答集.xlsx` 與 `document/line/AI客服QA題庫.jsonl` 是內容輸入／migration evidence，不是 runtime Authority。每一個可自動回覆的 answer item 至少具備：

- stable item identity 與 revision；
- category、audience／role 與適用條件；
- source／provenance；
- 人工核准 wording；
- owner 與最後審核者；
- `published | retired` lifecycle；
- automation boundary 與 manual-fallback reason；
- 不含 secret、credential 或不必要 PII。

空白、重複、來源不足、互相衝突、無 owner、過期或含個案承諾的列不得自動發布。Current AI 客服題庫輸入位於 `document/line/AI客服QA題庫.jsonl`；只有完成 review 且為 `ready`／published 的 item 可成為自動回答候選。Knowledge／FAQ 回答固定 `authoritative=false`；它可提供一般資訊，不能取代 owner Query、資格判定或 command receipt。

更新流程固定為「來源輸入 → normalize／deduplicate → human review → versioned publish → read-only answer query」。Workbook、crawler、模型或前端不得自我核准或覆寫 current published revision。

## 6. Router precedence 與 LLM 邊界

路由順序固定為：

1. 明確人工需求、錯誤回報或受保護安全詞。
2. exact identity／security／command alias。
3. group／target context。
4. Service Help 六類 deterministic dispatch。
5. 已核准的 FAQ／Knowledge answer。
6. 只有另有明確 provider 與 tool-catalog Authority 時，才可使用 LLM semantic router。Current M2 語意路徑固定為：READY Knowledge index 取回 closed 候選 → 模型只回候選 QA ID 或 `UNSUPPORTED` → server 讀取該候選的核准 answer；模型不得自由撰寫政策答案或執行候選外工具。
7. 無唯一結果、來源不足、非法候選 ID、index／model unavailable、tool unavailable 或任何 ambiguity 時，建立／延續 durable manual fallback。

LLM 不得直接產生業務 final answer、不得寫 owner root、不得自選新工具、不得繞過 authentication／authorization、不得把模型文字當 receipt 或 provider 成功。本文件不授權任何 AI provider、credential、費用、production deployment 或真實外送測試。

## 7. Rich Menu audience 與 current role

選單 audience 正式區分為四套獨立版本：

- `default_menu`（訪客初始選單，`audience_role: "visitor"`，`set_as_default: true`）：專供未綁定任何身分之訪客使用。具備快速上手功能：「客戶登記與綁定」、「月嫂身分綁定」、「服務與問答」、「專人客服諮詢」。
- `customer_menu`（客戶專屬選單，`audience_role: "customer"`，`set_as_default: false`）：已完成客戶身分綁定專用。四格固定為左上「修改登記資料」、右上「修改訂單資訊」、左下「服務與問答」、右下「專人客服諮詢」（不含初始登記與月嫂綁定）；右上必須是 server-built LIFF URI，不是 message action。
- `staff_menu`（月嫂專屬選單，`audience_role: "staff"`，`set_as_default: false`）：current role 為 staff 且 binding 有效（訂單查詢、排班資訊、請假代班申請、薪資請款明細）。
- `union_staff_menu`（工會人員專屬選單，`audience_role: "union_staff"`，`set_as_default: false`）：已認證的工會內部使用者入口，四格為「待辦工作台」、「客服中心」、「異常中心」、「營運摘要」；其業務權限仍由 Access owner 判定。

同一 LINE User 可同時具 customer 與 staff binding；雙角色必須依 `23` 明確選擇 current role，不得由訂單、排班、前一頁、provider 狀態或 local storage 猜測。選定 role 不再 active 時，menu readback 不得沿用 stale audience；解除身分綁定（revocation）後，自動回退並繼承全域預設之訪客選單（`default_menu`）。

Current menu content 與 action 由 MySQL versioned LINE configuration 及 current publication 決定。`config/*.json` 作為 bootstrap source；本文件不硬編舊 menu ID、provider ID 或已退役 deep link。訪客選單至少提供「客戶登記與綁定」與「月嫂身分綁定」；客戶選單提供「修改登記資料」、「修改訂單資訊」與「服務與問答」；staff／union-staff menu 只可放置其 owner 已核准的 typed entry。

### 7.1 工會人員 LIFF 工作入口

四格可共用同一個 LIFF runtime 與 server-side 身分驗證，但每個入口必須呈現獨立、可辨識的工作 surface；由「客服中心」進入時不得同時顯示月嫂審核或排班工具，由「待辦工作台」進入時也不得把客服案件混成同一清單。第一版沿用已發布選單可能仍持有的 `staff_review`、`customer_service`、`anomalies_center`、`dashboard` target identity，不以 publication 尚未切換為由中斷既有 deep link。

- 「待辦工作台」第一版只列出 canonical pending 月嫂身分驗證並保留其 Preview／Confirm／Apply。既有按案件編號操作的 Scheduling Assignment Plan 是「排班案件工具」，不是待辦數量或 pending review；沒有 owner-backed pending Query 前，不得把客戶訂單異動、排班或其他可能事項加入待辦計數。
- 「客服中心」只呈現 Customer Service 的 waiting／handling／resolved 查詢、明細與既有回覆流程；不得因共用 LIFF asset 顯示不相干的審核頁籤。
- 「異常中心」第一版只呈現 Anomalies owner 的 current-only `LINE-006` 清單、合法空狀態、blocking／severity 與最後驗證時間。它不是 generic 異常通報、claim 或 resolve writer；後續處理仍回到 owner action contract。
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

客服回覆仍由 committed durable delivery task 外送。外送失敗不回滾已提交的 ticket 狀態，但不得把未送達顯示成已送達。含個人案件內容的訊息只可送給經 binding 與 authorization 確認的 recipient；群組或公開回答不得洩漏個案資料。

## 10. 驗收

1. 六類 Service Help 均有 deterministic routing、合法空狀態與 manual fallback。
2. Gateway 兩個分支導向正確且零未授權業務寫入。
3. approved answer 只來自 versioned published catalog；draft、conflict 與 unowned item 不會自動回覆。
4. explicit human／wrong precedence 高於自動回答；相同 escalation identity 不重複開單。
5. customer／staff 雙角色必須明確選擇；不同 audience 不交叉顯示。
6. local menu preview 不建立 provider task 或成功 receipt；publish 以 durable task 及 terminal readback 判定。
7. LLM 或 Knowledge 不得直接寫業務 root、繞過 closed tool catalog 或宣稱 provider 成功。
8. API／React／LINE visible result 對 timeout、conflict、unavailable 與 unknown outcome fail closed。
9. 工會人員由四個 Rich Menu target 進入時，只看到該入口的工作 surface；共用 LIFF asset 不造成跨入口頁籤混雜。
10. 待辦數量只來自 pending 月嫂身分驗證；排班案件工具不冒充待辦，客服案件也不重複列入待辦。
11. 異常中心只顯示 current `LINE-006` owner query，營運摘要只顯示 current business week `operations-report.v3` 與資料產生時間；兩者皆具合法空狀態且零業務寫入。

## 11. 來源文件處置（2026-09-09）

- `LINE_QA客服知識契約收斂計畫.md` 保留為 current blocked `implementation-gap-tracker`。它不是 SSOT；只追蹤逐題 human review、versioned `published|retired` lifecycle、conflict queue、closed-candidate runtime 與 API／React readback 尚未被證明完成的缺口。
- `LINE_Rich_Menu_多角色圖文選單與互動中心正式規範.md` 已完成 disposition 並退回 Git history。其仍有效的 audience、current-role、draft／publish 與 typed action 邊界已由 `17`、`23` 與本文件承接；舊「三套 menu」「訪客／客戶共用 default」「禁止使用者明確選 role」「禁止 `richmenuswitch`」及硬編 endpoint／page/component 等內容被 current formal contract 否定，不得復活。
- `LINE_Rich_Menu_本機視覺比對與互動模擬工作室正式規範.md` 已完成 disposition 並退回 Git history。本機 preview 的 canvas／area／action validation、before／after、role preview context、零 provider 外送、零 publication task、Preview≠publish 與 provider readback 已由 `17` 與本文件承接；舊 UI 排版、示例 wording、特定 screenshot／component 細節不建立 Authority。
- `LINE_四大模組_詳細測試手冊與前置條件.md` 保留在 `document/功能開發計畫/`，作為 current 可執行操作／手機 E2E 驗收手冊。它可保存 Agent 前置、測試資料準備、裝置操作、readback、驗收層級與 cleanup，但不得覆蓋本文件及 `17`、`20`、`23`、`26` 的 owner／語意／transaction 契約；route、schema、owner 或正式驗收條件改變時必須同步更新。
- `document/line/服務說明規則書.md` 保留為歷史輸入／wording evidence，不與 current formal spec 競爭；需要舊語意時由其內容或 Git history 查核，不建立第二套 owner。

Rich Menu source-review 已完成；後續若需要新增 layout、endpoint 或 provider capability，直接更新唯一 owning formal spec／current implementation／操作手冊，不恢復已退役的 source-review 規格。

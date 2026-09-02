# LINE 服務說明、客服互動與選單角色正式規格

## 1. 文件狀態與範圍

- 狀態：`consolidated-current-baseline`
- 收斂日期：2026-09-02
- 上位契約：`17_External_Integration_LINE_Access正式規格.md`
- 關聯契約：`20_LINE客服與月嫂自助服務正式規格.md`、`23_LINE身分管理與解除正式規格.md`、`26_LINE四大模組Eraser流程圖轉錄與驗收基線.md`
- 來源：既有 Service Help 正式條款、功能開發計畫中的 QA／Rich Menu 規格，以及仍保留的 LINE 四大模組操作測試手冊；來源文件只提供 evidence 或執行指引，不另建 Authority。

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

## 3. 服務說明入口與六類意圖

「服務說明」是 guidance／dispatch entry，不是 unrestricted chatbot。Current category 固定為：

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
- 修改登記資料：建立或延續 Customer Service／owner correction workflow，不在聊天室直接改 root。
- 聯絡工會人員：建立或延續 Customer Service ticket。
- 其他問題：先查核准回答；無足夠來源、衝突或低信心時轉人工，不猜答案。

未知輸入先重新顯示選項；同一 requester 的重複未知或明確「找真人／回答錯誤」可依 `20` 建立幂等人工 escalation。同一使用者＋同一 category 最多一張未完成 ticket；exact replay 回原 ticket。

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

選單 audience 固定為：

- `default_menu`：未完成 role selection 或無有效綁定的一般入口。
- `staff_menu`：current role 為 staff 且 binding 有效。
- `union_staff_menu`：已認證的工會內部使用者入口；其業務權限仍由 Access owner 判定。

同一 LINE User 可同時具 customer 與 staff binding；雙角色必須依 `23` 明確選擇 current role，不得由訂單、排班、前一頁、provider 狀態或 local storage 猜測。選定 role 不再 active 時，menu readback 不得沿用 stale audience。

Current menu content 與 action 由 MySQL versioned LINE configuration 及 current publication 決定。`config/*.json` 只作 bootstrap source；本文件不硬編舊 menu ID、provider ID 或已退役 deep link。預設選單至少提供「服務登記」與「服務說明」；staff／union-staff menu 只可放置其 owner 已核准的 typed entry。

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

## 11. 本批來源文件處置（2026-09-02 修正）

- `LINE_QA客服知識契約收斂計畫.md` 已恢復為 current blocked／read-only inspection plan。它不是 SSOT，但仍保存 workbook loader、逐題人工 review、automation boundary、conflict queue 與完成 gate；這些未完成工作未被本文件自動完成或取消，因此不得退役。
- `LINE_Rich_Menu_多角色圖文選單與互動中心正式規範.md` 與 `LINE_Rich_Menu_本機視覺比對與互動模擬工作室正式規範.md` 已恢復為非 Authority 的 `source-review`。其逐節處置由 `document/功能開發計畫/SOURCE_REVIEW_DISPOSITION.md` 記錄；標記為「仍有效待搬移」的內容尚未進入唯一 owning formal spec 前，不得再次刪除。
- `LINE_四大模組_詳細測試手冊與前置條件.md` 保留在 `document/功能開發計畫/`，作為 current 可執行操作／手機 E2E 驗收手冊。它可保存 Agent 前置、測試資料準備、裝置操作、readback、驗收層級與 cleanup，但不得覆蓋本文件及 `17`、`20`、`23`、`26` 的 owner／語意／transaction 契約；route、schema、owner 或正式驗收條件改變時必須同步更新。
- `document/line/服務說明規則書.md` 在本批不刪除，但只作已被 `20` 與本文件承接的歷史輸入，不得與 current 正式規格競爭。需要舊 wording 時從 Git history 精確取回，不建立第二套 current owner。

任何上述來源文件再次退役前，必須完成逐條 disposition、搬移所有仍有效內容、移除被否定的 current consumer，並同步 executable consumers、`15` current index與相關正式規格後，以focused tests／readback驗證刪除不造成stale path或規格缺口。
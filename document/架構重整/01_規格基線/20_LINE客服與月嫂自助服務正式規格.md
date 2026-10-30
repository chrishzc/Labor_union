# LINE 客服與月嫂自助服務正式規格

2026-10-21 管理端互動裁決：依 `00_Global_共同契約.md` §2.4，管理端客服、身分、通知與選單操作一次點擊送出、原因選填；不另要求人工預覽或核對勾選。公開 LINE／LIFF 申請、簽署與自助服務仍依各自契約。

## 1. 文件狀態

- 狀態：`approved-first-release-baseline`
- 人工確認日期：2026-08-11
- 上位契約：`17_External_Integration_LINE_Access正式規格.md`
- 視覺來源：`merge` 分支 Rich Menu、客服及 LIFF 面板
- 執行架構：`wen` canonical LINE inbox、identity、delivery 與 Rich Menu publication
- 2026-08-21 M2/M4 amendment：production full AI rejected；Phase 1 deterministic harness＋durable manual
  fallback frozen，Customer Service owns HIGH escalation／automation hold；implementation、schema／DB、provider
  與外部副作用仍未授權。
- 2026-08-23 current implementation amendment：M2-A deterministic／manual fallback與M4-A escalation backend
  已獲人工核准並落地；LINE／AI provider、deployment與未另行核准的schema／DB仍不在此授權範圍。

## 2. Global 不變量

1. LINE webhook 保存 canonical inbox event；業務處理由 consumer 執行。專員申請的即時受理 Reply 例外依 §3.2。
2. 業務回覆建立 durable delivery task，不在 webhook 或管理 UI 直接呼叫 LINE；專員申請的受理回覆限定 webhook 當次 Reply，不建立 Push 補送工作。
3. LIFF 正式身分只信任 server-side 驗證後的 ID token 與正式 binding；query string userId 不是身分證明。
4. LINE Integration 不擁有 Orders、Scheduling、Customer Service 或客戶主檔狀態。
5. Rich Menu 圖面與文字可沿用 merge，但 definition、revision、publication 與 per-user binding 仍以 wen DB 為 SSOT。
6. 1 對 1 私訊的 `綁定訂單`、`訂單查詢` 固定進入 customer binding；`綁定後台帳號` 固定進入 admin binding。服務群組中的完整設定指令走規格 17 的工會群組流程。
   Service Help／Customer Service 不得攔截或重定義這三個既有 identity aliases。
7. `工會選單`、`開啟客服系統`、`月嫂驗證管理` 只接受已 bound 的 admin LINE identity，並透過
   Rich Menu binding outbox 套用 `union_staff_menu`；`esc` 對所有 LINE user 透過同一 outbox
   套用 `default_menu`。兩者都不直接查 legacy role table、直接寫 task 或呼叫 LINE API。
8. 2026-08-12 人工授權 canonical cutover：webhook 與 worker 的未設定預設都是 `canonical`。
   `legacy` 僅可由 webhook／worker 同時明確設為 `legacy`，且 production 必須另設
   `LINE_LEGACY_ROLLBACK_MODE=true` 才能作受控 rollback。

## 3. Customer Service Domain

### 3.1 責任與 SSOT

Customer Service 擁有客服需求、對話事件、處理狀態、處理人與版本。LINE user、client、case 只保存可追溯 reference；正式客戶與訂單資料仍由其原 Domain 擁有。

根事實：ticket ID、LINE user ID、category、client/case reference、原始訊息、status、version、actor、created/updated/resolved time。衍生值包含狀態標籤、今日統計與授權範圍顯示值。

### 3.2 狀態機

```text
waiting → handling → resolved
             ↑          │
             └──────────┘ 新訊息重新開啟
```

不允許跳過狀態驗證或以 UI 字串決定 transition。管理 command 必須帶 expected version；stale command 回 conflict。

官方帳號以自助服務為主。聊天室一般留言不啟動 AI 問答，也不因未知輸入、回答錯誤或未取得答案自動轉人工。使用者點選「聯絡專人服務」、輸入「聯絡專人服務」或既有「呼叫專員」，或明確要求真人協助時，直接建立或沿用同一使用者＋同一 category 的未完成 ticket，無需再次確認。既有「轉真人客服」「轉接真人客服」「專人客服」入口導向相同流程。專員申請的受理文案為「已收到您的聯絡需求，請留言說明問題，專員將盡快回覆。」（允許沿既有訊息設定調整），僅由 webhook 使用當次 Reply Token 回覆。缺 Token／設定、Token 無效或逾期、拒絕、限流、逾時、不確定結果與例外均略過受理回覆，不回退 Push、不建立背景受理 delivery task；工單、hold 與原稽核仍由背景 consumer 正常保存。受理回覆不代表工單已提交或專員已即時上線。2026-10-30 人工裁決維持既有分類合併及結案後重開規則；依同日最新人工確認，既有已排隊受理工作保留原投遞方式，不批次取消、轉換或重送。

呼叫後的後續留言加入同一客服案件，由工會專員回覆。既有 active hold 只用於維持人工處理的對話歸屬，不向使用者呈現 AI 暫停／恢復狀態；客服人員正式結案時依 owner version／lock 解除 hold；本節 React 清單「處理完成」不發完成通知，其他既有結案流程通知「您的客服案件已處理完成。如仍有問題，請再次呼叫專員。」。舊「繼續使用 AI」「恢復 AI」按鈕與文字指令只提示入口停用，不得結案、解除 hold 或宣稱聊天室 AI 已啟用。

### 3.2A 第一批資訊類 Reply-only（2026-10-30 人工核准）

只將新產生的歡迎／綁定及登記入口、服務與訂單修改導覽、服務流程／收費補助 LIFF 導覽、服務進度查詢、問題釐清、不可用／停用提示、身分切換說明及群組指令錯誤改成 Reply-only。原聊天室及原流程的防重複規則維持。依同日最新人工裁決，群組設定成功與邀請排入等操作人員提示一併採固定文案、Reply-only；服務當天的業務結果回覆維持原契約。

資料／訂單修改申請、客訴／回饋／訂金協助受理、月嫂意願及客戶媒合選擇等業務結果確認保留 Push；LIFF 表單及人工審核結果、排程、主動或跨收件者通知也不改。原專員呼叫受理仍依 §3.2 僅 Reply；不啟用或更改停用中的聊天室 AI 投遞政策。

新資訊回覆沿原 consumer／outer UoW 建立已提交的 durable task，以 `line_webhook_reply` 來源及原 webhook event identity 與舊 `line_webhook_event` 工作區分，無 schema migration。worker 只對該新來源讀取同事件、同一 user／group／room 的未使用 Reply 機會；standby、已即時 Reply、錯誤聊天室或錯誤事件不得借用 Token。沿用既有短效窗口，最多嘗試一次；缺 Token、過期、拒絕、429、逾時及例外均不回退 Push、不自動重試，結果如實保留失敗，不記為已送達。

本批僅影響新產生的資訊回覆；既有已排隊工作保留 payload、識別、狀態及原發送政策，不批次取消、轉換或重送。驗收須同時證明資訊回覆只呼叫 Reply、業務結果與舊工作仍走原 Push、同聊天室核對、失敗零 Push，以及原業務資料與操作語意未變。

2026-10-30 第二批人工核准修正：資訊回覆的原事件查詢涵蓋 user 的 follow，以及 user／group／room 的 message／postback；仍須同事件、同聊天室與未使用 Token，其他事件不得借用。既有 Knowledge 查詢限制維持。驗收須實際執行 adapter 的 SQL 條件，不能只以固定回傳資料的替身證明。

為縮短等待，consumer 只把本次 UoW 真正新建且已提交的資訊工作 ID 交回原 delivery worker，於下一個事件前沿既有逐筆租約、發送前複核與 attempt writer 處理。重複 enqueue 回讀的舊工作及業務確認不進此快速路徑；不更改既有佇列排序或任務內容。每輪資訊快速路徑最多使用 batch 上限的一半（向下取整），其餘沿原佇列處理；合計仍受原每輪預設25筆上限約束。提交失敗不發送；提交後的投遞失敗不得反向重試已完成的業務事件。流程不新增 Push fallback、重試、schema 或外部效果。

### 3.3 交易、冪等與 retry

- inbound event：ticket create/append、狀態事件與需要的業務 delivery task 同一 LINE Unit of Work commit；專員申請的受理回覆依 §3.2，不建立 ack delivery task。
- canonical webhook dispatch 任一業務處理失敗時，該 business Unit of Work 必須整筆 rollback；rollback完成後
  才可另開新的 Unit of Work，只保存`retryable_failed`／`terminal_failed` inbox completion。禁止把部分ticket、
  binding、outbox或其他業務 mutation與failure completion一起commit。
- admin reply：鎖定 ticket、驗證 version、保存回覆、更新狀態、audit、delivery task 同交易 commit。
- inbound idempotency 使用 LINE event ID；admin mutation 使用 caller idempotency key。
- provider timeout/5xx 只 retry delivery task；validation、authorization、stale conflict 不自動 retry。
- retry exhausted 建立 LINE runtime alert，客服資料不得因 provider 暫時失敗回滾。

### 3.4 Typed errors

- `customer_service_ticket_not_found`
- `customer_service_ticket_version_conflict`
- `customer_service_transition_invalid`
- `customer_service_category_invalid`
- `customer_service_delivery_unavailable`

## 4. Service Help Subsystem

精確 intent 為「服務說明」及六分類別名。分派順序固定為 identity、group、service help、knowledge fallback，避免「綁定」或知識問答搶走 intent。

第一版行為：

1. 服務說明：回覆六分類導覽；「其他問題」與一般服務入口共用唯一導覽文案。訂單異動導覽只開啟正式 LIFF，不再於導覽卡提供舊五分類按鈕；入口與舊模板目錄收斂依 `29` §3。
2. 服務流程、收費與補助：依 2026-10-30 人工裁決，選單按鈕直接開啟 AI 客服 LIFF；舊文字／數字別名只回同一 LIFF 導覽。說明由核准常見問答統一維護，移除重複固定回答與通知編輯項目；資料修改等受理通知保留。細部範圍及驗收依 `29` §3。
3. 查詢服務進度：只查已綁定客戶最新案件；未綁定則送 canonical 綁定入口。
4. 修改登記資料、聯絡工會人員、其他問題：建立或延續客服需求。
5. 同一 LINE user、同一 category 同時最多一筆未完成 ticket；exact replay 不追加重複訊息。

## 5. Staff Self-Service Subsystem

### 5.1 訂單查詢

以 verified LINE identity 對映 staff subject，再由有效 `case_staff_assignments` 限制可見案件。姓名或案件編號只作該授權集合內篩選，不可擴大權限。

### 5.2 排班查詢

重用 `subsystems.scheduling.staff_monthly_calendar_query`，以 assignment-owned `staff_schedule` 與正式 availability lock 投影。不得新增另一套排班 SQL writer。

### 5.2A 服務開始與代班結果

完整業務與驗收由規格 02「服務開始、排班與代班」SSTART-01～08 擁有；本節只定義 LIFF／工會 presentation 邊界。

1. 正常入口是客戶在服務群組提出、與月嫂自行協調；Bot 不讀群組對話判斷意願或日期，客戶訂單異動 LIFF 必須移除現有「服務日期／天數」選項、日期表單與新申請 API allowlist，不只移除本流程箭頭；既有客服日期歷史保留。
2. 月嫂從既有 verified staff LIFF 選本人有效案件／區段，選「接受，填寫開始日期」或「無法配合，請工會安排代班」。接受後填約定開始日並送出；系統檢查正式條件與檔期，通過即更新正式日期、排班及第一期款到期日，不要求人員核准。尚無正式 assignment 的有效方案本人亦可提交。
3. 不接受或檔期衝突需代班時才出工會待辦。工會確認區段、選定月嫂並詢問意願；不願意改問其他人，願意才寄該人的原群組邀請。加入原群組後，工會直接填日期接共同正式保存；不讓代班月嫂再提交接受／日期，不新增客戶確認關卡。
4. 工會 LINE 工作面與 React 正式日期／代班操作均採既有 capability 授權，不限 system_admin。正常案件只顯示結果，不列人工日期核准待辦。工作面呈現待辦、意願、選定人選、投遞與入群證據、日期處理及正式回讀，不由前端推算成功。
工會手機及 React 代班畫面必須逐項提供：替代區段／人選、詢問意願、最新本人回覆、不願意改問其他人、願意後「寄送本案群組邀請連結」、邀請及加入狀態／重新查詢、加入後人員日期表單及「儲存並更新排班」、結果未明查核與正式回讀。加入前不得保存正式代班；按寄送只針對該人，不要求回群組輸入全體邀請指令。詳細畫面與 API 對照由規格 02 同節擁有。

5. 正式保存成功後自動建立本案群組日期表寄送工作，內容為各月嫂區段與服務日，無確認／拒絕按鈕。投遞失敗只呈現寄送異常，不能回滾正式結果或重算帳務；開工當天群組提醒依 §6.8。服務開始與請假協調結果使用不同 typed intent，共用代班意願、原案件群組邀請與正式結果記錄機制。

### 5.2B 服務中換人

業務與帳務由規格 02「服務中換人」及既有正式 handover writer 擁有。原案件按鈕帶入原月嫂 assignment 與剩餘服務日，工會主動選人並詢問意願；不願意改問其他人，願意才寄送該人加入原案件群組的邀請。取得實際加入證據後，工會填交接日，畫面列出交接日起原區段全部剩餘服務日，一次儲存更新正式排班與帳務，再建立無按鈕日期表到原案件群組的寄送工作。無再次確認、無新群組、無客戶日期申請，工會不負責協調。

沿用既有代班詢問文案與「願意代班／無法代班」按鈕、單人群組邀請與手機工會待辦。工會具有 matching capability 即可操作，不限 system_admin；本人綁定、enabled Admin 與 current membership 不省略。開頁唯讀，點詢問／邀請才建立工作；交接日儲存時 fresh-read，排程衝突保留原資料及工會待辦，可改日期或改選人。已服務日、已收付款、actual start 與第一期到期日保留，不能以一般短期代班的帳務重建替代正式 handover correction。結果未明保留相同操作識別確認，不盲目新增命令。

### 5.3 請假、順延與代班

1. 不論客戶或月嫂請假，雙方自行在案件群組協調。工會只記錄協議結果或安排代班，不負責協調；Bot 不監控一般聊天。
2. 入口為月嫂與工會官方帳號的一對一聊天室，沿用「排班資訊與請假」選單的 `staff_schedule` LIFF，不須發布選單或輸入聊天指令。本人綁定由伺服器驗證，案件、正式指派與可選服務日由 Scheduling Query 提供。
3. 月嫂選案件及受影響原服務日，選「已協調順延」並逐日填入談妥的新日期，或選「需要安排代班」。直接送出，不需要工會受理或客戶同意卡片。
4. 順延由同一 outer transaction fresh-read／lock 正式資料、執行 canonical Leave/Substitution writer、更新正式日期／排班／Client Finance 與 Payroll，再建立原案件群組日期表工作。無衝突即完成，不產生工會核准待辦。日期表沒有再次確認按鈕。
5. 需要代班或排程衝突才進工會待辦；衝突時回滾排班與帳務變更，保留原資料與衝突提示。工會可記錄雙方重新談妥的逐日順延日期並重檢；工會不代雙方協調。
6. 代班沿既有 Scheduling nominee／LINE committed-delivery 機制：工會選人詢問意願 → 不願意改問他人 → 願意才寄送該月嫂本案群組邀請 → current membership evidence 確認加入原案件群組 → 工會填實際逐日服務日期 → fresh conflict check → canonical 更新日期、排班及帳務 → 群組日期表。不得以寄出邀請冒充已加入。
7. `leave-results/cases`／`leave-results/submit` 使用 staff-scoped transport；無權、stale、錯誤日期或 same-key/different-command 回 typed conflict。結果未明只用同一命令／key 查核，不能建立重複排班或工作；已完成服務的原服務日不可改動；日誌不新增審核或確認關卡。
8. 共用現有 Scheduling result／candidate 持久化；`execution_dates` 的 `leave-v1` envelope 保存原服務日、新日期、決策與衝突說明，與 service-start peer 結果明確隔離，不增加 schema 或人工審核關卡。工會 React／手機依既有 owner capability 可操作。
9. 舊 pending 請假建立與客戶同意順延入口已由新流程取代，回 410；歷史資料與唯讀查閱保留。舊客戶卡片點擊不再寫入或回覆，尚未投遞的舊客戶確認工作不得寄送。不存在新增客戶 LIFF 日期入口、私訊客戶確認或人員群組通知。
10. 群組日期表只記錄已提交結果。缺少案件群組時不退回私訊；結果顯示尚缺群組設定。寄送失敗不回滾已提交日期／帳務。

### 5.4 寶寶日誌與餐食照片

Rich Menu 的「寶寶日誌」開啟月嫂 LIFF。LIFF 只可用 server-side 驗證的 ID token 與已綁定月嫂身分；
後端依正式指派與服務日驗證後，才允許月嫂提交自己服務日的日誌。Scheduling 是日誌、附件關聯、
完成 event、receipt 與 outbox 的唯一 owner；LINE Integration 只提供身分入口、受控檔案傳輸與已提交
通知投遞。

每一服務案／指派／服務日最多一筆有效完成日誌。Orders root 的 `requires_cooking=true` 時，日誌完成
必須附至少一張餐食照片；`false` 時不要求；未知、關聯不唯一、檔案未保存或驗證失敗時一律不建立完成
事實。照片以受控 object reference 與去敏 metadata 保存，禁止放進 LINE 訊息 payload、URL query 或
日誌文字欄。日誌完成只停止後續提醒，不直接改正式排班、訂單或付款狀態。

照片 bytes 依 `00` §2.2 保存於工會地端受控 NAS；MySQL 只保存 Scheduling-owned 附件關聯、opaque
object reference、digest、MIME、size、版本與狀態。LIFF／管理端只顯示檔案清單投影，不暴露 NAS 路徑、
storage locator 或公開 URL；查看使用 authenticated download，重新處理後以受控上傳或指定投放區形成
新版本，不提供 Web 資料夾瀏覽或原地修改。月嫂即時新增照片仍須經 verified identity、assignment／
service-day 驗證、staging 與直接 Apply；不能因 NAS watcher 發現檔案就建立日誌完成事實或發送通知。

月嫂目前由獨立 `staff_baby_log.html` 選月份及本人正式服務日，填寫 1–5000 字日誌，直接點「送出日誌」。
不再要求日誌預覽、勾選確認或跨 request 的預覽指紋；選檔仍可本機預覽。需要下廚時附一張餐食照，
不需要下廚可不附照片或附一張寶寶照，僅接受 JPG／PNG 並遵守現行檔案容量限制。不顯示「尚未確定」
條件分類；既有必要資料缺失時以一般資料錯誤處理，不建立完成紀錄。後端保留本人身分、正式服務日、
附件與檔案驗證、fresh-lock、單一 outer UoW 及同操作重試保障。允許提前填寫，送出後不能修改。
畫面直接依已提交結果顯示成功及照片，讀取失敗不要求重送；結果未知只能以原操作重試。
既有 Preview API 保留媒體 staging 與既有 API consumer 的唯讀驗證用途，不構成目前畫面的送出前置關卡。

### 5.5 服務日誌內部提醒與案件群組發送

- 正式服務時段結束後才計入缺漏，依台北時區及跨日結束時間判斷。依案件及月嫂分開計算，
  日曆日期相連且未填的正式服務日連續超過 3 日（至少 4 日）才顯示；已填日、非服務日均切斷連續區間。
  零散缺漏不得累計達門檻，不同月嫂不得混算；排班重建、代班及補填後依 current facts 即時重算。
- 工會 LINE 管理端「案件群組」內提供「服務日誌提醒」，列出案件群組及連續缺漏幾日，server 分頁。
  Query 零寫入，不新增付款、案件或待辦狀態，不自動私訊月嫂，也不自動通知群組。
- 工會人員自行決定是否點「發送提醒」；點擊即以既有 LINE durable delivery 建立寄送工作，不再確認。
  文案為 `請 {月嫂姓名} 補上尚未填寫的服務日誌，謝謝。`，收件人固定為該案目前案件群組。
  缺少可用群組時列出內部提醒但停用發送，不改寄私人或其他群組。
- 建立工作與 provider 發送前皆重新核對所選連續缺漏區間及群組。補填造成區間失效、取消／換人／
  排班變更造成不適用或群組異動時，尚未寄出的提醒取消。同操作重試不重複建立工作。
- 退役每日服務結束自動私訊日誌提醒：移除預設通知規則與文字模板，既有 active 設定不得旁路建立
  新提醒，已排入的舊自動提醒在 provider 前攔下。歷史日誌、事件及寄送結果不刪除。
- 全部現行使用者介面與正式規格採「案件群組」名稱。日誌完成不自動發送內容給客戶或群組，
  不直接改正式排班、訂單與付款狀態。
- LINE 流程圖的「日誌連續缺漏－工會決定提醒」連到「通知與發送」的人工日誌提醒公版。
  預覽與人工寄送共用同一文案組裝，列出範例月嫂姓名及帶入值；狀態顯示「由流程控制」，
  由工會逐次決定是否提醒，沒有獨立啟用開關；提醒文案沿規格 17 LINE-COPY 的版本化設定維護，不連回退役自動私訊規則。

### 5.6 服務完工與滿意度問卷邀請

正常案件由既有 Orders command 成功提交服務完工後，在原案件群組通知一次，不等客戶與月嫂帳務全數結清。時段維持既有前置驗證；本流程不新增完工補件、空白時段日終放行、人工完工按鈕或問卷系統。

- 預設文案：「本案服務已完成，感謝您的配合。請填寫服務滿意度問卷，讓我們了解您的服務體驗。」不提帳務、不宣稱帳務結清。
- 問卷網址依人工指示先留空。目前使用既有可編輯文字模板 `LINE-SERVICE-COMPLETION-TEXT-V1`，沒有空白網址按鈕或假連結；人員日後直接於通知內容加入正式問卷網址，新工作採用新內容，既有工作快照保持不變。不要求填答才能完工、結算或恢復身分選單。
- 收件人固定原案件群組，規則為即時／單次 `order.service_completed`。只消費 Orders 明確標記的 committed completion outbox，取消／歷史與舊事件不補發；不掃描日期或日誌猜測完工，不私訊客戶或月嫂。
- source／decision／intent／delivery 沿既有 LINE 管線。發送前複核同一有效完工證據、原群組及綁定版本；已曾投遞的同一完工事件不因群組重綁再次通知。缺群組保留既有 LINE 內部處理項目，不改寄私人聊天室。
- 一般客戶沒有月嫂身分時，選單恢復保存正常略過 receipt，群組通知獨立建立；有效雙重身分仍沿規格 23 §9.5 的資格檢查。通知成功、失敗、點連結或問卷填答均不改 Orders／Scheduling／帳務狀態，不解散案件群組。
- LINE 訊息流程及統一通知內容清單均可定位此模板，提供公版預覽及既有內容編輯。設定更新不代表發送，也不發布 Rich Menu。

完工規則與模板沿現有版本化 Query／Preview／Apply 補齊既有資料庫，先備份目前設定並確認寄送程序停用。只新增缺少的完工項目、移除退役請假規則／模板，保留其他人員文案與歷史快照；重跑已齊備設定不新增版本。設定同步不建立寄送工作、不補發歷史案件或發布選單。流程圖缺少規則／模板時顯示「缺少訊息設定」，不能假顯示可用公版。

### 5.7 月嫂薪資請款明細

已驗證且綁定月嫂的本人由圖文選單「薪資請款明細」選擇目標付款月份，唯讀查詢逐案應付、已付、剩餘待付金額、目標付款日、實際付款日及交易紀錄。月份依正式 `due_date` 歸屬；金額與狀態直接取 Staff Payables 目前帳務。部分付款顯示「部分付款」及剩餘待付金額，補款付清或退匯／沖正後，重新查詢反映最新結果。查詢不建立請款、不改帳務；薪資結算與付款成功均不另發 LINE 通知。

### 5.8 取消訂單與退款

正式取消與退款結果僅由後台操作、查詢及 receipt／owner readback 呈現，不提供「取消成功」或「退款成功」LINE 通知、文案、訊息按鈕或發送工作。取消沿既有 terminal closure 依身分資格處理選單恢復，與通知及退款核銷分開。

## 6. UI 與人工入口

### 通知事項工作台與管理員待辦 LIFF

2026-10-30 最新人工裁決：桌面通知事項不重複承接系統內的六類作業。服務登記前往客戶名冊「待核准需求」並帶申請 ID；客戶資料異動前往名冊「資料異動審核」並帶申請 ID；確認資訊／調整條件前往同案媒合作業並帶問題 ID；開工／順延／代班前往排班調度並帶案件及需求 ID；LINE 寄送異常與通知建立異常前往 LINE「寄送與異常」，各帶 task ID／issue key。正式頁獨立重新讀取指定 identity，不依賴清單第一頁或通知舊 snapshot；不存在、已更新或案件不一致時明示原因，不改開另一筆。查詢／跳轉零 mutation，審核、發送、重試、取消與補送仍由原 writer、權限、版本及冪等機制處理；返回通知頁重新查詢。客戶／月嫂綁定人工提醒與人工建立案件群組保留電話、複製文案及 LINE 群組操作指引，不新增完成旗標。手機 LIFF 原作業面、現有訂金／逾期／日誌提醒操作維持。

後台 `#notifications` 的入口位於右上系統狀態旁；以「需要處理／寄送紀錄」接續原功能。待辦集中服務登記、身分／客戶資料審核、月嫂資訊與條件協調、24 小時／7 天內部跟進、推薦與簽約、服務日期／請假／代班、訂金通知、已付訂金尚未建群、各期逾期款、連續日誌缺漏、客服協助、LINE 寄送及系統異常。只依現行 owner Query 顯示，不建立新通知狀態、已讀表或人工結案關卡；相同聯絡需求以 ticket identity 合併，既有客服紀錄不得把簽約入口改成客服回覆。

桌面與管理員待辦 LIFF 共用 `notification-tasks` 的來源目錄及逐來源唯讀 projection。每次請求只讀一個來源的原查詢；通知異常重用既有 current projection 與 LINE owner 複核。保留 bounded 分頁／cursor 與原 total；畫面明示已載入範圍，搜尋只對已載入事項，不將第一批資料冒充完整清單。載入中、失敗、尚有後頁、搜尋無結果與真正零筆分開呈現，失敗來源可單獨重試。判斷以目前分類為範圍；有來源失敗時不能宣稱已無待辦，有下一頁時保留載入更多，兩者同時發生須保留重試及載入更多。寄送紀錄使用自己的讀取與錯誤狀態。查詢、開頁及同步不 enqueue、不喚醒 worker、不呼叫 provider。

「客戶綁定人工提醒／月嫂綁定人工提醒」由 LINE Identity 原查詢 owner 即時投影：僅列待補件、洽談中、訂單成立或服務中案件的客戶，以及啟用中的月嫂；owner 尚無 LINE 綁定且沒有待審核、已綁定或解除中的 canonical role binding 才列入。待審核身分仍在原審核待辦，不重複列入綁定提醒；取消、完工、歷史案件與停用月嫂不列入。桌面與 LIFF 顯示姓名、可用聯絡電話、案件及綁定方式，提供電話聯絡與複製提醒文字；客戶核對姓名與電話，月嫂核對姓名、身分證字號與生日。此為人工聯絡事項，不向未綁定者發送 LINE，不新增已提醒／已讀／完成狀態；完成綁定或不再符合條件後，重新查詢自動移除。沿用 `line.identity.binding.read` 能力與既有來源分頁，不新增表或寄送工作。

提醒按鈕沿原訂金、各期逾期及日誌 command，一次點擊建立 durable 寄送工作；只稱已建立工作，不宣稱送達。人員文案、客戶新條件審核、重新詢問、客服及代班重用原 Query／Preview／Apply 與 writer；審核／簽約／帳務進入同案原工作區。原版本、送前複核、同操作識別及唯一 outer commit 保留。未綁定 LINE、未建案件群組或資料不足時顯示原因與補齊入口，原待辦不因此假完成；失敗寄送可查閱及依原工作狀態重試／取消，不重做核銷。

LIFF 指定事項以事項 ID／案件編號定位；身分審核沿原 owner 單筆 Query，訂金沿原 followups 的同案、同核銷狀態篩選，其他來源先重查 eligibility，再只顯示相同 identity 的原操作卡片。通知頁 cursor 只作查詢位置提示，不能把同頁其他事項當成選取結果。原事項已處理、移動或不再符合時顯示更新提示並要求重新整理，不改選另一筆。面板每頁筆數或先前篩選不影響指定事項。

手機的 24 小時月嫂回覆待跟進提供「查看本案狀態」及「複製案件編號」，前者接既有手機狀態追蹤並帶入案號，後者明示回後台同案媒合工作區查看回覆及接續。查看／複製不移除待辦、不自動催覆、不交換後台登入。原 owner 判斷已回覆、由新詢問取代或媒合輪次結束時才退出；桌面仍沿原同案媒合入口。

返回、切換事項或離開待辦面板即使前一查詢失效；晚到的內容、錯誤或操作回應不得插回已離開事項或覆寫目前畫面。返回時重新讀取共用來源及 owner 狀態，原操作提交與未知結果查詢沿用既有識別，不因切換畫面重送。

舊請假 source 退出現行來源目錄，直接呼叫舊待辦或受理／退回入口回 410；既有歷史 Query 與正式處理證據保留。現行協調結果與例外沿既有 service-start／leave-result store，不建立轉換、搬移、人工結案或新的通知狀態。

LIFF 每次查詢／操作仍驗證 LINE token、有效工會身分及原 capability，不接收後台 Session、不自動轉入密碼登入。手機的簡易審核、客服、提醒與代班接回原手機面板；正式推薦及簽約提示原後台作業並可複製案號。案件結果或寄送狀態更新後重新讀取 owner，不以本機扣數標記完成。通知事項新增／返回不為每件待辦增加管理員私人推播。

「需要處理」的移除條件由原 owner 的最新狀態決定；從原流程返回或重新整理即重新查詢，不以按過提醒代替完成：

| 事項 | 不再顯示的條件 |
| --- | --- |
| 客戶／月嫂綁定人工提醒 | 已有有效角色申請或綁定；客戶案件取消、完工或成為歷史案件；月嫂停用、暫停或退役。待審核者轉由原審核待辦處理。 |
| 服務登記、身分審核、客戶資料異動 | 原申請已不在待處理狀態；三者各依其原流程，不以案件取消一律刪除申請。 |
| 確認資訊、調整條件、24 小時月嫂回覆跟進 | 原需求已被後續回覆／更新取代，或案件不再開放該媒合輪次；取消案件不繼續催問。 |
| 推薦確認、專人協助、待簽約 | 依最新決定及原客服／簽署結果推進；接受後由推薦跟進改列簽約，簽署齊全後移除簽約待辦；取消或離開適用階段後移除該階段提醒。獨立客服需求仍須依客服狀態結束。 |
| 日期、順延與代班 | 原需求已處理／被新需求取代，或案件已取消／完工；人員不再處理已取消案件的服務排程。 |
| 舊請假申請 | 僅保留歷史查閱，不列入桌面或 LIFF 現行待辦，不提供舊受理／退回操作。現行請假例外沿「開工、順延與代班」來源處理；退役入口不代表已完成排班。 |
| 訂金通知、尚未建群 | 訂金核銷後，繳費提醒改為原核銷通知；核銷通知已送達即移除。建群完成即移除尚未建群；取消、完工及歷史案件不再催訂金或建群。 |
| 各期款項逾期 | 該期餘額歸零、取消、無需該期或到期日更正為未逾期；取消及歷史案件不列原服務款逾期。完工但仍有合法未清款項時保留，不把完工當結清。退款仍由原帳務清冊處理。 |
| 日誌連續缺漏 | 補齊後不再連續缺漏超過 3 日，或案件不再適用日誌提醒（如取消／完工）；不以已按發送當作日誌已補齊。 |
| 客服、LINE 寄送異常、系統事項 | 客服依原案件處理狀態結束；寄送工作不再是失敗／待重試，或同一原通知已由有效補送成功處理／業務來源已不適用；監控恢復正常；通知對象設定待辦須有啟用對象、啟用管理員及目前有效且一致的 Admin LINE 綁定才移除。寄送歷史仍保留於寄送紀錄，不因退出待處理而刪除。 |

通知建立前受阻的 `recipient_unavailable`／`template_or_schedule_invalid` 沿既有 LINE-006 current-only projection 及 LINE owner fresh readback，列入「LINE 通知建立異常」來源；保留原 keyset cursor，不把來源頁號當游標。只投影案件、原因、原來源 ID 與可用動作，不輸出收件身分、訊息 payload 或 owner snapshot。已被此事項涵蓋的確切寄送工作 ID 不重複列入寄送異常；其他寄送失敗仍保留原 task 重試／取消入口；已合併的工作在同一異常明細呈現原控制，不因去重而失去入口。同一原來源有可接續工作時不另建補送，不限制同案其他來源；原工作已取消且 source 仍適用時可沿原流程重新補送。沒有新增通知表、完成旗標或自動補送。

設定修復本身不解除通知異常。人員重新核對後，原 source 仍適用、收件人及設定通過原補送驗證才可點「補送原通知」；補送薄轉接既有 manual replay writer，保留原 source lineage、操作識別與 original commit owner。排隊、寄送中及等待重試時仍列原待辦，禁止再次補送；terminal success、原通知不再適用或原 owner 的合法略過結果才依既有 predicate 退出。取消及歷史案件不繼續處理原服務通知。

寄送異常待處理清單由共用後端逐筆核對原通知及 exact replay lineage；同一來源已成功或業務來源不再適用時，不因原失敗歷史仍存在而回流。其他來源的失敗不受影響，原工作狀態與寄送紀錄保持不變。來源複核不完整時回傳可重試的無法讀取狀態，不當作零事項。fresh 複核後可有空候選頁；兩端沿原分頁繼續載入，不將未篩選候選總數當有效總數。手機件數只計算實際卡片；有下一頁時不宣稱已無事項，載入後移除舊空清單提示。

桌面與 LIFF 按本次操作的實際收件人及必要資料限制發送；缺綁定、群組或繳費資料時停用發送，但保留查看、聯絡及補齊入口。每個阻塞操作都須在畫面直接說明原因與下一步，不能只停用按鈕或只顯示錯誤碼。未綁定須指出客戶或月嫂；繳費資料須列出原 ready 判斷實際缺少的項目；原工作仍在排隊／寄送／待重試時說明應接續原工作；權限不足須提示核對登入身分或由有權限工會人員處理。案件／帳務、身分、群組及通知內容各接既有工作面；銀行代碼等部署設定不可在畫面編輯時明示需補項目，不能導向無關綁定頁充當修復。提醒資格仍在提交前由原 command fresh-read。確認資訊與條件協調中，客戶未綁定只阻擋發給客戶，不阻擋原本可用的月嫂回覆；兩端提供綁定方式及重新核對，重新核對不清除尚未寄送的文案。無法完成核對時保留草稿並明示原因，不將無法讀取當作可寄送。

手機管理端客服、身分及資料異動審核一次點擊提交，必要 Preview／Apply 由程式依序呼叫，不要求第二次人工確認；備註選填，原 writer 需要稽核原因時以系統操作說明保存。未知 Apply 結果保留原冪等鍵，不因重按而另建操作。成功後重查共用來源、數量及卡片；仍待客戶回答、欠款或缺日誌時保留。條件審核後保留原面板供選擇月嫂重新詢問。查詢、預覽、Apply 的成功及失敗回應均核對目前事項／畫面序號，離開後不得覆寫新畫面；再次進入讀回正式結果。

### React 客服案件清單（2026-10-29 人工核准）

2026-10-30 人工裁決：桌面通知事項的客服待辦按「前往客服案件」，直接跳至既有客服案件頁並帶入工單編號搜尋；推薦聯絡需求若已連結客服工單亦沿相同入口，待簽約事項仍進原簽約工作區。通知頁不展開舊客服操作面板、不讀取或呈現完整客服事件與技術紀錄。對象欄標示「客服對象」，有原 owner 姓名就顯示姓名，缺姓名顯示「未具名使用者」，不以「聯絡人」充當姓名。手機原客服面板與 writer 不變。

React「客服與營運」客服頁只列未結案案件，採六欄：客服對象、可複製的 LINE 顯示名稱、進件來源、客戶留言、申請時間、案件完成。不顯示 waiting／handling 狀態分頁、處理人、優先標籤、抽屜、站內回覆或聊天室跳轉；不建立聊天室網址對應。搜尋姓名、工單／案件編號及 server 分頁保留。LINE 顯示名稱不是搜尋好友用的 LINE ID，不以會員姓名或 U 開頭識別碼代替；透過官方唯讀 Profile 查詢取得，單頁至多100個對象、並行上限4，單頁外部查詢共用2秒預算，預算耗盡後略過尚未開始的對象，缺設定／封鎖／取得失敗顯示「尚未取得」，不影響其他案件查閱。這些是目前查詢實作上限，依實際效能／官方限制調整，不改業務資格。

`GET /api/v1/customer-service/tickets/reminders` 保留既有 reader、closed source、bounded search／pagination 與 waiting／handling 摘要契約。清單固定查未結案，公開 projection 增加 version、line_display_name、requested_at 與最近10則已保存的客戶留言；申請時間取 ticket 建立時間，不能拿更新時間代替。留言僅取已驗證人工對話 active-hold customer-message，不以系統受理文案、管理備註或回覆充當客戶留言，不重新揭露已遮罩客訴；沒有可呈現內容顯示尚未留言，已遮罩客訴明示去敏。多則留言同格展開，不開抽屜；文字保持純文字呈現。查詢不 commit／receipt／enqueue／worker wakeup，Profile 僅 GET，無 Push。

來源固定 `handoff|complaint|feedback|order|service|binding|unknown`，沿用既有 canonical event／同事件 escalation 的分類，不由留言或姓名猜測。`unknown` 是缺證據的既有案件；同一 ticket 多來源仍只列一筆，顯示最新已辨識來源。

「處理完成」一次點擊接回既有 detail／update Preview／Apply；程式重讀並核對清單 ticket version，保留內部備註，不要求人員再預覽或確認。新留言／其他人更新造成版本差異時保留案件、重查後由人員決定。Apply 在同一 outer transaction 鎖定 active escalation 及 ticket，沿現有 open→claimed→handling→resolved 升級路徑，保存版本、完成事件及解除 hold，僅一次 commit。待 owner 來源允許才完成；不單改前端或以清單消失假完成。此桌面「處理完成」不新增客戶完成通知或任何 Push；手機及既有專用 escalation 結案通知維持原契約。結果未明保留同一操作識別／payload，僅查核原操作，成功後重查正式清單及件數；成功前不移除案件。

DTO 不回傳 LINE user ID、電話、內部備註、event key 或 provider payload。授權限原客服 reader／handler。完成僅關閉當前工單並保留歷史；後續新訊息沿既有 owner 規則處理。驗收涵蓋六欄、名稱複製／缺值、真實留言／去敏、申請時間、server 分頁、晚到回應、版本衝突、完成與 hold 原子一致、同鍵重播及零 Push。

- merge 的 Rich Menu 圖面、按鈕標籤與 LIFF 卡片樣式可移植。
- 「客服與選單」的 Rich Menu 編輯器必須提供背景圖與按鈕顯示名稱的 draft 編輯入口；畫面預覽、
  Preview receipt 與 Apply 必須鎖定同一 revision。編輯草稿不等於發布，provider publication 仍依 `17`
  的 durable saga 執行；未啟用 provider 測試時只驗證到 committed definition／publication intent，不假造發送成功。
- 2026-10-17 人工裁決：Rich Menu 草稿編輯的原因改為「備註（選填）」，省略／空白以既有 reason 空字串保存；仍要求相同 revision、Preview fingerprint、人工確認、操作人員、冪等鍵及正式回讀。只放寬草稿 metadata，其他設定種類、實際發布與發布重試仍維持必填原因，不增加 provider 副作用。
- 背景圖選擇器只查目前 editable menu owner 的受控 metadata，並保存 exact asset ID／SHA-256／opaque
  version；已刪除項目保留歷史顯示但不得選取。畫面不得顯示 digest、version、storage locator 或 raw ID
  輸入框；合法空清單仍保留系統色彩背景。Preview 零寫入驗證 metadata，Apply 對新 command 於同一
  outer transaction fresh-lock 後才提交草稿 revision。
- 手機模擬器點擊每個熱區時，必須使用同一 draft revision 的真實 typed action；管理員可依 `17` §3.5
  修改 action kind 與該 kind 的 allowlisted target／內容。按鈕顯示名稱修改不得改變 action，action 修改也
  不得靠標籤推導；Preview、Apply 與 readback 必須讓編輯器、手機模擬及 server definition 顯示同一結果。
- 管理端必須使用 server 依 exact menu／revision 投影的 `editable／processing／published` lock；
  `processing` 只顯示人可讀業務原因且不掛載草稿 mutation controls，`published` 則允許以目前內容建立
  下一個 draft revision，且不得覆寫既有 publication snapshot。缺 lock 或 owner projection 漂移時唯讀 fail
  closed，不得由發布歷程首筆、按鈕標籤或瀏覽器 hardcode 猜測。
- Rich Menu 本機預覽不是待移除的 demo：它是正式編輯 UX 的零寫入互動層。編輯背景、標籤、action 或
  message text 後，手機畫面立即更新；點擊 message 只在模擬器顯示候選文字，點擊 URI／LIFF 只顯示該
  typed target 的模擬頁，不送訊息、不開 provider mutation。另保留獨立 server Preview、確認與 Apply。
- React 管理端固定保留「客服與選單」、「AI 事件工作室」、「LIFF 卡片工作室」、「群組與安全」四個獨立入口；
  API adoption 不得以未接線為由刪除既有設計功能、控制項或業務說明。
- LIFF 卡片工作室保留現行 LIFF 入口與 4 個訊息公版項目。已有 canonical route 的項目可產生不含 identity／token
  的真實測試連結；案件專屬入口缺少必要識別碼時不產生通用連結，不得以 demo token、樣本個資、
  假 provider payload 或不存在的 URL 補空。真實測試連結的 origin 由既有 LIFF runtime-config 回傳經驗證的
  `LINE_PUBLIC_BASE_URL`／`BASE_URL`；不得由 React 硬編 localhost、夾帶帳密、query、fragment 或身分資訊。
- LIFF 卡片工作室中央手機模擬器必須維持可閱讀的正常手機比例與最小內容寬度，不得被左右工作區 flex/grid
  壓縮成狹長欄；窄螢幕改為堆疊或可捲動配置。一般畫面不顯示歷史資產盤點說明；現行項目與正式操作入口保留。
- legacy `/static/bind.html` 僅為相容導向；正式入口 `/line-bind` 沿 canonical Customer Preview／Apply。網址預填不作身分依據。
- `/line-profile-update` 已提供 verified LIFF 資料異動 Query／Preview／Apply 與 applicant receipt；送出只建立待審申請，工會核准後才更新 owner 資料並讀回。契約見 §6.1，不再列為待建頁面。
- LIFF 工作室沿既有正常手機比例、資產入口與公開 runtime origin；模擬預覽不代表真實 verified-token、provider 送達或發布驗收。
- AI／常見問答僅在獨立 LIFF 提供。一般聊天室未知輸入回自助導覽，不啟動 AI 或自動開客服單；主動點「需要專人協助」才沿正式 Feedback／Customer Service owner 建立需求，不使用本機假統計或假工單。
- 客戶「已填過／尚未填過」選擇必須保存 canonical flow ID；未填過流程完成登記後才能完成同一 LINE 身分綁定。
- LINE 管理中心使用 Customer Service bounded API client；成功 payload 轉 typed Pydantic view，transport/schema error 轉 typed client error。
- Streamlit 只顯示 typed result 與提交 command，不包含 ticket transition 或 SQL 規則。
- 已綁定且 enabled 的工會人員可由 `line-mobile-admin` LIFF 的獨立 target surface 使用待辦工作台、客服中心、狀態追蹤與營運摘要。四個入口以 server-verified LIFF identity 與 current role-scoped LINE admin binding 取得既有 Admin owner 的 actor ID、角色與 capability；不得要求另一個 React／密碼／MFA Session，也不得把 LINE 憑證交換成可供一般後台使用的 Admin Session。各 owner 的 Query／Preview／Confirm／Apply 仍須以該 actor 重新驗證所需 capability。待辦工作台依 `29` 分組呈現 Client 資料異動、LINE Identity 客戶／月嫂重綁與身分異常、Scheduling 現行請假協調結果及代班／改期，以及 Matching／Scheduling 媒合指派／重新媒合；各組只呼叫原 owner 的 bounded Query／Preview／Confirm／Apply，不建立 LINE-owned 共用 approval root。客服保留既有查看／回覆；狀態追蹤只讀取 Orders 的 current operational-stage projection，依案件編號查詢未完成訂單的目前階段、最後更新與下一步，不建立或改寫訂單 root；營運摘要仍只讀取其 owner 的 current Query。舊 `anomalies_center` target 僅作既有連結相容別名並導向 `order_tracking`。QA／Knowledge 審核留在 AI 事件工作室；其 server-side ID token、binding、version、receipt 與 outbox 規則不因共用 LIFF runtime 而改變。

### 6.3 LINE Feedback正式契約（2026-08-31 人工裁決）

Feedback由LINE Integration的bounded Feedback capability擁有，不另建Generic Feedback／Analytics Domain。
subject固定綁定verified LINE actor／current binding、exact canonical response／interaction identity，以及存在時的
response contract/catalog/rule revision；同一actor＋source只允許一筆terminal decision。第一版closed outcome只有
`resolved | unresolved`：same outcome exact replay回原receipt，不同outcome固定conflict，不建立edit state machine。

root保存最小identity、outcome、binding/version、business time、idempotency、command fingerprint、correlation與
optional Customer Service ticket reference；不得保存raw prompt、provider payload、conversation dump、credential或
為統計複製完整訊息。一般統計只回aggregate count/rate。`resolved`不建ticket；`unresolved`必須由Customer
Service owner建立或exact-link正式ticket。Feedback root、receipt及ticket linkage由唯一outer UoW協調；若現行
架構不能同transaction安全完成，改用committed durable intent並明示`ticket_link_pending`，不得回報假完整成功。
正式surface至少包含feedback Query/readback、zero-write Preview、Apply、immutable receipt/readback與bounded
aggregate statistics Query。獨立 LIFF 已沿正式 Feedback owner 提交及讀回；`unresolved` 對應使用者明確點選「需要專人協助」，不從一般留言或查無答案自動推定。

### 6.4 聊天室與獨立 LIFF 問答邊界

聊天室先處理核准的 deterministic commands／security aliases；一般留言及未知輸入回自助導覽，不執行自由文字 AI、不自動開客服單。明確呼叫專員才直接建立或沿用同一客服案件。舊 AI 按鈕只提示停用，不結案或解除 hold。
AI 智慧問答與常見問答在專用 LIFF 提供；無唯一核准答案回主題選單，系統不可用如實顯示失敗。模型不產生業務承諾、不寫 root、不自行發布內容。使用者明確點選「需要專人協助」才走正式人工需求。

### 6.5 Scheduling mobile LINE 綁定授權（2026-09-09 人工裁決）

Scheduling mobile review以server-verified LINE token與current role-scoped admin binding確認工會人員，從enabled
Admin owner讀回actor ID、角色與capability；不得要求React password／MFA／Admin Session，也不得由binding簽發
一般後台Bearer token。binding失效、owner disabled或缺少Scheduling capability時fail closed。

LINE token不得進query、fragment、LINE message或postback。mobile adapter不複製Admin Session lifecycle，也不擁有
Scheduling root；正式mutation仍完整沿用Scheduling Query／Preview／Confirm／Apply、version、lock、fingerprint、
receipt與fresh readback。

LINE 管理 surface 驗收狀態（2026-08-25）：`completed`。案件群組與事件使用 additive
numbered Query，舊 `limit` API 保留；執行中的 FastAPI 更新至 current route 後，Chrome 實點群組頁
顯示合法零筆狀態，未再出現 `resource_not_found`。發送任務明細已實點開啟並立即關閉，晚到結果未重開
Drawer。Rich Menu 依 typed bounds 顯示本機幾何初檢，明示正式路由仍須 server Preview；Diff 在缺少
active typed snapshot 時明示 blocker，不猜 Before。外觀與 action 同時修改後，取消 action 仍保留外觀
candidate，再取消外觀可完整復原，且全程未送出 mutation。Focused React 3 files／20 tests、Python 4 tests
與 TypeScript 均通過。測試 DB 目前沒有案件群組，因此群組／事件正向翻頁為 `not_run`，由 focused
numbered pagination regression 覆蓋；不得為取得 Chrome 正向頁面而偽造 owner root fact。

### 6.0 LIFF 頁面設定的唯一來源

登記、綁定、導流頁及管理端設定統一讀寫 MySQL 的 versioned `liff` configuration。`config/liff_settings.json` 僅供明確 fresh bootstrap；執行中不得 fallback 讀檔。設定缺失、格式錯誤或資料庫不可用回 503；頁面不存在或停用回 404。
既有 `/api/config/liff`、`runtime`、`state`、主題／頁面／欄位儲存、history 與 rollback 保留入口，改經同一 configuration Query／Apply。ETag／If-Match 使用資料庫 revision；讀取後遭並行更新回 409，不能盲目覆蓋。共用 typed LIFF validation 同時約束管理 API 與通用 configuration writer。
歷史讀不可變資料庫版本；還原是在目前 revision 上新增一版，不修改舊版本或回寫檔案。舊檔案歷史不自動匯入或作現行還原來源。設定操作只產生設定版本與稽核，不建立訊息、排程投遞或選單發布工作。

### 6.0A 非市民 LIFF 填寫頁與設定（2026-10-29 人工確認）

狀態：`implemented / repository-local-verified`。使用者已於 2026-10-29 核准七階段實作與逐階段驗收；執行範圍及實際證據見 [非市民案件實作工作包](../非市民案件實作工作包.md)。此狀態不代表已部署、使用正式資料或完成外部 provider 驗收。

管理端 LIFF 工作室的頁面選擇、導流目標、欄位及文案設定需能維護新頁面；頁面 runtime、typed 設定驗證、歷史及還原均沿 §6.0 同一 versioned configuration owner。保留原補助問卷及既有頁面設定，新表單必填要求不套到其他申請類別。新增頁面不表示新增 LINE audience、選單發布或 provider 效果授權。

verified LIFF 送出只保存待審申請，顯示申請編號及「待工會核准」；工會核准後的正式案件及綁定由既有 owner 處理。後續登記、繳費資訊、服務及帳務頁面需接受 A 開頭案件識別，取用本案正式帳號與非市民政策，不由前端推算。

後續需驗收 gateway 非市民選項、新填寫頁、必填與退款用語、設定保存／runtime／還原、送出結果與核准回讀，以及原補助導流不變。本次僅更新規格，尚未建立頁面或改動設定。

### 6.1 LIFF 資料異動申請與管理核准（2026-08-25 人工裁決）

`profile_update` 不再是唯讀設計槽位；正式目標是 verified LIFF 使用者提出資料異動申請，經工會
管理人員審核後，由資料 owner 的 typed command 更新 DB，最後讓 LIFF 與管理端讀回一致結果。

1. LIFF 只接受 server 驗證的 ID token 與 current binding；query-string `userId` 只能保留導航資訊，
   不得決定申請人、subject、權限或 DB target。
2. 申請 payload 必須是 owner 核准的欄位 allowlist、目前 owner version、requested values、申請原因與
   idempotency identity。LINE Integration 只擁有 intake／binding evidence，不得直接更新 Client／Staff root。
3. 提交採 `PreviewProfileChangeRequest` → 使用者明確確認 → `ApplyProfileChangeRequest` → applicant-scoped
   receipt/readback；Preview 零寫入，Apply 只建立 immutable pending request，不代表資料已修改。
4. verified applicant可看自己的完整current/requested values；authenticated、enabled且具對應owner
   permission的管理端reviewer可看完整diff、subject、request version、必要evidence與明確業務blocker。
   一般UI仍不得顯示fingerprint、raw token、binding id、SQL、storage locator、secret或credential。
5. 核准採 owner-specific `PreviewApproveProfileChange` → 管理員明確確認 → `ApplyApproveProfileChange`。
   Apply 在單一 outer UoW fresh-lock request、binding、subject 與 owner version，由 owning repository 更新
   canonical DB root、append approval event／receipt／outbox 並 commit；route、LIFF、LINE callback 與 UI
   不得直接 SQL。拒絕只更新 request workflow，不修改 owner root。
6. Apply 成功後必須重新 Query owner DB projection與 request outcome；管理端和 applicant-scoped LIFF readback
   都要顯示相同的新業務值與 `approved_applied`。receipt 已提交但 readback 失敗時，顯示 outcome unknown 並
   只允許 reconcile，不得盲目重送或宣稱未修改。
7. stale owner version、已終結 request、same-key different payload、未綁定、subject mismatch、欄位未允許、
   validation failure 或 transaction failure 固定 fail closed；same-key same-payload replay 回原 receipt。
8. Browser 驗收必須實際由 LIFF 提交、管理端核准並讀回 DB 更新；另驗證拒絕、stale、replay、越權、
   rollback 與合法唯讀原因。不得以 API mutation、直接 DB patch、假 token 或改狀態欄取代 UI。

資料異動執行狀態（2026-08-26）：`approved`。人工已授權先由 Client／Staff owner 補齊 root、欄位
allowlist、version、repository contract 與必要 `lu_test_*` schema release，再依本節完成 LIFF／管理端 E2E。
所有 schema 工作仍須完整 DB change gates；production DB／`union_db` 與 provider push 不由 schema 授權推導。

### 6.1A 客戶訂單異動申請 LIFF（2026-09-09 人工裁決）

客戶 Rich Menu「修改訂單資訊」改為 verified LIFF URI。它是結構化人工確認申請，不是 Orders writer：

1. Query 只依 server 驗證的 LINE ID token 與 current customer binding 讀取本人有效訂單；不得接受 client-supplied user ID 或跨客戶 case number。
2. 新申請 allowlist 為服務地址、下廚需求、每日服務時段與其他訂單內容。移除原「服務日期／天數」選項及其起訖日／天數輸入、preview 與提交分支；新 request 不再接受 `service_days` 日期申請種類或其他種類夾帶 `start_date`／`end_date`，不能只隱藏前端。舊申請、客服事件及訂單日期唯讀查閱保留，不刪資料。服務地址 intake 包含 Client owner 的 `city`、`address`、`residence_type` current values，但不移轉其 root ownership。
3. 流程固定為 Query／Preview／human Confirm／Apply。Preview 顯示 before／requested diff 與影響提醒且零寫入；Apply fresh-lock binding 與 selected Order，校驗 order version、Client profile version 所形成的 fingerprint 與 idempotency identity。
4. Apply 只在 caller-owned outer UoW 建立／延續 Customer Service ticket event，回傳 ticket readback。畫面只能顯示「待工會確認／正式訂單尚未修改」；後續正式改單、費用、排班、媒合與月嫂同意均不在本流程 Authority。
5. 「修改登記資料」verified applicant allowlist 移除 `city`、`address`、`residence_type`；這三欄改由訂單異動 LIFF 提出影響性申請。Client owner 仍保留 canonical values 與後續核准寫入責任。
6. stale、binding drift、order 不屬本人、已終結 order、非法欄位、fingerprint mismatch、same-key different-payload 或 transaction failure 固定 fail closed；exact replay 回同一客服需求。

### 6.2 工作室公版預覽與候選回應契約

工作室訊息預覽重用既有公版目錄、純訊息組裝與對話預覽元件；公版不查真實案件、不建立憑證或投遞，按鈕僅顯示動作說明。預覽不宣稱實際流程或投遞已接通。現行項目如下：

| Asset | 原圖節點／業務作用 | Current owner source | 設計預覽邊界 |
|---|---|---|---|
| flex_dispatch | M1 Staff_Order_View 與 M3 派案意願調查：讓候選月嫂去敏查閱正式案件資訊；主動作為「願意承接」，另一動作固定為「提出疑問或無法承接」並開啟 recipient-bound LIFF | Scheduling Candidate Contact Pool、Orders case projection；LINE 只 render／deliver | 不代表已建立聯繫事件、delivery task 或送達；不得攜帶客戶姓名、電話、詳細地址；LIFF 不接受 query-string LINE 身分 |
| flex_leave_confirm | 案件群組服務日期表，記錄已確定的排班，無再次確認按鈕 | Scheduling 正式排班與日期表 renderer | 公版 service-start-result；不發客戶同意順延卡 |
| flex_alert_critical | M4 Step3_Push_Alert：將 committed HIGH escalation 的去敏摘要與需驗證身分的客服處理入口通知已設定的管理員個人對象 | Customer Service escalation；runtime alert target owner只提供 current recipient target；LINE負責delivery | 不顯示完整姓名、電話或 raw 摘要；不代表通知對象已設定、task 已送達或案件已被 claim |
| flex_negotiation | 人工條件協調詢問：月嫂提出調整條件後，由人員查看原文並自行輸入文案詢問客戶，客戶提供新條件後由工會審核 | Scheduling Candidate Contact Response／staff-authored question／customer answer／adjustment review | 不自動套用條件、不直接改 Orders；客戶回覆後仍走 fresh owner Preview／Apply |

`flex_dispatch` 的候選回應契約如下：

1. LIFF 固定提供服務地區、服務日期／檔期、每日服務時段、每日服務時數、下廚需求、交通／停車／樓層、個人因素，以及互斥的「沒有意願」八項。前七項可複選，且每項須標示為「確認資訊」或「調整條件」並提供結構化說明。「沒有意願」不要求理由，勾選時取消其他問題，按「送出回應」才保存；成功後僅在頁面顯示「已送出，謝謝您的回應。」，不另發聊天室訊息。人員端顯示「無意願」，備註顯示「沒有意願」，既有 `no_interest` 事件讀取時亦採此文字，不改寫歷史事件。不建立協調待辦或通知客戶，不影響其他月嫂回覆，也不自動取消或結束案件；推薦對象仍由人員決定。
2. 「確認資訊」與「調整條件」均保存為工會人員待辦，不自動詢問客戶、不產生草稿、不建立群組通知。月嫂畫面顯示「已收到您的問題，待工會確認後回覆。」；月嫂填寫的分類及原文只供已驗證的工會人員查看。
3. 工會 LIFF「月嫂確認與條件協調」呈現原文、已發出的詢問及客戶回答。文案欄預設空白，人員自行輸入後點「發送給客戶」才建立 durable task。確認資訊可由人員輸入文案後直接發送給月嫂；調整條件必須完成客戶新條件與工會審核流程。
4. 調整條件的客戶表單顯示人員輸入的詢問文案，要求填寫「更新後的條件」，不再提供可以／無法調整的二選一。客戶回答只更新人員待辦，不自動轉交月嫂，也不直接改單。每次詢問及回答綁定同一收件人、案件、原月嫂調整事件與本輪 staff-authored event；舊連結不能回答新一輪，exact replay 不重複建立事件或投遞任務。
5. 人員審核新條件：不通過時回到空白詢問文案，修改後再次詢問客戶，可反覆協調；通過時只需「審核通過並更新案件條件」，沒有「是否需要修改」分支。系統在同一 outer UoW fresh-lock 本輪回答與案件版本，透過 Orders Terms 的 fresh Preview／apply_in_current_uow 更新正式 DB 條件，並追加綁定 exact answer、resulting order version 與審核值的協調審核事件；任一步失敗全部 rollback。普通 Terms 保存仍不偽造 Orders 永久 receipt。
6. 審核面板使用現有 Orders Terms 欄位：預計開始日、服務天數、每日時數、下廚需求、樓層費與完整每日時段。月嫂原分類是協調來源，不得直接變成 DB 欄位或由自由文字猜測寫入。工會人員須先把客戶新條件核對到正式欄位後才審核通過；其他 owner 的地區／地址等資料不可由此旁路改寫。
7. 24 小時僅作工會內部回覆提醒，從成功送達起算，不關閉表單、不阻擋願意或其他回覆，不自動把未回覆者改寫成沒有意願，也不以時間到期觸發客戶協商。等待人員或客戶處理時留在待辦；不發月嫂逾時提示。初次搜尋零候選不建立協商或回覆提醒。「候選池為空／候選池協調建議」固定通知已退役：移除預覽項目、有效規則、模板與 bootstrap，不以停用或隱藏代替；設定 writer 拒絕重新加入，舊通知 producer／consumer 與待送工作亦不得恢復發送。保留歷史事件、receipt、稽核與查詢。
8. 可同時詢問多位月嫂；本人或其他候選的既有 willing 均不阻擋回覆或更正。最新結構化意願由 append-only event 投影，人員決定推薦誰給客戶確認，願意不代表獲選、媒合成功或正式指派。願意按鈕只回覆「已收到您願意承接的回覆，後續由工會安排媒合。」；案件／候選失效、原詢問期間已變更或 recipient 不符仍拒絕業務寫入，不發額外原因提示。
9. 工會人員已通過 LINE current binding、enabled Admin 及 matching capability 驗證即可協調、審核與改單，不限 system_admin；一般未綁定使用者不得使用人員入口。人員待辦是唯一提醒介面，不建立新的協調群組通知；既有未送出的自動調整／群組通知由 worker 取消，已送達歷史不改寫。
10. 審核通過並讀回新案件版本後，人員選擇目前有效的候選月嫂重新詢問。重送綁定同一 customer-answer 與 candidate 的冪等 identity，並檢查審核後案件版本未漂移。服務日期改變時，由既有 Scheduling writer 使用 current Orders 起訖日 fresh-read、重驗 availability、更新 contact period／coverage 並保留前後日期事件，不能沿用舊期間；重送不等於月嫂願意或正式指派。

客戶推薦由人員選定願意承接者並主動寄送確認資訊。專人協助回覆「已收到您的聯絡需求，請留下您的疑問。」，人員從待辦查看與回覆，原卡片仍可接受配對；接受時回覆「已收到您接受配對的回覆，後續由工會安排簽約。」，待辦改為辦理簽約，訂金正式核銷後由人員建立案件群組；簽約與付款可先後發生，建群不以雙方簽約完成為門檻。成功送達滿 7 天未接受僅作內部提醒，不阻擋回覆、不發群組通知。本人、current binding 與有效方案驗證不省略，取消、更換或最終決定的方案不能重用；履歷下載仍沿原短效憑證規則。

LIFF 圖例與正式入口依目前流程呈現：客戶無實際服務日期修改選項；日誌直接送出；月嫂填入已協調的順延日期，無衝突即更新，需代班或衝突才交工會。三個可設定頁面套用資料庫目前版本的主題、一般文字、按鈕與成功提示；正式結果狀態及申請編號始終由實際回執顯示。

閒置客服的營業時間、自動分派、閒置結束與預設訊息設定停用：目前設定清空、初始化不再載入、舊維護 API 回 410，設定 writer 只允許空定義以防還原復活。設定歷史與客服案件保留，不新增自動化。

### 6.6 通知內容統一維護（2026-10-15 人工裁決）

「通知與發送」只保留統一通知內容清單，歡迎訊息列入其中；一般操作頁移除獨立歡迎及發送紀錄分頁。案件通知歷程仍由待辦看板既有案件紀錄查詢；非案件通知不因此被宣稱具有案件歷程。Delivery Query API、worker 與仍有效的 standalone 元件不隨此 UI 入口精簡退役。

清單呈現通知名稱、對象、內容摘要與編輯入口，搜尋涵蓋名稱／內容。文字儲存沿用既有 manager 權限及 MESSAGE_TEMPLATES revision；任何內容儲存後重新 Query 全部內容以取得共用的新版本，stale／查詢或儲存失敗不得假裝成功或盲目重試。歡迎訊息仍由原加好友流程發送，不增加延後引導。

人工已一併授權將請假、媒合與告警的說明文字接通至實際通知組裝。條件詢問由工會自行輸入文案；已退役的客戶順延確認卡不再組裝或發送。M4 客訴／runtime critical 告警在原去敏摘要與管理入口之前加入對應設定說明，維持原發送格式；一般轉真人通知不套用這兩則說明。本文不授權把既有文字告警改成新的 Flex／安全連結流程。

設定更新只影響之後新組裝的通知；已提交的 intent／outbox／delivery payload 沿用 immutable snapshot，不能在 retry 時套用新文案或因儲存而重新送出。規則欄位收在次要發送設定，仍沿用既有 Preview／Confirm／Apply、取消待發工作的 owner 及效果上限；流程管理通知不得把 shadow rule 的停用狀態冒充實際流程關閉。

2026-10-24 人工確認：LINE 專區新增「LINE 流程圖」，沿用精簡版預覽。首頁僅顯示登記與身分、媒合到服務、客服與支援三組流程的步驟及正式目錄訊息數；點選步驟後才展開訊息，多則訊息可再選定個別項目。流程順序供導覽，不建立新的業務前置或改變 owner gate。流程圖只讀取既有訊息預覽目錄與通知規則 Query，以正式 descriptor／template 引用解析目前訊息 ID，不複製文案、假造啟用狀態或建立投遞。選擇訊息後定位「通知與發送」的對應項目，網址保留 `tab=push_queue&message=<目前訊息ID>` 供重新整理；清除會遮蔽該項目的搜尋／格式／狀態篩選。不存在或查詢失敗時明示不可用，不改選其他訊息。返回流程圖及切換仍沿既有未儲存草稿保護；返回時重新讀取正式規則，保留所選流程步驟。規則型通知呈現 current enabled；固定回覆及業務流程管理訊息標示「由流程控制」，不得以 shadow rule 狀態提供開關。編輯、啟用設定、權限與 stale 保護仍由原通知工作台 writer 承接；圖文選單發布、provider 發送與業務資料寫入不屬於流程圖操作。

流程圖的服務當天次層包含當日卡片及「服務正常」「需要協助」後的原案件群組受理回覆，預覽與正式回覆共用文案。客服與支援的既有步驟次層補列服務進度查詢／未綁定提示，以及管理員個人的系統健康、重大異常及重大客訴告警，不新增群組告警。代班詢問公版使用明列的指定服務日期，包含不連續日期情境；詢問卡與群組日期表均列出實際使用的日期、月嫂姓名及欄位路徑／值。訊息頁與流程圖共用狀態分類；所有固定回覆及流程控制訊息只在「全部狀態」列出，不列為獨立「已啟用／已停用」，發送設定明示「由流程控制」且沒有獨立開關。案件群組預覽項目的名稱統一採「案件群組」。

案件群組由工會人員在群內輸入 `綁定訂單 案件編號 邀請網址`，三段以空白、全形空白或換行分隔；網址自身不可拆行。設定只保存，不寄邀請。之後同群只輸入 `發送邀請`，以保存網址及目前核銷／身分資格排入私人邀請，無再次確認。更新網址重輸完整設定指令，保留成員歷史。格式錯誤回覆原因與正確範例，不保存或寄送；發送前資格或網址有變則取消舊工作。完整文案與錯誤提示依規格 17「服務群組設定與邀請指令」。

通知事項頁提交既有操作成功後，重新讀取相關來源與寄送紀錄，避免共用客服事項或舊寄送狀態殘留；條件審核後仍保留原操作面板供接續選擇月嫂。失敗來源保留明確錯誤與重試入口，不假裝處理完成。

寄送紀錄按原公開來源分類：契約、身分審核、媒合及群組邀請歸「審核與協調」；帳務、排班、日期與完工歸「款項與日誌」；其他歸「客服與異常」。分類在伺服器查詢及分頁前套用，回傳該分類完整總數；未查詢的分類顯示「—」。服務當天、服務狀況回覆、完工通知與第二期款提醒／核銷均沿用既有公開類別，不新增業務狀態；未知來源仍拒絕。

系統通知對象可用性同時核對通知設定啟用、管理員目前啟用及其目前有效的 canonical Admin LINE 綁定與主檔一致；沒有符合上述條件的對象時，顯示「系統通知尚無可用對象」待辦。只讀檢查不修改對象設定，也不發送測試通知。

### 6.7 訂金繳費提醒與核銷成功通知

訂金正式核銷後，尚未綁定服務群組的正常未結案案件另列在工會 LINE 工作台「尚未建群」；
只提供建群說明及複製群內綁定指令，規則與零副作用契約見規格 17 的 Order group observation workspace。
此待辦不要求客戶已簽約；已付訂金不代表客戶已簽約，也不自動建立正式排班。

- 訂金分類只提供「已銷帳／未銷帳」兩種狀態篩選，預設未銷帳；依既有正式核銷投影判定，不從寄送狀態推算銷帳。篩選與分頁不改變該分類的全部待處理總數。已銷帳通知完成後依既有通知條件移出，不補列歷史核銷；同案其他尚未完成工作仍各自保留。
- 2026-10-29 人工裁決：未核銷訂金的繳費提醒，須客戶及所有月嫂均已簽約完成才列入清單及總數。以同案正式 `contract_completed` 事件且其契約識別等於 Orders 目前契約識別為準；單方簽署、寄送完成或只有 PDF 不構成資格。送出提醒前及 provider 前重新核對；不符資格的舊待寄提醒取消。各期款項仍可預先計算、保存及合法核銷；已核銷成功通知與客戶繳費資料查詢維持原契約。
- 人員待辦「訂金繳費與核銷通知」只讀既有訂金應收。符合上述簽約資格、已綁定 LINE 且金額、期限、
  虛擬帳號與銀行代碼完整時，人員點「發送訂金繳費提醒」即建立 committed delivery task。
  使用 current enabled Admin binding 與 `line.task.read`／`line.task.send`，不要求第二次確認。
- 提醒文案：`案件〈{case_no}〉訂金 NT${amount}，請於{due_date}前完成匯款。`
  「查看繳費資訊」開啟客戶 LIFF；「專人協助」直接建立或接續 Customer Service 需求，
  回覆 `已收到您的聯絡需求，請留下您的疑問。`，後續聊天室留言加入同一客服案件，不發群組通知。
- 訂金核銷後待收餘額為零屬正常狀態；已核銷通知及繳費狀態 Query 以同案 current 義務事件的原額與正式 settlement projection 核對，不將零餘額視為無訂金而漏列。未結清提醒仍讀目前待收餘額，查詢不改帳務。
- 正式訂金核銷提交帶 `line_deposit_notification=true` 的既有財務 outbox 事件後，worker 自動建立成功通知：
  `案件〈{case_no}〉訂金 NT${amount}已確認入帳，謝謝您。`；「查看繳費狀態」開啟同案 LIFF，
  顯示已入帳金額及銀行實際入帳日期。同一 settlement identity 僅建立一個工作；不補發歷史核銷。
- 客戶頁 `/line-deposit-payment` 由 gateway `target=deposit_payment&case_no=...` 進入；
  Query 只接受 server-verified LINE ID token，並核對客戶主檔與 current customer binding。
  不信任 URL 案號或 userId 作身分。未入帳時顯示金額、期限、銀行代碼及本案帳號，提供複製帳號；
  已入帳只顯示狀態、金額與入帳日，不再引導匯款。
- 案號不符合既有虛擬帳號規則且無唯一匯入帳號時，不生成替代帳號；資料未齊保留「繳費資料待確認」
  待辦且禁止寄提醒。銀行代碼由明確部署設定 `CLIENT_DEPOSIT_BANK_CODE` 提供（三碼）；未設定不猜銀行。
  既有實際匯入帳號仍依 Client Finance 規則優先，LINE 不另行推算。
- 未綁定客戶保留人員人工通知待辦，不假造寄送成功；worker 後續依同一核銷事件重查綁定。
  寄送前 fresh-read 財務來源及收件者綁定；已入帳的催繳、條件已更新、已取消或失效綁定的工作取消。
  未實際 provider 成功前只顯示已排入／處理中，不能標為已送達。

### 6.8 服務當天群組繳款提醒與月嫂服務狀況詢問

- 觸發：以台北時區正式 `actual_start_date` 當天為準，讀目前有效班表的當日工作月嫂及本案目前有效綁定原服務群組（`bound／inviting／active／attention`）。未確定正式日期、沒有當日工作班、無原群組或案件已取消／完成時不建立提醒，不改用客戶私訊。不要求工會再次確認；同一案件／日期不因重跑或已發送後付款變動重複通知。
- 群組卡片文案：`【服務開始提醒】
案件編號：{case_no}
今天是本案的服務開始日，祝服務順利！`；第一期尚欠大於零時加上 `第一期款尚待繳納：{amount} 元，請於今天完成繳款。若已匯款，請勿重複繳納，待工會核對入帳。`；結尾為 `{caregiver_names}，請問今天的服務是否順利？`。已結清／零應付省略繳款段落，仍詢問服務狀況。
- 按鈕為「服務正常」「需要協助」。server 以可信 webhook 的群組及使用者身分，重新核對原群組、正式開始日、有效 generation、當日工作班及 current bound staff 身分；客戶、工會人員、其他月嫂、其他群組、私訊或失效卡片不得代答。不把卡片中的案號、按鈕 token 或角色文字當授權。
- 「服務正常」記錄回覆並在原群組回覆 `已收到，祝您服務順利。`；「需要協助」沿 Customer Service 正式 writer 建立／接續工會服務進度待辦，記錄案件及日期，原群組回覆 `已收到您的協助需求，請留下遇到的狀況。`。不額外建立管理員私人或案件群組告警。人員查看原服務群組；不監聽、抓取群組的一般討論內容。
- 每位合資格月嫂對同一詢問／同一選項只記錄及回覆一次；重複 webhook 或不同 event ID 重按不重開待辦、不重複致謝。正常回覆後仍可提出協助需求。回覆、待辦、ack task 與 receipt 共用 webhook consumer 的 outer transaction，失敗完整回滾。
- LINE 來源與回覆沿既有 source event／receipt／committed delivery task 保存，不新增 Orders、Client Finance 或 Scheduling 狀態、不建立出勤或核銷事實。第一期款不是開工新增關卡；核銷維持既有正式帳務流程。
- provider 前重新核對日期、群組、班表及未繳金額；改期、換群、換班、付款改變的未寄快照取消，當天掃描可建立新快照；已嘗試投遞者不因條件變動自動另建通知。舊服務前三日私訊來源／模板／待寄工作停止使用，不補發歷史提醒。第二期款依下節到期當天原群組流程。

### 6.9 第二期款到期群組提醒與核銷成功通知

- 先核對 Client Finance 正式第二期應付：付款條款有第二期到期日，且有唯一有效、原應付金額大於零的第二期應收。金額為零、無第二期或資料不足時，不產生第二期提醒來源、寄送工作或核銷成功通知；不把「已繳清」誤認成「不需第二期」。不新增人工計算、付款義務或案件狀態。
- 到期日仍由第一期到期日加 15 個曆日計算。台北時區到期當天、仍有未繳金額且案件未取消，才建立原服務群組提醒；不在前三日或客戶私訊催款。文案為 `案件 {case_no} 第二期款尚待繳納 {amount} 元，請於今天完成繳款。若已匯款，請勿重複繳納，待工會核對入帳。`，純文字無按鈕。
- 發送前重新讀取案件、第二期需求、期限、未繳金額及目前有效原群組（bound／inviting／active／attention）。已結清、取消、不需第二期、日期不為今天或來源失效時取消；金額／日期／群組變更取消舊快照，由當天新條件重新投影。新到期日尚未到則等待；同日已成功／已嘗試寄送不因重掃另建另一筆提醒，既有同工作 retry 維持原投遞契約。
- Finance 正式第二期核銷在原 outer UoW 的既有 `projection_refresh` payload 保存 `line_second_payment_notification=true`、settlement identity、選定第二期 obligation identities 與本次正式分配金額。交易 rollback 無通知；只有新標記事件可觸發，不補發歷史核銷，不改 Finance outbox status、不增加 enum／schema。
- 提交後才投影成功通知：`案件 {case_no} 第二期款 {amount} 元已確認入帳，謝謝。`，純文字無按鈕，發原服務群組。送前確認本案仍需第二期、原核銷分配及正式收款仍有效、無撤銷且第二期已結清；本次核銷 identity 去重。失效或撤銷取消通知；未核銷或僅有截圖／留言不通知。
- 缺少有效原群組，沿既有 LINE-006 `recipient_unavailable` 工會待辦留存；不猜群組、不改用私人通知。群組設定就緒時可重新按目前資料投影；一般群組談話不監聽。未實際 provider 成功不得宣稱已送達。
- 正常精確核銷不產生財務 `anomaly_review_required`；真正金額異常依既有拒絕／明示超收處理保留。提醒及入帳通知不變更 Orders／排班／出勤，也不以第二期款新增停工或完工關卡。

### 6.10 各期繳款逾期待辦與人工提醒

- 訂金、第一期、第二期均須符合 §6.7 的雙方簽約完成資格，才按各自正式到期日及同一期未核銷餘額，於台灣日期到期日隔天起且餘額為正列入工會內部待辦；不等待服務完工。未完成雙方簽約、不需第二期、金額零、未到期、已結清、已取消義務及歷史案件不列入清單或總數。工會應退給客戶的退款不屬於本提醒。保留原計算金額與期限，不從簽約日重新起算到期日。
- 「帳務作業 → 收款 → 逾期提醒」為主要入口，沿用原 LINE reminder Query／Send；原 LINE 繳款逾期深連結導向此工作區，不另加帳務頂層分頁。呈現各筆案件、期別、到期日、逾期天數、餘額、提醒對象與上次提醒／寄送結果。同案多期逾期分列，不跨期合計；零筆明示沒有符合提醒資格的逾期款，不代表全部欠款歸零。核對銀行入款保留同案脈絡；載入或重新整理只查詢；通知事項頁重用同一待辦與發送入口，沒有全域彈窗或另一套通知狀態。
- 工會人員自行決定是否點「發送提醒」；一次點擊直接建立既有 durable delivery task，不設再次確認視窗，不自動定期重發。同次操作重播沿用原工作；寄送未完成時不建立第二筆。收到結果不明時保留原操作供確認，不顯示成功或另建工作。
- 訂金提醒只寄本案客戶已綁定的私人聊天室；第一、二期只寄本案有效案件群組。缺少客戶綁定或群組時保留待辦、禁用發送並顯示原因；不得改送其他對象。既有到期當天第一、二期群組通知及訂金 LIFF 提醒保持原流程，不由逾期提醒重播。
- 文案為純文字、無按鈕：「本案{期別}尚有 NT$ {該期未核銷餘額} 未確認入帳，請協助確認繳款，謝謝。」期別僅為「訂金」「第一期款」「第二期款」，不用全案金額或未來期款；銀行資料未匯入不能宣稱客戶未繳款。
- 點擊時 fresh-read 雙方簽約完成資格、同案、同一義務、期別、projection version、event、到期日及餘額；資格不符或任一款項條件改變回 typed conflict，重查後由人員重新決定。只依當期真實餘額形成工作，不接受前端指定收件人。已提交工作在 provider 前再次核對雙方簽約完成資格、該筆款項及收件綁定／群組版本；資格不符、結清、不再逾期或來源變更時取消舊工作，不發錯期別、舊金額或舊收件對象。
- 發送後仍列待辦與提醒紀錄，直到該期正式核銷餘額歸零才不再列入；尚未寄出的提醒在 delivery gate 取消。提醒不建立收款、付款義務或財務異常，不修改 Finance／Orders／Scheduling，亦不代表退款或客戶端結算完成。沿用既有 LINE task、audit 與 worker，無新資料表或財務狀態。
- 驗收：訂金逾期而第一二期未到期只列訂金；第一期結清只保留真正逾期第二期；同案多期各自列示／核銷；到期日當天不列、台灣隔天列；零第二期不列；缺綁定／群組保留；Query 零寫入；錯期別、金額／日期／版本變更被拒絕；重播不重寄；核銷後待辦消失且 pending 工作不越過假 provider；工會角色可操作，未授權拒絕；React 入口與實際畫面可查詢、發送及核對銀行入款。

### 工會手機提醒待辦

已驗證且具有對應能力的工會人員，可在 LINE 手機待辦查看「繳款逾期」與「日誌連續缺漏」，含 owner 完整總數、分頁、重新整理與讀取失敗狀態。手機薄轉接既有提醒 Query／Send，不建立第二套日期、餘額、連續缺漏或寄送判斷。各期逾期隔天獨立列入，訂金寄客戶私人聊天室、第一／二期寄案件群組；日誌列案件群組與連續缺漏天數，超過 3 日才列入。人員點擊才建立寄送工作，發送前仍沿既有 owner 複核。未明結果保留同一操作識別查詢，不以重新整理重複寄送。手機不交換一般後台 Session，也不發布選單。

## 7. 第一版驗收

1. 服務說明回覆六分類且 exact replay 不重複建立 task。
2. 客服需求可建立、列表、查看、更新、回覆及完成。
3. 客服回覆透過 canonical delivery worker 發送。
4. 偽造 URL userId 無法讀取客戶、月嫂訂單或班表。
5. 月嫂只能讀取自己的有效 assignment 案件與班表。
6. merge Rich Menu 圖面／文案可由 wen publication 流程發布並 fan-out。
7. 客戶前導頁保留 flow ID，兩條路徑都不退回 legacy gateway。

## 2026-08-21 M2／M4 routing and escalation amendment

- 明確呼叫專員優先於自助路由，直接受理而不再確認；一般提及客服、錯誤或無法解決不自動開單。聊天室不啟動 AI／Knowledge 問答，既有 exact protected identity alias 仍由身分流程處理。
- 聊天室 AI 停用；一般留言回自助導覽，明確呼叫專員才建立或沿用客服案件。獨立 LIFF 問答沿核准 Knowledge 查詢；無答案回主題選單，系統失敗如實顯示，不自動開單。active hold 的留言只加入原客服案件。
- Customer Service 是 HIGH escalation／ticket／hold／人工處理的 owner；Anomaly 僅提供 source projection。escalation 透過 typed `TicketReferral`／escalation port，不競寫 M2 `service_help` 或 M4 `runtime_alert_application`；Scheduling 不在 escalation transaction。
- production composition必須注入automation hold／escalation gateway；active hold會在任何deterministic reply、ticket或
  delivery intent前fail closed。human escalation採`create → claim → handling → resolve`，每步驗證version、
  idempotency與typed receipt，resolve後才解除hold。
- `reply_provider` direct path已由durable delivery task取代；Service Help只enqueue，不在webhook transaction呼叫
  provider。LINE provider仍只能由已提交task的worker執行；本規格不授權AI provider、deployment或新的外部副作用。
- 2026-09-11 人工授權：一對一文字事件產生的 Knowledge answer／unsupported 最終回覆，已提交的
  delivery task在原 webhook `replyToken` 可用期限內必須優先使用不計月額度的 Reply API；只有尚未嘗試
  Reply且token不存在或已逾安全期限，或provider明確回覆 rate limit／server error 且確認本次未接受時，才可
  改用既有Push。Invalid／used token、Reply timeout與transport unavailable都可能位於「已送出但尚未記錄」
  crash window，禁止立即Push造成重複答案；所有其他主動、排程及人工客服通知維持Push。
- runtime／LINE管理畫面的audit清單只能使用closed bounded typed view；具owner permission的普通業務值
  不遮罩，但raw details、token、secret、credential、storage locator或額外欄位一律在API client boundary
  fail closed，不得穿透Streamlit／React render。

## 2026-08-26 current execution authorization amendment

- 人工已授權 current LINE lanes 的本機實作、`lu_test_*` 必要 schema gates、verified-token Chrome E2E、
  controlled NAS media flow、AI feedback contract-first 工作與 provider sandbox qualification。
- 先前「provider 尚未授權／先不真實 push」只就 current sandbox lane 由本 amendment supersede；執行前仍須
  回讀 exact environment、target、recipient、quota 與 worker isolation，只送最小受控案例並保存 provider receipt。
- 這項授權不允許猜測 production recipient、`union_db`、部署 target 或 entry switch，也不取消各 owner 的
  Preview／Apply、fresh-lock、idempotency、receipt、readback、rollback 與 manual fallback。


### 現行流程訊息的唯讀公版預覽補充

「通知與發送」除可維護模板外，列入現行固定流程產生的訂金繳費提醒／入帳卡及協助受理、服務群組私人邀請卡（操作人員的設定結果及格式／資格錯誤提示不列文案編輯）、月嫂願意承接受理與客戶推薦回覆、請假決策與失效／不可更改回覆、服務進度／登記與身分入口，；管理員系統健康告警於 2026-10-30 退役。一般無意願與客戶條件回答只有 LIFF 頁面結果，不虛構聊天室通知。
預覽共用實際流程的純文案／卡片組裝函式；所有動態值明列為公版欄位，不查真實資格、不簽發憑證、不建立任務或發送。資料庫中的有效規則／模板移除與歷史紀錄保存分開驗證。


## 2026-10-30 管理員 LIFF 系統狀態與通知退役

管理員主動於既有 `line-mobile-admin?target=staff_review` 待辦工作台最上方查看系統狀態卡，預設收合，可展開查看 LINE 發送服務、待發／失敗數、各服務與最近檢查時間，並手動重新整理。狀態讀取獨立於待辦清單；載入、無資料、過期、權限不足或讀取失敗不可呈現為正常，不輪詢或自動 Push。不新增 LIFF target 或獨立通知對象頁，其他管理員 LIFF surfaces 維持原用途。

取消重大客訴與其他管理員自動告警，仍保留客服工單、automation hold、事件、冪等及原處理／結案流程；不建立管理員告警 outbox。歷史待發管理員告警消化／取消但不發送，不回填虛構投遞成功或失敗。詳細身份、唯讀摘要與歷史 task 退役契約依規格 17 的 2026-10-30 裁決。


## 2026-10-30 群組操作人員提示固定化與 Reply-only

本次人工核准的有界範圍為 18 項群組操作提示：設定完成、邀請排入，以及群組設定／操作受阻和指令格式錯誤。操作人員提示使用原純函式／封閉錯誤對照的固定中文，移除通知與發送的目錄、公版及文案編輯入口，不讀取既有 `LINE-COPY-group-bound`、`LINE-COPY-group-invitations-queued`、`group-error-*` 或 `group-format-*` 設定。舊設定及版本歷史保留，不作資料庫刪改。

新提示沿原 outer UoW／durable task 入列，使用原事件、原群組的 `line_webhook_reply` source；Reply token 缺少、過期、已用、發送失敗或重試時不補 Push，不盲目重送。設定結果及邀請結果的 idempotency key、群組綁定、保存網址、audience fresh check 與投遞任務保持原 owner。客戶及月嫂收到的私人邀請卡屬業務通知，維持原 Push 與文案維護；服務當天／資料修改／訂單修改等業務受理結果也不因此退役。

管理員系統／重大客訴告警依前節改在 LIFF 查看，通知與發送不顯示且舊文案 Query／PUT 拒絕重新維護；不改寫歷史資料。驗收包含三類操作結果均 Reply-only、舊文案無法影響提示、缺少／失敗 Reply 零 Push、私人邀請仍發原對象、LIFF 狀態需有效管理員身分及 monitor 權限、讀取失敗不顯示為正常。此工作不包含 provider 真實發送、部署或 migration。

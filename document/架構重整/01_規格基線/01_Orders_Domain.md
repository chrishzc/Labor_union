# Orders Domain

> 2026-10-29 帳務參數裁決：規格04 §0 PRICE-02／03規範案件初建即綁定政策及個案人工覆寫。後續補件、日期更正與重排保留適用版本；不把服務日期當自動選價日期。原始條款／排班ownership不移交參數頁。\n


## 1. Domain 責任

Orders 擁有：

- `case_no` 訂單識別；
- Order Terms：`start_date`、`service_days`、`service_hours_per_day`、`requires_cooking`、`floor_fee`、統一服務時段三欄；
- `actual_start_date` 的首次確認與更正；無正式 Scheduling 時以 Orders aggregate
  current root 保存，已有正式安排或延遲訂金重新確認時才使用對應正式事件；
- 會形成 Scheduling／Finance／Payroll／lifecycle 正式影響的 Terms change，以及 cancellation、controlled reopen、lifecycle transition 等不可變事件；
- aggregate version、命令冪等 receipt；
- `status`、`end_date`、`actual_end_date` 與服務資料鎖的目前投影。

Orders 不擁有：

- `client_name`；
- 訂金到期日、訂金服務天數、收款、退款及其他 Client Finance 事實；
- assignments、正式服務日、檔期鎖及 `actual_hours`；
- 月嫂薪資與應付款；
- Alert 的 open／claimed／resolved；

## 2. Orders SSOT

| 資料 | 類型 | 唯一權威 |
|---|---|---|
| Order Terms | root_fact | Orders aggregate；有正式跨 owner／lifecycle 影響的變更另有最新有效 Terms event |
| 下廚需求 | root_fact | Case Import 明確正規化結果或後續 Orders Terms event；不得於 Matching 重新解析問卷 |
| 每日服務時間 | root_fact | `service_start_time`、`service_end_time`、`service_end_day_offset` 三欄完整 tuple |
| actual start | root_fact | 無正式 Scheduling 時為 Orders aggregate current root；已有正式安排的更正或延遲訂金重新確認為 Actual Start event |
| planned end | derived_projection | 凍結的 planned start、目前 Terms 與規劃服務日 |
| actual end | derived_projection | 有效 assignment-owned 正式服務日最大日期 |
| lifecycle status | derived_projection | Lifecycle evaluator |
| cancellation | immutable_event | Cancellation event |
| controlled reopen | immutable_event | Reopen event；不刪除 cancellation history |
| service-data lock | 不可逆 derived fact | completed 且客戶帳務義務結清 predicate 首次成立 |
| lifecycle version | concurrency projection | 每個成功非 replay aggregate command 加一 |
| `orders.staff_id` | compatibility_projection | 禁止作人力、排班或薪資 fallback |
| `orders.deposit_date` | compatibility_projection | Client Finance 的 deposit due date 才是正式權威 |

## 3. Subsystems

### 3.1 Order Query

責任：

- 組合 Orders roots、目前投影及其他 Domain 的 ViewModel。
- 分開回傳 `domain_blockers` 與 `alerts`。

禁止：

- 修資料、觸發狀態機、持久化重算或以 fallback 補造根事實。

### 3.1.1 Order Operational Timeline／11 步 SOP

- 七階段與 11 步 SOP 都是後端唯讀 typed projection；React 只能依 server status 呈現，
  不得由 `orders.status`、日期字串或畫面所在欄位重算完成、進行中或目前階段。
- 每一步固定回 `not_started | in_progress | blocked | completed | unavailable`。`completed`
  必須有完成標記，`in_progress` 必須有明確的目前執行強調，`blocked` 與 `unavailable` 必須
  分開顯示；不得把讀取失敗或缺根事實偽裝為尚未完成。
- 媒合聯繫、月嫂意願、客戶履歷推薦、月嫂簽回、訂金核銷、客戶簽回各讀取自己的
  immutable owner fact；不得用同一 Contract Completion event 代替月嫂與客戶兩種簽回。
- Step 2「媒合月嫂候選人加入意願池」只依 Assignments／Scheduling 的候選池／聯繫根事實完成；
  不得等待客戶接受正式方案。七階段的 Stage 2 仍依其完整媒合狀態投影，兩者不可互相覆寫。
- 正式日期完成證據採規格 02 SSTART 的月嫂接受／工會代班日期保存及正式回讀，不讀舊日期表按鈕確認。正常流程不列人工日期核准待辦；未來開工日到達時由 canonical lifecycle command 評估更新，不由 Query 寫狀態。
- 請假順延依規格 20 §5.3：月嫂提交雙方明確協議後，Scheduling 在同一交易執行 canonical Preview／Apply，Orders owner 依完整有效班表保存最早服務日及服務結束日，Finance 同步相關期限。沒有額外人工確認；已履約服務日保留，不能藉順延重設既往開工事實。代班或排程衝突才由工會記錄後續協議／安排人選。
- 第 9 步正式日期已確認只完成日期確認，不得自行把目前步驟推進到第 10 步；只有 persisted
  Orders lifecycle 已為 `服務中` 時，第 10 步「正式排班與服務履約」才能成為 current step。
  進入後的履約狀態只依 effective assignment-owned official service dates、完整 service-time tuple 與
  `BusinessClock` 投影 `not_started／in_progress／completed`；不得依可過期的 assignment status count。
- 正式服務完成後，current stage 必須前進至完工結案與請款，即使其中某個 settlement owner
  projection 仍為 `unavailable`；不得繼續把案件留在「正式服務履約／進行中」。
- Staff Payables 結清只讀 `staff_payable_projections` 的 current status／version／updated time；
  `staff_obligations` 是不可變義務來源，原始 `open` 不得被 Orders 誤判為付款仍未完成。

#### 作業步驟回退與 aggregate version（2026-08-27 人工裁決）

- append-only lineage 與 current aggregate version 不倒退，不代表 SOP step ordinal 只能往前。
  typed owner event 可使 current operational step 回到較早步驟，但新 event／projection version
  必須大於舊版，既有歷史 event不得刪除、改寫或改小 version。
- 服務前已配對月嫂因車禍、健康或其他正式不可服務事實必須整案換人時，由
  Scheduling owner 的 replacement Query／Preview／Apply 追加具名 event，並以 immutable
  successor lineage 使舊 caregiver-bound matching plan、recipient confirmation、commitment、簽回與
  assignment 轉為 superseded／不再滿足 current round。不得原地改 staff id。
- 整案重新媒合默認從 Step 2 `matching_pool` 開始；若 current owner readback 證明同一
  replacement round 已有可沿用的合法候選池，可由 server 計算為 Step 3／4。
  `resume_step` 必須是最早失效 owner root 的後端投影，不是人員任意輸入 status。
- 上述整案回到媒合只適用於 owner readback 證明尚未有任何 assignment-owned actual
  service fact。只要已提供服務，不得回 Step 2 也不新建另一套整案換人；必須使用
  Scheduling 既有 leave／substitution Query／Preview／Apply，只重建受影響日期，並沿用
  current Payroll impact／obligation lineage 計算原月嫂與代班月嫂薪資。
- 回退後 Step 1 與無關 caregiver identity 的合法 Orders／Client Finance 根事實保留；
  定金不因換人自動退款或重建。舊月嫂簽回、客戶對特定月嫂的承諾、
  日期確認與正式排班依 binding 失效範圍逐項重做。若日期／金額／條款未變，
  Finance 不得伪造新義務；若改變，仍走各 owner 正式 impact／adjustment 契約。

### 3.1.2 未完成訂單代辦看板（2026-08-25 人工裁決）

- 代辦看板的候選集合固定為所有尚未完成的訂單；canonical lifecycle 已為「訂單完成」的案件不得顯示。
- 「所有」是 server-authoritative 完整集合，不是第一頁或任意上限。若 public Query 採 cursor／continuation，
  React 必須自動續讀至 terminal page，合併時依 order identity 去重並維持 deterministic ordering；不得要求
  操作者按「下一頁」才發現其他待辦。
- 任一 continuation 失敗、timeout、abort、cursor 重複或 schema mismatch 時，頁面不得把 partial rows
  宣稱為完整看板；必須顯示載入未完成與 retry，並取消 stale request。
- 本看板是唯讀 Query projection，不得為了排除完成訂單而修改 Orders status、隱藏 blocked／unavailable
  案件或在瀏覽器重算 lifecycle。

#### 3.1.2.1 Beta 看板依作業狀態分類（2026-09-08 人工裁決）

2026-10-15 案件工作台 UI 裁決：辦理事項保留前五項，移除獨立「客戶收款與月嫂結算」步驟及重複的舊訂金放行表單。訂金關卡沿服務安排的既有入口處理；正式訂金／客戶結算／月嫂結算 current stage 導向第五項，不因移除 UI 改寫階段、結清或 lifecycle。正式 lifecycle 已服務完成時，第五項呈現「服務完工」，顯示 Orders 實際服務期間、完工事件時間、服務月嫂及兩端正式結算子投影；未知狀態不得視為結清。提供帶入同案的「查看本案帳務」及帳務中心返回案件入口。歷史服務完成案件的帳務完成 Preview／Apply 移至帳務中心所選案件下，沿用原 owner 與 fresh readback。

本節只調整 Beta 看板的唯讀查詢與 presentation，覆蓋以 normal／historical 作為主要頁籤的舊做法；不改 lifecycle evaluator、資料來源、歷史採納或任一 mutation owner。

- **WB-STATE-01**：主要分類為「進行中訂單／完成訂單／取消訂單」。Query 依已持久化的 canonical lifecycle 分組，不得在 React 依中文 status、日期或是否由歷史匯入重新判斷。進行中包含 `待補件`、`洽談中`、`訂單成立`、`服務中`、`歷史訂單－未服務`、`歷史訂單－服務中`；完成包含 `訂單完成`、`歷史訂單－服務完成`、`歷史訂單－帳務完成`；取消包含 `訂單取消`。三集合互斥且涵蓋現行 lifecycle enum。
- **WB-STATE-02**：進行中提供全部案件與十三階段篩選。歷史案件有正式 `historical_current_owner_stage_code` 時依該 current owner stage 納入階段篩選／counts；無 current owner stage 時仍保留在全部案件中，不得把 immutable historical baseline 當成真實完成事件。
- **WB-STATE-03**：正常案件的服務完工只完成第 11 步；客戶或月嫂結算仍未完成時，案件留在進行中並以第 12／13 步為目前待辦。兩端都完成後才進入完成清單，且完成及取消清單與案件抽屜不呈現十三步驟導覽／進度。完成不能冒充補助已結清；仍顯示既有正式結算狀態、提醒與查閱入口。取消保留既有紀錄與具資格驗證的受控重開入口。來源與歷史 evidence 留在案件詳情，不能再形成主要工作分類。
- **WB-STATE-04**：切換分類不帶入另一分類的 stage／substatus 篩選。沿用本節的完整 continuation、stale request 取消與 partial failure 規則；不得把前 200 筆當作完整結果。所有分類、counts 與 pagination 共用 server predicate。
- **WB-STATE-05**：既有 `/api/orders/core-stage-timelines` 增加可選 `workbench_scope=in_progress|completed|cancelled`。未指定時維持既有 branch／historical Query 契約，供歷史詳情與既有 consumers 使用。新的工作分類不與 legacy branch／historical facet 合併使用；完成及取消分類不得帶 stage／substatus。此 additive Query 不增加寫入、migration、provider effect 或改變生命週期事實。

#### 3.1.2.2 第 6–8 核心階段外部簽署順序（2026-09-09 人工裁決；2026-09-15 推薦完成條件補充）

十三核心階段總數維持不變；第 6–8 階段依實際外部平台流程固定為：

客戶決策已接受、matching plan 已成為 `accepted`，或該方案已有 Scheduling-owned 的有效等待訂金鎖時，第 5 階段「推薦客戶與確認」即完成並進入「契約與文件」；履歷是否由系統記錄成功寄送只保留為 delivery evidence，不得使已接受或已鎖檔案件停留在第 5 階段。

6. `external_signing_dispatch`：系統建立目前 accepted plan 的契約文件，由工會人員明確確認已送交外部簽署平台。
7. `external_signing_completion`：客戶與所有月嫂在外部平台完成簽署，以本系統驗收並保存的最終簽署 PDF 為完成根事實。
8. `deposit_settlement`：最終簽署 PDF 完成後才進入客戶定金核銷；未結清保持 blocked，結清才完成。

月嫂或客戶的個別完成回報可留作稽核 evidence，但缺少個別回報不得阻擋最終 PDF 的 Preview／Apply，也不得使第 7 階段永久卡住。外部平台交接必須是明確保存的系統事實；PDF 下載、LINE delivery 或 UI 顯示均不得冒充已送交。第 9–13 階段的 code、順序與 owner 不變。

驗收：混合一般與歷史案件時，每件只出現在正確分類；歷史未服務案件不因沒有正式步驟而消失；完成／取消頁面及抽屜沒有十三步驟；已完工但未結清案件仍呈現真實結算提醒；分類切換不保留無效篩選；跨頁集合完整、續讀失敗不顯示假完整結果；舊 branch Query 與歷史 evidence 查閱保持可用。

來源：2026-09-08 使用者要求以進行中／完成／取消取代正常／歷史分類並移除完成／取消的十三步驟；完成定義沿用本文件 §3.3，歷史狀態沿用 Historical Orders 已有正式 lifecycle。分類屬 presentation Query contract，不構成新 business state。

### 3.1.3 訂單管理未完成清單（2026-08-25 人工裁決）

- 訂單管理主清單採與代辦看板相同的候選集合、完整 continuation、identity 去重、deterministic ordering
  與 partial-failure 規則：同頁顯示所有未完成訂單，完成訂單固定排除。
- 分頁 cursor 可作 transport 細節，但不得成為操作者工作步驟；React 必須自動續讀至 terminal page，
  不顯示「下一頁」按鈕，也不得只因預設 page size 而漏掉未完成案件。

驗收狀態（2026-08-25）：`completed`。代辦看板與訂單管理已共用 server-owned `unfinished`
lifecycle scope，自動讀完 continuation；Chrome 回讀兩頁皆為 94 筆、完成訂單 0 筆且無人工下一頁入口。
React adapter 不再自行解讀中文狀態縮減集合；focused tests 與 production build 已通過。
- 代辦看板與訂單管理可採不同 presentation，但必須消費同一 server lifecycle predicate；兩頁不得各自
  以中文 status、日期、card lane 或 local cache 判斷是否完成。

### 3.1.4 非市民案件沿用訂單推進（2026-10-29 人工確認）

狀態：`implemented / repository-local-verified`。使用者已於 2026-10-29 核准七階段實作與逐階段驗收；執行範圍及實際證據見 [非市民案件實作工作包](../非市民案件實作工作包.md)。此狀態不代表已部署、使用正式資料或完成外部 provider 驗收。

使用者已逐項確認下列流程。沿用是沿用各步驟既有 owner、正式條件、事件、操作及回讀，不代表畫面切換即可推進，也不新增非市民專用 lifecycle。

| 順序 | 步驟 | 非市民處理 |
|---|---|---|
| 1 | 進件與資料完整性驗證 | LIFF 合併表單依 `17` 驗證，工會核准才正式建案 |
| 2 | 建立候選月嫂池 | 沿用候選篩選及工會選人方式 |
| 3 | 詢問月嫂接案意願 | 沿用 |
| 4 | 等待與處理月嫂意願回覆 | 沿用 |
| 5 | 推薦月嫂給客戶確認 | 沿用 |
| 6 | 建立契約並送交外部簽署平台 | 操作沿用；適用非市民政策及自費條文 |
| 7 | 雙方簽署完成與文件回收 | 沿用現行分開簽回及完成條件 |
| 8 | 客戶定金繳款與核銷 | 按 5 天服務費收取；收款及核銷沿用 |
| 9 | 服務日期確認與排班 | 沿用 |
| 10 | 服務開始與履約 | 實際開工、服務紀錄及服務中異動沿用 |
| 11 | 完工／服務完成確認 | 沿用 |
| 12 | 客戶端結算 | 結清、補收及退款沿用 |
| 13 | 月嫂端結算 | 報酬結算及付款沿用 |

費率、定金及剩餘服務費公式由 `04` §0.1 擁有；媒合、排班及月嫂給付依各既有 owner 契約。看板／工作台須承接非市民正式案件；僅案件統計依 `15` §15.3 分流，不得把統計排除條件套在案件工作清單。後續 UI、共用案件識別及驗收影響見 `17` §5.1.2；本次未修改實作。

### 3.2 Terms Preview／Apply

Terms 的唯讀 Query 與 Preview／Apply 的異動資格檢查分離。已有客戶應付義務但尚未建立執行 assignment 是正式簽約流程的合法狀態，不得因此拒絕 Query；Query 回傳已保存條款、各 owner 的實際版本、確認服務日期及目前指派。服務資料鎖仍限制編輯而不限制查閱；Preview／Apply 保留下游完整性與版本檢查。此合法狀態下修改預計開始日、服務天數、每日時數或樓層費，須讀取 current Finance facts，透過 owner 重算已存在期款，並在同一 Apply 同步付款條款與 immutable event；不得僅因已有客戶期款拒絕此次補正，也不得提前建立尚未存在的期款。

Preview 輸入接受 Terms 根事實意圖。依 Issue #326 的本機修復授權，尚未開始服務且已有正式日期／指派的
合約天數修改，可在同一 Terms Preview／Apply 附上由既有 server 精算得到的完整
`replacement_service_dates`；已有指派時另由操作者明示每個既有 `assignment_id` 的
`replacement_allocations.service_days`。只重用既有人員與順序，不猜測分配或新增服務量來源。
日期須按同一新合約天數驗證唯一、排序及可選期間，分配總量必須完全守恆；缺漏即拒絕。
已開始服務的完整日期／天數重排依 2026-09-19 人工裁決維持拒絕，待另定保留已履行歷史的規則；
其他原有合法條款異動不受此限制。輸出：

- before／after；
- assignment 與 schedule 重建候選；
- planned／actual end、hours、樓層費，以及本次實際受影響的兩端未核銷投影差異；
- blockers、aggregate version、fingerprint，以及 server 衍生的 `requires_formal_apply`；
- 排班 candidate 與 current effective assignments 的日期／人員形狀是否真的不同。

Apply：

1. 驗證 actor、expected version，以及 request 回傳的 `requires_formal_apply` 與 fresh Preview 一致；不得由前端自行降級。
2. 鎖定並讀取 fresh Orders、Scheduling，以及本次 candidate 實際需要的 Finance／Payroll facts；
   未建立正式 assignment 且沒有既有下游義務時，只在預計開始日、服務天數、每日時數或樓層費異動且
   已有 Finance root 時讀取該 owner 的付款條款計算 facts；日期異動經同一 Apply 同步付款條款與事件，
   不提前建立訂金或期款應收；建立時點依第 `21` 份正式規格的所有月嫂簽約完成與客戶簽約完成關卡。其餘修改不讀取完整帳務、費率或政策，也不要求或偽造其版本；此分支不新增 Payroll 依賴。
3. 以相同 candidate builder 重建 Preview。
4. 驗證 fingerprint。
5. 若變更不形成 Scheduling、confirmed service dates、Finance、Payroll 或 lifecycle 正式影響，走普通保存：只更新 Orders Terms 與 aggregate version，回傳當次 HTTP result；不要求 reason／idempotency key，不建立 command claim、Terms／lifecycle event、audit／outbox、snapshot／history 或永久 receipt，也不呼叫其他 owner writer。
6. 若 `requires_formal_apply=true`，才要求 reason 與 idempotency key、追加 Terms event、按實際影響委派 Finance／Payroll、重評 lifecycle，並保存 audit／outbox／永久 receipt。只有 assignment identity／人員／日期／區間真的改變時才委派 Scheduling replacement；單純費用、每日時數、下廚需求等不改變排班形狀的正式異動沿用 current generation 與真實 assignment identity，不增加 Scheduling version、generation、rebuild event、通知失效 outbox 或 Scheduling receipt。
   此時 Terms receipt 的 `scheduling_command_receipt_id` 為 `NULL`，但仍保存 current scheduling version／generation；不得建立空 generation 或虛構 Scheduling receipt 補舊格式。
7. 兩種分支皆由同一 outer Unit of Work 單一 commit；普通保存若 transport 結果不明，client 必須重新 Query 比對 current Orders version／Terms，不得以同一或新 key 盲目重播。

每日服務時間 tuple 契約：

- `service_start_time`、`service_end_time`、`service_end_day_offset` 必須全空或全有；既有全空
  tuple 未被本次修改時，可隨預定開始日等獨立欄位原樣保存，不得猜填或重算；使用者實際
  修改服務時段時仍必須一次提供完整 tuple。新匯入訂單進入契約完成、waiting-deposit lock
  或訂金核銷前必須全有。
- `service_end_day_offset` 只允許 `0 | 1`，必須由契約明確提供；不得依結束時間小於開始
  時間自行猜測跨日。
- legacy 三欄全空可載入並保留，且不阻擋無關 Terms 欄位修改；仍阻擋契約完成、收訂金、
  進入服務與自動完成，不得以預設上下班時間補值。
- legacy 案件可先建立空的 Client Finance／Payroll account、付款政策與 Scheduling
  aggregate，讓正式 Terms Preview／Apply 得以補登時段；此架構初始化本身不建立訂金
  或其他帳務義務，因此不得把它誤判為簽約或收款。
- Terms Apply 改變任一時間欄時，與其他 Terms 一樣重建 Scheduling candidate、完成時刻、
  未核銷帳務／薪資日期與 lifecycle impact；服務資料鎖形成後不得修改。

下廚需求契約：

- HCM `服務方式` 是 Client-owned `clients.service_type`，不是 Orders term；Orders 不新增
  `service_type`。Orders `end_date` 仍依正式 terms／lifecycle root facts 衍生，Client／Case Import
  修正不得直接寫入或以服務方式猜測。
- `requires_cooking` 是可為 unknown 的 Orders root；HCM 獨立匯入時若尚未唯一綁定 Client
  BeClass，固定保存 `NULL`，不得預設為否，也不得因此阻擋 Client／Order 建立；
- HCM 與 Client BeClass 唯一配對後，Case Import reconciliation 才可從明確 yes／no source
  經 typed Orders command 補入 `requires_cooking`；問卷空白、矛盾或自由文字無法唯一判定時保留
  `case_import_cooking_requirement_ambiguous` review，但不得回滾或刪除已匯入的 HCM roots；
- 此一唯一來源補正只改料理條款；即使歷史 root 已有 `actual_start_date`、但尚無正式 Scheduling
  segment，仍可補入。不得藉此變更服務日期、時段、工時、費用或其他服務形狀；服務資料鎖仍為硬性 blocker；
- 原始 `survey_details` 保留為來源 evidence，但 Matching 只讀 Orders root；
- 服務資料鎖形成後不得修改。

### 歷史訂單待確認與警示投影（2026-08-14，已人工確認）

2026-08-28 人工裁決將歷史訂單 canonical workbook 固定為六欄：`client_name`、`case_no`、
`start_date`、`end_date`、`status`、`staff_name`（標準中文標頭為「客戶姓名、案件編號、開始日期、
結束日期、狀態、月嫂姓名」）。第七欄起包含「月嫂姓名2」不採納，不得建立第二月嫂
pairing evidence或 assignment candidate；原檔 bytes 仍參與 content digest。前六欄的單一月嫂可使用訂單開始／
結束日期作為其服務區間。

歷史訂單採納列若已唯一匹配既有 Order、但 status、月嫂或其他來源欄位仍有 issue，安全可採納欄位
照既有規則保存，同時建立 immutable review evidence；不因 review 回滾同列合法 status／日期或配對
evidence。Orders outbox 將 review 投影為 `HISTORICAL-ORDER-001`，identity 為 review identity，僅顯示
遮罩案件識別與 issue codes。案號空白、找不到或對到多筆 Order 的列固定不寫 Orders、review、outbox 或 anomaly；
案號唯一且 `client_name` 非空時，`client_name` 僅為來源 evidence。即使姓名包含歷史次序尾碼（如 `-2`、`-3`）、
多餘空白或舊拼寫而與 HCM 不同，仍採納該唯一案號的列，並保存 `historical_client_name_mismatch` review evidence；
姓名空白固定捨棄。

### 歷史 review 更正來源重新匯入（2026-08-26，已人工確認）

`HISTORICAL-ORDER-001` 不得因只能查看或追蹤而永久懸置。Orders 必須提供以單一 immutable
`review_identity` 為根的人工 remediation；Anomalies 只可組合受控入口，不能直接修改 Orders root、
review 或 alert status。首版只接受一份僅含該 review 對應列的更正 `.xlsx`，不得接受任意
`corrected_fields` 或以多列檔案猜測對應關係。

1. Context Query 以 server-owned `review_identity` 讀取 immutable review、原 adoption receipt 與
   Orders root，僅回傳去敏案件識別、每個衝突的 `field_path`、來源值／既有 Orders 值（依權限遮罩）、
   檢核規則與可採用值、造成的流程阻擋、必要 workbook contract、review／disposition version，及
   reason／evidence 要求；不得回傳原始工作簿或未遮罩個資。只回傳 `issue_codes`、顯示「欄位衝突」
   或空白判斷依據不符合此 Query 契約。
2. Preview 零寫入，必須重新讀取並鎖定 prior review、原 receipt 與目標 Orders root，驗證 actor
   capability `orders.historical_review.remediate`、prior review／disposition version、唯一來源列對應、新檔 digest、根事實與既有
   disposition。它產生只能用於該 prior review 的 fingerprint，並明示可採納或仍須建立 successor
   review 的 blocker。
3. Apply 必須帶 `prior_review_identity`、expected review／disposition version、preview fingerprint、
   idempotency key、reason 與 evidence；在一個 Orders outer Unit of Work fresh-read 後重驗全部
   binding。它可委派既有歷史採納 typed command，但不得重複 lifecycle event、assignment 或既有
   adoption receipt。
4. 原 `historical_order_adoption_reviews` 永遠 immutable。更正結果必須另以 append-only
   remediation disposition／receipt／outbox 表示 `prior_review_identity → replacement adoption receipt`
   的唯一關係，保存 actor、reason、evidence、source digest、版本、時間與可重播 identity。
5. 2026-08-29 current-state anomaly slimming 裁決後，上述 immutable review、Orders
   remediation disposition／receipt／outbox 仍是 Orders owner evidence，但不再建立或保存
   anomaly occurrence、field-warning tracking event、replacement history 或 auto-resolve event。
   更正列合法採納且沒有 issue 時，Orders 在同一 commit 寫入 durable recheck intent；
   fresh recheck 證明 predicate false 後直接刪除 current row。若更正列仍有 issue，
   Orders review Query 繼續顯示當下問題；只有符合 current 15-code contract 的問題才投影
   current issue，不另造 prior／successor anomaly history。
6. duplicate Apply 只回同一 receipt；payload mismatch、stale version、未授權 actor、非唯一對應、
   preview stale、worker timeout 或 projector readback 未達 predicate 均回 typed error／pending，保留
   可見 blocker。Apply 結果必須可從 Orders receipt、disposition、owner review Query 與
   anomaly current projection readback 驗證。predicate 已解除時 current row 必須刪除；
   Orders audit 只保留 owner review／remediation evidence，不保留 anomaly alert 或 warning timeline。
7. 更正來源若通過 Orders 完整規則、但採納後 status、日期與 assignment 均與現行 root
   相同，這是合法 no-op adoption：必須可寫入 remediation disposition，但不得建立
   lifecycle event 或增加 lifecycle version。schema constraint 也必須同時允許此形狀，並繼續對
   真實狀態轉換強制 event 與 `resulting_lifecycle_version = expected_lifecycle_version + 1`。

### 3.2.1 Contract Completion Preview／Apply

客戶簽約完成所對應的契約完成事件是 Orders 根事實，但客戶應付義務由 Client Finance 擁有。
簽約與應收用詞依第 `21` 份正式規格 §1.1，不區分正式／非正式應收。所有月嫂簽約完成時
建立一次訂金應收（deposit obligation）；客戶簽約完成時的 Contract Completion 必須保留
該 deposit，建立其餘尚未建立的期款應收。客戶簽回證據、Orders contract event 與
Client Finance 建立其餘期款應收必須使用同一 outer Unit of Work：

1. Preview 讀取客戶簽回證據、有效 commitment 的精確服務日、完整服務時段、Client Finance
   付款條款、既有 deposit／剩餘義務與兩個 aggregate versions。
2. commitment 精確服務日數必須等於訂單服務天數；不得由起訖日猜測休假日。缺漏時仍回
   stable error `official_service_dates_incomplete` 且零寫入；不得為滿足此 blocker 先建立
   execution schedule。
3. 舊資料若已有客戶義務、卻沒有正式契約完成事件，回
   `client_obligation_history_conflict` 交異常中心人工確認；不得反推補造事件。
4. Preview 顯示既有 deposit 與預計補足義務的筆數、服務日數、整數金額與到期日，並證明
   deposit 金額與 identity 不會被重建或重複計入。
5. Apply fresh-read 並驗證 Contract Signing status、Orders 與 Client Finance expected version、
   Preview fingerprint 及 idempotency key；先追加契約完成事件，再委派 Client Finance 建立
   其餘尚未建立的期款應收，最後
   重評 lifecycle、寫 outbox 與 receipt，單一 commit。
6. 任一步失敗時，簽回事件、契約事件、新義務、兩端 outbox、versions 與 receipt 全部回滾；
   相同命令 replay 回傳原 receipt，不得重複建立義務。

### 3.3 Lifecycle Projection

輸入只接受：

- 有效取消事件；
- 正式契約流程完成事實；
- 訂金有效核銷；
- Client Finance 當前有效的訂金未付人工放行（獨立於核銷事實）；
- actual start confirmation／reconfirmation；
- assignment-owned 最後服務結束時刻；
- Domain 根事實 blockers；
- 客戶帳務義務結清；
- 不可逆服務資料鎖。

優先序：

1. 全部約定服務尚未完成且有有效取消事件：訂單取消。
2. 全部約定服務已完成：訂單完成；拒絕後續取消。
3. 契約完成、訂金有效核銷或仍有效的訂金未付人工放行、execution schedule 有效、actual start 已到且無 reconfirm blocker：服務中。正式排班與開始日重排不得因訂金仍未付而把有效人工放行的案件退回洽談中；付款條款正式改變使放行失效時仍須重新確認放行。
4. 訂金有效，或 Client Finance 已由 system admin 建立有效的一般市民訂金未付人工放行：訂單成立；人工放行不代表訂金已核銷或歸零。此狀態不代表客戶已簽回，也不單獨授權 execution conversion。
5. 其他：洽談中。

Lifecycle Application 是 status、history 與服務資料鎖投影的唯一 writer。任何 caller 都不得傳入 target status。

### 3.3.1 服務完成時刻與 AutoComplete

`AutoCompleteOrderService` 是 Orders 唯一可將服務完成結果持久化的 command。它必須在同一
Orders outer Unit of Work 中鎖定 lifecycle aggregate、effective Scheduling generation、
assignment-owned official service days、`actual_end_date`、完整 service time tuple 與 active
lifecycle controls，再以 Asia/Taipei business clock 評估：

```text
completion_instant
= actual_end_date + service_end_day_offset + service_end_time
```

只有 `evaluation_at >= completion_instant`、正式服務日完整一致、沒有 `auto_complete` blocker，
且訂單未取消／未完成時，才可由 `服務中` 轉為 `訂單完成`。完工確認當下必須在同一交易建立
不可逆服務資料鎖，立即凍結服務日期、時數、服務單價、樓層費及其所形成的財務本金；不得等待客戶
或月嫂款項結清後才鎖定。姓名、電話、地址、備註等非財務個資仍可由其 owner 獨立更正。
Apply 必須追加 immutable lifecycle event、以 expected lifecycle version 更新 projection、保存 idempotency receipt 及 post-commit Orders
source outbox，最後單次 commit；不得重建或結清 Client Finance、Payroll、退款或補助義務。

相同 idempotency key 與 command fingerprint replay 回原 receipt；payload mismatch、expected version
或 authoritative facts 漂移固定回 typed conflict。時刻未到、服務日不完整、effective generation
矛盾、human hold 或取消固定為 typed `domain_blocked` 且零寫入。automatic discovery 只可將 due
candidate 放入 durable command queue；worker 仍只能呼叫此 command，不得直接更新 `orders.status`。

2026-10-15 服務安排 UI 裁決：一般工作台移除人工「辦理完工確認」，改以
`GET /api/v1/orders/{case_no}/service-completion` 唯讀投影 authoritative completion instant、
目前 lifecycle status、等待排班／等待服務／尚未到時／已到時／blocked／completed／cancelled 狀態。
查詢不執行完成，也不以介面時計或資料缺漏猜測 eligible。背景 durable-job cycle 先 discover due
candidate，再由既有 canonical handler 套用；到時後畫面回讀 owner 狀態自動推進。
人工 Preview／Apply API 與稽核／恢復契約保留，正常頁面不再要求人員按一次完工按鈕。

AutoComplete 與 Scheduling leave-substitution Apply 必須序列化於同一 Orders lifecycle aggregate。
任一方先提交都會使另一方持有的 Orders expected version 失效；舊 command 不得以舊服務日完成，
也不得在完成後補寫請假。人工後續更正必須使用獨立、可稽核的 correction command。

正式排班日期登錄錯誤時，`official-service-dates` Query／Preview／Apply 是上述更正命令。
它只接受已完成案件現行 effective generation 中，每個 assignment 完整且日數守恆的正式服務日期；
Preview 綁定 Orders／Scheduling 版本、原日期、新日期及必要 Finance／Payroll 版本。
Apply 在同一交易委派 Scheduling generation replacement，追加維持 `訂單完成` 的不可變更正事件，
推進 Orders version 並以 successor 的最後正式服務日更新 current `actual_end_date`。
原 completion event 與 `order_service_data_locks` 不得改寫或移除。日期更正若涉及特殊薪資、
雙倍薪、既有調整或補助退還等無法證明金額 no-op 的事實，Preview 必須阻擋；
純日期更正不得新建 Client Finance／Payroll 義務。此命令不取代事前 confirmed dates、
Actual Start、Terms 或請假代班流程。詳細可驗收情境以 Issue #346 為本次 bounded package。

訂金 receipt／reversal 與 actual-start reconfirm 綁定：

- 訂金有效性只由 Client Finance 的正式 deposit obligation、succeeded receipt、合法 reversal
  與 allocation reducer 推導；`deposit_reconciled` 不是可寫入欄位。
- 每次 deposit ledger Apply 都以同一 outer Unit of Work 送出
  `deposit_reconciled | deposit_reversed` lifecycle intent，並綁定不可變
  `deposit_settlement_identity` 與有效結算日期。
- 尚未開始服務時，reversal 使 `deposit_reconciled = false`，阻擋進入服務；不得刪除原
  receipt、reconfirmation 或 lifecycle history。
- 已開始或已完成服務後，deposit reversal 只重開 Client Finance 義務並形成帳務異常，
  不倒退服務狀態、不取消 assignment，也不解除服務資料鎖。
- reversal 後再次有效核銷若發生於原 `actual_start_date` 之後，既有 reconfirmation 因
  settlement identity 不同而失效，必須重新確認 actual start；reversal 本身不猜測新的
  actual start。

### 3.3.2 LINE Identity terminal-closure handoff（2026-09-01 Task96 contract）

Orders lifecycle 是案件 terminal closure event 的唯一 source owner。當案件依本節 lifecycle
predicate 進入 terminal closure，Orders 必須在同一 outer Unit of Work 追加 immutable
`case_terminal_closure` event、receipt 與 post-commit outbox；event identity 由
`case_no`、`terminal_kind` 與 resulting lifecycle version 組成，並帶 source subject、
producer reference、occurred time、correlation 與 idempotency identity。此 event 是對 LINE
Identity 的 typed handoff，不是 LINE、UI、worker 或付款／通知 adapter 可自行產生的命令。

若 terminal closure 依賴 Client Finance refund／archive 等其他 owner 結果，Orders 只能在
既有 typed coordination 中引用該 owner receipt；不得跨域寫入 Finance、Staff、Scheduling
或 LINE root。event producer 必須保留 current lifecycle version，讓 consumer 可辨識 stale
event；相同 key／payload replay 回原 receipt，payload mismatch 固定 conflict。

一般客戶沒有月嫂綁定時，LINE 保存正常略過 receipt，不建立選單恢復工作；已處理的事件依 LINE receipt 排除，不更動 Orders outbox。 Orders 原本允許未綁定 LINE 的案件以 NULL source subject 保存 immutable handoff；consumer 依規格 23 §9.5 核對同樣未綁定的 owner、版本、terminal 狀態與 capability 後，使用原正常略過 receipt，不補造身分或改寫 Orders 來源。

LINE Identity 依該 committed outbox 呼叫既有 role-scoped Query／Apply：只有該 LINE User ID
的 staff binding 仍為 `active`，且其全部 active client-role cases 都由 owner readback 證明
terminal，才可建立一次 staff default menu intent。仍有 active client case 時必須回 typed
no-op；staff retirement／revocation pending 或 revoked 優先，絕不可由此 event 恢復 staff role。
consumer 不得修改 Orders 或任何其他 Domain root；binding／menu version、subject mismatch
與 stale event 必須 fail closed，透過 owner Query／manual reconciliation 處理，不得盲目 retry。

正常服務完工的同一 Orders outbox 另帶 `line_service_completion_notification=true`，由既有 LINE source worker 在 commit 後建立原案件群組的單次完工／滿意度問卷邀請通知（規格 20 §5.6）。此標記不代表訊息已送達，不是付款或結案的新狀態；取消、歷史完工及沒有標記的既有事件不補發。選單恢復與通知分別去重，一般客戶略過選單不影響群組通知。既有時段前置驗證維持，不新增完工補件或空白時段自動完工流程。

### 3.4 Actual Start Preview／Apply

正常案件服務開始及本次工會代班的觸發、操作權限與結果紀錄，以 `02_Assignments_Scheduling_Domain.md`「服務開始、排班與代班」SSTART-01～08 為準。客戶在群組提出、月嫂 LIFF 接受並填日期；檔期無衝突且既有正式條件通過即自動更新，無人員再次核准。拒絕／檔期衝突需代班時才由工會介入，選定願意者、邀請加入原群組，再由人員直接填日期。無客戶 LIFF 日期替代入口、雙方日期表確認或代班月嫂再次填日期步驟。
正式服務結果由共同 coordinator 在原 outer UoW 委派 Orders actual-start／Scheduling 及 Client Finance 期限 writer，同步正式開始日、完整班表、結束日與第一期款到期日；成功後才建立群組日期表 outbox。現有底層日期-only／獨立更正契約如下，不得把其僅保存日期的 HTTP 成功當成新服務開始流程已完成。Preview／fresh-lock 檢查保留於 server，並不增加正常流程人工 Preview／Confirm 關卡。

- 首次確認與更正都必須 Preview／Apply。
- 不得以 planned start、訂金日期、第一個 schedule 或 UI default fallback。
- 延遲訂金核銷後仍須人工重新確認真正開始日。
- 尚無有效正式 assignment 時，Actual Start 是後續日期精算的 Orders 輸入：Query／Preview／Apply
  只讀寫 Orders root，以 `lifecycle_version` 作 owner concurrency control；Finance／Payroll／Scheduling
  root 與版本可不存在，回應必須以 `NULL` 表示不存在，不得補造 root、版本、金額或正式安排。
- 上述日期-only Apply 只更新 `actual_start_date` 與 Orders version，不建立 Actual Start event、
  Scheduling generation、Finance／Payroll impact、lifecycle event、永久 receipt、快照、歷程或變更原因。
  HTTP 保存結果與 owner readback 只是本次操作結果，不升格為永久業務紀錄；未知結果以 Orders
  version 與日期重新查閱判定，不盲目重送。
- 日期-only 首次保存後，只要仍無有效正式 assignment，再次修正仍走相同日期-only 路徑；
  單純 `actual_start_date IS NOT NULL` 不代表 `service_started`、實際履約、付款完成、排班完成、
  AutoComplete eligibility 或服務資料鎖。
- Preview 後若有效正式 assignment 已形成，日期-only Apply 必須以 typed conflict 關閉並重新
  Preview，不得在同一 request 偷換為重排流程。
- 已成功完成歷史訂單重啟正常流程、且目前正常 lifecycle 可追溯至該 restart event 的案件，於正式
  actual start 確認日不晚於 business date 時，進入 `服務中` 不以訂金核銷或契約完成為前置條件；
  此例外只移除 lifecycle gate，不得偽造或改寫 Client Finance／契約事實。一般訂單仍維持原條件，
  完整邊界與驗收由 `27_歷史訂單生命週期與服務天數帳務正式規格.md` 擁有。
- 已有有效正式 assignment 時，Apply 才同交易重建 assignments、正式服務日、actual end 與
  lifecycle；服務天數與金額契約不變，因此不重算 Client Finance／Payroll 金額、不新增或調整
  obligation，也不推進 Client Finance／Payroll root version。Scheduling cancel-old／create-new 產生
  successor assignment identity 時，Payroll persistence adapter 只可把該 segment 唯一 source assignment
  的 immutable rate snapshot 原值搬移至 successor；不得重套目前 case policy、改費率或把搬移解讀為
  Payroll impact。source snapshot 缺失、重複或 lineage 不唯一時以 typed integrity blocker 零寫入，
  不得用 case policy fallback。一般案件只允許唯讀既有訂金核銷狀態作 lifecycle gate；Orders／
  Scheduling versions、fingerprint、idempotency、reconfirmation、receipt 與衝突契約維持不變。
- 原過期日期到新確認日期之間不得補造服務日。
- 已有有效正式 assignment 的更正操作須先以新 `actual_start_date` 產生可見的逐段排班 Preview，
  讓內部操作者逐段核對；此畫面不新增請假、假日上班或其他排班日期編輯入口，
  相關調整仍須走既有受控流程。Preview 期間 Orders／Scheduling 均零寫入。
  每次開始日改變，都要由 Scheduling 重新精算、驗證並顯示新候選；舊 Preview
  不得直接確認。操作者最後一次明確確認，才以綁定該候選的 fingerprint／owner versions
  執行原有 Actual Start Apply，同一交易保存開始日、完整正式排班及結束日。取消、離開、
  驗證失敗或 stale conflict 時兩個 owner 的正式結果都不變；不得先保存日期再等待排班確認。
  成功後只回讀 effective Scheduling，不另開第二個排班 Apply 或未保存草稿。

#### 3.4.1 事前服務日期精算與排休覆寫

2026-10-13 後續人工裁決（每週服務時間說明）：初步候選階段可對照原始服務方式，暫時勾選
休假星期並即時試算每週天數／時數；以單一「保存預計日期」操作沿用 Service Dates writer，
不另要求人工核對頁、第二次確認或 reason 輸入。Preview／fresh-lock Apply 的版本與冪等驗證仍保留。
只保存事前服務日期，不保存星期設定、不呼叫 Actual Start、不建立正式排班，也不代表客戶同意。
重新開啟及後續客戶確認內容使用已保存日期；寄送時沿用既有不可變通知內容快照。
此裁決僅適用前段每週說明；後段服務開始依規格 02 的月嫂提交／工會代班流程，不以日期表確認作正式排班關卡。

2026-10-13 人工裁決：排班畫面顯示原始匯入服務方式，供操作者對照後勾選每週休假星期。
星期僅為當次 `custom_rest_weekdays` 試算參數，不新增 DB 欄位、不保存為案件條款或持久草稿。
勾選立即更新 server 建議日曆並使舊 Preview 失效；仍需人工確認，確認後只沿用既有 writer
保存實際服務日期。離開重開只回讀正式日期，不恢復星期設定。原始文字不自動轉換；
未辨識文字必須明確指定星期或無固定週休，不猜測。可選範圍須涵蓋每週至少一日服務及既有假日緩衝。

2026-09-22 #335 UI 接線：服務日期畫面允許輸入此次開始日，輸入改變後自動呼叫既有 server 精算；
試算與核對期間零寫入，日期範圍須對齊此次輸入，不得以舊範圍裁掉合法建議。人工選日的天數及起訖
即時投影；條件改變時保留人工選日並要求重新核對或明確採用新建議。開啟已保存案件只讀正式日期。
尚無有效正式 assignment 時，最終確認才串接既有 Actual Start 與 Service Dates writer；
第一步正式回讀後使用新 owner versions 重新 Preview／Apply 第二步。已有有效正式 assignment
時改依 §3.4 的逐段可見 Preview 與單一原子 Apply，不串接事前 Service Dates writer；正式
重排候選須等於人員核對結果，不得靜默保存另一組日期。
部分完成保留原操作及已保存結果，回讀失敗不得重送已成功寫入；工作台提示接續日期確認，完成前不能
將舊日期視為本次已確認安排。保存後自動更新工作台及相關正式安排投影。正常服務開始不再要求操作上述人工日期表確認，改由規格 02 的共同 Apply 保存結果。國定假日人工確認方式依
Scheduling 規格 2026-09-22 退休獨立 agreement 的最新裁決，不恢復已退役入口。

- 在尚未形成正式 assignment 前，服務日期確認 UI 必須由 server 精算：`週休1日` 預設週日、
  `週休2日` 預設週六與週日；國定假日預設休假，事前請假由人工明示。
- 國定假日只有在目前正式媒合方案針對該日期明確形成「客戶及該方案全部目標月嫂均同意上班」的
  version-bound agreement 時，才可列為服務日。agreement 必須綁定 current matching plan／segment、
  服務日期、客戶與每位目標月嫂的個別肯認、操作者、非空協調依據及 idempotency identity；plan、
  segment、日期或任一確認變動即失效。缺少、過期、拒絕或無法回讀任一肯認時一律維持休假，並由
  server 順延，UI 不得以勾選、預設值或重送舊回覆推定同意。
- 一般月嫂意願或客戶接受正式媒合方案，只證明對該方案的媒合決策；它不等於國定假日上班同意，
  不得重用為前項 agreement。LINE 不是唯一入口；電話、現場或紙本協調可由具有既有人工媒合權限的
  內部操作者補登，但仍須保存同一組 current-plan/date-bound 個別肯認，不得偽造 LINE 發送或回覆。
- 固定週休可由人工覆寫為服務日，並以 `custom_work_dates` 重跑 server 精算；此欄位只覆寫
  固定週休，不能覆寫國定假日休假或事前請假。取消覆寫後必須恢復該固定週休；國定假日的
  `is_work_day` 只能由前述 agreement 的 owner readback 決定，不得接受任意
  `custom_holiday_rest_dates` 集合來反轉。
- UI 不得自行加減、重排或提交服務日；每次覆寫都必須重新取得目標合約天數完全守恆、且全數位於
  server `selectable_dates` 的結果，才可進入既有服務日期 Preview／Apply。
- `selectable_dates` 自本次服務開始日起，連續提供「合約服務天數＋30 個日曆日」的可選期間。
  額外 30 天是為客戶請假、臨時中斷等情況預留的排程緩衝，不增加合約服務天數。一般確認以已確認的
  `actual_start_date` 為基準，尚未確認時以 planned start 為基準；Terms 完整日期替換以本次擬議的
  `planned_start_date` 為基準。開始日之前或超出該期間的日期固定拒絕。
- 一般案件與完成 Precision Restart、current effective generation 仍是空 tombstone 的歷史案件，本節都只
  確認 Orders 的事前服務日期；Service Dates Apply 不得切換 `staff_schedule.is_work_day`、建立 assignment／
  buffer、寫 rate snapshot 或增加 Scheduling version。歷史案件 Query 仍回傳 immutable pairing evidence 的
  `bound_staff`，但日期保存成功只表示 confirmed dates 已成立，不表示正式排班、薪資或履約已建立。
- 歷史重啟案件後續由明確的「建立正式安排」Preview／Apply 接續：只接受 current restart tombstone、current
  confirmed-date version 與既定 `bound_staff`，不要求重做候選、意願或推薦。單月嫂可形成一個 segment；
  多月嫂只有在既有正式 allocation 可唯一重用時才可預填，否則必須由操作者明確提供每個連續 segment
  及其服務日 ownership。不得平均分配、按人員順序猜測或虛構 source assignment lineage。
- Service Dates Query 的 `arrangement_pending` 僅由 current restart tombstone 與 current confirmed-date
  version 投影，不是新增持久狀態；一般訂單即使尚未正式指派也不得顯示歷史待安排操作。正式安排
  Apply 必須綁定 Orders／Scheduling／confirmed-date 版本與預覽 fingerprint，並以原冪等鍵回傳同一結果。
- 真正建立安排時才由 Scheduling canonical generation replacement writer 驗證占用並建立 current assignment／
  `staff_schedule`／buffer；Payroll adapter 同交易凍結費率。存在 source assignment snapshot 時只能原值搬移；
  歷史 pairing 原本沒有 source assignment 或 snapshot 時，才可使用案件已存在的 case payroll policy 建立首次
  assignment snapshot，缺少政策即 typed blocker，不得自造費率。不得建立 historical overlay；正式排班後的
  Actual Start 更正、請假與代班回到各自既有 owner 流程。

### 3.5 Cancellation

- 只適用於全部約定服務完成前。
- 尚無正式 assignment 的日期-only 開始日不代表已服務，不得因此要求逐日服務補登。
- Cancellation 專用 reader 必須驗證下游 owner 的存在與完整性。尚未服務且 Scheduling、Client Finance、Payroll
  root 合法不存在時，Query／Preview／Apply 與 receipt 的對應 version、generation、impact／Scheduling receipt link
  使用 `NULL`，不得自動 bootstrap、補造版本或義務。已初始化 owner 仍維持既有取消 impact；已有收款但未排班
  仍必須由 Client Finance 處理退款。partial root、孤立財務歷史或正式服務缺必要 root 一律 typed blocker、零寫入。
- Apply fresh-read 並鎖定 Orders 及既有下游 facts；不存在的 owner 若在 Preview 後建立，或既有 owner version 改變，
  以原有 typed version conflict／stale preview 拒絕，不得盲目略過。取消事件、取消控制、等待訂金鎖釋放、lifecycle
  與 committed outbox 仍由同一 outer transaction 保存；只有不存在的下游 writer 可省略。
- 已開始服務時，Preview 由使用者確認逐日「實際服務日期＋實際月嫂」；現有事實預填，新增或改派必須指定月嫂與原因。
- 取消 Query 依注入的台北業務日期自動排除取消日之後的排班，僅預填截至當日的候選服務日；當日是否已服務由人員保留或移除，不逐筆刪除未來排班。開始日期或預排不代表已實際服務，確認完全未服務可按 0 日取消；已鎖定的完整履約及未來日驗證仍不得旁路。取消原因選填，點擊取消即執行內部 Preview／Apply，結果依 receipt／正式回讀確認。
- Apply 取消舊 assignments、未來 schedule 與 buffer，依確認後服務日建立新 assignments，重算 hours、整數樓層費、Client Finance 與 Staff Finance。
- 沒有取消費或解約違約金。服務中取消的服務本金固定為已確認實際服務時數乘有效服務單價；已正式
  核銷的訂金與第一期款都納入既有實收，與新本金比較後只形成應退款、應補收或無帳務變動。
- 月嫂應付同步改為該月嫂已確認實際服務時數乘有效服務單價，再加依法有效的樓層費與其他調整；
  未服務的原排定日期不得形成薪資或補助時數。
- 取消結果若包含 Client Finance impact，Orders 只轉送 owning Domain 的 typed 結果；每筆必須帶
  `direction`（`refund_due`／`additional_charge_due`／`no_finance_change`）與
  `direction_amount_ntd`。Orders、API 與 UI 不得由 action kind、obligation amount 或金額正負自行推定。
- 完整履約後取消回 `order_cancellation_after_full_service` blocker 並零寫入；狀態、薪資與服務結算維持完整履約。
- 取消與退款成功均不建立 LINE 訊息。既有取消 terminal closure 僅依 LINE 身分資格處理選單恢復，不代表退款或通知已完成。

#### 3.5.1 服務中代班的契約邊界（2026-08-27 人工裁決）

服務中已有至少一筆 assignment-owned actual service fact 時，代班是 Scheduling 對受影響日期
的 substitution，不是 Orders 的整案換人或契約重建：

- 正常代班不要求代班月嫂另簽獨立服務契約／簽回，也不要求客戶追加確認或簽署變更文件；既有
  commitment、客戶契約、已服務日期與原月嫂的合法薪資根事實保留。
- 代班月嫂 identity、受影響日期、原／新 assignment 與 Payroll impact 由 Scheduling／Payroll
  的 typed substitution lineage 擁有；缺少新契約、簽回、客戶確認或變更文件，不得阻擋代班
  Apply、排班 lineage、actual-service readback 或薪資。
- 人員可另走人工受控的 optional `substitution_supplement` 文件／證據入口。附件只形成可稽核
  supplemental evidence，不自動形成 signed／customer-accepted 事件；無附件或 archive 失敗
  不影響代班合法性。若內容要改變日期、條款或金額，須另依 Terms／Finance impact／adjustment
  owner command 處理，不得由附件直接改寫 Orders root。
- substitute identity 不存在、occupancy conflict、fresh version stale 或 owner readback 失敗等
  真實 blocker 仍須 fail closed；以「沒有追加契約」作為 blocker 則不符合本契約。已有 actual
  service 卻嘗試整案回 Step 2，仍固定拒絕且零寫入。

### 3.6 Controlled Reopen

- 只有尚未產生取消相關正式退款、reversal 或 settlement 才可受理。
- 取消時未初始化的 Finance／Payroll root 可保持不存在；Preview／Apply 版本以明確 `NULL` 表示並做 fresh presence
  比較。若取消 receipt 無 Payroll version，仍查閱取消後的薪資支付歷史，不得把缺版本解讀為可略過金融資格驗證。
- 追加 reopen event，不刪除 cancellation history。
- 不恢復舊 assignment、schedule、lock 或 payment stage。
- 受理後必須 fresh Preview；已有正式退款或結算時另建新訂單。

### 3.7 Historical Order Adoption

2026-10-16 匯入頁統計補充：terminal receipt 的 additive `import_counts` 由原 workbook
outer UoW 依每列實際 receipt 計數；replayed row 只計入 `duplicate_skipped_count`，
其餘 adopted row 計入 `imported_count`，其他 row 計入 `not_imported_count`，三項合計等於來源列數。
review overlay、assignment 數量與來源檔外的取消訂單均不增加來源列統計。
整份 workbook 結果重查保留原 terminal counters。歷史 immutable receipt 沒有此欄且有混合
row replay 時，不猜測重疊分布，管理端以「—」標示缺少的統計，不改寫歷史收據。
2026-10-20 人工補充：同一 terminal receipt 的 additive `row_issues` 保存實際未匯入且非 replay
的來源列號、案件編號、問題欄位與去敏原因碼，供匯入頁顯示；不包含成功列的 review overlay。
整份重查沿用原明細；舊收據缺少明細時回傳不可用，不重算歷史結果。

restricted historical source 只能補登既有 Order，不建立 Client／Order。唯一匹配鍵為唯一的
`case_no`；非空的 `client_name` 只作來源 evidence，姓名差異建立 review evidence但不阻擋採納。案號或姓名空白、
案號找不到或不唯一固定為 `unmatched_case`，零 Domain mutation且不建立警示。
source profile v1 只接受 0→取消、1→已付訂金、2→洽談中；空白／其他值保存 review evidence。
來源狀態是獨立歷史語意，不得直接視為 Orders lifecycle enum：`1` 表示客戶已付訂金，
採納後 Orders lifecycle 為 `訂單成立`，Historical Operational Baseline 推進到第 5 步「確認事前服務日期」，
不得因 `1` 直接標記完成服務或結案。

2026-08-28 狀態判定補充裁決：numeric `0`不得因falsy正規化而與空白共用row fingerprint；
Preview與Apply receipt必須由Orders回傳`0／1／2／invalid`守恆數量，管理端只顯示該typed結果，
不得由前端重算或提供target status editor。完整契約與驗收位於
`PROV-20260828-historical-order-six-column-status-observability-spec-gap.md`。

`actual_start_date`、`actual_end_date` 永遠允許 `NULL`。2026-08-31 人工裁決：歷史來源開始日若與
HCM／Orders `start_date` 預期開始日相同，代表尚無實際服務開始日，`actual_start_date` 維持
`NULL`；兩者不同時，才以歷史來源開始日寫入 `actual_start_date`。2026-09-01 最新人工裁決：
一旦歷史來源開始日可採納為 `actual_start_date`，同列可解析且不早於開始日的歷史結束日必須直接成為
Orders `actual_end_date`，不得再以訂單預設 `service_days` 延展或取代。正式服務日只可在歷史
`actual_start_date..actual_end_date` 閉區間之外產生；歷史月嫂 assignment 也不得超出其來源區間。
來源期間與既有條款不一致時，以這次歷史期間建立實際根事實，不得把預設契約天數偽造成已服務天數。

2026-09-01 最新人工覆決：歷史起訖只證明實際期間，不能證明逐日服務／排假日曆。Historical Orders
Apply 必須直接保存可採納的來源 `actual_start_date`、`actual_end_date` 與歷史 lifecycle branch，但不得因
匯入本身呼叫 Actual Start 精算或依 `service_days`、服務模式、假日曆建立正式服務日。後續帳務不再強制
要求逐日服務日期；工會可在「歷史訂單服務與帳務」介面逐位月嫂確認 `actual_service_days`，依歷史單薪
規則建立 Client Finance／Payroll obligations。未服務及服務中的歷史訂單亦可重啟天數精算回正常
lifecycle。狀態、日期、樓層費、雙邊結清、回歸精算、API／UI 與驗收的完整最新契約由
`27_歷史訂單生命週期與服務天數帳務正式規格.md` 擁有；本節較早「只有逐日服務日才可建帳務」及
`historical_accounting_service_calendar_unconfirmed` 一律阻擋至精算的語意由第 27 份規格 supersede。
欄位不可解析或違反 Orders invariant 時仍以 typed validation／conflict fail closed。
此受限斷言只授權 Orders-owned historical adoption command，不授權一般 adapter 或 UI 寫入。Preview 零寫入，Apply 每列鎖定 fresh
Order、驗證 version／fingerprint，並以單一 UoW 保存 Orders root、event、receipt、outbox及來源配對 evidence。

2026-09-01 人工校正：Historical Orders 的本次用途是以空白 DB 一次性建立完整且真實的歷史
排班基準，取代前述 `ROW_ATOMIC_RESUMABLE` 契約。Preview 必須先對整份工作簿完成所有可採納列、
狀態機、實際期間與來源內月嫂區間的零寫入驗證；不同案件的同月嫂來源區間重疊固定為
`historical_order_source_schedule_conflict`，不得以列順序覆寫。Apply 必須以單一 outer UoW 同時保存
workbook claim、全部列的 Orders／歷史 assignment evidence 與 terminal receipt；任一列失敗即整份 rollback，
不得留下 claim、row receipt、assignment、schedule、occupancy、event、outbox 或部分 Order 狀態。same
key＋same canonical workbook 僅 replay terminal receipt；same key＋different workbook 固定 conflict。
來源資料不得因既有測試排班而刪除或覆寫其他案件；同案若已有 current generation，仍只可由
Scheduling canonical cancel-old／create-new replacement 處理。`assignment_candidate` 與
`evidence_only_pairing`是`adopted`子分類，不得重複計入source-row aggregate。

HCM Current仍由Case Import編排whole-workbook outer UoW。HCM案件身分以非空且合法的案件編號為唯一鍵；
不同案件編號即使姓名或IP相同仍建立新的Client／Order，姓名／IP重複只可形成非阻擋人工警示，不得自動
合併或阻擋。只有案件編號已存在才依same-source exact replay／conflict處理且不得覆寫既有資料。尚無唯一
Client BeClass對方的合法案件仍建立Order並讓`requires_cooking = NULL`。完整HCM案件的訂金到期日與四種
canonical服務方式／排休日語意由第17份正式規格§5.2.1擁有；archive成功不等於Orders commit，rollback後
的archive compensation由Case Import擁有。

### 3.8 Historical Operational Baseline（2026-08-27 人工裁決）

只有 Historical Orders 可由具權限人員以 append-only Preview／Apply 設定目前 11 步作業基準。選定
第 `N` 步後，第 `1..N-1` 步投影為 `historical_baseline_completed`，第 `N` 步為 current／in-progress；
一般新案件不得使用此狀態。baseline event 必須保存 case/order identity、selected step、actor、reason、
evidence、current owner versions／fingerprints、idempotency 與 receipt，且不得建立不存在的 LINE delivery、
簽章、付款、allocation、assignment 或 lifecycle event。

歷史案件可免除重建已不可得的過去操作軌跡，但從 current step 繼續執行所需的 canonical root 仍必須存在。
缺少 matched caregiver、有效 commitment、confirmed official dates、effective assignment、actual start、
service-time tuple 或 owner financial root 時，必須建立具體、可由 owning Domain Q/P/A 補齊的異常；補正後
fresh readback 使該 occurrence 消失並允許後續推進。歷史簽回或傳遞證據確實不可取得時，可追加具
actor／reason／獨立 evidence 的 `historical_evidence_unavailable_accepted` disposition；它只結束補找舊文件的
operational blocker，不得偽造成 signed／delivered／paid，也不得繞過 current/future command 的必要 root。

Orders service completion 與 Client Finance、Staff Payables、Government Subsidy settlement 分開投影：
服務根事實完整可使 Orders 完成；未結清金流仍各自保持 actionable alert，不得把 Orders 倒退為服務中。
取消則依 §3.5 分流，沒有額外解約違約金；服務前無正式金流不要求付款紀錄，已有收款或服務中取消所形成的
退款、補收、月嫂應付／追回仍由各 owner 結清後才解除。

## 4. Module

### Confirmed Service Dates (2026-08-12)

Orders owns the `Confirm Service Dates` Preview/Apply command. The candidate must contain
exactly the contracted service-day count, be unique and sorted, and every date must be within
the server-provided selectable range. Apply locks current Orders/Scheduling facts, validates the
Preview fingerprint, creates one immutable version and receipt, and invalidates the current
matching schedule snapshot. It never creates an assignment, staff schedule, Payroll impact, or
outbound LINE task.

Calendar-week views use Sunday through Saturday. A modification never overwrites historical
confirmed versions or prior schedule-confirmation events; it creates a new current lineage which
must be previewed, sent, and confirmed again before formal assignment can proceed.

尚未建立任何 Scheduling segment、current confirmed service dates 且服務尚未開始時，Orders Terms 可先
修改 planned start 與 `service_days`；planned end 由 Orders 依修改後條款重新計算，並建立不含 assignment
的下一代 Scheduling generation。此時「尚無正式排班」是允許修改的前提，不得反向成為 blocker，也
不得為了修改進件資料先虛構 assignment 或逐日服務日期。

2026-10-17 人工裁決：一般進件資料補件（姓名、日期／天數／時段及補件完成）的人工「修改原因」改為「備註（選填）」。既有 intake Apply 的 `reason` 省略或空白皆保存空字串，仍納入原 command fingerprint；actor、版本、Preview、冪等鍵、事件、receipt、回讀與同交易初始化契約不變。自動初始化步驟獨立記錄「系統依已完成進件資料初始化本案」作為實際系統觸發說明，不冒充人工備註；人工原文／空白仍保留在 Orders 命令紀錄。取消訂單的取消原因維持選填；省略或空白仍納入原命令比對，人工備註保留空白。解除接案意願鎖與啟用取消控制等系統稽核事件，空白時記錄「系統記錄取消訂單」，不冒充人工填寫原因。正式 Terms 影響、重開、實際服務更正與財務操作的原因依各自現行契約。

2026-10-13 人工裁決：進件補件畫面只顯示 owner Preview 的 `missing_fields` 中實際缺少的
服務開始日／服務天數；已齊全的欄位不作為補件輸入顯示。補一項時沿用另一項已保存的值，
仍走既有 Orders Preview／Apply。完整日期／天數的早期異動保留「修改服務日期／天數」明示入口，
由人員主動展開，不以可異動資格冒充缺件，不改 missing-field 判定、lifecycle 或交易邊界。
日期／天數草稿以 Orders intake owner Preview 的 current values 為準，不得被一般訂單明細或
列表摘要的空值覆蓋。案件初始資料修復入口同樣只顯示實際缺少的日期或天數，另一項沿用
owner 已保存的值，不要求人員重填合法欄位。
待辦看板與案件處理中的進件條款缺漏提示直接顯示「缺少欄位：」及實際缺少的欄位名稱；
不顯示「訂單條款根事實尚未齊備」或以階段標題取代缺件內容。沿用既有完整性判定與階段狀態。

2026-10-13 人工裁決：待補件／洽談中且尚無下游 Finance、Payroll、非 pristine Scheduling、實際開工
或服務資料鎖的案件，既有 intake terms bootstrap Preview／Apply 可承接可選的
`proposed_service_time`（每日服務時數、開始時間、結束時間、跨日值），補齊因每日時數缺失而
無法開啟一般 Terms 編輯器的案件。沿用 Orders lifecycle version、既有跨 request 預覽確認、
同一 outer UoW 與 idempotent receipt；只修改明確變更欄位，不建立排班、帳務或外部通知。
既有日期／天數命令未提供此欄位時保持原 fingerprint／receipt 語意；時間補件不擴及歷史案件。
進件完成 Preview 額外回傳 typed current service time 供表單與正式回讀比對，不擴張其原本
姓名／日期／天數 missing-field 判定。介面僅在 current 時間資料不完整時顯示時間补件；
起訖試算的時數允許人員按協調結果修正，必須為正半小時且不超過排定區間。
驗收 A 依人工指定保存 `08:00～17:00`、每日 8 小時；不將排定的 9 小時逕作服務時數。
保存後重新讀取正式階段，符合完整性才接續媒合；不得由 UI 直接改寫 lifecycle／階段。

2026-10-15 人工裁決：缺件補齊後必須接續本案初始化，不新增或重排前端區塊。待補件案件的
「完成進件補齊」Apply，及洽談中案件透過 intake Apply 補齊姓名、日期、正服務天數、每日時數與
完整時段後，均由 Orders 既有 outer UoW 委派 canonical Case Architecture Bootstrap，使用既有
Client Finance 付款政策與 Payroll 費率分類建立缺少的本案初始資料。此條覆蓋前述僅在這兩個
完成時點「不建立下游 roots」的限制；一般分段補件、歷史修補及 Query／Preview 保持零下游寫入。
初始化與 Orders 保存／進件完成及原命令 receipt 同交易 commit；任何失敗全部 rollback，
不得保留已完成補件卻未初始化的部分結果。初始化僅建立付款條款、薪資政策與空 aggregate，
完整計價資料由 Client Finance 在同一交易自動同步客戶應付，不新增人工建帳關卡；不建立實際收付款 ledger、正式 assignment 或外部通知。same-key 重播回讀原 receipt，
不重複初始化；既有完整初始資料維持原值，partial roots typed 拒絕，不補零、不覆寫。
既有案件資料回填不在本次施工範圍，驗證使用 localhost 全新隔離 lu_test_* 合成資料。

此 preassignment Terms Query／Preview／Apply 只讀 Orders、Scheduling 與判斷下游完整性所需的最小
存在／義務 facts；Client Finance／Payroll root 可合法不存在，回應與 receipt 的對應 version／impact
使用 `NULL`，不得以 `0`、空金額或自動 bootstrap 冒充完整資料。若 root 已存在但內部關聯不完整，或已
存在不符此次異動的 nonstage Client／Staff 帳務，固定 fail closed；若未讀取該 owner，該 owner 的無關版本變動不得使
Preview／Apply stale。已有有效 segment 時仍讀取完整下游 facts、驗證版本並執行既有 impact writer。

若已有 current confirmed service dates，planned start 平移且 `service_days` 不變時，Apply 保留原日期
間隔並以相同日差建立新的 immutable current version；同一 transaction 同步保存版本 receipt 並使既有
matching schedule snapshot 失效。若 `service_days` 改變，必須提供完整 replacement dates；
Terms 面板使用既有 server 日期精算後，與新條款在同一 Preview／Apply 提交，不先單獨保存日期或天數。
已有 segments 時另須明示完整分配，由 Scheduling canonical replacement writer 在原有 outer transaction
重建，並同步 Client Finance／Payroll、confirmed-date immutable version 及 receipt，否則 fail closed。
Apply 成功但 Query 失敗時保留已提交狀態，重新讀取不得重送異動；結果未知時只允許人工重播同一命令。若要重新聯繫既有候選人，
Scheduling 仍須以修改後 current Orders 起訖日及 current confirmed dates 重驗其完整檔期。

### Confirmed Service Dates (2026-08-12)

Orders owns the `Confirm Service Dates` Preview/Apply command. The candidate must contain
exactly the contracted service-day count, be unique and sorted, and every date must be within
the server-provided selectable range. Apply locks current Orders/Scheduling facts, validates the
Preview fingerprint, creates one immutable version and receipt, and invalidates the current
matching schedule snapshot. It never creates an assignment, staff schedule, Payroll impact, or
outbound LINE task.

Calendar-week views use Sunday through Saturday. A modification never overwrites historical
confirmed versions or prior schedule-confirmation events; it creates a new current lineage which
must be previewed, sent, and confirmed again before formal assignment can proceed.

| Module | Input | Output | SSOT／限制 |
|---|---|---|---|
| TermsValidator | current／candidate terms | typed validation | 未修改的全空 tuple 可保留；時段異動須三欄完整，正式流程前必須完整 |
| ServiceTimeTermsValidator | start、end、day offset | canonical tuple／typed blocker | offset 僅 0/1；不推測跨日 |
| PlannedEndCalculator | planned start、terms、規劃服務日 | end date | 不讀 actual facts |
| ActualEndCalculator | 有效正式服務日 | actual end | 忽略 cancelled、休假與 buffer |
| CompletionInstant | actual end、服務結束時間、day offset | Taipei instant | 不使用午夜或伺服器時區 |
| LifecycleEvaluator | typed roots | status decision | 不讀 Alert 或 target status |
| ServiceDataLockPredicate | completion、客戶結清、既有鎖 | lock decision | 一旦 true 永不回 false |
| TermsDiff | before／after roots | canonical diff | 不含 client name 或 Finance-owned 欄位 |
| PreviewFingerprint | relevant roots、candidate、contract version | deterministic hash | 顯示欄位改變不得誤判 stale |
| CancellationServiceDayValidator | 合約服務量、逐日 owner | validated actual service facts | 完整履約後禁止取消 |
| FloorFeeProration | 原費用、合約日、實際日 | 整數總額 | `ROUND_HALF_UP` |
| LargestRemainderAllocator | 整數總額、各 assignment 日數 | 整數 allocations | 固定 assignment 順序；總和守恆 |
| ReopenEligibility | cancellation 及財務事件 | allow／blocker | 不恢復舊資料 |
| DepositSettlementIdentity | obligation、receipt、reversal、allocation | deterministic identity | reconfirmation 必須綁定目前 identity |

Terms 編輯畫面以起訖時段推算每日服務時數時，4 小時班不扣休息；8 小時班的排定時段為 8.5 小時，其中 30 分鐘為休息，因此例如 `08:30～17:00` 的 `service_hours_per_day` 為 8。

Module 必須為純函式，不得讀 DB、取得現在時間或 import API／UI。

## 5. Typed API

```text
GET  /orders/{case_no}
POST /orders/{case_no}/terms/preview
POST /orders/{case_no}/terms/apply
POST /orders/{case_no}/actual-start/preview
POST /orders/{case_no}/actual-start/apply
POST /orders/{case_no}/cancellation/preview
POST /orders/{case_no}/cancellation/apply
POST /orders/{case_no}/reopen/preview
POST /orders/{case_no}/reopen/apply
```

Apply request 只接受原始 intent、actor、reason、expected version、preview fingerprint 及 idempotency key。不得接受 status、actual end、actual hours、金額或前端計算完成的 assignment 結果。

Stable errors：

- `order_not_found`
- `invalid_order_terms`
- `service_time_terms_incomplete`
- `service_time_terms_invalid`
- `service_data_locked`
- `actual_start_reconfirmation_required`
- `order_cancellation_after_full_service`
- `order_reopen_financial_history_exists`
- `order_version_conflict`
- `stale_preview`
- `idempotency_conflict`
- `cross_domain_candidate_rejected`
- `transaction_failed`

## 6. 現況遷移

可吸收既有 lifecycle command envelope、facts validation、pure candidate、persistence、outbox 與 typed API client 的結構，但必須：

- 補入契約完成根事實；
- 移除 target-status manual correction；
- 不讓 human hold 成為新核心依賴；
- 將 cancellation shell 擴充為完整跨 Domain transaction；
- 以 Terms Preview／Apply 取代 ownership 過寬的 assignment synchronization；
- 將 UI 日期、金額與 status 計算移回後端。

既有 dirty／untracked lifecycle 成果必須逐檔吸收，不得刪除後重建。

Live writer 退出清單：

- `services/order_lifecycle_persistence.py` 可吸收為 Orders persistence adapter，但只能由
  Lifecycle Application 呼叫。
- `services/client_payment_writer.py`、Finance Import 與 Client Finance 只能送 lifecycle
  intent，不得直接寫 `orders.status`。
- `services/caregiver_availability_lock_conversion_service.py`、
  `services/caregiver_availability_lock_cancellation_service.py`、
  `services/order_assignment_synchronization.py` 與 `services/db_service.py` 的 status／日期
  writer 必須遷移至 Orders typed port 後關閉。
- `scripts/imports/import_client_hcm.py` 與 `services/line_review_service.py` 只可建立初始
  Orders root facts，不得自行推進 lifecycle。
- final writer scan 必須證明 `orders.status`、`actual_start_date`、`actual_end_date`、
  服務時間三欄與 lifecycle version 都只有目標 owner 可寫。

## 7. Domain 驗收

至少覆蓋：

- 匯入洽談案件到成立、服務中、完成及服務資料鎖；
- 相同與衝突 Import replay；
- Terms 全案重建；
- 延遲訂金後重新確認 actual start；
- 服務時間三欄缺漏時，契約完成、waiting lock conversion、訂金核銷、進入服務與完成都
  fail closed；跨日 offset 不由時間大小推測；
- 訂金 reversal 在服務前阻擋進入服務；服務開始後只重開財務義務，不倒退服務狀態；
- reversal 後的新延遲核銷使用新 settlement identity，舊 actual-start reconfirmation
  不得重放；
- 多月嫂中途取消及雙邊重算；
- 全部服務完成後取消零寫入；
- 服務中代班不要求新契約／簽回或客戶變更簽署，缺少文件仍可完成 substitution、排班 lineage
  與薪資；optional supplement 只保存人工 evidence；
- 完成但未鎖時補登正確服務根事實；
- 鎖形成後退款／reversal 不解鎖；
- legacy status／assignment writers 不可達或固定 Gone。

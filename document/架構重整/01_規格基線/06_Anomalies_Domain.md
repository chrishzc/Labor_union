# Anomalies Domain

## 1. Domain 定位

Anomalies 是根事實衍生的保護與人工作業 Domain，不是其他 Domain 的控制中心。

三層 SSOT：

1. 異常條件：各 source Domain 的根事實與正式事件。
2. 異常定義：`AnomalyDefinitionRegistry`，保存 code、source domain、fingerprint fields、severity、projection kind 與 display schema。
3. 工作流：
   - 財務敏感異常保存 immutable occurrence／event；
   - 流程與資料異常保存 current-state projection；
   - claim／resolve event 只代表人員處理進度。

Alert details JSON、UI 文案、review status 及 reconciliation pending 都不是異常條件 SSOT。

### 歷史訂單待人工確認（2026-08-14，已人工確認）

`HISTORICAL-ORDER-001` 的 owner 是 Orders。每個 immutable
`historical_order_adoption_reviews.review_identity` 最多投影一筆 current-state warning；fingerprint
僅為 `review_identity`。projector 必須由 review root 讀取遮罩案件識別與 issue codes，不得採用
outbox snapshot 中的原始案件編號、姓名、日期或月嫂資料。`unmatched_case` 是零 mutation、零 anomaly，
不得投影此碼。歷史 review 的根事實不因 alert claim／resolve 而被修改，也不得用 generic resolve
假結案；人員必須透過 Orders 的 `review_identity` 綁定「更正來源重新匯入」Preview／Confirm／Apply
閉環處理，詳見 `01_Orders_Domain.md` 的同名契約。

### 全異常人工 remediation 閉環（2026-08-26，使用者明確裁決）

每一個 active anomaly code 都必須提供人員可完成的、owner-specific remediation 閉環。異常中心的
「可查看」、純導覽、claim、tracking transition、projector retry 或人工 `resolve` 都不構成 remediation；
它們不得被用來把仍存在的 root predicate 藏起來。此裁決取代所有將 `available_actions=[]` 或
`no_automated_recovery=true` 視為可交付終態的舊範圍解讀；後者只能表示系統不自動猜測，不能免除
人工處理入口。

每個 code 的正式 owner 規格與 registry 必須明列至少一條可驗收路徑：

1. fixed source bindings、actor capability、必要 reason／evidence 與可顯示的 blocked reason；
2. owning Domain 的 typed Query／Preview → 人員確認 → Apply，或對外部／人工取得的事實採同等嚴格的
   evidence-verification command；
3. fresh root／version lock、preview fingerprint、idempotency、replay、timeout reconciliation、receipt／event
   與 outbox；
4. completion predicate、Apply 後 readback 與 projector recheck。只有 predicate 消失、合法 replacement
   source 已接手，或 owner 規格明定且已驗證的 immutable disposition 成立時，alert 才能 auto-resolve；
5. React typed renderer 或受控 owner workbench entry，讓操作者能從 anomaly context 實際走完上述流程。
   只開另一頁而沒有帶入受驗證的 source context／完成 readback，不算完成。

每個 code 還必須分開聲明兩種解除渠道，不得用其中一種的缺席免除另一種：

1. 若可安全自動補正（例如 LINE 要求客戶補填／更正且收到可驗證回覆），owner 必須定義自動 command、
   recipient／來源驗證、重試／逾時與重新檢核 predicate；它只在根事實真的成立後解除 alert。
2. 無論是否有自動渠道，都必須有具同等 owner binding 的人工渠道，供客戶以電話、現場或其他非系統管道
   提供更正資料時，由獲授權人員輸入或上傳 evidence 並 Preview／Apply。人工渠道不可要求客戶再次走 LINE
   才能完成，也不可只是記錄「已聯絡」。

異常 detail 是 remediation 的操作契約，不是追蹤記事。每一筆 active alert 至少要以去敏資料顯示：
來源／案件識別、具體失敗的欄位或規則、收到值與規則期待值（可揭露時）、發生時間、目前根 predicate、
阻止的後續狀態，以及可選的自動與人工解除方式、所需輸入與完成條件。`issue_code`、籠統的「欄位衝突」
或空白判斷依據都不合格。若因 PII／權限不能顯示值，必須改顯示受遮罩的 field label 與可執行的修正
指示，不能留空。

Apply 的完成 readback 若 predicate 已消失，current alert 必須從 active 列表移除；歷史 occurrence、
receipt 與 replacement link 僅留在 audit／history view。若 correction 產生新的合格關聯問題，原 alert
必須消失並由明確連結的 successor alert 取代，且畫面要說明新問題與下一個解除方式。tracking state
只能輔助工作交接，不能是主畫面的唯一動作、完成訊號或流程閘門。

自動解除 predicate 不是 Anomalies 自行發明的技術條件。每個 code 都必須在 registry／owner 契約中
引用 owning Domain 正式規則書的具體章節，列出該規則實際使用的 root facts、業務完成條件與仍應保持
active 的反例。projector 只能重用同一個 owner predicate 或其有版本、可機械證明等價的 typed result；
不得以 API 成功、job／tracking status、通知已送出、曾收到客戶回覆、欄位非空、人工聲稱完成或較寬鬆的
projection 條件取代真實業務流程。規則書沒有足夠證據、owner readback unavailable、版本不明或 detector
與 owner predicate 不等價時固定 fail closed，保留 alert 並回傳可理解的 blocker。

每條自動解除路徑的驗收至少同時證明：符合完整業務規則時解除；只完成部分步驟、外部動作成功但根事實
未成立、root fact 於 recheck 前漂移、readback 失敗或存在規則明定 blocker 時不解除；若業務規則產生合法
successor，則只可依明確 replacement relation 取代原 alert。規則書或 owner predicate 變更時，對應
definition contract version、detector、測試與 remediation completion predicate 必須同批更新，否則不得發布。

Anomalies 永遠不得成為 generic root editor、任意 status changer 或跨 Domain SQL writer。原因或修復結果
不唯一時，owner 必須提供有限、可驗證選項或保留明確 blocker；不得預選答案。各 code 的欄位、資料效果、
豁免適用性與 lifecycle boundary 必須仍由 owning Domain 規格定義，並通過其 Work Package／DB gates。

### 異常必要性與一般工作項分界（2026-08-27，使用者明確裁決）

`default_anomaly_registry()` 載入的 42 個 code 只是 legacy/current inventory，不是必須永久保留的產品目標。
只有下列情況可留在 active anomaly：owner root 已違反業務不變量、外部或 legacy 事實無法由正常 typed flow
保證、已超過 owner 明定期限／SLA，或完整性 readback 發現矛盾。正常 11 步驟尚未執行、尚在等待回覆、
已到可執行日期的例行工作，或一個合法操作已建立 successor 工作，都不是異常；它們必須由 Orders／LINE／
Finance owner work queue 顯示，不得為了湊齊 42 碼而替它們建立人工「解除異常」表單。

本次 42-code necessity audit 的 current disposition 如下：

1. `SCHEDULE-005` 的 hard-anomaly 語意退役。Staff preference 只影響媒合排序與 explanation；目前以
   `國定假日必休 + is_work_day` 投影警示的 producer 是 `live-drift`。真正的 assignment overlap、不可服務期間、
   official-date 或 coverage 衝突仍由其各自 Scheduling code 處理。
2. `ORDER-001`～`ORDER-004`、`DOC-SEND-001`、`LINE-002`、`SUBSIDYADVANCE-001` 改列 owner work item。
   現有 predicate 分別只代表媒合尚在某一步、履歷尚未發送、訊息尚未回覆、或工會墊付已到可執行日期，
   都沒有 breach／overdue／invalid oracle。未來若 owner 定義明確 SLA，只有超時且仍未完成的另一個
   versioned anomaly definition 才可進異常中心；不得沿用目前的「尚未完成即異常」。
3. `staff_payout_overpayment` 保存為 immutable payout-difference occurrence／history；建立
   `staff_overpayment_recovery_open` successor 後，current active list 只顯示後者，不得讓同一追償 root
   同時出現兩個待處理警示。successor 未成功建立時，以 integrity blocker 保留原 occurrence，不得兩者皆消失。
4. `LINE-004` 保留為 Identity integrity code，但只可代表同一 subject type 多重有效綁定、binding root 與
   projection 矛盾，或 replacement／revocation 未完成。同一 LINE 帳號同時是 customer 與 staff 是合法狀態，
   不得投影 `LINE-004`。
5. `SCHEDULE-002` 只可代表 replacement／substitution lineage、實際服務結果或必要 Finance／Payroll split
   尚未完成；合法 replacement 本身不是永久異常。owner completion 後必須由 fresh predicate 自動解除。

因此 current 目標不是「替 42 碼全部補表單」，而是 `33` 個 current active anomaly definitions、`7` 個 owner
work items、`1` 個退役 false-positive code，以及 `1` 個只留 audit history、由 successor 接手的 occurrence。
退役／移轉完成前，必須先證明 replacement work queue、history 與 successor 投影可讀，且 bounded rescan 能讓
既有錯誤 active alert 消失；不得直接刪 registry code 造成既有案件失去操作入口。

#### Necessity migration disposition contract

既有 active alert 的移轉不是 tracking resolve，也不是刪除 current row。Anomalies 擁有一個只處理 definition
生命週期移轉的 immutable `AnomalyReclassificationDisposition`，合法 disposition 僅有：

- `reclassified_to_owner_work_item`：必須 fresh-read 一個已存在、可從正式 owner Query 讀回的工作項；
- `retired_false_positive`：只適用正式規格已明定 predicate 不成立的 code，例如 `SCHEDULE-005`；
- `replaced_by_successor`：必須先 fresh-read 唯一 successor alert／owner root，且 successor 仍可操作。

每筆 disposition 固定保存 disposition identity、alert fingerprint、definition code、source identity/version、
expected workflow version、target domain、target reference/version（false-positive 可空）、actor、reason、獨立
evidence reference、Preview fingerprint、idempotency／correlation identity、receipt 與建立時間。same key＋same
payload replay 原 receipt；same key＋different payload、stale alert/source/workflow、target 不存在、target version
漂移、successor 不唯一或 readback failure 固定零寫入。

Apply 必須在單一 Anomalies outer UoW 中重新鎖定 alert 與 target readback，append disposition／receipt，將
current predicate 轉 inactive，並 append system `auto_resolve` workflow event；history／occurrence／舊 snapshot
不更新、不刪除。`retired_false_positive` 仍需綁正式規格版本與 release evidence，不能由操作者自由選擇。
一般人員 UI 不提供此 disposition 表單；它只由已核准 migration runner 使用。

Migration runner 使用 deterministic `(definition_code, source_identity)` cursor，每頁最多 100 筆，batch receipt
必須完整保存 before／next cursor 的兩個欄位、sorted unique eligible-code subset及approved migration policy
identity／fingerprint，並輸出 scanned／applied／blocked、before／after fingerprints。同一operation＋before cursor
使用bounded deterministic idempotency identity；request fingerprint只綁呼叫前已知的eligible codes、page size、cursor、
policy、actor，不可綁第一次執行後才產生的page結果，否則成功後active row消失會使unknown-outcome replay錯誤衝突。
same request replay原batch receipt；相同identity但policy、actor、eligible subset或page size不同固定conflict。
單筆 blocker 不可被略過為成功；若同一 outer Unit of Work 需要保存 blocker 後繼續下一筆，必須先建立該筆
database savepoint，所有可能已發生的 disposition／workflow event／receipt 寫入都在失敗時 rollback-to-savepoint。
沒有 savepoint 能力或遇到 unknown adapter／commit outcome 時固定中止並 rollback 整批，不得 catch 後繼續 commit。
存在 blocker 的 batch 不得標 completed，且該 definition producer 不得停用。只有全部既有 active rows 都取得
terminal disposition／readback，且從start cursor重新掃描的completion sweep證明eligible active rows為零後，才依序
停止對應 producer。blocked batch是immutable evidence；來源修正後以新的operation identity從原before cursor或start
cursor重掃，不得覆寫舊batch。歷史 Query仍由完整catalog `codes()`解碼舊紀錄。

Registry 必須分開 `catalog definitions`、產品目標 lifecycle 與 migration 期間的 operational effective state。
完整 catalog 在 migration／retention期間仍包含42個 legacy code；`active_codes()` 表示人工裁決後的33-code產品目標，
不是「目前DB已只剩33碼」的證據，也不得在migration完成前直接當作producer admission gate。operational effective
state必須由每個definition的target readback、既有active-row terminal disposition及producer cutover receipt共同投影：
A～C完成後可宣稱34個effective anomaly definitions，D完成後才可宣稱33。尚未取得terminal disposition的legacy row
仍須在異常中心可見且保有處理入口；不能只靠target lifecycle或UI filter隱藏。完成cutover後，非target-active
definition才拒絕新的`desired.active=true`，但migration inactive desired state與歷史readback仍可依上述contract處理。

Lifecycle gate 先於個別 detector：服務前取消時，沒有已發生金流／服務／外部效果的流程型 alert 全部 inactive；
服務中取消只保留已發生服務所衍生的 Scheduling、Finance、Payroll 與 integrity 問題；完成且結清案件在
`actual_start_date`／`actual_end_date`、必要 assignment、匯款與 allocation 根事實齊全後，不得繼續顯示媒合、
發送、等待回覆或資料補登工作項。任何 integrity 或實際金額差異仍須依 owner root 處理，不能被 status 字串遮蔽。

### 匯入警示追蹤（2026-08-14，WP92 已人工確認）

HCM、Client／Staff BeClass、Historical Orders 與 Finance Import 的 source warning／review 必須使用
欄位級 immutable occurrence：同一來源列的每個 `logical_code + field_path` 各自保存 issue codes、
去敏來源識別與解除 predicate。UI 可以依案件或來源分組，但不得以群組按鈕整案修正或一起消除。

Anomalies 只擁有匯入警示的追蹤狀態機與 current task projection；觸發條件、正式資料效果、資料有效性、
候選唯一性及解除 predicate 仍由 Case Import、Staff、Orders 或 Finance Import 擁有。警示中心不得接收
`corrected_fields`、直接選擇任意候選、merge roots、修改 bank row 或旁路寫入 source Domain。

警示中心可提供「轉介」：以 `warning_id`、owning lane、field path、expected warning version 與去敏來源 reference
建立至 owning Domain typed command 的受控操作入口。轉介本身不寫入 Domain root；目標 command 必須重新讀取並鎖定
正式 root、驗證輸入與 actor capability、保存其 own receipt／event，成功後才由系統依 lane predicate `auto_resolved`
對應 warning。若 command 不存在、資料無法驗證或版本已 stale，固定回 typed error 並保留 warning，不得退回警示中心
直接修正資料。

```text
open → awaiting_external_confirmation → response_recorded → reimport_requested
任一 active state → closed
owning Domain predicate 消失 → auto_resolved
```

前四個狀態是 active。人工 `closed` 只代表外部聯絡工作結束，不代表資料已修正；`auto_resolved` 只能由
system actor 在 fresh-read owning Domain root 後產生。exact source replay 只回既有 receipt，不新增 occurrence、
tracking event、outbox 或 task。顯式關聯的新來源若仍不合格，必須建立新 occurrence 並成為 current task，
system actor 對舊 task 追加 `closed(reason=replaced_by_new_warning)`；舊 source、issue codes、occurrence 與事件永不刪除。

沒有 formal root 的來源警示不得用姓名、手機、列號或模糊內容猜測新舊關係；新提交必須攜帶可驗證的
prior warning／source association。第一階段只記錄公會人員以既有 LINE、電話或法定管道聯絡的進度，
不自動傳 LINE、不推定 recipient、不保存對話全文。

上述六狀態只適用 WP92 匯入警示追蹤。其他既有 current-state anomaly 在完成各自 migration／entrypoint
裁決前，仍沿用下方 generic Alert Workflow；不得把兩套 status 語意混用或只以 UI label 互相映射。

## 2. Subsystems

### Root-fact Detection

依 Domain event 增量偵測，並提供 bounded rescan。Detector 只讀根事實或 canonical projection，必須同時輸出 active 與 inactive desired state。可提早發現的缺漏應在下游流程前出現。

### Domain Blocker Projection

接收各 Domain blocker intent 並建立顯示投影，但 blocker authority 仍在 source Domain。Domain command 不得查 Alert status 決定成敗。

### Current-state Alert Projector

以 fingerprint upsert 唯一 current row。根條件消失自動 resolve；條件仍存在或再次出現時，即使曾人工 resolve 也必須 reopen。

### Finance Occurrence Recorder

每次新的銀行流水、重試批次或正式 Domain event 可形成 immutable occurrence。單純 rescan 不新增 occurrence；重試同一 source event 必須 idempotent。

銀行來源檔、canonical row、occurrence、classification 與 reprocess audit 的 owner 是
Finance Import Domain。Anomalies 不得直接解析銀行 raw payload、重分類或 dispatch。

Finance Import 的警示依根因分成兩條互斥路由：

1. 可安全保存、但暫時無法判斷業務歸屬的 canonical bank fact，建立
   `finance_import_manual_review` 財務警示。Identity 為
   `finance-import-row:<finance_import_row_id>`，同一 canonical row 同時最多一筆 active
   review，顯示於「異常警示中心 → 帳務」。
2. 解析缺列、fingerprint collision、occurrence 缺失、批次部分完成或狀態矛盾等
   匯入完整性問題，才以 `IMPORT-006` 投影至 canonical `anomaly_current_alerts`。Identity 為
   `finance-import-batch:<batch_id>`，每 batch 最多一筆，並阻擋該批正式 Apply。

一般 Query 不 scan；只有 import／reprocess outbox 或明確 bounded historical scan Command 可刷新。
Details 不得保存姓名、完整帳號或 raw payload。`IMPORT-006` 的 sample canonical row ids
上限為 20。普通待確認帳務不得同時再形成 `IMPORT-006`；若同一 row 另有完整性故障，
先顯示並處理阻擋型 `IMPORT-006`，完整性恢復後才投影可操作的財務待確認。

### Alert Workflow

```text
open → claimed → resolved
resolved --根條件仍存在或再次出現→ open
```

claim 使用 row lock／version；他人已認領回 conflict。resolve 必須有原因，但不得改正式帳務、derived amount、Domain blocker 或根事實。

### Query／Typed ViewModel

API 回傳 typed summary、detail 與 allowed actions。財務 occurrence 與 current reminder 可同頁顯示，但不能共用同一 status 語意。

#### Public detail／recovery boundary（2026-08-22，Phase 3D-H）

- `display_snapshot`、occurrence evidence、workflow timeline、action source bindings 與 recovery root snapshot
  必須輸出 closed typed variants；raw mapping 不得穿越 `/api/v1/anomalies` 或
  `/api/v1/anomaly-recovery` public boundary。
- definition-owned `display_fields` 是公開 evidence allowlist。缺欄、額外欄位、未知 evidence kind、
  非正整數 numeric identity、非法 ISO date、未知 action／schema version 固定回
  `anomaly_projection_data_integrity_violation`，且 Query 保持零寫入。
- server-owned identity／version 必須保留為穩定公開值；姓名等 PII 只輸出去敏 variant，private navigation
  payload 與 internal recovery bindings 不得混入 display fields。
- recovery action 只公開 owning Domain Preview／Apply metadata、required inputs、capability、completion
  predicate 與完整 typed source bindings；Anomalies route 不執行 repair，也不得把人工 resolve 描述為根事實已修正。

#### React detail／recovery dispatcher boundary（2026-08-24）

- React Anomalies Drawer 只能透過 bounded typed GET client 取得 detail、timeline、evidence 與 recovery
  context；client、schema、adapter 與 page 不得接收 raw dict、拼接 endpoint 或由 definition code 推導業務欄位。
- `anomalies.drawer.detail`、`anomalies.drawer.timeline`、`anomalies.drawer.evidence`、`.root-evidence` 與
  `.recovery` 是穩定讀取 surfaces；`anomalies.card.claim` 與通用 `anomalies.drawer.resolve` 必須原生 disabled，
  不能以 loading、recovery metadata 或人工 resolve 文案冒充根事實已修復。
- 唯一例外是 recovery context 明確註冊 `form_schema_key=finance_import.correction.v1`、owner 為
  `finance_import`、完整 `finance_import_row_identity`／`source_version` bindings 且具有 Preview／Apply
  operation 的 action。React 只能以該 action 的 source binding 預填不可編輯銀行列，再讓人員輸入該
  typed form 所要求的有限 selection、reason 與 evidence；未知 schema、缺 binding、owner／operation 不符
  一律不渲染表單且 fail closed。
- Finance correction 固定為 Preview 零寫入 → same preview versions／fingerprint 的 durable Apply → 只讀
  `correction-outcome` terminal receipt re-query。`202 Accepted` 只表示 worker 已受理；只有 `succeeded`
  且 strict immutable receipt 可讀回時才顯示根事實修正完成，並重新查詢 anomaly。queued／running／failed、
  outcome error 或缺 receipt 不得宣稱修正完成。
- detail／recovery 任一 GET 失敗、404、timeout、abort、stale response 或 schema mismatch，只能在對應
  Drawer 區塊顯示 typed unavailable／error；不得清空仍有效的摘要、跨 Drawer 污染狀態，或發出 POST／PUT／
  PATCH／DELETE（已註冊 Finance correction Apply 除外）。Detail 成功與 recovery 失敗是可並存的
  partial-failure 結果。
- 未取得 terminal receipt 前，UI 不得顯示 repair receipt、完成 predicate 消失或「已修復」；recovery
  404 只代表目前 context unavailable，不改變 Anomalies root、workflow 或 owning Domain 狀態。
- Browser 驗收必須以真 FastAPI＋Vite Network↔DOM 證據確認 typed detail redaction 與局部 unavailable；
  Happy DOM、mock-only、單一 HTTP 200 或 component fixture 不足以證明 recovery positive path。

### Human-assisted Recovery

異常中心必須讓人員完成「看懂 → 確認 → 操作」，但不直接修改任何 source Domain：

- 顯示觸發警報的根事實、事件時間線、目前差額、受影響訂單／assignment／義務及資料版本。
- 依 anomaly code 與 source Domain 回傳 typed `available_actions`，例如修正根事實、重新分類銀行流水、建立 adjustment Preview、建立 reversal Preview、補登服務日、重新 Preview 排班或重試 projector。
- 每個 action 只是一個 owning Domain command link／typed intent；Anomalies 不自行產生金額、日期、ownership 或 target status。
- 人員選擇 action 後先取得 owning Domain Preview，確認影響再 Apply。
- `finance_import_manual_review` 可提供 `CorrectAndPostFinanceImportRow`：
  人員選擇正確帳務類型與關聯義務後，後端在同一 transaction 鎖定 canonical bank fact、
  active alert 與所選義務，重新計算 candidate，驗證銀行金額完整 allocation 且每個所選
  義務精確歸零，再依序 append classification event、寫入 owning Finance ledger／allocation、
  reconciliation receipt 與 alert resolved event。任一步驟失敗全部 rollback。
- 上述 `CorrectAndPostFinanceImportRow` 只處理金額可精確核銷的一般分支。實際金額與義務
  不相等時，必須改走 Registry 指定的 Client Finance、Staff Payables 或 Government Subsidy
  專用 difference／overage command，並驗證「正式 allocation＋remaining／recovery／overpayment
  root＝完整銀行金額」；不得放寬一般 action 或由 Anomalies 自行拆帳。
- 上述「直接修正」只代表 UI 呼叫 typed backend command；UI 不得直接 SQL，且不得修改銀行
  日期、金額、方向、帳號、撤銷碼、raw payload、fingerprint 或 occurrence 等來源根事實。
- 操作成功後由新根事實驅動 projector 自動更新／解除 Alert；人工 resolve 不可取代正式操作。
- 原因或修復方式不唯一時只提供選項與證據，不預選、不自動 Apply。
- 本節的 "available actions" 對所有 active code 都是 delivery requirement；尚未具備完整 owner action
  的 code 必須列入 current remediation backlog，不得以 state-only、tracking-only 或 UI 文案宣稱完成。

### Typed Recovery Action Registry（2026-08-11，已人工確認）

`AnomalyDefinitionRegistry` 必須同時保存定義與有限 action descriptors。每個 descriptor 為
後端 typed result，至少包含：

- `action_key`、業務中文 `label`、`owning_domain`、`form_schema_key`；
- `source_bindings`：由 anomaly context 固定帶入、UI 不可改寫的 bank row、case、staff、
  obligation、recovery、batch/item identity 與 source version；
- `required_operator_inputs`：唯一選擇、reason、evidence、disposition 或 capability；
- `preview_operation`、`apply_operation`、required capability；
- `completion_predicate` 與 Apply 後應重新投影的 definition codes；
- action contract version。

每個 active finance definition 必須顯式二擇一：有完整 `available_actions`，或設
`no_automated_recovery=true`。兩者不可同時成立，也不可同時缺席；後者只代表 state-only，
不得由 UI、相容 API 或人工 resolve 補成未登記的金錢操作。

`no_automated_recovery=true` 只表示系統不能自動 Apply，不表示「不需要人工修正」。每個仍屬
current active anomaly 的 definition 都必須另有 owner-specific 人工 Query／Preview／Apply／receipt／
fresh recheck 入口；若 owner 只允許人工輸入或正式處分，Registry 必須顯示該入口與完成條件。
只有已正式分類為 owner work item、retired 或 audit-only 的 code 才不受這項 active-anomaly
人工閉環要求約束。

Registry 不保存衍生金額。Recovery context assembler 必須向 owning Domain Query 取得 current
remaining、候選 target 與 versions；UI 不得從 alert details JSON 或中文 message 推算 action。

#### 正式 action mapping

| Definition／predicate | Action key | 系統預填 | 人員可輸入 | 完成 predicate |
|---|---|---|---|---|
| `finance_import_manual_review` | `classify_and_post_bank_row` | bank row、batch、fact/alert version | 唯一 classification/target、reason、evidence | row 已由 owning Domain 正式 posting，manual-review predicate 消失 |
| `finance_import_manual_review`（選定客戶入款列） | `apply_client_receipt_overage` | incoming row | case、receivable obligation、收款階段、reason；歧義時唯一 target | receipt 全額存在、receivable 歸零、差額 refund payable 成立 |
| `client_refund_underpayment` | 無第二次 Apply（state-only） | 已建立的退款少匯 source | 無 | 原出款列已由 `finance_import_manual_review` 的客戶退款核銷 Preview／Apply 消費；後續只能以新的同帳戶出款列對原退款單 remaining 重走 Preview／Apply，全部結清才關閉 |
| `finance_import_manual_review`（選定客戶退款出款列） | `apply_client_refund_overage` | outgoing row | case、refund obligation、reason、evidence | refund obligation 歸零且同額差額 recovery root 成立 |
| `client_over_refund_recovery_open` | `match_client_over_refund_recovery`／`collect_client_over_refund_recovery`／`adjust_client_over_refund_recovery` | client recovery；matching/collection 另綁 canonical incoming row | matching：唯一 incoming row、reason、evidence；collection：reason、evidence；adjustment：amount、reason、evidence | matching 只建立關聯、不解除；partial collection/adjustment 更新 remaining 並保留；只有 remaining=0 且 `recovered|adjusted` 才消失 |
| `finance_import_manual_review`（選定月嫂出款列） | `apply_staff_payout_difference` | outgoing row | `underpayment|overpayment`、同一月嫂 payable obligations、reason、evidence | payout 已記錄；少匯投影 remaining／partial，或多匯建立 staff recovery root |
| `staff_payout_underpayment`／`staff_payout_overpayment` | 無第二次 Apply（state-only） | 已建立的 payout difference source | 無 | 少匯在 remaining 清償後關閉；多匯在 recovery 結清／adjust 後關閉；不得重送已消費銀行列 |
| `staff_overpayment_recovery_open` | `match_staff_overpayment_recovery`／`collect_staff_overpayment_recovery`／`adjust_staff_overpayment_recovery` | staff recovery；matching/collection 另綁 canonical incoming row | matching：唯一 incoming row、reason、evidence；collection：reason、evidence；adjustment：必須等於全部 remaining 的 amount、reason、evidence | matching 只建立關聯、不解除；partial collection 保留；staff adjustment 只允許一次處分全部 remaining；只有 remaining=0 且 `recovered|adjusted` 才消失 |
| `GOVSUB-006` | `dispose_government_subsidy_overpayment` | incoming row、receipt、overpayment root、eligible targets、recipient readiness | `offset|return`、offset targets/amounts 或 return due date/recipient snapshot、reason、evidence | overpayment 進入合法 offset 或 return payable 分支，不再 pending_review |
| `GOVSUB-007` | 無 Apply（state-only） | 已解析的 government outgoing row、唯一未結退款單、超額事實 | 無 | 實際多匯保持可見；不得由 alert 自動核銷、抵扣或新增付款義務 |
| `finance_import_manual_review`（選定出款列） | `reconcile_government_overpayment_return` | canonical outgoing row | government overpayment identity、reason、evidence；多筆候選時唯一退款單 | bank row 已對回退款單且 remaining 正確降低／歸零；退款單日期不是配對條件 |

同一 anomaly 若只有一個合法 action，UI 直接顯示該表單；有有限分支（例如政府 offset／return）
時，分支是同一 owning Domain Preview intent 的 enum，不是 UI 自由拼 endpoint。沒有完整 backend
action 時 `available_actions=[]` 並顯示「尚未支援此修復」，不得產生假按鈕。

#### UI dispatcher 邊界

UI 只依 `form_schema_key` 選擇已註冊的 typed renderer，renderer 必須對應單一 bounded Domain
API client。Dispatcher 不接收 raw endpoint、不用 definition code 寫業務 if/else，也不傳未驗證
dict。未知 contract version／schema key fail closed，顯示 `recovery_action_not_supported`。

所有表單流程固定：Query context → Preview → 顯示金額守恆／row changes／blockers → Apply →
顯示 receipt → 重新 Query anomaly。Apply disabled 直到 Preview 成功且 fingerprint、source version、
operator inputs 未改變。timeout 先查 receipt/job；不得換新 idempotency key盲目重送。

#### Registry 驗收

- 每個 active finance definition 必須明確為 `no_automated_recovery` 或至少一個 descriptor；
- action key、schema key、capability 與 contract version 唯一且可靜態驗證；
- source bindings 缺失、跨 Domain、stale 或多義時 Preview fail closed；
- completion predicate 仍成立時 anomaly 保持 open，不因 Apply receipt 或人工 resolve 假結案；
- 新增 definition 未登記 action 時 CI 失敗，但不影響只讀異常清單顯示。

## 3. Modules

- `AnomalyDefinitionRegistry`
- `DetectionPredicate`
- `AnomalyFingerprint`
- `SeverityPolicy`
- `DesiredAlertState`
- `BlockerIntentMapper`
- `BlockerCodeCanonicalizer`
- `SystemAlertReducer`
- `AutoResolvePolicy`
- `ReopenPolicy`
- `FinanceOccurrenceIdentity`
- `OccurrenceIdempotencyValidator`
- `ClaimPolicy`
- `ResolvePolicy`
- `WorkflowTransition`
- `AlertSummaryAssembler`
- `AllowedActionPolicy`
- `RecoveryContextAssembler`
- `DomainActionLinkBuilder`
- `RecoveryCompletionPredicate`
- `RecoveryActionDescriptor`
- `RecoveryActionRegistryValidator`
- `TypedRecoveryFormSchema`
- `ImportWarningIdentity`
- `ImportWarningOccurrenceIdentity`
- `ImportWarningTrackingState`
- `ImportWarningTransitionPolicy`
- `ImportWarningTaskProjector`
- `ResubmissionAssociation`

## 4. Ports 與交易

輸入：

- `DomainFactEventPort`
- `DomainBlockerIntentPort`
- `FinanceReconciliationOutcomePort`
- `FinanceImportReviewDesiredStatePort`
- `FinanceImportCorrectionCommandPort`
- `ImportWarningDesiredStatePort`
- `ImportWarningPredicateQueryPort`
- `ImportResubmissionOutcomePort`
- `ClockPort`

基礎設施：

- `SystemAlertProjectionRepository`
- `FinanceAlertOccurrenceRepository`
- `AlertWorkflowEventRepository`
- `ImportWarningOccurrenceRepository`
- `ImportWarningTrackingEventRepository`
- `ImportWarningCurrentTaskRepository`
- `ImportResubmissionAssociationRepository`
- `OutboxConsumerCheckpointRepository`

Projector transaction：

```text
lock outbox message + fingerprint
→ 驗證 event version／idempotency
→ append finance occurrence 或 upsert current alert
→ 更新 consumer checkpoint
→ commit
```

Projector 失敗可 retry，不回滾來源 Domain。claim／resolve 是獨立短交易。Rescan 只能 auto-resolve 自己 detector/code 範圍的 Alert。

Projector retry 不得無上限。同一 source event 的自動嘗試上限為 3 次，每次失敗必須
保存去敏 error code、attempt count 與 retry-ready time；達上限後轉為不再自動 claim 的
dead-letter，且不得阻擋後續事件。管理員必須能查詢具體 projector、owner event identity、
嘗試數、去敏錯誤與可採取的處理；來源根事實修正後，只能以具 reason、獨立
evidence reference、Preview fingerprint、stable idempotency key 與 immutable receipt 的 typed
Apply 重排。純 retry 不是業務 remediation，也不得解除業務 alert；它只恢復 projector
來重讀 owner root 並重新計算 predicate。

只有已存在較高 owner source version 的成功投影，且 fresh owner root／current alert readback
證明舊事件已被完整取代時，才可以 typed `supersede` 處分 dead-letter。無法解析來源、
無 successor 或 readback unavailable 時固定保持 dead-letter 並引導先修正來源；不得把 status 改成
`delivered`、不得用人工 close 假裝已投影。

匯入警示 transition 使用獨立 outer Unit of Work：鎖定 current task 與 expected version，驗證 actor／fingerprint，
append tracking event、更新 current projection、寫 receipt 與 outbox 後一次 commit。owning Domain mutation 不得加入
這個 tracking transaction；其成功提交後由 committed outbox 或同一 owning transaction 內的 predicate result 驅動 rescan。

Preview固定零寫入；Apply回獨立terminal receipt，含occurrence identity、before/after status、resulting
version、receipt identity、原始correlation與replayed flag，不回PII、note或raw evidence。receipt identity沿用
immutable tracking event identity，同key／同payload回同一receipt並標示replayed；同key／異payload回conflict。已認證
receipt query用於commit結果不明時重查，unknown與malformed receipt必須fail closed。

React presentation必須以strict typed client接續上述狀態機；編輯會使Preview失效，Apply timeout／network／retryable
503只可保留原payload與同一idempotency key進`outcome_unknown`，receipt觀察失敗則保留已收到receipt。只有authenticated
receipt re-query的occurrence、before/after status、resulting version、receipt identity與correlation一致才可顯示tracking
disposition完成。Apply／unknown／re-query期間輸入、分頁與Drawer close均原生鎖定；此完成語意不等於來源根事實修復、
重新匯入或Anomaly Claim／Resolve。

## 5. 驗收

- fingerprint 穩定、duplicate event 不重複。
- active／inactive desired states 能清除舊提醒。
- resolve 後條件仍在會 reopen。
- 修正根事實後自動 resolve。
- Domain blocker 在 Alert resolved 時仍 fail closed。
- finance occurrence replay 不重複，單純 rescan 不新增 occurrence。
- projector 暫停後恢復不遺失事件。
- projector failure 不回滾來源 Domain。
- claim 並行只有一人成功，resolve 原因必填。
- 同一異常能顯示完整 recovery context，且每個 available action 都路由至正確 owning Domain。
- 不唯一的修復情境不會自動建立 adjustment、reversal、服務更正或狀態變更。
- 人員透過 owning Domain Preview／Apply 修正後，Alert 依新根事實自動解除。
- 一般待確認帳務只建立 `finance_import_manual_review`，不重複建立 `IMPORT-006`。
- `CorrectAndPostFinanceImportRow` partial failure 不留下單獨 classification、ledger、
  allocation、receipt 或 resolved alert。
- 銀行金額未完整 allocation 或任一所選義務未精確歸零時，零正式寫入並維持警示。
- 同一來源列的多個欄位警示可獨立補齊及 `auto_resolved`，UI 分組不改變 field-level identity。
- exact source replay 不新增 warning occurrence；新失敗取代舊 task 時由 system 留下 replacement event。
- 人工 `closed` 不改正式 root；root predicate 仍成立時不得回傳資料已修正。
- rootless warning 沒有顯式 prior source association 時，不得以模糊相似度替代或解除舊 task。

## 6. Typed Commands／Results／Errors

Commands：

- `QueryAnomalySummary`
- `QueryAnomalyDetail`
- `ClaimAnomaly`
- `ResolveAnomalyWorkflow`
- `ScanAnomalyDefinition`
- `RetryAnomalyProjector`
- `QueryRecoveryPreviewLink`
- `QueryImportWarnings`
- `PreviewImportWarningTransition`
- `ApplyImportWarningTransition`
- `QueryImportWarningTransitionReceipt`
- `AssociateImportResubmission`

Results 分開回傳 source facts、workflow state、domain blocker、severity、timeline、
available actions、owning Domain、version 與 projection freshness；UI 不得解析 details JSON
推導 allowed action。

Stable errors：

- `anomaly_not_found`
- `anomaly_definition_not_found`
- `anomaly_claim_conflict`
- `anomaly_resolve_reason_required`
- `anomaly_version_conflict`
- `anomaly_source_fact_invalid`
- `anomaly_projection_stale`
- `anomaly_projection_data_integrity_violation`
- `import_warning_transition_not_allowed`
- `import_warning_idempotency_mismatch`
- `import_warning_receipt_not_found`
- `import_warning_receipt_invalid`
- `import_warning_resubmission_association_invalid`
- `import_warning_predicate_owner_unavailable`
- `recovery_action_not_available`
- `recovery_action_not_supported`
- `recovery_action_contract_version_mismatch`
- `recovery_source_binding_incomplete`
- `projector_unavailable`
- `transaction_failed`

## 7. Live writer 退出

- `services/anomaly_alert_detection.py` 與各 finance detector 只產生 typed desired state／fact，
  不直接寫 source Domain。
- `services/system_alert_service.py` 遷移為 current-state projector／workflow adapter；任意
  delete helper 不得用於正式根事實或 finance occurrence。
- `services/finance_alert_wiring.py` 的同步 caller wiring 改為 source Domain outbox。
- `services/finance_alert_workflow.py` 可吸收 claim／resolve concurrency，但不得修改正式
  ledger、差額或 blocker。
- `services/finance_import_review_alerts.py` 不得直接擁有 Finance Import 分類或 dispatch。
- final writer scan 必須證明 finance occurrence/event、system current projection、
  workflow events 與 consumer checkpoint 都只有 Anomalies adapters 可寫。

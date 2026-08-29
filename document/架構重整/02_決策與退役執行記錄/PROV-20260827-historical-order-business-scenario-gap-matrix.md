---
doc_type: scenario-gap-matrix
declared_status: in-progress
date: 2026-08-27
owner: Orders / Scheduling / Anomalies / owning Finance and Contract Domains
current_item: CUR-ANOMALY-MANUAL-REMEDIATION-01
---

# 歷史案件、異常修正與服務變更業務情境差距矩陣

## 1. 用途與施工順序

本矩陣先從實際業務情境定義操作者、根事實、功能、狀態推進與異常終點，再對照
current system 判斷 `REUSE_READY | PARTIAL_GAP | MISSING | AUTHORITY_GAP`。只有情境、功能邏輯、
current gap 與 UI acceptance 都對齊後，才可編譯 implementation work package。

禁止從現有頁面、table 或 function 反推業務；禁止用 tracking close、任意 status editor、receipt-only、
provider success 或前端假計算宣稱情境完成。

## 2. 所有情境共用的人工操作閉環

每個可修正情境都必須具備：

1. **Query**：顯示 exact case／occurrence、哪個 owner root 異常、received／expected、version、
   影響哪個 SOP step，以及合法修正方法。
2. **Preview**：零寫入；顯示會新增、supersede、保留與禁止的 roots，並列出 Orders、
   Scheduling、Client Finance、Staff Payables／Payroll、Contract 與 Anomalies 影響。
3. **Confirm／Apply**：actor capability、reason／evidence、expected versions、fingerprint、idempotency，
   fresh lock／rebuild，一個 outer Unit of Work 與 immutable receipt／outbox。
4. **Readback**：同時重讀 owner roots、11步 projection、active anomalies 與必要的 Finance／Contract
   projection。不能只因 Apply 200 或 receipt 存在就移除警示。
5. **Result**：修好一個 occurrence 只解除該筆；其他問題轉成具體 successor blocker。
   最後一個完成後 umbrella 才從 active list 消失，後續狀態才能繼續。
6. **Fail closed**：stale／identity drift／readback failure／permission denied／outcome unknown 不解除
   alert、不自動重送；保留同 payload／key 的查詢式 reconciliation。

## 3. 情境矩陣

### 3.1 歷史案件建立作業基準

| ID | 業務情境 | 必要根事實與邏輯 | 預期功能／結果 | Current |
|---|---|---|---|---|
| H-01 | 歷史案在 Step N，必要 roots 全齊 | Historical provenance、Orders version、owner bindings、evidence | baseline Q/P/A；Step 1..N-1為 `historical_baseline_completed`，N為current；不伪造owner events | `PARTIAL_GAP`；workflow＋pure Domain focused `25 passed`，repository／schema／API／React／projector仍缺 |
| H-02 | Step N 缺單一必要 root | exact field/root path、owner、version | 建立一筆 actionable occurrence；owner Q/P/A 後 fresh recheck 解除該筆 | `MISSING`；minimum-required-facts assembler／fresh consumer／repository／API／UI referral缺 |
| H-03 | Step N 同時缺多個 roots | occurrence identities、umbrella aggregate | 逐項修正；修一項只減一項；最後一項才移除umbrella | `PARTIAL_GAP`；workflow／pure Domain focused `25 passed`，HCM 3→2→1→0可重用，Historical assembler／repository／API／UI缺 |
| H-04 | 歷史文件確實無法取得 | document kind、affected steps、actor、reason、independent evidence | `historical_evidence_unavailable_accepted`；只解除補找文件blocker，不建立signed／paid／delivered事實 | `PARTIAL_GAP`；Domain validation已有，persistence／capability／UI缺 |
| H-05 | baseline 後案件正常往後進展 | append-only successor lineage、current owner versions | current version可增加；舊baseline不改寫；舊alert依fresh terminal解除 | `MISSING`；outer lineage readback與stage composition缺 |
| H-06 | typed business event 使 current step ordinal回退 | baseline immutable；new event version > prior | baseline不變；current step由earliest-invalidated-root重算；禁止任意status editor | `MISSING`；replacement successor與projection缺 |

### 3.2 月嫂無法服務：服務前整案換人與服務中代班

| ID | 業務情境 | 必要根事實與邏輯 | 預期功能／結果 | Current |
|---|---|---|---|---|
| R-01 | 服務前、只有候選池，月嫂不可服務 | 0 official service day；current pool/version | supersede受影響candidate，依剩餘合法pool回Step 2／3／4 | `PARTIAL_GAP`；matching coordination可重用，atomic replacement Q/P/A缺 |
| R-02 | 服務前、已accepted matching plan，未鎖檔期 | 0 service；accepted plan/segments/version | append replacement event，supersede plan/replies/confirmations，新matching round，current Step 2 | `MISSING`；current `ApplyRematch`只是handoff |
| R-03 | 服務前、已有waiting lock／commitment／簽回 | 0 service；exact lock/commitment/signback bindings | Preview列出supersede/retain；取消舊current locks，保留immutable history，新round不沿用舊recipient gates | `MISSING` |
| R-04 | 服務前已建formal assignment，但官方服務日為0 | 0 actual service；effective generation/assignment/version | atomic supersede／new matching round；effective projection不再顯示舊月嫂；Step 2 | `MISSING`；Assignment Plan不允許empty segments |
| R-05 | 已提供至少一日服務，後續月嫂不可服務 | assignment-owned actual service facts > 0 | 禁止整案回Step 2；referral至既有Leave/Substitution Q/P/A；只重建受影響日 | `REUSE_READY_SOURCE`；typed source/React tests已有，actual-service誤走replacement負例與真Browser `NOT_RUN` |
| R-06 | 代班後薪資與客戶義務 | original/substitute assignments、official days、Payroll/Finance versions | 沿用 current Payroll／Finance impacts；原月嫂已服務金額保留，代班日算新 assignment；不建新公式。正常不要求代班月嫂獨立契約／簽回或客戶追加確認／變更簽署；可選人工 `substitution_note`與可選附件，未填、取消、寫入或附件archive失敗都不阻擋代班、排班 lineage 或薪資 | `PARTIAL_GAP`；核心無新文件 gate `28 passed`；B1／S1／S2已採用，note owner／lineage／method已收旂，但schema／release／API／readback／Browser `NOT_RUN`，維持 `DB_CHANGE_NOT_READY` |
| R-07 | 服務前找不到替代月嫂 | successor round exists；0 legal candidate | 維持Step 2 blocked，顯示可行處置；不恢復舊月嫂、不假推進 | `REUSE_READY`；Matching owner Q/P/A→RPRE Q/P/A→1012 persistence→Apply response canonical readback→no-auth true Browser均PASS；final case `115960427`顯示Step 2、0 candidate、`blocked_no_candidate`、`complete=true`且不宣稱異常解除。 |

### 3.3 訂單取消

| ID | 業務情境 | 必要根事實與邏輯 | 預期功能／結果 | Current |
|---|---|---|---|---|
| C-01 | 服務前取消，無任何正式收款 | actual days=0；Finance no receipt/obligation | Orders取消；履約與不適用付款缺漏alerts消失；不建付款紀錄；公開 Finance impact 明確為 `no_finance_change`、amount=0 | `PARTIAL_GAP`；backend Q/P/A已有，React/runtime未收斂 |
| C-02 | 服務前取消，已收定金／款項 | Finance receipt/allocation | Orders取消成功；建立並保留 `refund_due` obligation／alert至銀行出款核銷；公開 direction 不由 action kind／金額推定 | `PARTIAL_GAP` |
| C-03 | 服務中取消 | operator-confirmed actual dates/staff；owner versions | 逐日確認；Preview列客戶退／補收與各月嫂薪資／追償，每筆 Finance impact 帶 `refund_due`／`additional_charge_due`／`no_finance_change`；Orders alerts與Finance alerts分開 | `PARTIAL_GAP`；backend可重用，React有3個P1待修 |
| C-04 | 全部約定服務已完成後嘗試取消 | actual day count=contract | `order_cancellation_after_full_service`；Orders/Scheduling/Finance/Payroll零寫入 | `PARTIAL_GAP`；backend已有，UI負例oracle待補 |
| C-05 | 取消後仍有真實帳務問題 | current obligations/remaining/allocation | 履約alerts inactive；Finance/Payables/Government alerts依owner terminal保留 | `PARTIAL_GAP` |
| C-06 | 取消帳務公開結果 | 每筆 action 的 server-owned `direction`、`direction_amount_ntd`、`obligation_amount_ntd`、receipt/readback | UI 只渲染明確 direction；`replace_open` 減額與 `cancel_open` 固定 `no_finance_change`／direction amount=0，`create_refund` 才是已有收款後的 `refund_due`；缺漏／不一致／schema drift／outcome unknown 零假成功，不以 action kind 或正負金額猜測 | `PARTIAL_GAP`；Python direction contract `36 passed`；React receipt-first focused `56 passed`且build PASS；真 MySQL／API／Browser `NOT_RUN`，case-scoped anomaly readback 未完成 |

### 3.4 完成案與結清

| ID | 業務情境 | 必要根事實與邏輯 | 預期功能／結果 | Current |
|---|---|---|---|---|
| F-01 | 歷史來源宣稱訂單完成，但缺actual start | Orders completion lineage + actual start missing | 建具體root anomaly；不假完成；owner Q/P/A補齊 | `MISSING` |
| F-02 | 缺official service facts／service-time tuple | effective assignment-owned facts missing | occurrence-level anomaly；補齊後fresh stage projection | `MISSING` |
| F-03 | Client已結清、Staff未結清，或反之 | independent owner versions/remaining | Orders completion與兩邊Finance projection分開；未結清alert保留 | `PARTIAL_GAP`；owner workflows可重用，Historical composition缺 |
| F-04 | Orders completion、Client與Staff各自的terminal owner lineage全齊 | canonical completion + owner-specific terminal settlements；一般銀行路徑使用exact bank/allocation，符合歷史fallback資格時可使用已核准的owner historical event | Step 11 completed；historical operational/import alerts inactive；歷史lineage保留 | `REUSE_READY`；`HOB-F04-ROUTE-A-001` 已在 canonical `lu_test_task96_scenarios_20260827` 由正式bank-backed command lineage推進至 stage-07-settled；typed API／projector／React／no-auth Browser正向PASS。該receipt是合法銀行路徑的既有證據，不代表銀行allocation是歷史案件唯一合法terminal來源。 |

### 3.5 異常修正與系統恢復

| ID | 業務情境 | 預期系統行為 | Current |
|---|---|---|---|
| A-01 | 單一異常、人工從電話取得正確資料 | exact owner Q/P/A補正root；fresh recheck後alert消失與stage繼續 | 42碼中只部分具備 |
| A-02 | 同review有3個問題 | 3→2→1→0；逐項解除，最後一項才移除umbrella | `REUSE_READY_SOURCE`；HCM source 84-test/E3 passed，真owner correction／active-list Browser `NOT_RUN` |
| A-03 | 客戶透過LINE補資料 | recipient/task-bound response進owner Apply；同時保留人工電話入口 | 多碼 `PARTIAL_GAP/MISSING` |
| A-04 | Apply timeout/network/decode，結果不明 | 鎖住盲送；保留same key/payload；重查owner/stage/alerts後才判定 | HOB-D React有P1；其付線型可重用 |
| A-05 | stale/version/identity drift/readback failure | 零寫入或rollback；alert保留；要求fresh Query/Preview | 必須逐情境驗證 |
| A-06 | 人員只改tracking status／備註 | 不解除owner root、不移除alert、不推進stage | rulebook guard已有，UI仍須移除誤導 |

## 4. UI 情境驗收模板

每個 scenario ID 必須有一組可重現驗收；Task96 依最新人工指示以 development `local_bypass` no-auth
在真實 FastAPI／React／canonical `lu_test_task96_scenarios_20260827` 執行。formal persisted-human Session
不再是 Task96 completion gate，但 production authorization contract tests仍須維持 fail closed：

1. 從 Orders 或 Anomalies active list 進入 exact case／occurrence。
2. Detail 能回答「哪裡異常、received／expected、owner、影響步驟、如何解除」。
3. 操作入口只指向正確 owner workbench，不顯示tracking resolve 當主要處理。
4. Preview 前輸入驗證，Preview 後顯示完整跨域影響／blockers，不只顯示泛稱。
5. Apply 需確認、reason／evidence、版本與fingerprint；處理中防關閉／串案。
6. 成功後同時回讀 owner root、Orders card／11 steps、active anomalies。
7. 只修一個問題時只消失該 occurrence；剩餘問題顯示具體 successor。
8. 最後一個問題完成後 umbrella 消失，current step 依正式projection推進或回退。
9. timeout／network／decode 進 `outcome_unknown`，不生成新key盲送；操作者可重查。
10. stale、越權、missing readback、服務中誤走服務前換人與全履約取消皆明確blocker且零假成功。

## 5. Current 總體差距（待三條情境 lane 完整對齊）

- `REUSE_READY`：Leave／Substitution Domain／workflow、Orders cancellation backend、部分 Finance／
  Payables owner Q/P/A、HCM occurrence aggregate、server-owned stage projection。
- `PARTIAL_GAP`：HOB-A workflow／pure Domain focused `25 passed`但 repository／schema／API／React／projector
  未完成；HOB-C 核心無文件 gate `28 passed`且B1／S1／S2已收旂，但note schema／release／API／
  runtime未完成；HOB-D cancellation direction／receipt-first React focused `56 passed`但尚未完成 runtime；HOB-E completion oracle
  combined `60 passed`但尚未接 ports／API／projector／UI；歷史 review remediation、部分 42-code owner actions。
- `MISSING`：Historical baseline outer Q/P/A／storage／API／UI、11步minimum-required-facts assembler／
  occurrence action composition，服務前atomic caregiver replacement／Step 2 successor，完成案aggregate oracle。
- `RUNTIME_PARTIAL`：2026-08-27 已由本專案 Docker Compose 啟動 `mysql_db`，並以 current
  validation manifest `labor-union-validation-schema-2026-08-27-v14` fresh-bootstrap
  `lu_test_task96_scenarios_20260827`（343 objects／342 base tables）；尚未建立scenario business
  data，也尚未啟動API／React或以上述scenario IDs執行Browser驗收，不用mock代替最終UI不卡關證據。

## 6. 2026-08-27 三條 Luna High 情境稽核對齊

| Lane | Source evidence | 確認可重用 | Material gap |
|---|---|---|---|
| Orders／Scheduling | `stage_projection_query.py`、`leave_substitution_workflow.py`、`cancellation_workflow.py`、`auto_completion_workflow.py`；focused 62 passed | 服務中代班、取消backend、auto-completion、server stage projection | 服務前accepted plan／waiting lock／0-service assignment 的atomic replacement；Historical baseline production Q/P/A |
| Finance／Contract／Payroll | `04`、`05`、`16`、`21`規則書與typed impact source | 取消後refund／collection／Payroll impacts、代班薪資lineage、optional note evidence 邊界 | cancellation direction／receipt-first React focused `56 passed`；真 MySQL／API／Browser `NOT_RUN`。代班note的owner／lineage／method已依B1／S1／S2收旂；schema／release／API尚未施工，維持 `DB_CHANGE_NOT_READY` |
| Anomalies／UI | React 41 passed、Python 62 passed；`06`與42-code oracle | occurrence tracking/referral、Government/Staff typed workbench、Substitution React flow | Historical baseline/missing-root UI、pre-service replacement workbench、completion-root remediation、cancellation anomaly isolation／outcome-unknown／readback false success |

### 6.1 已確認 P1（不得以 focused green 宣稱完成）

1. current `ApplyRematch` 只回 `rematch_required`，不建 successor round、不supersede accepted plan／
   assignment／waiting lock，不會使 Step 2 current。
2. HOB-A workflow＋pure Domain focused `25 passed`，但 repository／schema／API／React／projector／outbox／receipt
   仍未完成；不能把 candidate 當成跨層完成。
3. cancellation React 已收旂same payload/key、applying drawer/case guard、late response identity、完整
   Finance／Payroll actions與receipt-first reconciliation，focused `56 passed`且build PASS；case-scoped
   Anomalies readback因缺canonical case binding仍是material gap。
4. Historical review workbench 仍須驗證owner／anomaly readback失敗不留假成功；cancellation UI已有
   owner/card/stage readback但尚未證明case alert已消失且狀態可繼續。
5. completion-root remediation 的 subsystem completion oracle combined `60 passed`，但尚未接 owner
   ports／API／projector／UI；缺 actual start／official service／Client settlement／Staff payout 的情境仍未完成。

### 6.2 2026-08-27 人工裁決已收斂

- 服務中代班正常不需代班月嫂獨立契約／簽回，也不需客戶追加確認／變更簽署；既有契約與
  commitment 保留。人工 `substitution_note` 及S2 method只是 optional note，缺少或 archive 失敗
  不阻擋 substitution、排班 lineage 或 Payroll；真正的 identity／occupancy／version／readback
  blocker 仍 fail closed。對應 `HOB-SUB-A1`、`HOB-SUB-A2`、`HOB-SUB-N1`。
- Client Finance 取消公開結果逐筆必須帶 `direction`：`refund_due`、`additional_charge_due`、
  `no_finance_change`，另帶 `direction_amount_ntd`（客戶現金／待收付影響）與既有
  `obligation_amount_ntd`（義務 delta／新建義務金額）。`replace_open` 減額與 `cancel_open` 固定
  `no_finance_change`／0；`create_refund` 才代表已有正式收款後的退款。amount invariant、schema
  drift、stale、outcome unknown 均不可由 UI 猜測。對應 `HOB-FIN-DIR-A1`、`HOB-FIN-DIR-N1`、矩陣 C-06。
- 上述裁決移除本節的 authority blocker；仍待實作與 runtime／Browser 驗收的差距不再標為
  `AUTHORITY_GAP`，也不因本規格 READY 而宣稱已完成。

## 7. 2026-08-27 package progress 與 runtime boundary

- `WP-HOB-A`：workflow＋pure Domain `25 passed`；repository、schema／migration、API、React、projector
  仍未完成。
- `WP-HOB-C`：核心「沒有代班新契約／簽回也可完成 substitution」gate `28 passed`；
  B1／S1／S2已採用，`substitution_note`及method明確為不影響流程的備註。note schema／release／API
  尚未實作，故維持 `DB_CHANGE_NOT_READY`；不得以note缺漏或失敗阻擋代班。
- `WP-HOB-E`：Orders/Scheduling adapter主代理重驗`26 passed`；Client Finance adapter主代理重驗
  `26 passed`，並在真MySQL兩案回讀無blocker lineage。Orders/Scheduling真MySQL僅absent-case PASS，
  positive尚`NOT_RUN`。Staff Payables因多staff case-level version／settlement lineage未定轉回
  `PROV-20260827-historical-staff-payables-completion-root-spec-gap.md`；API／projector／UI未完成。
- cancellation explicit `direction`：Python `36`；React receipt-first `56 passed`且build PASS；真 MySQL、FastAPI API、
  enabled-human Browser 均 `NOT_RUN`。
- `CLIENTREFUND-001` 與 `PAYOUT-001`：static source closure 已記錄；真 MySQL／API／Browser 仍 `NOT_RUN`，
  不得升格為 runtime completion。

本輪 DDH 依能力、write-set 隔離、Authority 與驗證狀態動態調整計畫與運作模式；所有實際建立的子代理
均為 `gpt-5.6-luna`／`high`。此為執行證據，不改變 package 的 scope、owner、acceptance 或 completion gate。

## 8. 封存 Part 00 測試情境契約的採用範圍

### 8.1 權威邊界

封存文件
Part 00 全域測試資料治理與 Scenario 契約（歷史原文已自工作樹移除）
只作為測試情境設計與既有資料採用方法的參考，不恢復其 `superseded` 狀態，也不覆蓋 current
Global／Domain 規格、根層 `AGENTS.md` 的 2026-08-21 DB 裁決或本矩陣記錄的最新人工裁決。

本次採用下列仍與 current architecture 相容的部分：

1. 每個 scenario 都要有 manifest、root fixture、expected result、command lineage、DB／API／UI
   oracles、receipt 與 inventory；不得只有一段 Browser 操作。
2. evidence applicability 固定標記 `required | optional | not-applicable | blocked`；Browser 只證明
   使用者可見操作與結果，Domain／API／DB invariants、idempotency、retry 與 projector 則由
   pytest／verifier 分開證明。
3. 測試資料不得直接 seed derived status、projection、alert、receipt、outbox 或完成狀態；必須由
   正式 owner command／projector 產生。歷史不可得證據也只能走已裁決的 typed manual command。
4. 既有 scenario 若要採用，先記錄 `source scenario/receipt → current successor scenario`，逐欄
   判斷 unchanged／renamed／re-derived／invalid；舊畫面可操作不代表 current oracle 成立。
5. 警示情境的完整 UI 終點是「顯示具體錯誤 → 抵達 owner 修正入口 → Preview／Apply →
   fresh readback → 警示消失或轉成具體 successor → 回原 Orders／Scheduling 工作區證明 blocker
   已解除且後續操作可繼續」。

### 8.2 本任務的 Route 裁決

| Route | 本任務用途 | Current 裁決 |
|---|---|---|
| Route A／clean replay | 從乾淨 `lu_test_*` 以正式 command 建立核心 root lineage，重播歷史案、換人、取消、完成與異常修正 | **主路線**。canonical target固定為`lu_test_task96_scenarios_20260827`；`HOB-F04-ROUTE-A-001` 已由root fixture＋正式commands建立並保留，API／projector／React／no-auth Browser正向PASS。其他R／C／H／A情境仍須各自依manifest執行，不由F-04結果代替。 |
| Route B／adopt and augment | 採用已存在且可證明的 development rows，補足日常 UI 狀態或特殊邊界 | **後續選配**。只有 current `lu_test_*` 已存在、identity 可盤點、before/after 可回讀且有 scoped cleanup／保留策略時才使用；不得成為 Route A 前置依賴 |

Route A 與 Route B 使用不同 scenario identity／target profile；最終只合併 versioned scenario
artifacts、expected oracles 與 receipts，不合併兩個 DB，也不操作 `union_db` 或 production target。

### 8.3 可重建階段基線

沿用封存 Part 00 的 staged-baseline 概念，但 root、command 與 terminal predicate 全部以 current
規格重定義：

| Stage | Current root baseline | 代表情境 |
|---|---|---|
| stage-00-clean | schema-ready、無 scenario business rows | 全部 Route A 前置 |
| stage-01-order-root | Orders identity／terms／historical provenance | H-01、H-02、F-01 |
| stage-02-matching | candidate pool／contact／reply／selected binding | R-01、R-02、R-07 |
| stage-03-commitment | accepted plan／waiting lock／contract signback／commitment | R-03 |
| stage-04-assignment | effective assignment、official date/time；尚未有 actual service | R-04、C-01、C-02 |
| stage-05-in-service | 至少一筆 assignment-owned actual service fact | R-05、R-06、C-03 |
| stage-06-service-complete | contracted service facts齊全，但 owner settlement可各自未完成 | C-04、F-02、F-03 |
| stage-07-settled | Orders completion、Client settlement、Staff payout皆有各自terminal owner lineage；來源可為一般exact bank/allocation或符合資格的approved historical owner event | F-04 |

每個 stage 只能由上一 stage 的正式 command lineage 推進；R-02～R-04 的服務前換人會 append
successor event 並把 current operational projection 回到 stage-02 所代表的 matching gates，但不刪除
或倒退已發布的 baseline／aggregate version。R-05／R-06 已有 actual service，只能走 substitution，
不得回 stage-02。

### 8.4 Scenario package 最小欄位

| Artifact | 必填內容 |
|---|---|
| manifest | scenario ID／revision／owner／business clock／Route／start stage／dependencies／commands／expected terminal |
| root fixture | 只放可由正式 workflow 接受的根事實輸入與 external test facts；不得放 derived state |
| command lineage | actor、capability、reason／evidence、expected versions、fingerprint、idempotency key、Q/P/A 次序 |
| expected oracle | retained／superseded／created roots、current step、active／inactive occurrence identities、Finance／Payroll／Contract impacts |
| evidence applicability | Domain／Subsystem／API／DB／projector／React／Browser 各自 `required | optional | not-applicable | blocked` 與理由 |
| UI checklist | 進入 exact identity、看懂差異、修正、fresh readback、回原工作區、繼續下一步；另含 stale／403／outcome_unknown／readback failure 負例 |
| receipt／inventory | 使用的 target profile、owned row identities、before/after、cleanup或保留策略、驗證狀態與證據路徑 |

### 8.5 第一批代表性 E2E 與分層覆蓋

第一條完整跨頁 E2E 採 `H-03 + A-02`：Step N 同時缺三個不同 owner roots，操作者逐一修正，
驗證 `3→2→1→0`、umbrella 最後才消失、Orders current step 隨 fresh roots 繼續。這條情境證明
人工修正閉環，但不能取代其餘業務分支。

其餘 scenario 以獨立可 reset package 覆蓋：

- 服務前換人：R-02、R-03、R-04、R-07。
- 服務中代班：R-05、R-06，並加「已有 actual service 卻嘗試整案回媒合」負例。
- 取消：C-01～C-06，分別驗證 Orders alerts、仍真實存在的 Finance／Payables alerts，以及逐筆
  direction／direction amount mapping。
- 完成：F-01～F-04，特別驗證 status-only 不足與三個 owner terminal predicates。
- 安全與恢復：A-04、A-05、A-06，覆蓋 same-key reconciliation、stale、permission、readback
  failure 與 tracking-only false closure。

```yaml
convergence:
  status: READY
  blockers: []
```

`declared_status` 仍為 `in-progress`，因矩陣保留實作／runtime 追蹤；spec convergence 已為
`READY`，可由後續 owner 依 §8.4 自行編譯 bounded task package，且不得把未完成驗收當成已完成。

# 歷史案件作業基準與狀態感知異常規格

- `spec_id`: `PROV-20260827-historical-order-operational-baseline`
- `declared_status`: `approved`
- `current_item`: `CUR-ANOMALY-MANUAL-REMEDIATION-01`
- `owner`: Orders operational projection；各必要根事實仍由原 owning Domain 擁有
- `authority`: 2026-08-27 使用者選擇 append-only lineage，並裁決歷史案件可由人員設定目前 11 步作業基準；基準以前步驟正式投影為歷史基準完成，必要欄位缺漏則轉成可人工補齊的具體異常。歷史文件不可取得時允許具 actor／reason／evidence 的人工處分；Orders completion 與各 Finance settlement 分開；取消不計額外違約金。服務中代班正常不要求代班月嫂獨立契約／簽回，也不要求客戶追加確認／變更簽署，但保留人工追加補充文件的選配路徑，且缺少該文件不得阻擋代班、排班 lineage 或薪資。取消公開 Client Finance 結果必須逐筆帶明確 `direction`：`refund_due`（應退款）、`additional_charge_due`（應補收）或 `no_finance_change`（無帳務變動），UI 不得由 action kind 或金額正負推定。
- `formal_sources`: `01_規格基線/00_Global_共同契約.md` §2、`01_規格基線/01_Orders_Domain.md` §3.1.1、§3.5.1 與歷史 review 更正、`01_規格基線/04_Client_Finance_Domain.md` §3、`01_規格基線/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md` §4.3、各步驟 owning Domain 正式規格

## 1. Objective 與 observable behavior

歷史案件不得因缺少當年 LINE、媒合、簽約或其他逐步操作事件而永久停在無法判斷的異常狀態。已授權人員可選擇案件目前實際位於 11 步 SOP 的哪一步；系統以 append-only `HistoricalOperationalBaselineConfirmed` 語意保存 actor、reason、evidence、選定步驟、當時 Orders version、必要根事實 bindings、Preview fingerprint、idempotency identity 與 receipt。

1. 選定第 `N` 步後，第 `1..N-1` 步正式投影為 `historical_baseline_completed`，第 `N` 步為 current／in-progress；此狀態只適用 Historical Orders，不得套用一般新案件，也不得偽造 LINE delivery、provider callback、簽章、付款、allocation、assignment 或其他不存在的 owner event。
2. 第 `N` 步及後續步驟仍由正常 server-owned 11 步 projection 計算；React 不得由 step number、`orders.status` 或日期自行推進。
3. 每個 step 都有 versioned minimum-required-facts contract。缺任一必要根事實時建立具體 field/root anomaly，顯示缺少項目、owner、影響步驟、合法補正方式與 terminal predicate；不得只顯示「歷史訂單欄位衝突」。
4. 每個缺漏 anomaly 必須提供 owning Domain 的人工 Query／Preview／Confirm／Apply，或明示尚未具備 Authority 的 blocker。tracking、備註或 generic resolve 不得代替補正。
5. owner Apply 後重新讀取 current roots、11 步 projection 與 anomaly predicate；缺漏已補齊時原 alert 從 active list 消失，後續步驟可繼續。若仍缺其他根事實，必須顯示新的具體 blocker／successor，而不是保留無法處理的舊警示。
6. 歷史文件確實不可取得時，可由具權限人員追加 `historical_evidence_unavailable_accepted` disposition，保存文件種類、受影響步驟、actor、reason、獨立 evidence reference、版本、fingerprint、idempotency 與 receipt。它只解除「補找歷史文件」的 operational blocker，不得建立 signed/delivered/paid 事實，也不得解除仍需該根事實才能安全執行的 current/future command blocker。

## 2. Lineage 與版本規則

`exact snapshot` 只用於 Preview／Apply 交易內的 stale gate。非同步投影不得要求 current Orders／assignment snapshot 永遠等於 Apply 當下：

- prior review、baseline、remediation disposition、replacement receipt、owner correction events 與 successor relation 全部 append-only；
- current owner aggregate／lifecycle version 不得小於 baseline 或 remediation result version；
- current version 較大時，必須能由 immutable successor events 連續追溯，合法後續進展不阻擋舊異常解除；
- version 回退、identity mismatch、lineage 斷裂、owner readback unavailable 或 successor 缺失固定 fail closed；
- step ordinal 不是 aggregate version。合法 reversal、controlled reopen 或 cancellation 可以改變 current projection，但必須由 typed owner event 解釋，不得直接覆寫 baseline history。
- baseline selected step 是不可變歷史起點，不因後續作業回退而改寫；但 current
  operational step 可因 version 更大的 typed replacement／reversal／reopen event 回到較早
  ordinal。例如 `v10 / Step 10 → v11 / caregiver_replacement_required → current Step 2`；
  這是新 successor state，不是 version 或 history 倒退。
- 步驟回退只能由 owner root 決定。人員可執行 replacement Query／Preview／Apply 並填寫
  reason／evidence，不得用 baseline editor 或任意 status editor 把 current step 改小。
- caregiver replacement 再分兩條：無任何正式服務事實時才可回媒合；已有任何服務事實時
  不回退 SOP，固定走既有 Scheduling leave／substitution 與 Payroll impact lineage。

## 3. 狀態感知規則

### 3.1 訂單取消

有效 Orders cancellation event 是歷史作業流程的 terminal branch。取消後不再要求補齊候選聯繫、意願、推薦、簽約、未來排班、actual start 或服務完成等只為繼續履約所需的歷史流程資料；相關 historical operational／import-completeness alerts 應轉 inactive。取消不得抹除已發生的服務或金流根事實，並依下列三個互斥分支處理：

1. **服務前取消**：confirmed actual service days 固定為空。若 current Client Finance readback 證明沒有正式收款、退款、補收或其他 open obligation，取消完成後不得為了補齊歷史流程而要求付款紀錄，也不建立 Finance anomaly。若已收訂金或其他款項，取消仍成功，但必須由 Client Finance 建立並保留退款義務直到正式銀行出款完成核銷。
2. **服務中途取消**：操作者必須逐日確認實際服務日期與實際月嫂；未服務的未來日期不得送入 confirmed actual service days。Apply 依正式規則重建 effective Scheduling、重算實際時數與按比例樓層費、Client Finance 應收／補收／退款，以及每位月嫂的應付／差額／追回義務。Orders 取消與歷史履約 alerts 可完成，但 Finance／Staff Payables alerts 只在各 owner 的正式 obligation、ledger、bank allocation 與 fresh terminal predicate 成立後解除。
3. **全部約定服務已完成**：不得再以取消縮減客戶費用或月嫂完整薪資；固定回 `order_cancellation_after_full_service` 且零寫入。後續客訴或帳務爭議必須走各 owner 的 adjustment／refund／reversal／recovery 流程。

取消事件只結束 Orders 的後續履約要求，不是跨 Domain 的 generic resolve。ledger integrity、退款待付、補收、月嫂應付／追回、補助退還及其他仍有真實根因的 alert 必須保持 active；只有 owner 根事實證明不存在或已合法結清時才消失。

現行 React 的逐日日期／月嫂／reason editor、服務前空 actual days 與 strict owner-impact
decode 已有 source candidate，但仍有 `live-drift`：Apply 結果未明時沒有保留同一
idempotency key／payload 的 reconciliation，可產生新 key 盲送；Drawer 關閉／切案後的 late
response 缺少 identity guard；Client Finance／Payroll actions 只顯示部分明細，Apply 後也
沒有重查 Anomalies active list 證明 Orders alerts 消失而真 Finance／Staff alerts 保留。在
outcome-unknown、完整 impact、cross-case stale guard、owner／card／stage／anomaly readback 與 focused／Browser
scenarios 全部補齊前，不得宣稱服務前或服務中取消已有完整 React 人工入口。

### 3.2 訂單完成

不得只因 `orders.status='訂單完成'` 或歷史來源 status code 就清除異常。完成分支至少須由 current owner readback 證明：

- canonical Orders completion lineage；
- `actual_start_date` 的 Orders owner fact；
- assignment-owned official service facts 與必要服務期間／服務時間資料；
- Client Finance 正式義務由canonical bank reconciliation，或2026-08-28核准的pre-system
  historical owner-specific人工付款／結清event，達到本owner terminal；
- Staff Payables 正式義務由canonical bank payout reconciliation，或同一核准歷史人工付款／結清event，
  達到本owner terminal；Client已付款不得推定Staff已付款；
- 規則書另列的 completion-required root 均存在且無 integrity blocker。

缺項時不得把案件偽裝完成；必須產生具體、可人工補齊的必要資料異常。全部成立後，historical operational／import-completeness alerts 才轉 inactive，11 步 Step 11 顯示完成。

### 3.3 進行中案件

進行中案件由人工 baseline step 與 current owner roots共同決定顯示：

- baseline 只回答「歷史上已經走到哪一步」，不替 owner 編造事實；
- minimum-required-facts contract 決定該步是否 `in_progress | blocked | completed | unavailable`；
- 缺根事實時產生 actionable anomaly；補齊後以 fresh projection 推進；
- baseline Apply 與任何必要根事實補正都使用各自的 expected version、fingerprint、idempotency、receipt 與 readback，不合併成任意 root editor。

取消 Preview／Apply 的每一筆 Client Finance impact 都必須原樣公開 server-owned
`direction`，並在 receipt／readback 中保留相同值。`refund_due` 表示客戶應收回款項、
`additional_charge_due` 表示客戶仍應補繳款項、`no_finance_change` 表示本次取消沒有帳務變動；
`direction_amount_ntd` 是非負整數，前兩者必須大於零，後者必須為零；它是客戶現金／待收付
影響，不等同於 `obligation_amount_ntd`。`REPLACE_OPEN` 減額與 `CANCEL_OPEN` 因沒有正式
收款歷史固定是 `no_finance_change` 且 direction amount 為 0；已有正式收款而義務下降才是
`CREATE_REFUND`／`refund_due`。action kind、amount 的正負或顯示順序都不是 UI direction
來源。多筆影響必須逐筆保留，不得先由 UI 合併成一個方向；完整 mapping 以 Client Finance
正式規格 §3 的表為準。
缺少 direction、direction_amount 與 direction 不一致、或 owner readback 無法確認時，回 typed
schema／domain error 或 `outcome_unknown`，零假成功；UI 只能渲染該 enum 的標籤，不得 fallback
或猜測。

### 3.4 服務中代班的契約與文件邊界（2026-08-27 人工裁決）

服務中已存在至少一筆 assignment-owned actual service fact 時，代班是 Scheduling 的受影響
日期 substitution，不是重新建立整案契約。正常路徑固定如下：

1. 代班月嫂不需要獨立服務契約或簽回；客戶不需要為代班追加確認或簽署變更文件。既有有效
   commitment／客戶契約及不受影響日期的簽回、日期與服務根事實保留；代班 identity、日期與
   原／新 assignment 只由 Scheduling substitution lineage 記錄。
2. 系統不得因缺少代班契約、簽回、客戶確認或變更文件而阻擋 substitution Apply、受影響日期
   的正式排班 lineage、actual service readback 或 Payroll obligation／薪資計算。代班日薪資沿用
   既有 Payroll impact／obligation 規則，不由 Orders 或 UI 建立新公式。
3. 工會人員可選擇以人工受控流程追加 `substitution_supplement` 文件／證據。這是 optional
   evidence，必須保存 actor、reason、method、digest／版本與 receipt；沒有文件、文件尚未
   上傳或文件 archive 暫時不可用，都不改變代班與薪資的合法性，也不產生 signed／customer-
   accepted 事實。若補充文件要改變條款、金額或日期，仍須另走相關 owner 的 Terms／Finance
   impact／adjustment command，不得由附件本身改根事實。
4. 代班失敗仍只依 Scheduling／Payroll 的真實 blocker 判定，例如 substitute identity 不存在、
   日期 occupancy conflict、fresh version stale 或 Apply readback 失敗；不得把「未簽新文件」
   當成 blocker。已有 actual service 卻嘗試整案回 Step 2 的 request 仍固定拒絕且零寫入。

### 3.5 取消帳務 direction 的相容與失敗規則

既有 action kind、before／after amount 與 due date 可繼續作為明細，但不是公開語意的替代品。
新／更新的 Client Finance public view 必須對每筆取消 impact 帶 required `direction`，並以
固定 enum 與上述 amount invariant 驗證。舊 caller 若無法驗證 direction，必須顯示 typed
schema-drift／unavailable，而不是以 action kind 或金額正負補值；Apply 結果不明時先以同一
idempotency identity reconciliation，禁止換 key 盲送。

## 4. 11 步 minimum-required-facts contract 待收斂表

| Step | 作業名稱 | baseline 可避免重建的歷史過程 | 不可憑 baseline 偽造的代表根事實 |
|---:|---|---|---|
| 1 | 進件報名與資料完整性驗證 | 當年進件操作軌跡 | Order／Client identity、必要 Orders terms |
| 2 | 候選人加入意願池 | 候選搜尋過程 | 後續使用的 canonical caregiver identity |
| 3 | 發送訂單資訊詢問意願 | 當年 provider delivery | candidate/staff identity 必須存在；現有 Candidate Contact Pool 可用人工資訊確認 Q/P/A 留存 method／reason／actor，且不偽造 LINE delivery |
| 4 | 月嫂回傳接案意願 | 當年 LINE reply | 後續採用月嫂與案件的唯一 binding；現有 matching-plan manual response 可保存特定 segment 的人工意願 |
| 5 | 寄送月嫂履歷給客戶 | 當年 provider delivery | 後續 customer decision／selected staff binding；現有 manual customer profiles Q/P/A 可保存人工說明 evidence |
| 6 | 月嫂契約與簽回 | 單純寄送過程 | 不得偽造簽章或文件；現有 `manual_attested` 只在核准模板版本＋實際簽回檔＋method／reason／actor／plan segment binding成立時可形成正式簽回 event |
| 7 | 客戶定金核銷 | 無 | Client Finance deposit obligation與owner payment／settlement root；對帳單為首要證據，pre-system historical case才可使用核准的owner-specific人工付款event；baseline與status 1不得代替付款 |
| 8 | 客戶契約與簽回 | 單純寄送過程 | matched caregiver／有效 commitment 必須唯一存在；`manual_attested`仍必須有實際簽回 evidence，不接受口頭勾選 |
| 9 | 確認事前服務日期 | 當年 LINE／現場通知過程 | Orders terms、current confirmed-date version、完整日期集合；現有 `manually_confirmed` Q/P/A 可保存電話／紙本／現場確認且不偽造 LINE task |
| 10 | 正式排班與服務履約 | 當年通知過程 | effective assignment、assignment-owned official dates、actual start、服務時間 tuple |
| 11 | 完工驗收與結清 | 當年提醒過程 | Orders completion、Client Finance terminal readback與Staff Payables terminal readback；兩owner各自接受bank-backed或核准historical evidence lineage，但任一付款不得跨owner推定 |

本表的 owner roots 由各正式規格與 2026-08-27 focused rulebook audit 收斂；baseline 只免除重建過去操作軌跡。從 current step 繼續執行所需的 identity、version、assignment、日期、金流或法律根事實仍必須存在，缺漏即產生 owner anomaly，不得直接拿 SQL 欄位存在性或人工勾選代替。

## 5. Acceptance scenarios

- `HOB-A1`：人工選 Step 8，Preview 顯示 Step 1～7 將以 historical baseline 表示、matched caregiver 等必要 facts及缺漏；Apply 後不新增 LINE、簽章、付款或 assignment 假事件。
- `HOB-A2`：Step 8 必要 caregiver binding 缺失時，建立具體 anomaly，顯示缺哪個 identity、如何以 owner Q/P/A補齊；補齊並 fresh readback 後 alert 消失。
- `HOB-A3`：baseline 後 Orders／Scheduling 合法進展使 current versions 增加，outbox 以 append-only lineage 驗證後仍能解除 prior alert，不因 snapshot 不完全相等永久卡住。
- `HOB-A4`：服務前且無任何正式金流的有效取消完成後，歷史履約流程缺漏與不適用的付款缺漏不再 active；若已收款，客戶退款義務與 alert 保留至銀行出款核銷。
- `HOB-A4B`：服務中途取消由人員逐日選定實際服務日期與月嫂，Preview 明列客戶原／新義務、
  各筆 `direction`／`direction_amount_ntd`（退款、補收或無帳務變動）及各月嫂薪資差額；Apply
  後 Orders 履約 alerts 解除，未結清的 Finance／Staff Payables alerts 保持 active。
- `HOB-A4C`：完整履約案件嘗試取消固定回 `order_cancellation_after_full_service` 且 Orders、Scheduling、Client Finance、Staff Payables 均零寫入。
- `HOB-A5`：來源宣稱完成但actual start、official service facts、Client Finance terminal或Staff Payables
  terminal任一缺失時，完成必要資料anomaly保持active。Owner terminal可來自正常bank reconciliation或
  核准的pre-system historical payment／settlement event；Orders status、baseline、Client已付款或Staff已付款
  均不能代替另一owner。全部required roots成立後Step 11與historical alerts才完成／消失。
- `HOB-FIN-HIST-A1`：客戶付款給工會後Client Finance可terminal；工會尚未付款給月嫂時Staff Payables
  仍payable、Step 11仍未完成。客戶補助退款由Client Finance處理，不投影為Government Subsidy完成。
- `HOB-N1`：任意 target status、tracking resolve、receipt-only、provider success、stale baseline、version回退、readback failure或identity mismatch均不得解除 alert或推進 lifecycle。
- `HOB-N2`：baseline step replay同 key＋同 payload回原 receipt；同 key＋不同 step／evidence固定拒絕。
- `HOB-A6`：歷史案已在 Step 10，服務前月嫂突發車禍且必須整案換人。Apply
  追加 version 更大的 replacement event，舊 matching／簽回／排班 lineage 保留但
  對新 round 無效；current SOP 回到 server 計算的 Step 2（若有可沿用候選池則 Step 3／4），
  Orders／Scheduling version 仍單調增加。定金與無關月嫂 identity 的合法根事實保留；
  新月嫂的意願、客戶確認、簽回、日期確認與排班依 fresh gate 重做。
- `HOB-A7`：月嫂無法繼續服務時已有至少一日 assignment-owned actual service fact。
  整案回 Step 2 的 Preview 固定拒絕且零寫入；操作者改走既有 leave／substitution，
  原月嫂已服務日與薪資保留，代班日由新 assignment 與 current Payroll 規則計算。
- `HOB-SUB-A1`：服務中 substitution Apply 不要求代班月嫂獨立契約／簽回或客戶追加確認／
  變更簽署；缺少這些文件不阻擋受影響日期排班 lineage、actual-service readback 或 Payroll。
- `HOB-SUB-A2`：人員選擇追加 substitution supplement 時，系統以獨立 optional evidence
  保存 actor／reason／method／digest／receipt；取消上傳、archive unavailable 或沒有附件均不
  改變代班成功結果，也不偽造 signed／customer-accepted。
- `HOB-SUB-N1`：substitute identity／occupancy／fresh version／readback 任一真實 blocker 仍
  fail closed；以缺少新契約或客戶簽署作為 blocker 是不合法結果。
- `HOB-FIN-DIR-A1`：取消 Preview／Apply 的每一筆公開 Client Finance impact 都帶
  `direction ∈ {refund_due, additional_charge_due, no_finance_change}` 與
  `direction_amount_ntd`；`REPLACE_OPEN` 減額／`CANCEL_OPEN` 固定為
  `no_finance_change`／0，已有正式收款後的 `CREATE_REFUND` 才是 `refund_due`。UI 顯示 enum
  對應標籤，不由 action kind 或正負金額推定。
- `HOB-FIN-DIR-N1`：direction 缺漏、`direction_amount_ntd` 與 direction invariant 不符、schema drift、stale 或
  outcome unknown 時，零假成功且保留同 key／payload reconciliation；不得猜成退款或補收。

## 6. Scope 與未裁決事項

In scope：Historical Orders 的 operational baseline、status-aware field/root anomaly、append-only lineage terminal predicate、11 步 projection、人工補正入口組合、服務中代班的契約／補充文件邊界及取消帳務 public `direction` contract。

Out of scope：直接修改 Finance ledger、偽造 provider delivery／簽章／付款、抹除 immutable review／event、generic anomaly resolve、production deployment或資料 migration。

```yaml
convergence:
  status: READY
  blockers: []
```

`terminal_status`: `SPEC_READY`

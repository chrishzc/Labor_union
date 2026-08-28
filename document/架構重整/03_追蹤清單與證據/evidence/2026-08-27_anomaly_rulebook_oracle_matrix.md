# 42-code 異常規則書解除 Oracle Matrix

- 日期：2026-08-27
- Current item：`CUR-ANOMALY-MANUAL-REMEDIATION-01`
- Authority：`00_Global_共同契約.md`、`06_Anomalies_Domain.md`「全異常人工 remediation 閉環」
- Inventory count：`default_anomaly_registry()` 目前實際載入 42 codes；這只是 live inventory，不是產品必須
  永久保留的 anomaly target。2026-08-27 necessity audit 依最新人工裁決收斂為 33 個 current active anomaly、
  7 個 owner work items、1 個退役 false-positive code、1 個轉為 audit history 並由 successor 接手的 occurrence。

## 判定方式

每個 alert 只能由 owning Domain 的 fresh root readback 重新計算。下列任何單一事實都不等於解除：

- API／job／outbox／provider／通知成功；
- 客戶或月嫂曾回覆，但不是當前 recipient-bound typed response；
- 人員 claim、tracking close、generic resolve、備註「已處理」；
- receipt 存在，但 owner root、remaining、allocation、binding 或 disposition 尚未達完整業務條件；
- detector 自己的較弱欄位判斷，例如欄位非空、舊 timestamp 存在或排班筆數相等。

所有正向解除測試都必須同時有以下負向 oracle：部分完成、外部成功但 root 未成立、stale、owner readback
failure、正式 blocker。任一負向成立時固定保持 active；若產生合法 successor，先建立 successor 與 replacement
relation，再移除原 active alert。

## Import／LINE（9 codes）

| Code | Owner 規則書與 root facts | 完整解除 oracle | 必須保持 active 的代表反例 | Current action 狀態 |
|---|---|---|---|---|
| `BECLASS-001` | `17` counterpart reconciliation；HCM、Client BeClass、accepted mapping、case identity | HCM↔Client BeClass 形成唯一、一致、可追溯 accepted mapping | 只有 `beclass_id` 非空、零／多候選、tracking closed、readback failure | `SPEC_GAP`；需 Case Import typed linking／合法更正來源 |
| `IMPORT-001` | `17` §5.3–5.4；source identity/digest、normalized candidate、field validation、mapping | 修正來源通過該 lane 全部 validation 並由 owner Apply 合法採納 | 只補部分欄位、只收到電話／LINE 回覆、stale source、readback failure | `SPEC_GAP`；缺 received/expected detail 與 owner referral |
| `IMPORT-003` | `17` import reconciliation；counterpart identities、accepted mapping | 重新解析後只有一個合法且一致的 counterpart mapping | `hcm_case_no` 非空、姓名相似、多／零候選、聯絡成功但未 reimport | `SPEC_GAP`；不可在警示中心人工挑候選 |
| `IMPORT-004` | `15` HCM 裁決、`17`；HCM source/digest、case root、field path、validation | prior-warning-bound corrected source 通過 HCM validation 並完成 owner Apply，該 occurrence predicate 消失；同 review 未解數為零時 umbrella 才 inactive | 只修部分欄位、無 prior association、stale、receipt 有但 root 未修正、人工 tracking close、缺 current task／alert | owner resubmission backend 已綁 exact occurrence、fresh root與review aggregate；3→2→1→0 focused regression與 Luna High E3 passed，真 MySQL／active-list runtime `NOT_RUN` |
| `LINE-001` | `23` §2–5；customer binding root/version、subject、Client projection | canonical customer binding 有效、非 revocation pending，projection 與 binding root 一致 | `clients.line_user_id` 非空但無 binding、錯 subject、通知成功、readback failure | `SPEC_GAP`；需 Identity replacement/revocation/manual recovery |
| `LINE-002` | `17` §3.3–3.4、`20`；delivery task、recipient、snapshot/token、typed response event | 一般 task 等待 recipient-bound typed response／decision；目前沒有 overdue／SLA breach oracle | 同 user 任意 webhook、provider sent、舊 token/snapshot、不相關訊息 | `RECLASSIFY_WORK_ITEM`；等待回覆本身不是異常，移入 LINE owner task；未來 SLA breach 必須用新 versioned definition |
| `LINE-004` | `23` §2–5；versioned binding roots、replacement/revocation review、projections | 同 type 多重有效 binding 或 root/projection drift 經合法 disposition Apply 後消失 | 只清 projection、人工 resolve、stale/readback failure；customer＋staff dual-role 是合法狀態 | `KEEP_INTEGRITY`；live SQL 把合法 dual-role 當 conflict，必須修正 producer |
| `LINE-005` | `23` §2–5；staff binding root/version、subject、Staff projection | canonical staff binding 有效且 Staff projection 與 binding root 一致 | `staff.line_user_id` 非空但無 binding、錯 subject、token/通知成功 | `SPEC_GAP`；需 Identity owner action |
| `LINE-006` | `17` delivery/config；recipient、task source、attempt/outcome、provider receipt | recipient/config 合法且 delivery owner terminal outcome 經 fresh readback 完成 | queued/sent、provider success、retry exhausted、config drift、receipt unavailable | `SPEC_GAP`；只有 timeline Query，缺 reconciliation/manual fallback |

## Orders／Scheduling／Delivery（11 codes）

| Code | Owner 規則書與 root facts | 完整解除 oracle | 必須保持 active 的代表反例 | Current action 狀態 |
|---|---|---|---|---|
| `HISTORICAL-ORDER-001` | `01` 歷史 review；review identity、adoption receipt、Orders root、issue codes | 單列更正來源通過完整 Orders validation，寫入 adopted disposition；或 successor 先建立後以 replacement disposition 接手 | workbook 仍有 issue、非唯一列、stale、timeout/readback failure；`unmatched_case` 不應建 alert | owner Q/P/A、successor、React 已接通；persisted-human Browser 尚未完成 |
| `ORDER-001` | `01` §3.1、`02` Candidate Contact Pool；candidate、coverage、info-1 lineage | 正常媒合 work item：建立候選並進行 info-1；目前無 overdue／invalid oracle | 只加入候選、只送通知、legacy timestamp、任意回覆、stale plan | `RECLASSIFY_WORK_ITEM`；「尚未發送」是正常步驟，不是異常 |
| `ORDER-002` | `02` candidate contact；candidate、info-2 delivery、recipient/plan lineage | 正常媒合 work item：accepted candidate 進行 info-2 | `sent_info_2_at`、delivery success、任意 webhook、stale plan | `RECLASSIFY_WORK_ITEM`；目前無 breach／SLA predicate |
| `ORDER-003` | `02` willingness；candidate、recipient、current plan version | 正常等待 work item：當前 recipient-bound willingness/decision | 任意 LINE 回覆、通知送達、舊 plan decision | `RECLASSIFY_WORK_ITEM`；等待回覆本身不是異常 |
| `ORDER-004` | `02` customer decision；matching plan、customer decision lineage | 正常媒合 work item：等待正式 customer decision／matching confirmation | 只發 info-2、月嫂願意、舊日期表確認、delivery success | `RECLASSIFY_WORK_ITEM`；目前無 breach／SLA predicate |
| `DOC-SEND-001` | `02` matching、`17` delivery；固定 object/digest/recipient、durable task | 正常 delivery work item：指定 object/digest/recipient 取得 terminal durable delivery receipt | UI/API 成功、queued、provider success但 digest/recipient drift、readback failure | `RECLASSIFY_WORK_ITEM`；未發送是下一步，只有 terminal delivery failure 才可另投影異常 |
| `SCHEDULE-001` | `02` holiday/schedule；assignment interval、holiday horizon、official dates、daily schedule | holiday＋official-date correction 通過完整 planning predicate | 只補 schedule row、只改 holiday 顯示、未重算 coverage、stale/readback failure | `SPEC_GAP`；唯一 correction command 未裁決 |
| `SCHEDULE-002` | `02` replacement lineage；assignment generation、replacement、service/finance facts | canonical replacement、service outcome 與必要 finance split review 全部完成 | 只換人、只看財務、alert workflow resolved、舊 generation active | `IMPLEMENTED_GUARD`；generic workflow resolved 抑制已移除，replaced root rescan會reopen；真正owner completion predicate與人工remediation仍`SPEC_GAP` |
| `SCHEDULE-003` | `02` assignment ownership；effective intervals、assignment/day owner | 同 caregiver/day 僅一個合法 owner，且有 correction receipt/readback | 只消除一個 overlap、直接改 calendar row、仍有第二有效 assignment | `SPEC_GAP`；target selection/completion 未裁決 |
| `SCHEDULE-005` | `02`、`24`；matching preference/version | 不適用；偏好只影響排序與 explanation，不形成 hard anomaly | live `國定假日必休 + is_work_day` producer 是 false positive | `RETIRE_FALSE_POSITIVE`；移除 producer／current registry，既有 active alert 以 bounded rescan 解除 |
| `SCHEDULE-006` | `02` Assignment Plan；contract days、official dates、coverage、ownership、occupancy、generation | official dates、coverage、ownership、occupancy、generation 全合法且有效服務量等於 Orders 契約量 | 只比 day count、補 schedule rows、忽略 leave/cancel/buffer、stale/readback failure | `SPEC_GAP`；owner Assignment Plan action 未綁 anomaly |

## Finance／Payables／Subsidy（22 codes）

| Code | Owner 規則書與 root facts | 完整解除 oracle | 必須保持 active 的代表反例 | Current action 狀態 |
|---|---|---|---|---|
| `PAYOUT-001` | `05` §3、`16`；payable obligation、bank fact、payout allocation/balance | 所有受影響 payable 經合法 allocation 後 balance=0 | partial、外部匯款成功但未 allocation、帳戶不唯一、stale/readback failure | owner payout Q/P/A存在；scan transaction 已鎖定 owner root，`source_version` 以日期＋root version 單調遞增，已通過 auto-resolution gate |
| `PAYOUT-002` | `05` §3；obligation、due date、late adjustment/payout event | late change 經合法 adjustment/payout 且 root/projection 一致 | 只改日期/projection、receipt success但 root 不一致 | `SPEC_GAP`；只有 review Query |
| `PAYOUT-003` | `05` §3；唯一有效 bank master、obligation、bank fact、reconciliation | unique valid bank master＋exact payout reconciliation | 只補帳戶但未核銷、共用／多帳戶、金額不符、stale | `SPEC_GAP`；bank master correction 未綁 anomaly |
| `GOVSUB-001` | `14` §3–4；government bank fact、approved batch、outstanding/allocation | bank fact 唯一對應 approved batch 並 exact allocation | partial、款已入但 batch 不唯一、stale/readback failure | `SPEC_GAP`；bindings/Apply/React 缺 |
| `GOVSUB-002` | `14` §4.3–4.4；receipt、claim items/outstanding、M:N allocations | selected allocations exact 且總額守恆 | partial、receipt exists但 allocation 不完整、候選歧義 | `SPEC_GAP`；缺完整 descriptor/React |
| `GOVSUB-003` | `14` §6；receipt/allocation、batch revision、integrity projection | current revision 無任何 ledger/projection integrity blocker | 只修 projection、retry/outbox success但 roots 矛盾、readback unavailable | `SPEC_GAP`；Query/retry 不是修復 |
| `GOVSUB-004` | `14` §3、§5；原 receipt/allocation、reversal bank fact、remaining | 原receipt與allocation唯一時owner可執行合法partial／exact reversal；alert仍須由專屬fresh terminal binding另行判定 | 多個remaining allocations無法唯一分配、over reversal、invalid receipt、stale/readback failure；合法partial本身不是歧義，但不能單憑receipt解除alert | owner reversal Q/P/A存在；完整anomaly binding未完成，auto-resolution fail closed |
| `GOVSUB-005` | `14` §6；frozen claim、assignment/service facts、revision | 合法 revision/correction 後 frozen claim 與 official facts 一致 | 只改一欄、核准/receipt 成功但 drift 仍在、readback failure | `SPEC_GAP`；current/frozen correction contract 不足 |
| `GOVSUB-006` | `14` §4.5.1；overpayment root、payer、offset targets/return recipient | status 離開 `pending_review`，進合法 offset 或 return branch | partial offset、receipt/outbox success但仍 pending、無 eligible target、stale | owner disposition Q/P/A 已有；persisted-human Browser Apply 尚未完成 |
| `GOVSUB-007` | `14` §4.5.1；outgoing row、既有 return payable、remaining/overage | owner reconciliation 後 remaining 正確，超額另有合法處置 | 自動部分核銷、建立新退款單、日期猜配、readback failure | `SPEC_GAP`；需 bounded reconciliation command |
| `client_over_refund_recovery_open` | `16` §3.5.1；refund/recovery root、remaining/status | remaining=0 且 status=`recovered|adjusted` | matching-only、partial、receipt exists但 root 未 terminal、stale | owner match/collect/adjust backend 已有；完整 UI/projector evidence仍補強 |
| `client_refund_underpayment` | `16` §3.6；refund obligation、已消費 outflow、remaining | 後續新的合法 outgoing rows 使原 refund remaining=0 | partial、外部匯款但未匯入核銷、重用原 bank row | `SPEC_GAP`；state-only，缺新 row owner referral |
| `staff_overpayment_recovery_open` | `16` §2.4.2；staff recovery root、remaining/status/version | remaining=0 且 status=`recovered|adjusted` | matching-only、partial collection、非全額 adjustment、stale/readback failure | owner backend 已有；完整 React/projector evidence仍補強 |
| `staff_payout_underpayment` | `16` §2.4.1；payout allocation、remaining payable | 後續新的 canonical payout 使 remaining=0 | partial、receipt exists但 remaining>0、重用原 row、readback failure | `SPEC_GAP`；state-only，缺新 bank-row referral |
| `staff_payout_overpayment` | `16` §2.4.2；payout、obligation allocation、recovery root | 建立合法 `staff_overpayment_recovery_open` successor 後，由 successor 負責至結清／adjustment | successor 未建立、lineage 不完整、recovery root 無法讀回 | `MERGE_TO_SUCCESSOR`；本碼只留 immutable occurrence/history，active list 不得與 recovery-open 重複 |
| `finance_import_manual_review` | `09` §6.1、`22` §5.2；canonical bank fact、classification、obligations、versions | owning Domain 完成正式 posting/allocation，manual-review predicate 消失 | classification/job/receipt success但 ledger未成立、partial、stale | generic correction與六種正式 classification owner dispatcher均已實作；Python六型＋拒絕`non_business_review` 13 tests、React六型selector/exact-oracle 16 tests已通過 |
| `CLIENTREFUND-001` | `06` action table、`16` §3.6；refund root、return/reversal linkage、progress | valid refund-return linkage 且 owner progress readback 完成 | return receipt exists但 target/progress錯、partial、stale | action有實作；detail allowlist／完整 predicate仍需收斂 |
| `IMPORT-006` | `09` §6.2、`06` integrity；batch、occurrences、collision/missing/partial counts | 全部 integrity conditions一致，`integrity_inconsistent_count=0` | retry/job success但 duplicate/missing/partial仍存在、readback unavailable | `LIVE_DRIFT / AUTHORITY_GAP`；canonical root version已存在於`finance_import_batch_contracts.batch_version`，但projector仍預設0且未在同一transaction鎖定batch contract／完整性根集合；source-only契約核准前auto-resolution fail closed |
| `RECEIVABLE-001` | Client settlement規格 §2–3；逾期 open receivables/remaining | 本碼所有逾期 receivable obligations remaining=0 | partial、聯絡/receipt success、錯方向/類型、stale/readback failure | owner Q/P/A與既有runtime已完成；scan transaction 已鎖定 account／完整 obligation set，日期＋aggregate version 單調版號已通過 auto-resolution gate |
| `CLIENTPAYABLE-001` | 同上；逾期一般 refund/adjustment payables，不含 subsidy return | 本碼所有一般 payable remaining=0 | partial、外部付款/receipt但 remaining>0、混入 subsidy return | owner Q/P/A與既有runtime已完成；同一 transaction-bound owner lock 與單調版號已通過 auto-resolution gate |
| `RETURN-001` | 同上；逾期 subsidy-return payable | 所有 subsidy-return obligations remaining=0 | partial、外部退款/receipt但 remaining>0、混用一般 refund | owner Q/P/A與既有runtime已完成；同一 transaction-bound owner lock 與單調版號已通過 auto-resolution gate |
| `SUBSIDYADVANCE-001` | `04`、`14` §3；entitlement、government allocation、Staff advance/payout、recovery link | `union_advance_due` 是 Staff Payables typed Preview／Apply work item，非異常 | 只 payout 或只收政府款、重複 payout、link 未成立可另形成 owner integrity anomaly | `RECLASSIFY_WORK_ITEM`；移出 anomaly registry，保留正式工作項與 recovery lineage |

## Coverage 與發布門檻

- 上述 partition 為 `9 + 11 + 22 = 42`，與 live registry inventory 完全相符；necessity audit 後的目標分布為
  `33 active anomalies + 7 owner work items + 1 retired false positive + 1 audit-only successor occurrence`。
- 舊文件中的 `SCHEDULE-004`、`LINE-003`、`IMPORT-002`、`MATCH-SEND-001`、snake_case Staff labels 與
  field-level logical warning codes不是額外 current canonical codes；必須透過 owner lane＋field path，或另立
  正式 canonical mapping，不能直接 seed alert。
- `SPEC_GAP` 的 kept anomaly 固定 fail closed；在 owner 規則書、root/version、action、detail、
  Preview/Apply、receipt/readback、正負向 oracle 未完成前，不得發布自動解除。
- `RECLASSIFY_WORK_ITEM`／`RETIRE_FALSE_POSITIVE`／`MERGE_TO_SUCCESSOR` 不得以 fail-closed 永久留在 active
  anomaly list；必須先交付 replacement/history/successor read model，再以 bounded rescan 清除既有錯誤投影。

## 2026-08-27 42-code necessity／reachability audit

三條互斥 Luna／high 唯讀 lane 逐碼檢查 current producer、owner rulebook、人工 remediation、auto-resolution
與 live drift，聯集精確為 42、無重複或遺漏。DDH native reconciliation 為 `passed`，terminal receipt 位於
ignored `scratch/task96-drift-audit-20260827/native-terminal-r3.json`。主代理依最新人工裁決完成跨 lane
語意校正；子代理的「live producer 可達」只證明現況會產生，不代表產品上應繼續把它叫做異常。

Current registry capability 數字必須分開解讀：42 definitions；27 碼有 action descriptor，其中 17 碼只有
Query／navigation／referral，10 碼有 typed Apply descriptor；15 碼完全沒有 descriptor；另有 10 碼具
versioned auto-resolution contract。這些集合互不等價，不能再用「有 action」或「可自動解除」冒充人工
remediation 已完成。

除上述 9 個移轉／退役／successor disposition 外，其餘 33 碼均保留，但仍須修正 lifecycle 與 producer
predicate。例如 `BECLASS-001` 不得掃描已取消／已完成且無 counterpart 義務的訂單；`SCHEDULE-001` 需區分
尚在規劃期的一般工作與服務已開始／已超過決策期限的真異常；`SCHEDULE-002` 不得把每筆合法 replaced root
永久投影 active；`LINE-004` 不得把合法 dual-role 當衝突。`KEEP_INTEGRITY` 代表即使健康 typed write 理論上
阻止新錯誤，仍因 legacy import、external drift、migration、concurrency 或 partial failure 而保留偵測與人工
recovery，不能因「正常新資料不會發生」直接刪除。

## 2026-08-27 規則書 fail-closed gate 實作

- `domains/anomalies/registry.py` 現在為每條可發布的自動解除保存 versioned
  `AutoResolutionContract(owner_rulebook_reference, terminal_predicate)`；42 codes 中目前10碼同時通過
  owner終態與fresh-root/version稽核，其餘32碼即使detector暫時回報inactive，既有active alert
  仍保持 active。這是 migration 前 live behavior；其中被裁決為 work item／retired／audit-only 的碼不得以
  fail-closed 為由永久留在異常中心，須依 necessity migration 安全清除。這項白名單只裁決
  auto-resolution，不代表該碼人工 Query／Preview／Apply 已完成。
- tracking `resolved` 不是 owner root；下一次 rescan 在根因仍存在或 code 無已確認 terminal contract 時會回到
  `open`。`finance_import_manual_review` 的 legacy warning 也不再因 generic correction／dispatch event 自動變成
  `auto_resolved`。fail-closed 時 generic current-state projector 保留上一份 actionable detail；finance root-fact
  projector 則把 snapshot 保持 `root_condition_active=true` 並標記 rulebook-contract blocker reason，避免畫面顯示
  active 卻把問題詳情覆寫成「無異常」。
- HCM field warning 是目前唯一明列的 legacy warning auto-resolution contract：correction outbox 消費時先鎖定
  prior-warning-bound HCM current facts，要求 logical code 為 `HCM-FIELD-001|002`，且 current root fingerprint
  仍等於 committed correction event 的 `root_after_fingerprint`；stale 或跨 code 固定 fail closed。同一
  review 中每個 occurrence 獨立解除，人工 `closed`不是terminal；只有未解數從3→2→1→0的最後一筆
  owner correction 完成後，`IMPORT-004` umbrella 才能 inactive。
- `IMPORT-006` 的 integrity total 已納入 duplicate occurrence；`PAYOUT-001` 與 Client Settlement 三碼改以正的
  current remaining/balance 為 active 根事實，不再讓不一致的 `settled|completed` tracking status 隱藏欠款。
- `GOVSUB-004` 的單一 allocation partial reversal 可是合法 owner 操作，但規則書尚未把該操作完整綁定到
  特定 alert 的 fresh terminal predicate，因此撤出自動解除白名單；`GOVSUB-006` 在 authorized disposition
  進入 `offset_reserved|return_payable` 後由正常 successor workflow 接手，不被誤改成「remaining 必須歸零」。
- 後續Luna/high source audit證明`PAYOUT-001`與Client三種逾期的日期版號及未鎖定scan存在同日stale clear；
  現已改為transaction-bound owner lock與daily-root單調版號，四碼恢復白名單。`IMPORT-006`、`LINE-001/005`
  仍缺足夠fresh contract。Historical雖已保存／重讀Orders snapshot，但全snapshot等值與合法後續lifecycle
  進展的語意尚未收斂，仍fail closed。HCM legacy warning已補完整event／root binding。
- focused integration `50 passed`、HCM multi-occurrence final focused `84 passed`、current broad regression
  `373 passed, 18 skipped`；服務與 MySQL 依使用者
  說明未啟動，runtime evidence 為 `not_run`。詳細 receipt：
  `2026-08-27_anomaly_rulebook_auto_resolution_guard_receipt.md`。

## DDH 執行證據

本輪使用三條互斥、唯讀 E4 lanes，分別稽核 Finance、Orders/Scheduling/Staff、LINE/Import/Historical；
三個子代理均明確為 `gpt-5.6-luna`／`high`，禁止 nested delegation，workspace effects 為零。三條均在每兩分鐘
監控週期內 terminal；主代理是唯一 evidence integration writer。規則書稽核後發現多碼 owner authority 不足，
因此動態模式由 E4 read-only discovery 收斂為序列 integration，沒有派發任何猜測性的 implementation writer。

本次再稽核原投影為三條 E4 read-only owner-family lanes，兩條成功建立且均為
`gpt-5.6-luna`／`high`；第三條因 Host thread quota 未建立，由主代理完成同等 Orders／Scheduling 規則書
唯讀稽核。DDH reconciliation 如實記錄 2 completed／1 blocked，隨 capability delta 將剩餘工作重投影為 E2
主代理單寫整合；未把 quota 拒絕或未啟動 lane 算成多代理成果。

較早候選凍結後沿用同一 `gpt-5.6-luna`／`high` agent 進行 E3 唯讀驗證。round 1 有三項讀到 stale candidate，
並把 alert predicate 誤等同 successor workflow 全部結清；主代理以 current source 與 `14` 規則書明文要求
fresh recheck。round 2 結果 `PASS`，P0/P1=0；唯一 P2 是 allowed-contract metadata 測試可更精確，已補成
14 碼 exact predicate／version 對照。final-delta round 3 當時結果為 `PASS`、P0/P1/P2=0；其後新增的兩條
Luna/high rulebook/source audit 找到 stale-root P1，已明確使該舊 candidate 與驗證失效，並將剩餘工作從
E4 唯讀稽核重投影為 E2 單一 writer。current 5-code candidate另由明確指定的`gpt-5.6-luna`／`high`
agent完成fresh E3驗證：17 passed，P0/P1/P2=0；此PASS不回溯恢復舊14-code candidate。其後E4三條互斥
writer修正Historical、PAYOUT與Client；PAYOUT／Client cross-lane E3為45 passed且P0/P1=0。Historical verifier
兩度未在監控週期內收斂並被中止，因此不算成果；current 9-code candidate不含Historical。

2026-08-27 necessity catalog execution：registry 現已保留完整 `codes()` 42-code 歷史目錄，另以 definition
lifecycle 精確投影 `33 active / 7 work_item / 1 retired / 1 audit_only`。精確集合測試與既有 rulebook／route
regression 合計 `30 passed in 0.33s`，`py_compile`、strict UTF-8 與 `git diff --check` 均 PASS。本切片沒有
改 producer、reducer、DB、API 或既有 alert，因此只證明 catalog 分類，不證明 legacy alert 已移轉或 UI 已
排除9碼。

本切片的 DDH E3 Luna High exact-patch lane 連續兩份 proposal 分別違反精確代碼分區、破壞 authority digest／
patch syntax；主代理均在套用前拒絕。能力／品質狀態 material 改變後，剩餘切片重投影為 E2 主代理 writer，
最終補丁耗時 `0.251s`。這項動態調整與兩份未採用 proposal 不構成驗收成功，只有 current worktree 與上述
測試輸出是本切片程式證據。

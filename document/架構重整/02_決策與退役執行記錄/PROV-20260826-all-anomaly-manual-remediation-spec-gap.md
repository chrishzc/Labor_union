# 全異常人工 remediation 收斂缺口

- 狀態：`in-progress`
- Current ID：`CUR-ANOMALY-MANUAL-REMEDIATION-01`
- Authority：使用者於 2026-08-26 明確要求「所有異常都應該要有人工修正的功能」。
- 正式 owner：Anomalies 作 capability composition；每個 source Domain 保有自己的 root correction。
- controlling specification：`01_規格基線/00_Global_共同契約.md` §2、
  `01_規格基線/06_Anomalies_Domain.md`「全異常人工 remediation 閉環」。

## Scenario 與目標

操作者由異常中心看見一筆 active alert 後，必須能取得受驗證的 owner context，完成
`Query/Preview → Confirm → Apply → receipt/readback → predicate recheck`。根因確實消失時 alert 自動解除；
仍無法唯一判斷或證據不足時保留 clear blocker，不得以 tracking close、claim、generic resolve 或 UI 文案
假結案。每個 code 的解除 predicate 還必須逐一對照 owning Domain 正式規則書的真實業務流程；不得只因
API、job、通知、tracking 或外部聯絡成功就解除，也不得以 detector 自訂的較弱條件取代 owner 規則。

## 現況與 scope

目前 registry 現場載入 42 個 code，但 2026-08-27 necessity audit 已確認它只是 inventory，不是產品目標：
33 個保留為 current active anomaly、7 個移回 owner work queue、`SCHEDULE-005` 退役、
`staff_payout_overpayment` 只留 immutable occurrence/history 並由 `staff_overpayment_recovery_open` successor
接手。現況 27 碼有 action descriptor，其中 17 碼只有 Query／navigation／referral，10 碼有 typed Apply
descriptor；15 碼沒有 descriptor；另有 10 碼具 versioned auto-resolution contract。這四個數字不能互相
替代，也不代表 owner-specific 人工 remediation 已通過。

本包涵蓋每個 active code 的 owner、source bindings、capability、operator inputs、Preview／Apply、
completion predicate、negative path、receipt/readback 與 React／owner-workbench entry；並須逐碼聲明
自動修正渠道（若安全可行）與不依賴該渠道的人工修正渠道。detail 必須說出具體 field/rule、遮罩後
來源與期待值、流程阻擋、修正輸入與完成條件；tracking 不是 remediation，也不是 UI 的主要終點。歷史訂單是第一個
使用者發現的 scenario，但不可以它的特殊 UI 取代其餘 code。

排除：Anomalies 直接寫 root、任意 status 編輯、通用 `corrected_fields` 表單、production／`union_db`、
provider 假送達與未獲 owner 規格允許的 schema／data migration。

## 已知分組與交接

| 分組 | Current evidence | 必要 successor |
|---|---|---|
| 現有完整 UI action | `finance_import_manual_review`、`CLIENTREFUND-001` | 重驗 contract，確認每次 Apply 後 predicate recheck。 |
| owner backend 已存在、UI 缺口 | `GOVSUB-006`、`client_over_refund_recovery_open`、`staff_overpayment_recovery_open` | 擴充 typed renderer／owner workbench entry，不得在 Anomalies 拼 endpoint。 |
| 僅導航／查詢／retry | matching、delivery、payables、schedule、import integrity 等 | owner 先定義可完成 repair command，navigation 本身不算 remediation。 |
| 無 action／tracking-only | LINE binding、BeClass、schedule 與 state-only finance codes；`HISTORICAL-ORDER-001` 已拆出 | 先完成 owner root-fact／disposition contract；不得先加 close button。 |
| historical Orders first slice | `HISTORICAL-ORDER-001` | 已由 `PROV-20260826-historical-order-review-remediation-work-package.md` 定義 immutable disposition／correction workbook 契約；依其 DB gates 實作與驗收。 |

## 2026-08-27 necessity audit 校正

異常中心不承接一般 11 步驟 work item。`ORDER-001`～`ORDER-004`、`DOC-SEND-001`、`LINE-002` 與
`SUBSIDYADVANCE-001` 現行 predicate 都只表示正常下一步／等待／到期工作，沒有 breach 或 invalid oracle，
固定移回 owner work queue；若未來需要逾期警示，必須另定 SLA、business clock、root/version 與新的
definition contract。`SCHEDULE-005` 與 preference-only Authority 衝突，固定退役。Staff payout overpayment
建立 recovery root 後只顯示 `staff_overpayment_recovery_open`，原 difference occurrence 留 audit history，
不得在 active list 重複要求人員處理同一根因。

這些移轉不是直接刪資料：先交付 work queue/history/successor read model 與 bounded rescan，再移除 current
registry producer，證明既有 active alerts 解除且後續流程仍可操作。其餘 33 碼繼續依本包補 owner-specific
人工閉環；其中 healthy typed writes 理論上不會產生、但 legacy／import／external drift／concurrency 仍可能
造成的 integrity code 必須保留，不能只因新流程有 validation 就刪除。

## 已確認的 auto-resolution live-drift

| Code | Live evidence | 正式規則衝突 | 處置 |
|---|---|---|---|
| `SCHEDULE-002` | `process_reminder_anomaly_source.py` 以已人工 `workflow_status=resolved` 的 assignment ID 令 `active=false` | `02_Assignments_Scheduling_Domain.md` 明定 `replaced` 僅為 legacy 相容；人工 alert workflow 不是 Scheduling 根事實 | 在 owner 規則與 canonical replacement／financial review completion fact 收斂前保持 fail closed，不得因人工 resolve 停止重開。 |
| `LINE-001`／`LINE-005` | detector 直接以 `clients.line_user_id`／`staff.line_user_id` 非空判定解除 | `23_LINE身分管理與解除正式規格.md` 明定這些欄位只是 projection，`line_identity_bindings` 才是 SSOT | 改由 LINE Identity owner 的 verified current binding predicate；projection 非空不足以解除。 |
| `LINE-002` | detector 只檢查同一 LINE user 在 task sent time 後是否出現任意 webhook event | 正式流程要求 recipient-bound typed decision／task evidence；任意後續訊息不能證明該任務已回覆 | 在 task-specific response correlation 規格與 owner query 完成前保持 active；不得以任意 webhook 回覆解除。 |
| `LINE-004` | detector 以 legacy client／staff projection 欄位相同判斷 conflict 是否消失 | LINE Identity 正式 owner 是 versioned binding root，projection 清空或漂移不能單獨證明 conflict 已合法處置 | replacement／revocation Preview／Apply receipt 與 current binding readback 必須共同成立後才解除。 |
| `GOVSUB-006` | disposition Apply 會寫 offset／return outbox，但 anomaly consumer 只消費 `government_subsidy_overpayment_established` | `14` §4.5.1 明定 authorized offset／return decision 使 root 離開 `pending_review`；alert 必須依此解除 | consumer fresh-read current overpayment status，消費合法 disposition events；不能只在 UI Apply 後 rerun。 |
| `client_over_refund_recovery_open`／`staff_overpayment_recovery_open` | live consumer 等 recovery matching 才建立 alert，且 partial/update event 未完整重新投影 | `16` 明定 recovery root 在 open/partially_recovered 時即是待處理根事實，remaining 歸零才結清 | root establishment 即 active；每次 update 重讀 remaining/status，partial 保留並更新，full/adjust 才 inactive。 |
| 全碼 generic `/resolve` | `api/routes/anomaly_registry.py` 可對任意 fingerprint 呼叫 `AnomalyApplication.resolve` | `06` 與 `17` 明定 tracking/claim/manual resolve 不得代替 owner root correction | application boundary 已 fail closed 拒絕 `anomaly_manual_resolve_forbidden`；保留 route 相容邊界但零 mutation。 |
| `finance_import_manual_review`／`CLIENTREFUND-001`／`IMPORT-006` | manual correction/reversal 存在較弱 inactive 判定；`IMPORT-006` active sum 曾漏 duplicate occurrence | `09`、`16` 要求 owner posting/allocation/return linkage 與完整 integrity root readback | `IMPORT-006` duplicate sum 已修正；generic finance correction／dispatch 不再自動關閉 legacy warning，canonical manual-review 因無 rulebook terminal contract 固定 fail closed。`CLIENTREFUND-001` 仍只依已驗證 linkage/progress predicate。 |

以上是現況證據，不自行補造缺少的 owner 業務規則。42-code source map 與
獨立規則書等價性稽核已完成；多數 code 的 owner command 仍是 `SPEC_GAP`，不得因稽核完成就宣稱 remediation 完成。

## 42-code owner／規則書 source map（2026-08-26）

Canonical partition 固定為 Import／LINE 9、Orders／Scheduling／Delivery 11、Finance 22；
`BECLASS-001` 由 Case Import lane 擁有，`IMPORT-006` 由 Finance Import lane 擁有。三條 Luna High
read-only audit 與獨立 coverage verifier 證明 union 恰為 registry 42 codes、無 missing。

| Code | Owner 規則書 | 業務解除基準摘要 | 收斂狀態／主要缺口 |
|---|---|---|---|
| `BECLASS-001` | `17` BeClass counterpart | 唯一且一致 Client BeClass↔HCM accepted mapping | `SPEC_GAP`：泛用匯入未綁 warning；live 只看 `beclass_id`。 |
| `IMPORT-001` | `17` §5.3–5.4 | 修正來源通過 lane validation 並合法採納 | `SPEC_GAP`：缺 field received/expected 與 owner referral。 |
| `IMPORT-003` | `17` import reconciliation | 唯一且一致 counterpart mapping | `SPEC_GAP`：live 以 `hcm_case_no` 非空即清除。 |
| `IMPORT-004` | `17` HCM Case Import | HCM corrected source Apply 後 field warning predicate 消失 | `IMPLEMENTED_SOURCE`：exact occurrence binding、逐項auto-resolve與umbrella 3→2→1→0 source已完成；真owner correction／active-list Browser仍`NOT_RUN`。 |
| `LINE-001` | `23` §2–5 | canonical customer binding root 成立且 projection 一致 | `IMPLEMENTED_GUARD`：detector 已要求 bound＋customer subject/reference＋Client projection一致，relation drift／缺 root／revocation/whitespace fail closed；人工 remediation 仍 `SPEC_GAP`。 |
| `LINE-002` | `17` §3.3–3.4、`20` §3.3 | task-specific recipient-bound reply／owner completion | `RECLASSIFY_WORK_ITEM`：等待回覆沒有 SLA breach，不是異常；live 任意 webhook predicate 亦不合法。 |
| `LINE-004` | `23` §2–5 | 合法 replacement/revocation disposition＋binding readback | `KEEP_INTEGRITY`：dual-role 已裁決合法；live cross-role conflict SQL 必須修正。 |
| `LINE-005` | `23` §2–5 | canonical staff binding root 成立且 projection 一致 | `IMPLEMENTED_GUARD`：detector 已要求 bound＋staff subject/reference＋Staff projection一致，缺 root／revocation/whitespace fail closed；人工 remediation 仍 `SPEC_GAP`。 |
| `LINE-006` | `17` §3.3–3.4、`20` §3.3 | recipient/config 合法且 delivery owner outcome 完成 | `SPEC_GAP`：只有 timeline Query，無 inactive/readback 閉環。 |
| `HISTORICAL-ORDER-001` | `01` 歷史 review correction | corrected source adopted，或 linked successor review 接手 | `IMPLEMENTED_RUNTIME_PARTIAL`：Q/P/A、詳細欄位規則、append-only disposition/outbox、successor projector與React已接通；真MySQL Apply／replay／outbox／active-list removal PASS，enabled persisted-human Browser仍`NOT_RUN`。 |
| `ORDER-001` | `01` §3.1、`02` matching | 正常 candidate／info-1 下一步 | `RECLASSIFY_WORK_ITEM`：無 overdue／invalid oracle。 |
| `ORDER-002` | `02` candidate contact | 正常 accepted candidate／info-2 下一步 | `RECLASSIFY_WORK_ITEM`：無 overdue／invalid oracle。 |
| `ORDER-003` | `02` willingness | 正常等待 recipient-bound willingness/decision | `RECLASSIFY_WORK_ITEM`：等待本身不是異常。 |
| `ORDER-004` | `02` customer decision | 正常等待正式 customer decision／matching confirmation | `RECLASSIFY_WORK_ITEM`：無 breach predicate。 |
| `DOC-SEND-001` | `02` matching、`17` delivery | fixed object/digest/recipient 的 durable delivery work item | `RECLASSIFY_WORK_ITEM`：未發送是正常下一步；delivery failure 另由 owner anomaly。 |
| `SCHEDULE-001` | `02` holiday/schedule | owner holiday＋official-date correction通過完整 planning predicate | `SPEC_GAP`：不可任意補 schedule row。 |
| `SCHEDULE-002` | `02` replacement lineage | canonical replacement/service/finance review completion | `IMPLEMENTED_GUARD`：已移除 generic workflow resolved抑制，replaced root rescan會 reopen；真正 owner completion與人工 remediation仍 `SPEC_GAP`。 |
| `SCHEDULE-003` | `02` assignment ownership | 同 caregiver/day 唯一 owner 且合法 correction receipt | `SPEC_GAP`：target selection/completion 未定義，detail shape 漂移。 |
| `SCHEDULE-005` | `02`、`24` holiday preference | preference 只排序，不形成 hard anomaly | `RETIRE_FALSE_POSITIVE`：live producer 與正式規格衝突。 |
| `SCHEDULE-006` | `02` assignment plan | official dates、coverage、ownership、occupancy、generation 全部合法 | `SPEC_GAP`：live 只比 day count，command 不存在，detail shape 漂移。 |
| `PAYOUT-001` | `05` §3、`16` §2.2–2.3 | exact canonical outgoing payout allocation 使原義務 balance=0/completed | `IMPLEMENTED_SOURCE`：人工detail-bound Q/P/A與React workbench已完成；後續稽核確認anomaly source以日期fallback作version且scan未鎖定，auto-resolution fail closed。真MySQL/API/Browser仍`NOT_RUN`。 |
| `PAYOUT-002` | `05` §3 | late change 經合法 adjustment/payout，root 一致 | `SPEC_GAP`：只有 review Query。 |
| `PAYOUT-003` | `05` §3 | unique valid bank master＋exact payout reconciliation | `SPEC_GAP`：bank master correction 未綁 anomaly。 |
| `GOVSUB-001` | `14` §3–4 | bank fact 唯一對應 approved batch 並 exact allocation | `SPEC_GAP`：legacy preview link 缺 bindings/Apply/React。 |
| `GOVSUB-002` | `14` §4.3–4.4 | selected claim allocations exact 且總額守恆 | `SPEC_GAP`：缺完整 action descriptor/React。 |
| `GOVSUB-003` | `14` §6 | current batch revision 無 integrity blockers | `SPEC_GAP`：Query/retry 不能修 contradictory roots。 |
| `GOVSUB-004` | `14` §3、§5 | owner可執行合法partial／exact reversal，但alert解除仍需專屬fresh terminal binding | `SPEC_GAP`：successful-ID receipt-only shortcut已移除；single-allocation合法partial不誤報但也不自動消警示。完整人工action binding、owner readback與React Q/P/A仍需專屬人工確認addendum。 |
| `GOVSUB-005` | `14` §6 | frozen claim 以合法 revision/correction 與 official assignment 一致 | `SPEC_GAP`：current/frozen values 與 correction contract 缺失。 |
| `GOVSUB-006` | `14` §4.5.1 | status 離開`pending_review`進合法offset／return branch，owner＋exact anomaly fresh readback一致 | `CODE_ONLY_SOURCE_PASS`：recipient ambiguity／future account／lineage fail closed，React exact contract、timeout no-resend、stale re-Preview與三重readback完成；Luna High E3 round2 P0/P1=0。partial-offset unique-key仍`BLOCKED_SCOPE`，不得宣稱full completion。 |
| `GOVSUB-007` | `14` §4.5.1 | existing return payable 經 owner reconciliation，remaining 正確 | `SPEC_GAP`：state-only code 無 action binding。 |
| `client_over_refund_recovery_open` | `16` §3.5.1 | remaining=0 且 `recovered|adjusted` | `IMPLEMENTED_RUNTIME_PARTIAL`：owner projector／terminal predicate／React與真MySQL lifecycle PASS；enabled persisted-human Browser Apply／partial／stale仍`NOT_RUN`。 |
| `client_refund_underpayment` | `16` §3.6 | 後續新 outgoing bank allocations 使 refund remaining=0 | `SPEC_GAP`：不得重用原 row，無直接 owner referral。 |
| `staff_overpayment_recovery_open` | `16` §2.4.2 | remaining=0 且 `recovered|adjusted` | `IMPLEMENTED_RUNTIME_PARTIAL`：owner projector／terminal predicate／React與真MySQL lifecycle PASS；enabled persisted-human Browser Apply／partial／stale仍`NOT_RUN`。 |
| `staff_payout_underpayment` | `16` §2.4.1 | 後續 canonical payout 使 remaining=0 | `SPEC_GAP`：state-only code 無新 bank-row owner referral。 |
| `staff_payout_overpayment` | `16` §2.4.2 | 建立 recovery successor 後由 successor 負責結清／adjust | `MERGE_TO_SUCCESSOR`：只留 occurrence/history，不與 recovery-open 同時 active。 |
| `finance_import_manual_review` | `09` §6.1、`06` action table | complete owner posting/allocation，manual-review predicate消失 | `IMPLEMENTED_SOURCE`：registered generic correction與六種正式 subtype owner dispatcher均已實作；test matrix證明六型selector／dispatch並拒絕`non_business_review`。owner terminal contract不存在時仍保持active，不以receipt冒充解除。 |
| `CLIENTREFUND-001` | `06` action table、`16` §3.6 | canonical incoming row＋exact original refund reversal＋fresh predicate readback | `IMPLEMENTED_SOURCE`：安全detail／actual row binding／snapshot roundtrip／formal reversal與canonical bank-row fresh guard／React exact-fingerprint terminal recheck已完成；Luna High E3 round 4 P0/P1=0。真 MySQL/API/Browser仍`NOT_RUN`。 |
| `IMPORT-006` | `09` §6.2、`06` integrity route | 所有 batch/occurrence/reprocess integrity conditions一致 | `LIVE_DRIFT / AUTHORITY_GAP`：duplicate公式已補；既有 Finance Import 根契約已提供`finance_import_batch_contracts.batch_version`，不需另造版本公式，但live projector仍預設`source_version=0`且未在同一transaction鎖定batch contract／完整性根集合。完成approved source-only Q/P/A／outbox contract前auto-resolution固定fail closed。 |
| `RECEIVABLE-001` | `04` §2–3、`16` §3.6 | canonical incoming allocation 使 receivable remaining=0 | `COMPLETED_RUNTIME`：owner Q/P/A、transaction-bound account／obligation lock、aggregate-version source與真MySQL／API／Browser active-list removal PASS。 |
| `CLIENTPAYABLE-001` | `04` §2–3、`16` §3.6 | valid outgoing allocation 使 payable remaining=0 | `COMPLETED_RUNTIME`：owner Q/P/A、partial-retain、transaction-bound freshness與真MySQL／API／Browser active-list removal PASS。 |
| `RETURN-001` | `04` §2–3、`16` §3.6 | subsidy_return payable 經 exact payout allocation歸零 | `COMPLETED_RUNTIME`：owner Q/P/A、與一般退款互斥、transaction-bound freshness與真MySQL／API／Browser active-list removal PASS。 |
| `SUBSIDYADVANCE-001` | `04`、`14` §3 | Staff Payables typed advance/payout work item，後續 recovery 正確連結 | `RECLASSIFY_WORK_ITEM`：`union_advance_due` 是正常到期工作，不是異常。 |

## DDH 動態執行紀錄

| 時間／觸發 | 原運作模式 | material change | 新運作模式 |
|---|---|---|---|
| 2026-08-26 初始稽核 | E4 三條隔離、唯讀 owner-family lanes；全部明確為 `gpt-5.6-luna`／`high` | Finance、Import／LINE、Orders／Scheduling 的規則書與 live detector 可獨立讀取，write set 為空 | 三條 lane 平行建立逐碼 source map，主代理為唯一規格整合 writer。 |
| 2026-08-26 規則書要求加入 | 同上 | 使用者新增「auto-resolution 必須符合真實業務流程」；acceptance 與 evidence scope material 改變 | 只重投影剩餘唯讀工作：各 lane 增列 owner rule section、root facts、完整／反例 predicate 與誤解除風險。 |
| 2026-08-26 多週期無 checkpoint | 長時間整批稽核 | 三條 lane 連續多個監控週期維持 running，未回覆進度；交接狀態不可觀測 | 中斷當前 turn 後沿用相同 Luna High agents，改成每 turn 最多 10 codes 的 checkpoint 交付；仍唯讀且禁止 nested delegation。 |
| 2026-08-27 42-code oracle 稽核完成 | E3 規則書序列交接 | 發現 generic resolve 與 LINE／Scheduling 弱 predicate 可誤解除，且 finance projector poison event 可無限重試 | 先切為 P0 fail-closed guard 與 WP-D dead-letter/manual recovery；owner contract 凍結後才恢復 E4 React 隔離 lanes。 |
| 2026-08-27 finance owner contracts 凍結 | E3 單一 backend writer | Government／Client／Staff Query、predicate、guard 與 retry ceiling 已有 focused evidence，三個 React write set 可獨立 | 恢復 E4 三條隔離 React lanes；全部固定 `gpt-5.6-luna`／`high`，共享 `AnomaliesPage` 仍由主整合器單點寫入。 |
| 2026-08-27 三條 React lanes 完成 | E4 隔離並行 | 三個 workbench 均完成，進入 shared dispatcher、build 與 evidence sync 的序列整合期 | 收斂為 E3 integration writer；verifier 發現 descriptor／owner mismatch／outcome reconciliation 缺口後退回修正；final exact action/form-schema dispatcher、focused 24 tests、oxlint 與 production build PASS。 |
| 2026-08-27 LINE／Scheduling／Historical Orders 再盤點 | E4 三條 Luna High 唯讀 lanes | LINE／Scheduling 多碼缺 approved owner contract且 live detector 與規則書不等價；Historical Orders 已有 approved WP 與互斥 write set | LINE／Scheduling 固定 fail closed 並回到 owner-spec；Historical Orders 切換為 E4 backend／projector／React writers，主代理保留 shared hot spots。 |
| 2026-08-27 Historical first candidate | E4 writers → E3 verifier/integration | 初版綠測試未覆蓋 adoption composition、router、path／DTO 與完整 owner Preview；獨立 verifier 判定 P0/P1 fail | 拒絕 terminal acceptance；序列修正 caller-owned UoW、完整規則 Preview、API/React round-trip 與 projector binding，再派三條 Luna High re-verification lanes。 |
| 2026-08-27 全碼規則書再收斂 | E4 三條隔離、唯讀 owner-family lanes；全部為 `gpt-5.6-luna`／`high` | 使用者再次明確要求自動解除必須符合真實業務流程；原 source map 不足以作發布證據 | 保留 E4，但 material 重投影三條 lane 的剩餘驗收：逐碼引用 owner 規則章節、root facts、完整完成條件、部分完成／外部成功／stale／readback failure 反例及 bounded successor WP。DDH native reconciliation 3/3 PASS、零 workspace effect；正式 integration 仍由主代理序列寫入。 |
| 2026-08-27 Client Settlement 執行 | E3 verifier lane 候選＋主整合 writer | Host terminal-thread quota 拒絕建立新的 `gpt-5.6-luna`／`high` verifier；可用 capability material 下降，但已凍結 WP-A/B write set 可由主代理序列完成 | 動態切回單一 integration writer；真 Browser 暴露 `adjustment` Query 與 owner loader 漂移後，立即重投影剩餘驗證，修正 purpose-bound loader 並增加回歸。未把未啟動代理算為成果；既有三個已完成子代理皆為 Luna High。 |
| 2026-08-27 Client Settlement WP-C 重投影 | 主整合 writer 序列真 Browser／MySQL | `RETURN-001` 首次被 stale guard 擋下；根因為 MySQL `Decimal` account version 被 adapter 錯誤降為 0，屬 material capability/evidence drift | 不放寬 stale guard；修正 owner version typed conversion、增加回歸後重跑正式 projector 與 Browser。三碼最終均 predicate=false／resolved 且從活動頁消失。 |
| 2026-08-27 LINE binding predicate guard | E4 三條規則書 discovery → 主代理單一 implementation writer → E3 Luna High verifier | 規則書稽核證明 `LINE-001/005` live projection-only 判定可誤解除；第一輪 verifier 再發現 Client `client_id/case_no` drift 與 whitespace 兩項 P1 | 保持單一 writer序列修正，補 relation drift、canonical identity、revocation與 rollback regression；第二輪同一 `gpt-5.6-luna`／`high` verifier `PASS`，P0/P1=0。 |
| 2026-08-27 PAYOUT-001 remediation | E4 backend／React Luna High writers，parent保留 shared integration | 第一輪 E3 發現 action綁在 detail但頁面只讀 recovery context 的 P0，以及 stale 無重新 Preview入口的 P1；第二輪再發現 recovery空 actions會蓋掉detail action的P1 | 立即收斂為單一 integration writer，改以typed detail action fallback、stale fresh Query、unknown同 key調和及非空 recovery優先；同一 `gpt-5.6-luna`／`high` verifier第三輪 `PASS`，P0/P1=0。 |
| 2026-08-27 CLIENTREFUND-001 remediation | E4 backend／React Luna High writers → E3 verifier | round 1 發現分頁誤完成、snapshot遺失原refund、canonical row未fresh驗證與detail過度遮蔽；round 2抓到重複分頁及currency缺失；round 3證明列表不存在不是可靠terminal oracle | 先以三條隔離Luna High/high P1 lanes平行回修，再收斂為單一exact-query writer；terminal改查原fingerprint typed detail並要求predicate=false及列表刷新一致。round 4 Luna High/high `PASS`，P0/P1=0，零競寫。 |
| 2026-08-27 GOVSUB-004規則書與P0 guard | E4三條Luna High/high唯讀rulebook／live／UI lanes | live closure只因`successful_reversal_source_receipt_id`存在就inactive，違反receipt-only不得解除；完整action contract仍是SPEC_GAP | 動態切為單一exact guard writer，只移除ID shortcut並補ambiguous partial／invalid／over反例；Luna High/high E3 `PASS`。完整remediation未擴張，維持等待人工addendum。 |
| 2026-08-27 GOVSUB-006 code-only remediation | E4 backend／React Luna High/high writers → E3 | round1發現列表刷新未證明消失、future recipient Query/Apply不一致、stale無re-Preview及binding kind/value未驗；另辨識partial-offset unique-key為schema blocker | 只重投影code-only剩餘工作，以兩條隔離lane回修，不碰schema；round2 Luna High/high E3 P0/P1=0。schema blocker維持`BLOCKED_SCOPE`，不把code-only PASS冒充full completion。 |
| 2026-08-27 全碼 auto-resolution fail-closed gate | E4 三條 Luna High/high 唯讀 owner-family lanes | 首輪兩條 lane terminal、第三條遭 Host thread quota 拒絕，available isolation capability material 下降；後續重新使用兩條 Luna/high lane 深查 fresh-root。規則書比稽核摘要更高權威，且合法 owner 操作不自動等於 alert terminal。 | DDH reconciliation 如實記錄 capability delta並重投影為 E2 主代理單寫整合。首版14-code白名單因後續稽核找到Historical／LINE／PAYOUT／IMPORT-006／Client三種逾期 stale-root P1及GOVSUB-004 binding SPEC_GAP而失效；該輪候選先收斂為5-code白名單、37-code fail-closed guard，後續狀態由下一列接續。HCM另補event／prior occurrence／case／client／review binding與fresh-root gate；未把舊PASS沿用到新candidate。 |
| 2026-08-27 fresh-root repair round | E4三條互斥Luna/high writers → E3 cross-lane verification | Historical、PAYOUT、Client具approved source-only Authority；LINE／IMPORT-006／GOVSUB-004仍SPEC_GAP。PAYOUT與Client可用owner lock＋daily-root版號修復；Historical全snapshot可能與合法後續lifecycle進展衝突。 | PAYOUT＋Client四碼完成修正並經cross-lane 45 tests、P0/P1=0，白名單由5增為9、fail-closed由37降為33。Historical兩次verifier未在監控週期內收斂，均中止且不算成果；未恢復其auto contract。 |

## Convergence

```yaml
convergence:
  status: NOT_READY
  blockers:
    - requirement: 33 個 kept anomaly definitions 的唯一 remediation 行為
      owner: 各 source Domain
      evidence_gap: 多數 kept definitions 尚未有 owner Preview/Apply/completion predicate
      return_path: owner-spec-workshop
    - requirement: work-item／retired／successor dispositions 的安全移轉
      owner: Orders／LINE／Staff Payables／Scheduling／Anomalies
      evidence_gap: 7 個 work queue replacement、SCHEDULE-005 bounded rescan、staff overpayment successor 去重尚未實作驗收
      return_path: necessity-migration-work-package
    - requirement: 每個 kept code 的自動解除符合真實業務規則
      owner: 各 source Domain
      evidence_gap: 42-code inventory oracle 與 live drift 已盤點，但 kept codes 的弱 predicate及多碼 owner completion contract尚未修正
      return_path: per-owner-spec-and-implementation
```

結果：`SPEC_GAP`。本文件固定需求與範圍，但不授權以未定義的欄位、豁免、schema 或跨 Domain 寫入開始實作。

逐碼 root facts、完整解除 oracle、部分完成／外部成功／stale／readback failure 反例與 current action 狀態，
見 `03_追蹤清單與證據/evidence/2026-08-27_anomaly_rulebook_oracle_matrix.md`。該 matrix 以 current registry
實際 42 codes 完整覆蓋；舊文件中的非 canonical labels 不另算 current code，也不得直接 seed alert。

## Acceptance 與 evidence

每個 kept anomaly code 都必須在其 owner package 留下：正向 Preview／Apply／receipt／root readback／alert recheck，及
stale、replay、permission、insufficient evidence、transaction failure／rollback 的 focused evidence。React 或
owner workbench 必須以真 API／Browser 實點流程；mock、toast、tracking status 或單一 HTTP 成功不足。正向
路徑須證明原 alert 已自 active 清單消失，或被具明確 relation 與新修正入口的 successor 取代。
每個 auto-resolution 測試還必須引用 owner 規則書並覆蓋：完整業務條件成立才解除；部分完成、通知／外部
聯絡成功但 root facts 未成立、recheck 前版本漂移、readback unavailable 及 owner blocker 仍存在時保持 active。
測試還必須鎖定對應 owner rule／definition contract version；規則書、owner predicate、detector、detail completion
copy 或 projector 任一變更時，正向與上述負向 evidence 必須同批重跑。只重跑 projector、重送通知或取得
Apply receipt 而未重新讀取 owner root facts，不得計入 auto-resolution acceptance。

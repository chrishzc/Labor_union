# 歷史案件作業基準與狀態感知異常工作包

> 2026-08-28 人工 priority correction：本文件的 `WP-HOB-A/B/C/D/F` 與 H/R/C/A versioned scenarios 是
> Task 96 第一主線。不得因 Rich Menu、LINE 或其他 package 較早 `PACKAGE_READY` 而跳過；只有本主線遇到
> 明確 `BLOCKED` 且等待必要人工裁決時，才可執行後順位包。HOB-E／F-04 已完成，不重做也不能代替其餘情境。

- `package_set_id`: `PROV-20260827-historical-order-operational-work-packages`
- `declared_status`: `approved`
- `package_status`: `PACKAGE_READY`（B1 baseline storage、S1 substitution note與S2 note method已於2026-08-27人工採用）
- `controlling_spec`: `PROV-20260827-historical-order-operational-baseline-spec.md`
  (`approved`／`SPEC_READY`；`convergence.status: READY`；`blockers: []`)
- `authority_digest`: 2026-08-27 人工裁決 append-only lineage、歷史11步baseline、B1獨立baseline storage、缺根事實形成可人工補正異常、服務前換人回媒合、服務中只能substitution、S1／S2非阻擋代班備註與固定method enum，以及取消Client Finance明確direction。
- `effect_ceiling`: 本機 source、versioned additive schema 與 `lu_test_*` 驗收；不含 `union_db`、production、provider 寫入、deployment、entry switch、既有事件改寫或 generic anomaly resolve。
- `research_basis`: `NO_RESEARCH`；行為由 current Orders／Scheduling／Client Finance／Contract／Anomalies 正式規格、live source gap 與人工裁決完整涵蓋。

## 1. Entry、necessity 與 reuse

| 候選工作 | Necessity | Source basis | Reuse decision |
|---|---|---|---|
| Historical baseline＋minimum-required-facts | `required_now`；否則進行中歷史案永久卡在泛化異常 | controlling spec §1–2、§4、HOB-A1～A3／N1～N2 | reuse historical adoption／remediation lineage；新增最小 baseline owner workflow |
| 服務前 replacement successor round | `required_now`；live `ApplyRematch` 只有旗標，current step 不會真正回媒合 | controlling spec §2、HOB-A6 | reuse current rematch Query／Preview；copy-adapt Scheduling successor event pattern |
| 服務中 substitution 備註例外 | `required_now`；不得因不存在的新契約或備註阻擋代班與薪資 | controlling spec §3.4、HOB-A7／SUB-* | reuse existing leave／substitution／Payroll impact；optional note採獨立minimal-glue，附件可空 |
| Cancellation outcome safety＋direction | `required_now`；現行 UI 可盲送新 key、串案且帳務方向靠人解讀 | controlling spec §3.1、§3.3、§3.5、HOB-A4*／FIN-DIR-* | reuse canonical cancellation workflow；direction 與 reconciliation 採 minimal-glue |
| Completion owner-terminal closure | `required_now`；status-only 會錯誤清除仍有根因的異常 | controlling spec §3.2、HOB-A5 | reuse Orders／Client Finance／Staff Payables owner readbacks；新增 aggregate oracle composition |
| Versioned scenarios＋Browser closure | `required_now`；來源綠測試不能證明人員可解除異常並繼續 | gap matrix §8、H-03＋A-02、R／C／F scenarios | copy-adapt archived Part 00 manifest method；不恢復封存規格權威 |

其餘 production cleanup、UI 重排、provider 自動化、production migration、直接改寫歷史 rows 與未列入
acceptance 的 hardening 均為 `remove` 或 `required_later`，不得進入本 package set。

## 2. WP-HOB-A：Historical baseline 與具體缺根事實異常

- `objective`: 以 append-only baseline 保存人工確認的 current step，並由 versioned minimum-required-facts contract 產生 owner-specific actionable anomalies。
- `requirements/acceptance`: HOB-A1、HOB-A2、HOB-A3、HOB-N1、HOB-N2。
- `dependencies`: canonical historical order identity、Orders aggregate version、11-step server projection、各 step owner root query；API authentication 沿用 Orders 正式規格既有 `orders.historical_review.remediate` capability atom，依 Global 同權限內部存取規則只作 authenticated operation/audit gate，不新增內部業務權限分級。
- `in_scope`: Domain candidate、Query／Preview／Apply、repository／receipt／outbox、typed API、React workbench、owner anomaly successor composition；若需 schema，只能 additive 並完整通過 DB gate。
- `prohibitions`: 不建立 LINE delivery、簽章、付款、allocation、assignment 等不存在事件；不得用 step number 或 tracking 推進 owner aggregate。
- `steps`: Query current baseline／versions／minimum facts → zero-write Preview → fresh locked Apply → append baseline／receipt／outbox → owner roots與 step projection readback → 原 alert inactive或具體 successor active。
- `negative/failure`: stale、version 回退、identity mismatch、lineage 斷裂、readback unavailable、same-key different payload 全部 fail closed；transaction rollback，outbox 可 exact retry。
- `verification`: pure candidate、workflow/repository/API contract、fresh/preserve-data MySQL、projector replay、React/Browser HOB-A1～A3與N1～N2；保留去敏 receipt、owned-row before/after與 active-list readback。
- `human_fallback`: 缺 owner root 走該 owner Q/P/A；不可取得的歷史文件只走 typed evidence-unavailable disposition。

## 3. WP-HOB-B：服務前 replacement successor round

- `objective`: 尚無任何 actual-service root 時，以版本更大的 typed replacement event 建立新 matching round，使 current operational step 合法回到媒合，而 history/version 不倒退。
- `requirements/acceptance`: HOB-A6、HOB-N1。
- `dependencies`: WP-HOB-A step projection；Candidate Pool／Matching Plan／Scheduling current versions與 occupancy roots。
- `in_scope`: rematch Query／Preview／Apply、accepted plan／assignment／waiting lock supersession、successor round、readback與異常投影。
- `prohibitions`: 已有 actual service 不得使用本包；不得改寫舊 round、既有付款或 aggregate version。
- `steps`: Query service existence與current round → Preview retained/superseded roots → lock/revalidate → append replacement＋successor → readback current round/step → projector 更新。
- `negative/failure`: actual service exists、stale、occupancy conflict、identity ambiguity或 successor 未建立均零寫入／rollback；retry 必須沿用同 idempotency identity。
- `verification`: HOB-A6 正向與 actual-service 負例；source contract、真 MySQL lineage、API/React、Browser 回原 Orders workspace證明可繼續。

## 4. WP-HOB-C：服務中 substitution 與 optional note

- `objective`: 有actual service時沿用Scheduling substitution＋Payroll impact；缺少代班新契約、客戶追加簽署或備註永不成為blocker，另提供獨立optional substitution note。
- `requirements/acceptance`: HOB-A7、HOB-SUB-A1、HOB-SUB-A2、HOB-SUB-N1。
- `dependencies`: existing leave/substitution、assignment-owned actual service、Payroll impact、controlled file archive port。
- `in_scope`: 移除不合法文件gate；substitution readback；可選`substitution_note` Query／Preview／Apply、actor/note/method/version/receipt與nullable controlled-file reference。
- `prohibitions`: note不得建立signed/customer-accepted、改條款／金額／日期或回退整案；note／archive failure不得回滾已提交substitution。
- `steps`: Query actual-service＋Scheduling roots → substitution Preview／Apply／readback → Payroll readback；note若選用則以獨立UoW追加，附件可空。
- `negative/failure`: substitute identity、occupancy、fresh version、readback仍fail closed；未留note、沒有附件、取消或archive unavailable只影響optional note結果。
- `verification`: HOB-A7/SUB-* source與真 MySQL；React 可明確略過文件；Browser 驗證有／無／archive failed三路代班與薪資均一致。

## 5. WP-HOB-D：取消結果、Client Finance direction 與 outcome reconciliation

- `objective`: 完成服務前／服務中／完整履約三分支，逐筆公開 server-owned Finance direction，並使 React 在 outcome unknown、切案與 late response 下不盲送或串案。
- `requirements/acceptance`: HOB-A4、HOB-A4B、HOB-A4C、HOB-FIN-DIR-A1、HOB-FIN-DIR-N1。
- `dependencies`: canonical Orders cancellation、Scheduling impact、Client Finance obligation planning、Payroll impact、Anomalies active-list query。
- `in_scope`: 每筆 action required `direction`＋`direction_amount_ntd`、Domain invariant/fingerprint、typed API/React decoder、完整 actions顯示、same-key reconciliation、identity guard、apply後 Orders/Finance/Payables/Anomalies readback。
- `prohibitions`: UI 不得由 action kind／正負金額推斷；不得只顯示前三筆；不得以新 key重送 outcome-unknown命令；Orders cancellation不得 generic resolve Finance alerts。
- `steps`: Query roots → Preview逐日與全 owner impacts → confirm → Apply same key → outcome reconciliation → owner/card/stage/anomaly readback → 顯示 Orders完成及仍 active owner alerts。
- `negative/failure`: missing/invalid direction、schema drift、stale、cross-case late response、timeout或readback failure均不顯示假成功；完整履約取消固定零寫入。
- `verification`: action mapping unit contract、API/Zod fail closed、workflow/replay、真 MySQL三分支、React focused、enabled-human Browser C-01～C-06。

## 6. WP-HOB-E：完成案件 owner-terminal closure

- `objective`: 只有 Orders completion、actual start、official service facts、Client settlement與Staff payout正式 terminal lineage 全部成立時，Step 11與historical alerts才完成。
- `requirements/acceptance`: HOB-A5、HOB-N1。
- `dependencies`: WP-HOB-A；Orders、Scheduling、Client Finance、Staff Payables typed readbacks；若要支援無法可靠還原銀行資料的pre-system historical case，須先完成 `PROV-20260828-historical-payment-and-owner-settlement-work-packages.md`。
- `in_scope`: aggregate completion oracle、missing-root actionable anomaly、owner referral與fresh terminal projector。
- `prohibitions`: 不以 `orders.status`、匯入 status、receipt-only、provider success或 alert tracking代替 owner terminal facts。
- `steps`: Query所有 owner roots/version → 計算缺項 → 各 owner走其正式Q/P/A（一般exact bank/allocation；僅符合資格的歷史案件可走owner-specific historical event）→ fresh aggregate readback → Step 11／alerts projection。
- `negative/failure`: 任一 owner unavailable/stale/integrity blocker保持 active；不得跨 Domain直接寫 ledger或payout。
- `verification`: F-01～F-04 source、真 MySQL/API/React/Browser，證明每項缺漏逐一解除及最後才完成。

## 7. WP-HOB-F：Versioned scenario 與跨頁 UI 驗收

- `objective`: 將 A～E 的 observable behavior封裝為可重建 scenario package，證明異常可解除、消失且原工作流可繼續。
- `requirements/acceptance`: gap matrix §8.1～§8.5；H-03＋A-02；A～E全部 acceptance 的 integration oracle。
- `dependencies`: 對應功能包 source candidate；Route A fresh `lu_test_*`；enabled persisted human Session 才能宣稱 Browser PASS。
- `in_scope`: manifest、root fixture、command lineage、expected oracle、evidence applicability、UI checklist、receipt/inventory；Route B僅在owned rows可盤點時選用。
- `prohibitions`: fixture 不得 seed derived status/alert/receipt/outbox；不得以mock/browser單層取代Domain/API/DB證據；不得操作 `union_db`。
- `steps`: stage-00依正式commands推進 → 執行exact scenario → DB/API/projector/React/Browser分層oracles → scoped cleanup或明確保留。
- `failure/retry`: 每次唯一 scenario identity；same-key retry、stale、403、timeout、readback failure與successor anomaly均保留receipt。
- `verification`: H-03＋A-02驗證 `3→2→1→0`；R、C、F及安全情境分開reset執行；原Orders/Scheduling工作區需可繼續下一步。

## 8. 雙向 coverage matrix

| Requirement／Acceptance | Source | Package step | Direct oracle |
|---|---|---|---|
| HOB-A1／A2／A3 | controlling spec §1–2 | WP-A Q/P/A＋projector | baseline無假事件、缺根異常、較新合法lineage可解除 |
| HOB-N1／N2 | controlling spec §2、§5 | WP-A/B/D/E stale/replay gates | zero-write、same-key replay／mismatch rejection |
| HOB-A6 | controlling spec §2 | WP-B replacement successor | version增加且current step回媒合、舊lineage保留 |
| HOB-A7／SUB-A1／A2／N1 | controlling spec §3.4 | WP-C substitution＋獨立note | 無note仍成功、optional note receipt、真Scheduling blocker仍拒絕 |
| HOB-A4／A4B／A4C | controlling spec §3.1 | WP-D cancellation三分支 | service-before/mid/full MySQL＋API＋Browser oracle |
| HOB-FIN-DIR-A1／N1 | controlling spec §3.3／§3.5、Client Finance §3 | WP-D direction contract/reconciliation | mapping/invariant、Zod fail closed、same-key readback |
| HOB-A5 | controlling spec §3.2 | WP-E aggregate terminal query | 缺任一owner root保持active；全部terminal才Step 11 |
| 跨頁解除與推進 | gap matrix §8 | WP-F versioned scenarios | `3→2→1→0`、alert消失/具體successor、回原頁可繼續 |

每個 retained step 均回指 current acceptance 或不變量；沒有 orphan implementation step。執行時如
formal spec、owner interface、schema、外部效果或 acceptance material 改變，只把受影響 package
退回 spec-workshop，其他 package 不連帶失效。DDH 另依當時隔離與驗證事實選擇執行拓撲。

## 8.1 2026-08-28 Spec Pipeline 校正與後續執行分包

本節不重做已完成 HOB-E／F-04，也不把33個產品 anomaly inventory冒充已驗收情境。後續按下列 bounded
packages執行；每包開始前仍須確認本文件與 controlling spec 的 `SPEC_READY/PACKAGE_READY` current：

| Execution package | Scope | Current boundary |
|---|---|---|
| `PKG-H-BASELINE` | H-01～H-06；Orders-owned baseline assertion、step history、evidence、typed Q/P/A/projector | B1 storage與未掛載 backend base已完成 source slice；minimum-required-facts/projector/public API與React bundle已於2026-08-28人工採用，後續依`PROV-20260828-historical-baseline-projector-work-packages.md`執行，未runtime通過前不得宣告完成 |
| `PKG-H-REMEDIATION` | `HISTORICAL-ORDER-001` live-drift與no-auth Browser | active時`_apply_payload.remaining_issues`不得固定空；missing anomaly row視為projector readback缺失並fail closed保持active；只有明確inactive row才解除；prior/successor/predicate exact readback |
| `PKG-R-PRE` | R-01～R-04、R-07 service-before replacement | Scheduling-owned successor round bundle已於2026-08-28人工採用；current `ApplyRematch`只有handoff，不算完成；後續依`PROV-20260828-service-before-replacement-successor-work-packages.md`執行 |
| `PKG-R-SUB` | R-05～R-06 service-in substitution | 沿用leave/substitution；optional note不阻擋；note schema/runtime另過DB gates |
| `PKG-C-CORE` | C-01～C-04、C-06 | server-owned Finance direction、same-key outcome reconciliation、case-scoped owner readback |
| `PKG-C-ISOLATION` | C-05 | `AUTHORITY_REQUIRED`；等待ACB1 generic case binding/read model裁決 |
| `PKG-A-SAFETY` | A-04～A-06 | timeout/stale/tracking-only負向oracle；不併入A-01/A-02/A-03 owner包 |
| `PKG-V-SCENARIOS` | H01～H06、R01～R07、C01～C06、A04～A06 versioned manifests | canonical Route A；root-only fixture，禁止seed derived state |

另確認兩項 live-drift 不得被既有 focused green 掩蓋：historical adoption repository 直接寫
`case_staff_assignments` 不能代表 Scheduling owner adoption；HistoricalOperationalBaseline 目前只有 pure
domain/workflow，尚無完整 API/repository/assembler/UI outer path。Task96 Browser 驗收依最新人工指示使用
development `local_bypass` no-auth；formal persisted-human驗收不再是上述 Task96 packages 的必要 gate。

## 9. 2026-08-27 execution status snapshot

本節是 package execution evidence，不把 source／focused green當成跨層或 runtime 完成。後續唯讀
schema inventory曾發現WP-HOB-A storage與WP-HOB-C optional note缺material table／lineage／method
contract；2026-08-27人工已採用B1／S1／S2，並確認S1／S2僅是不影響流程的備註功能，故package
回到`PACKAGE_READY`。詳見`PROV-20260827-historical-operational-storage-and-supplement-spec-gap.md`；
schema／release／runtime gates仍不因人工裁決自動PASS。

| Package | Current evidence | Status boundary |
|---|---|---|
| `WP-HOB-A` | workflow＋pure Domain `25 passed`；B1 1010 schema/release/descriptor與MySQL repository、typed Q/P/A base已落盤，2026-08-28 main integration重跑 backend `48 passed`、DB static `37 passed`、`git diff --check` PASS | route依規格缺口未註冊；owner-root catalog、whole-vector fingerprint、projector、React、Browser尚未完成。DB read-only plan／engine／developer acceptance `NOT_RUN`，固定`DB_CHANGE_NOT_READY`。 |
| `WP-HOB-B` | 服務前 replacement successor round contract ready | owner workflow、persistence、API／React與真runtime尚未完成。 |
| `WP-HOB-C` | 核心無新契約／簽回 gate `28 passed`；S1／S2 note contract已裁決 | note schema／release／API／runtime尚未施工，維持 `DB_CHANGE_NOT_READY`；note未填或失敗不阻擋substitution／Payroll。 |
| `WP-HOB-D` | cancellation explicit `direction` source candidate：Python `36`；receipt-first React focused `56 passed`且build PASS | 真 MySQL／FastAPI API／enabled-human Browser 均 `NOT_RUN`。 |
| `WP-HOB-E` | SP2-Q三owner readbacks＋fresh projector＋typed API／React；正式`HOB-F04-ROUTE-A-001`由root fixture及Q/P/A command lineage建立同案terminal roots。final focused Python `141 passed`、React `20 passed`、build PASS；r4 fresh Luna High verifier與DDH reconciliation PASS；canonical MySQL API回讀completed／active alerts 0，no-auth Browser Step 11與三owner settlement正向PASS、console 0。 | `completed`；TIME／Decimal／immutable obligation runtime差異已fail closed修正；OrderTracker預設仍只查unfinished，操作者明確勾選後才同步以all-scope載入completed摘要與stage projection。未操作`union_db`、DDL／migration、provider或Graphify。 |
| `WP-HOB-F` | `HOB-F04-ROUTE-A-001` manifest／root fixture／expected oracle、formal runner與cross-page Browser closure已完成 | `in-progress`；F-04 slice已PASS，但H-03＋A-02、R／C及其他安全情境仍須分開建立scenario package與驗收，不能由F-04代替。 |

`CLIENTREFUND-001`、`PAYOUT-001` 的 source status 為 static closed；真 MySQL／API／Browser 均 `NOT_RUN`。
本輪 DDH 依 Authority、能力、write-set 隔離與驗證結果動態調整計畫／運作模式；所有實際建立的子代理均為
`gpt-5.6-luna`／`high`。此紀錄不創造新的 owner、scope 或 completion gate。

Staff Payables necessity review另確認：正式規格要求case-scoped current readback與既有owner material
mutation的version／immutable successor lineage，未要求新增持久化case settlement root、跨域scalar version
或其歷史backfill。因此`SP1-M`只保留為未來SLO／查詢成本證據成立時的可選優化；當前最低必要候選為
`SP2-Q` query-only typed source vector，並已於2026-08-27獲人工確認。open／partially recovered overpayment必須維持獨立異常，但在原
obligation歸零且Staff owner terminal lineage完整時，不自行阻擋Step 11；一般案件的lineage仍由exact payout/allocation形成，符合新裁決資格的pre-system historical case則可由approved historical owner event形成，不得跨owner推定。

SP2-Q internal slice的兩輪Luna High verifier均先找出阻擋反例，主代理依DDH terminal receipt回到E2修正；
所有子代理零寫入。最終主代理候選已通過`78`項focused／相鄰回歸、compile、`git diff --check`與
真MySQL唯讀SQL解析。修正後fresh independent verification留給下一session，不把修正前review標成PASS。

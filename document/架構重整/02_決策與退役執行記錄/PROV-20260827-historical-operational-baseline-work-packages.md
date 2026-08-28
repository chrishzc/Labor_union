# 歷史案件作業基準與取消人工操作工作包

- `package_set_id`: `PROV-20260827-historical-operational-baseline`
- `declared_status`: `superseded`
- `superseded_by`: `PROV-20260827-historical-order-operational-work-packages.md`
- `controlling_spec`: `PROV-20260827-historical-order-operational-baseline-spec.md`
- `spec_revision`: 2026-08-27 current `SPEC_GAP`
- `convergence`: `NOT_READY`；blockers 為服務中代班的 Contract／客戶變更文件裁決，以及取消 action 的 Client Finance direction public contract。
- `authority_digest`: 使用者已裁決 append-only lineage、Historical-only 11 步 baseline、歷史證據不可取得人工處分、Orders completion 與帳務分開、取消無額外違約金，以及缺必要 root 時建立可人工補齊的具體異常。
- `research_basis`: `NO_RESEARCH`；直接依 current Orders／Scheduling／Contract Signing／Client Finance／Staff Payables／Anomalies 正式規格與 current typed Q/P/A。

## 1. Necessity 與 reuse

| 工作 | 判定 | Source basis／reuse |
|---|---|---|
| Historical baseline immutable root與Q/P/A | `required_now` | 新 owner root；沿用 Historical remediation 的 expected-version／fingerprint／idempotency／receipt 模式，`copy-adapt`，不得重用其 workbook disposition identity。 |
| 11步 historical projection＋缺root occurrence | `required_now` | 沿用 server-owned `stage_projection_query` 與 canonical anomaly projector，`minimal-glue`；不建第二套 stage machine。 |
| React baseline與owner referral | `required_now` | 沿用 Orders Drawer 與 Anomalies exact action dispatcher，`minimal-glue`；不得 raw dict 穿透 renderer。 |
| 取消逐日實際服務確認與雙邊帳務明細 | `required_now` | backend Cancellation Q/P/A 已存在，補 strict React contract與操作面，`reuse`。 |
| 額外解約違約金 | `remove` | 使用者裁決不存在；移除誤導文案，不建立公式。 |
| provider補送、偽造簽章／付款、任意status editor | `remove` | 違反 Authority 與 owner root invariant。 |

## 2. HOB-WP-A：Historical baseline owner root與typed Q/P/A

- Objective：以 append-only `HistoricalOperationalBaselineConfirmed` 與可選的
  `historical_evidence_unavailable_accepted` 保存 Historical-only 作業基準，不製造任何 owner 假事件。
- Requirements：規格 §1–2、HOB-A1、HOB-A3、HOB-N1、HOB-N2。
- In scope：Orders Domain model、Subsystem Query／Preview／Apply、API schema/route、repository、immutable event／receipt／outbox、additive schema release、focused tests。
- Exclusions：一般新案件、owner lifecycle/status直接寫入、LINE/provider、Finance ledger、production／`union_db`、migration switch。
- Effect ceiling：只新增 Historical baseline owned roots及投影 outbox；所有 schema change 必須依根層 §3.1 完整通過 fresh、preserve-data與developer acceptance gates。
- Preconditions：精確識別 Historical Order、current Orders version、selected step 1–11、actor capability、reason、evidence、fingerprint、idempotency。

### Ordered steps

1. 建立 pure candidate：驗證 Historical-only identity、step 範圍、版本、evidence disposition與 no-fabrication invariant。
2. Query 回傳 current baseline／owner bindings；Preview 零寫入並綁完整 current roots；Apply fresh lock/rebuild、append event／receipt／outbox並單次 commit。
3. same key＋same payload replay receipt；same key＋different payload、非Historical、step/version stale、identity drift、evidence缺失固定零寫入。
4. 建立 additive release、descriptor、assembly/catalog、read-only plan、fresh bootstrap與代表性舊 Orders preserve-data驗證。

### Direct verification

- event/receipt immutable；baseline 不新增 lifecycle、assignment、delivery、signature、payment、allocation。
- legal later Orders progression使 current version增加時，lineage可追溯且 baseline 不倒退。
- migration gate表只用 `PASS | BLOCKED | NOT_RUN`；任一必要 gate未PASS固定`DB_CHANGE_NOT_READY`。

## 3. HOB-WP-B：11步 projection與具體缺root異常

- Objective：讓 Step 1..N-1 顯示 `historical_baseline_completed`，Step N為current；只對 current/future 安全執行所需 root 建立 occurrence-level actionable anomaly。
- Requirements：規格 §1–4、HOB-A1–A5、HOB-N1。
- Dependencies：HOB-WP-A baseline Query；各 owner 現有 read ports／Q/P/A。
- In scope：Orders stage projection、Historical issue assembler、`HISTORICAL-ORDER-001` occurrence field/root paths、Anomalies action descriptor／fresh predicate consumer、tests。
- Exclusions：新增任意 generic code、把 baseline 當owner terminal、跨Domain寫入。
- Effect ceiling：沿用 canonical anomaly code，以 issue identity／field path區分；不新增第二 alert state machine。

### Ordered steps

1. 固定 Step 1–11 exact owner bindings：Case Import/terms、candidate pool/contact、matching/customer decision、Contract Signing、deposit allocation、confirmed dates、effective assignment/actual start、Orders completion、Client settlement、Staff payout。
2. baseline prior steps只讀 annotation；current/future command所需 root缺失時產生具體 occurrence，detail列 owner、缺少identity/version、影響步驟、合法Q/P/A與terminal predicate。
3. owner Apply後fresh requery；單一 occurrence修好只解除該 occurrence，仍有其他缺root時保留 successor；最後一個完成後umbrella inactive。
4. cancellation依服務前無金流／服務前已收款／服務中／完整履約四分支；只解除不再適用的履約 occurrence，真實 Finance alerts保留。
5. replacement／reversal／reopen 使 current operational step 回到較早 ordinal 時，驗證
   aggregate version 仍增加、baseline 不改寫、舊 caregiver-bound roots 保留但 superseded，
   並由 earliest-invalidated-root 投影選擇 Step 2／3／4，不接受人工任意 target status。
6. caregiver replacement 先鎖定服務根事實：無 actual service 才可新建 matching round；
   有 actual service 固定 referral 至既有 leave／substitution，不建新薪資或代班功能。

### Direct verification

- Step 8 baseline不偽造Step 1–7 owner events；matched caregiver缺失顯示可操作 anomaly，補齊後推進。
- receipt-only、tracking resolve、stale/readback failure、owner root unavailable均保持active。
- Orders completion與Client/Staff/Government settlement分開，Finance未結清不倒退Orders。
- Step 10 服務前換人可以 version 更大的 typed replacement event 投影回 Step 2／3／4；
  舊 event 不刪、baseline 不改、新 caregiver round 不得沿用舊人的意願／簽回／排班 gate。
- 已有 actual service 的月嫂中斷案不得回 Step 2；既有 leave／substitution 完成受影響日重建與
  Payroll impact，原月嫂與代班月嫂的金額不由 HOB 重算。

## 4. HOB-WP-C：React Historical baseline與人工補正入口

- Objective：提供 step選擇、影響預覽、evidence處分、confirm/apply/readback，以及每個缺root的exact owner referral。
- Requirements：HOB-A1–A3、HOB-A5、HOB-N1–N2。
- Dependencies：HOB-WP-A/B strict API。
- In scope：strict Zod client、Orders/Anomalies workbench、outcome-unknown reconciliation、focused component/client tests、production build。
- Exclusions：raw dict、前端推導stage、直接拼owner endpoint、假成功或generic close。

### Ordered steps

1. 實作 strict Query/Preview/Apply schema與selected-step preview；顯示哪些步驟為歷史基準、哪些roots仍缺。
2. evidence unavailable 必須獨立 reason/evidence/confirm，清楚標示「未建立簽章／送達事實」。
3. 缺root action只依 registry exact descriptor路由到owner workbench；成功receipt後fresh讀 owner、stage與anomaly三方。
4. timeout不自動重送；保留same payload/key reconciliation，stale要求fresh Preview。

### Direct verification

- browser/DOM不顯示tracking status作主要修正；最後一個issue完成後active list移除。
- disabled capability、unknown descriptor、schema drift、readback failure與outcome unknown均fail closed。

## 5. HOB-WP-D：React訂單取消逐日確認與帳務明細

- Objective：讓現行 backend cancellation 在React真正可操作，且移除不存在的違約金文案。
- Requirements：規格 §3.1、HOB-A4、HOB-A4B、HOB-A4C。
- Dependencies：既有 Orders Cancellation Query／Preview／Apply；不依賴HOB-WP-A schema。
- In scope：strict cancellation impact schemas/client、逐日實際服務日期＋月嫂＋必要reason editor、Client Finance／Payroll action金額明細、confirmation/readback、React tests。
- Exclusions：修改取消公式、額外違約金、付款執行、backend owner mutation、schema。
- Effect ceiling：React及其typed client/tests；若發現backend payload不能形成strict public view，停止並回到API schema package，不以raw record繞過。

### Ordered steps

1. 服務前預設confirmed days為空，即使已有未來assignment也不得送出；服務中以既有日期預填，但操作者必須移除未服務未來日並逐日確認staff。
2. 新增/改派日期必填reason；未來日、重複日、無staff、完整履約與service-data lock blocker在Preview前後皆清楚顯示。
3. Preview明列Client各stage before/after/action/refund-or-adjustment，以及Staff各assignment before/after/payable-or-recovery；不得只顯示泛稱已計算。
4. Apply沿用expected四個owner versions、fingerprint、reason、idempotency；receipt後fresh readback Orders與相關alerts。

### Direct verification

- 服務前有正式未來排班仍送空actual days且可Preview；服務中四天排班只確認兩天時只提交兩天。
- 完整履約取消零Apply；退款／薪資未結清時不顯示「全部異常已解除」。
- 文案不含違約金，除非未來另有人工核准公式。

## 6. HOB-WP-E：服務前整案換人與重回媒合

- Objective：當 current owner roots 證明尚未有任何正式服務事實、現任月嫂已無法
  履約時，以 version-increasing typed event 建立 successor matching round，讓 Orders current SOP
  回到 server-owned Step 2／3／4；已服務案固定 referral 到既有 leave／substitution。
- Requirements：規格 §2、HOB-A6／A7；`01_Orders_Domain.md` 作業步驟回退；
  `02_Assignments_Scheduling_Domain.md` Assignment Plan／Leave／Substitution。
- In scope：Scheduling owner pure candidate、Query／Preview／Apply，service-fact fresh lock，old/new
  matching／assignment／lock／commitment bindings，immutable event／receipt／outbox，Orders stage projection，
  exact Anomalies referral，focused tests。
- Reuse：existing matching round／coordination、assignment generation，waiting-lock cancel，stage projection，
  outer Unit of Work與idempotency receipt；不用 legacy direct-SQL `create_matching_plan_version` 當正式 owner command。
- Exclusions：已服務案整案回 Step 2、原地改 staff id、刪歷史、自動退定金、新建薪資公式、
  人工 target status editor、production／`union_db`。
- Effect ceiling：若 persistence 需新 table／column／constraint／index／trigger／view，必須另以 additive
  release 通過根層 §3.1 全部 DB gates；本包不得修改已 hash-locked release。

### Ordered steps

1. pure candidate 鎖定 case／Orders／Scheduling／matching／assignment identity與version，reason、
   evidence與 no-actual-service proof；只要有一日 official service fact就回
   `caregiver_replacement_requires_substitution`且零寫入。
2. Preview 列出將 supersede 的 caregiver-bound roots 與保留的 Orders／Client Finance roots；
   建立 successor matching round candidate 並由 earliest-invalidated-root 計算 resume step。
3. Apply fresh lock/rebuild；append replacement event、supersede links、successor round、receipt、outbox，
   及必要的 waiting-lock／assignment current projection 轉移在同一 outer Unit of Work commit。
4. same key＋same payload replay；same key＋different payload、stale／identity drift／missing readback／
   actual service／partial write 皆 fail closed。成功後 fresh Query Orders stage／effective Scheduling／
   matching successor／anomalies，不以 receipt 單獨宣稱完成。

### Direct verification

- `v10 / Step 10 / no service → v11 replacement event → Step 2`，old roots append-only且不滿足新 round。
- 有 actual service 時 replacement Preview 零寫入並回傳既有 leave／substitution referral；
  Payroll 不由本包重算。
- 日期／金額／條款不變時不新建 Client Finance obligation，定金根事實保留。

## 7. Bidirectional coverage

| Requirement／Acceptance | Source | Package step | Oracle |
|---|---|---|---|
| append-only baseline／A1／N2 | controlling spec §1–2 | WP-A 1–3 | immutable event、replay/conflict、0 fake roots |
| lineage不倒退／A3 | controlling spec §2 | WP-A 2–4；WP-B 3 | higher version successor可追溯、stale fail closed |
| missing root可修／A2／A5 | controlling spec §1、§3–4 | WP-B 1–3；WP-C 3 | occurrence detail→owner Q/P/A→fresh inactive |
| 取消分流／A4/A4B/A4C | controlling spec §3.1 | WP-B 4；WP-D 1–4 | pre/mid/full scenarios與Finance alert isolation |
| 不偽造／N1 | Global、Orders、Anomalies | WP-A 1–3；WP-B 2；WP-C 2–4 | tracking/receipt/provider/readback negative matrix |
| React可操作 | 使用者異常中心需求 | WP-C、WP-D | strict client/component/build＋真API/Browser |
| 服務前換人／服務中代班 | 2026-08-27 人工裁決 | WP-E 1–4；WP-B 5–6 | no-service 回 Step 2／3／4；actual-service 固定導向既有 substitution |

## 8. Stop conditions、evidence與交接

- owner、SSOT、business formula、public API或schema超出本包時立即停止並回spec；不得以測試便利擴張。
- 任一 `apply_patch` 超過30秒由執行協調者中止並通知使用者；本包本身不選擇Agent拓撲。
- 服務未啟動時MySQL/API/Browser標`NOT_RUN`，不得以mock代替；source工作與不依賴服務的focused驗證可繼續。
- 保存最小 final receipt、命令、測試摘要、schema gate表與去敏Browser證據；raw/intermediate output留ignored scratch並於final receipt後依治理清理。

`package_status`: `SUPERSEDED`；本文只保留歷史編譯軌跡，current package scope、authority、acceptance與狀態一律以
`PROV-20260827-historical-order-operational-work-packages.md` 為準。

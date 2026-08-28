# 三類財務追償／溢撥異常閉環工作包

- 狀態：`approved`
- package status：`PACKAGE_READY`
- Authority digest：2026-08-26 使用者要求所有異常有人工修正，且自動解除必須符合 owner 規則書；已授權本機 code/tests 與 `lu_test_*` 受控 mutation，不含 replacement、schema、`union_db`、production 或 provider。
- controlling spec：`PROV-20260826-finance-recovery-anomaly-closure-spec.md`（`SPEC_READY`；convergence `READY`）。
- codes：`GOVSUB-006`、`client_over_refund_recovery_open`、`staff_overpayment_recovery_open`。

## Necessity／reuse

| Candidate | Classification | Basis／reuse decision |
|---|---|---|
| owner root lifecycle → anomaly projection correctness | `required_now` | reuse existing owner roots/outbox/projector; minimal-glue；現況會晚建、漏更新或不解除。 |
| exact owner recovery detail Query | `required_now` | reuse existing repositories/domain candidates；minimal-glue；不得由 UI/alert 推算。 |
| React typed clients/renderers | `required_now` | copy-adapt current strict transport/finance correction UX contract；不重用 raw Streamlit client。 |
| generic all-code form engine | `remove` | 未由規格要求，會形成 generic root editor。 |
| recovery evidence additive schema／migration | `required_now` | 唯有的方式是保存 reason 以外的不可變人工佐證；不改金額／狀態語意。 |
| 其他 schema／migration | `remove` | 超出本規格與使用者要求的最小必要範圍。 |
| provider／production deployment | `required_later` | 明確排除於 current effect ceiling。 |

## FRAC-WP-A：Owner projection 與 typed context

- Objective：讓三碼從 root 建立到 partial/full completion 都投影正確，並提供符合規則書的 strict typed context。
- Requirements：FRAC-R1、R2、R3、R5；Acceptance：FRAC-A1～A5。
- Dependencies：既有 Government Subsidy／Client Finance／Staff Payables roots、outbox、repository、recovery action descriptors。
- Effect ceiling：本機 source/tests、既有 schema 上的 `lu_test_*` scenario rows；0 schema／migration／provider／production。

### Ordered steps

1. 為 client/staff recovery establishment 產生或路由 owner outbox event，使 open root 在 matching 前即可投影；event payload 只含必要 identity/version，不含 raw bank／PII。
2. 擴充三個 anomaly consumers：fresh query current root，建立 active/partial/inactive desired state；消費 Government offset/return、Client recovery update、Staff recovery update/collected 等合法事件；exact replay 與 monotonic version 保持現有 projector contract。
3. 由 owner query 提供 remaining/status/version、合法 target／recipient readiness／matching evidence；補 strict API schemas 與 action descriptor required inputs。Anomalies 只組合 typed result，不重算金額。
4. 完成 focused positive、partial、full、stale、replay、malformed payload、missing owner root、transaction failure／rollback 與 redaction tests。
5. 在受控 `lu_test_*` 建立唯一 scenario identity，驗證 root establishment → alert active → partial remains active/updated → full/disposition inactive；保存 before/after readback 並 scoped cleanup。

### Verification oracles

- 三碼 establishment event 後各只有一筆正確 fingerprint 的 active alert。
- `GOVSUB-006` 只有 status=`pending_review` active；offset/return terminal receipt 後 inactive。
- Client／Staff remaining >0 時 active 且 amount/version 更新；`recovered|adjusted` 且 remaining=0 才 inactive。
- query failure、stale/readback unavailable、outbox delivered 但 root 未完成時保持 active。
- same event replay 不新增 occurrence/current row；malformed/cross-owner payload 整筆 rollback。

### Stop／rollback／evidence

- 發現需 schema／migration、改 owner 金額公式或新 capability 時停止並回 spec/Authority；不得擴包。
- 測試資料只清理本 package scenario rows；不清理其他資料。Source rollback 為回退本包 patch；DB mutation 以 scoped scenario cleanup/replay receipt 對帳。
- 保留 focused test command、真 MySQL before/after/predicate receipt、失敗 negative summary；不得保存 raw 個資。

## FRAC-WP-B：React typed remediation workbench

- Objective：讓操作者由 anomaly context 實際完成三碼 Query／Preview／Confirm／Apply／readback。
- Requirements：FRAC-R2、R3、R4、R5；Acceptance：FRAC-A2～A7。
- Dependency：FRAC-WP-A projector 與 FRAC-WP-C owner Query/evidence final strict API contract 的 tests PASS。
- Effect ceiling：React source/tests、本機真 FastAPI＋Vite browser；0 schema／provider／production。

### Ordered steps

1. 為 Government Subsidy、Client Finance、Staff Payables 各建立 bounded strict Zod schemas、typed errors 與 client；只接受已核准固定 endpoints／operations。
2. 建立三個 `form_schema_key` renderer；readonly source bindings，顯示 current root evidence／完成條件／blocker，提供有限 branch/target/amount/reason/evidence inputs。
3. 接入既有 Anomalies recovery dispatcher；未知 schema/version、owner mismatch、binding 缺失 fail closed。不得以 definition-code endpoint switch 或 raw dict 穿透。
4. 實作 Preview invalidation、Apply lock、same-key outcome reconciliation、partial/full readback 與 anomaly list refresh；只有 inactive predicate 顯示已解除。
5. 跑 strict client/schema、component、dispatcher focused tests，再以真 FastAPI＋Vite Browser 驗證三碼至少各一條正向流程及 partial/stale/typed error negative flows。

### Verification oracles

- Network payload 只含 typed owner fields；source identities/version readonly。
- Preview 前 Apply disabled；input change invalidates candidate；double submit 無第二 mutation。
- partial receipt 顯示新 remaining 且 alert 保留；full/disposition readback 後 alert 從 active list 消失。
- timeout/unknown 以同 identity re-query；未確認 terminal result 不顯示完成。
- 無 console error、無 mock-only completion claim、無 Finance form 誤套其他 owner。

### Stop／rollback／evidence

- API response 與 WP-A final contract 不同時停止並回 WP-A，不在 UI 放寬 decoder。
- Browser 需要 provider、production credential 或 schema 時停止；本包只用 local test identity與 `lu_test_*`。
- 保留 focused test output、Browser Network↔DOM receipt 與去敏 screenshot；移除重複暫存。

## FRAC-WP-C：Owner Query 與 immutable evidence contract

- Objective：先凍結 React 所需的 current owner facts，並讓 client/staff authorized adjustment 保存
  獨立 evidence reference。
- Requirements：FRAC-R2、R3、R3A、R5；Acceptance：FRAC-A2～A5、A8、A9。
- Dependencies：FRAC-WP-A projector contract；正式 `14`／`16` owner rules。
- Effect ceiling：owner Query/API/schema/repository/tests 與 additive evidence release；禁止金額公式、
  status semantics、`union_db`／production／provider。

### Ordered steps

1. 完成 DB scope/change inventory、static release、descriptor 與 read-only plan gates；只新增 client/staff recovery
   event 獨立 evidence reference 所需 additive object，既有 rows 必須可保留。
2. 將 evidence 納入 strict Preview/Apply body、command fingerprint、event/receipt、replay/conflict；
   不得把它合併到 reason 或來源銀行描述。
3. 建立 Government/Client/Staff 各自 bounded recovery Query repository、strict response schema 與 GET；
   Query 只讀 committed root/eligible targets/readiness，不讓 Anomalies 重算。
4. 更新 registry descriptors：open recovery 有 matching 與 authorized adjustment，matched recovery 另有 collection；
   Government inputs 完整列出 targets/due date/evidence/reason。
5. 跑 schema metadata/manifest/descriptor/plan tests、fresh bootstrap 與 preserve-data disposable candidate；
   之後跑 owner API zero-write/stale/replay/evidence/query focused tests。

### Verification oracles

- 缺 evidence 不能 Preview/Apply；same key 更換 evidence conflict；去敏 evidence 可由 immutable event/receipt 對讀。
- Query 回傳 current remaining/status/version；Government target/readiness 來自 owner，不是 UI 推算。
- open recovery 即有 matching/adjustment；matched 才有 collection；任一 action receipt 都不直接宣告解除。
- schema gate 任一必要項 `BLOCKED|NOT_RUN` 時總結仍為 `DB_CHANGE_NOT_READY`。

### Stop／rollback／evidence

- 需變更 owner 金額／status/capability 時停止。未經另行精確授權不對現有 `union_db`
  或 configured source 做 replacement／`--switch`。
- rollback 是此 additive release 的明確 rollback artifact；驗證只用 disposable DB 或 allowlisted `lu_test_*`。

## FRAC-WP-D：Projector dead-letter 與人工復原

- Objective：壞的 projector event 不再無限重試或擋住後續事件，管理員能在修正來源後
  透過可稽核的 Preview／Apply 重試，或在有已驗證 successor 時處分舊事件。
- Requirements：FRAC-R1、R5、R6；Acceptance：FRAC-A5、A10。
- Dependencies：三個 owner projector 與現有 `admin_command_receipts`；不依賴 React WP-B。
- Effect ceiling：三個 consumer、Anomalies maintenance Query／Preview／Apply、static outbox allowlist、
  admin receipt adapter 與 focused tests；0 schema／provider／production。

### Ordered steps

1. 將三個 consumer 固定為最多 3 次自動嘗試，claim 排除達上限事件，失敗寫去敏
   stable error code；證明 poison event 不阻擋後續 event。
2. 建立 bounded dead-letter Query；只以 static mapping 查詢三個 outbox 的已登錄 intent，不回傳
   payload snapshot、raw error 或 PII。
3. 建立 retry Preview／Apply；鎖定 event 並核對 expected attempt/status、reason/evidence、fingerprint、
   capability 與 idempotency，同交易重排及寫 admin receipt。
4. 建立 fail-closed supersede Preview／Apply；只在較高 source version 已投影且 owner root/current alert
   readback 等價時提供，不改舊 event 為 delivered。
5. 驗證 stale、concurrent worker、same-key/different-payload、missing evidence、transaction rollback、
   retry 後再失敗／recover，supersede blocked/successor 正向路徑。

### Verification oracles

- 第 3 次失敗後同 event 不再自動 claim，下一 event 仍可處理。
- 人工 retry 只重排 projector event；owner root 未完成時 business alert 仍 active。
- retry/supersede 的完成只以 immutable receipt 表示維運命令已提交，不取代各碼業務解除條件。
- 沒有 successor 或 owner readback 不可用時，dead-letter 保持可見且 supersede 拒絕。

## Bidirectional coverage matrix

| Requirement／Acceptance | Source | Package step | Oracle |
|---|---|---|---|
| FRAC-R1／A1／A5 | spec lifecycle、`14`/`16` state machine | WP-A 1-3 | establishment/partial/full MySQL projection readback |
| FRAC-R2／A2 | `06` detail contract | WP-A 3-4；WP-B 1-3 | strict schema/redaction＋DOM exact evidence |
| FRAC-R3／A3／A4 | Global Q/P/A；owner command rules | WP-A 3-5；WP-B 2-4 | zero-write Preview、stale/replay/rollback receipts |
| FRAC-R3／A8 | `16` reason/evidence／adjustment | WP-C 1-2，5 | additive schema，fingerprint，event/receipt replay |
| FRAC-R3A／A9 | `14`／`16` owner Query | WP-C 3-5 | strict GET／zero-write／missing/ambiguous tests |
| FRAC-R4／A6／A7 | `06` React dispatcher | WP-B 1-5 | typed unit/component＋真 API/Vite Browser |
| FRAC-R5 | Authority/effect ceiling | WP-A/B stop checks | diff inventory、schema NOT_APPLICABLE、provider=0 |
| FRAC-R6／A10 | `06` projector dead-letter/manual recovery | WP-D 1-5 | retry ceiling、queue progress、typed maintenance receipt／supersede blockers |

所有 retained step 均回指上述需求；沒有 research/adoption candidate 或外部套件。

結果：`PACKAGE_READY`，交 DDH 選擇執行拓撲。

## 2026-08-27 執行證據快照

- WP-A：三個 owner projector、terminal predicate、status／remaining invariant 與 matching guard 已實作；focused
  backend final candidate `144 passed`。另於真 MySQL `lu_test_task96_fin_recovery_r4b` 驗證三碼 lifecycle：
  Government 只有完成 offset disposition 後解除；Client／Staff partial 均保持 active，remaining 歸零且 owner
  root terminal 後才 inactive，`3 passed`。這些判定來自 fresh owner root readback，不以 receipt、outbox delivered
  或 tracking status 代替業務完成。
- WP-B：三個 strict React client/workbench 已由三條隔離 Luna High lane 完成，主整合器只依 exact
  action descriptor、`form_schema_key` 與 typed source bindings 路由；focused `24 passed`、oxlint PASS、
  production build PASS。
  真 FastAPI＋Vite Browser 的三碼 Query/detail、owner completion text、exact action routing 與 local-bypass
  Preview 403 負向已 PASS；enabled persisted human 的正向 Apply／partial／stale 仍 NOT_RUN。
- WP-C：owner Query/evidence source 與 additive release static evidence已完成；Docker Desktop 的 explicit CLI
  可用，`mysql_db`／`union_redis` 均運行。final schema fresh bootstrap 與三碼真 MySQL lifecycle PASS；另由
  pre-1007 `lu_test_task96_finrec_source_1006` 建立四張 altered table 的代表性舊 event／matching，完成 dump →
  absent candidate restore → 1007／1008 ordered apply → verify。兩 release 均為 `exact`，四筆舊資料的 pre-additive
  columns／row fingerprint 保留，新 `evidence_reference` 均為 NULL，沒有暗中補造人工證據。developer local
  replacement／`--switch` 仍 NOT_RUN，故總結仍為 `DB_CHANGE_NOT_READY`。完整 receipt：
  `03_追蹤清單與證據/evidence/2026-08-27_finance_recovery_anomaly_mysql_receipt.md`。
- WP-D：三次自動嘗試上限、dead-letter Query、具 reason／獨立 evidence 的 retry Preview／Apply 與 immutable
  receipt 已完成；人工 retry 只重排事件，不宣稱業務解除。supersede 已改為只在「更高版本
  successor 已 delivered＋exact projection receipt＋current alert/source version＋fresh owner roots 等價」時寫入
  immutable admin receipt；舊事件不重排、不修改 delivered 狀態。focused Python `25 passed`，獨立
  Luna High 覆核無 P0／P1 假解除路徑。真 MySQL queue-progress integration 因本次未啟動 DB／service，仍為 `NOT_RUN`。

DDH 在本快照後原計畫以三條 Luna High 唯讀 lane 分別覆核 Government／Client／Staff runtime readiness；Host
已結束的 agent threads 仍占滿 thread quota，沒有新 lane 被建立。這是 material capability delta，故只重投影
剩餘工作並由 E4 改回主代理單寫者的 E0–E2 序列驗證；沒有競爭寫入，也沒有把未啟動 lane 算成子代理成果。

後續規則書 reconvergence 使用三條既有 `gpt-5.6-luna`／`high` 唯讀 lane，分別覆核
finance/staff/government、LINE/access/service、scheduling/orders；三者 write set 均為空且已 terminal。共享
FastAPI／Vite／MySQL Browser integration 開始後，runtime state 不具隔離性，DDH 再由 E4 動態調整為 E2
主代理單一 writer。Browser 暴露的 source-domain／detail-action drift 使 verification profile 增加 public API、
DOM 與 auth-negative，但沒有改變 owner Authority 或「fresh root predicate 才能解除」的規則書門檻。

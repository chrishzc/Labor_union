# 客戶應收、應付與補助退還異常 remediation 工作包

- 狀態：`approved`
- package status：`PACKAGE_READY`
- Authority digest：2026-08-26～2026-08-27 使用者要求所有異常有人工修正，自動解除必須符合 owner 真實業務流程；本機 `lu_test_*` 可做受控 mutation，不含 schema、replacement、`union_db`、production 或 provider。
- controlling spec：`PROV-20260827-client-settlement-anomaly-remediation-spec.md`（`SPEC_READY`；convergence `READY`，blockers `[]`）。
- codes：`RECEIVABLE-001`、`CLIENTPAYABLE-001`、`RETURN-001`。

## Entry、necessity 與 reuse checks

| Candidate | Classification | Source basis／reuse decision |
|---|---|---|
| owner current detail Query composition | `required_now` | `04_Client_Finance_Domain.md` §2–3與 CSR-R1；reuse 既有 receipt/refund repositories，`minimal-glue` 組合本碼 obligations 與 eligible bank facts。 |
| anomaly-bound action descriptors/projector predicate | `required_now` | CSR-R2–R3；reuse canonical anomaly registry/projector，不建第二個 alert state machine。 |
| receipt/refund/subsidy-return owner Q/P/A | `required_now` | `04` §6 與 live routes/workflows 已存在；`reuse`，只補齊 strict query/action handoff 與異常綁定。 |
| React strict clients/workbenches | `required_now` | CSR-R2、A2；`copy-adapt` 既有 Client Receipt typed query transport 與 Finance recovery workbench interaction contract。 |
| generic dynamic form engine / generic alert close | `remove` | 不符 CSR-R2/R4，且會繞過 owner 根事實。 |
| auto allocation / auto customer communication | `remove` | 規格只允許自動 fresh recheck；ownership 或 bank fact 不唯一時必須人工。 |
| schema、seed、backfill | `remove` | CSR-R4 及 schema inventory 均為 none；如出現即停止回規格／DB gate。 |
| production/provider execution | `required_later` | 超過 current effect ceiling，本批次不進入工作包。 |

Research status：`NO_RESEARCH`。所有重要決策皆由 current 正式 Client Finance/Anomalies 規格與專案內已存 owner Q/P/A 覆蓋，不採用外部套件或第三方實作。

## CSR-WP-A：Owner detail、action context 與 terminal projection

- Objective：以 Client Finance current root 提供三碼具體 detail 與 immutable typed actions，並以完整的同碼逾期 obligation predicate 建立／更新／解除 alert。
- Requirements：CSR-R1、R2、R3、R4；Acceptance：CSR-A1、A3–A7。
- Preconditions：Client Finance formal Q/P/A 與 canonical `client_obligations`/ledger/allocation repositories 仍是 current；現有 schema 可支援所需 Query。
- Effect ceiling：Client Finance/Anomalies query、action descriptor、projector/consumer composition 與 focused tests；受控 `lu_test_*` scenario rows；0 schema/provider/production。
- Exclusions：generic resolve、直接 UPDATE obligation/projection、猜測 bank ownership、修改金額公式或 transaction boundary。

### Ordered steps

1. 新增／擴充 bounded Client Finance current Query：依 case 回傳 account version、三碼分離的當前 obligations、due/remaining/type/direction 及合法 incoming/outgoing bank fact 的去敏 typed candidates；Query 零寫入。
2. 為三碼建立 exact action descriptors：固定 owner、form schema/version、capability、Query/Preview/Apply operation、source bindings、operator inputs 與 completion predicate；identity/version 缺失或錯 owner 時不提供 action。
3. 修正 detector/projector：每次只用 fresh current obligations；同碼任一逾期 `open` positive remaining 即 active，全部消失才 inactive。`CLIENTPAYABLE-001` 與 `RETURN-001` 使用互斥 type predicates。
4. 綁定 owner commit/outbox/recheck entry，讓 apply、replay 或 scanner 能可重放地更新 alert；receipt/outbox delivered 不直接寫 inactive。
5. 完成 unit/API/projector tests：多 obligation、部分清償、全部清償、一般退款／補助退還隔離、stale/readback failure、replay、wrong direction/type、transaction rollback 與 redaction。

### Verification oracles

- detail 的 identities/count/sum/type/direction/version 與同一交易中讀取的 owner facts 一致，不含 raw PII/bank description。
- 三碼各只有一個正確 fingerprint；任一筆同碼 overdue open balance 存在時 active。
- 只清一部分 obligation 後 detail/version 更新但 alert 不消失；同碼全部歸零才 inactive。
- refund 完成不影響 subsidy-return alert，反之亦然。
- Query/readback 失敗、stale 或事實非唯一時保留 current alert，不生成修正 mutation。

### Failure、rollback 與 evidence

- 如需 schema、新 capability、金額／到期公式或新 owner command，立即停止並回 `spec-workshop`；如為 DB 變更，再依專案 3.1 回報 gate table。
- source rollback 只回退本包 patch；DB 只清理本包唯一 scenario identities，保留 before/after/readback receipt，不動他人 rows。
- 保留 focused command summary、去敏 detail samples、predicate before/partial/full receipts；刪除重複 raw dump。

## CSR-WP-B：React bounded 人工處理工作台

- Objective：讓人員由異常頁完成三碼真實 owner `Query → Preview → Confirm → Apply → readback`，包括依電話結果人工選擇正確根事實。
- Requirements：CSR-R1–R3；Acceptance：CSR-A1–A2、A4–A8。
- Dependency：CSR-WP-A final exact Query/action descriptor contract 的 strict tests PASS。
- Effect ceiling：React strict schemas/clients/components/dispatcher/tests 與本機 Vite Browser；0 schema/provider/production。
- Exclusions：tracking editor 作為 completion、raw dict 穿透、definition-code endpoint switch、電話／LINE 送達即解除。

### Ordered steps

1. 依 WP-A final contract 建立 three bounded strict Zod schemas、typed errors 與 typed clients；每個 form schema 只能呼叫對應 owner operations。
2. 建立三個或一個具 sealed purpose branches 的 Client Settlement workbench；顯示所有本碼 obligations、餘額、到期日、bank candidates、blocker 與「全部同碼義務歸零才解除」。
3. 接入 Anomalies exact action/form-schema dispatcher；source identities/version 只讀，未知 schema/version、owner mismatch、binding 缺失均 fail closed，不 fallback 到 tracking close。
4. 實作選擇 bank/obligation、reason、Preview invalidation、確認、Apply lock、same-key unknown-outcome reconciliation 與 fresh owner readback。
5. 只有 readback 證明原 code inactive 才顯示已解除並 refresh list；partial 顯示剩餘明細與下一可行動作。
6. 完成 strict schema/client/component/dispatcher/accessibility tests，覆蓋三條正向、partial、type isolation、input mutation、double submit、stale、typed error、timeout/readback unavailable。

### Verification oracles

- UI 精確列出「哪些義務、金額、到期日、何種方向」異常，而非只顯示 code 或累計次數。
- Preview 前 Apply disabled；任一 input 改變使 preview invalid；apply 期間禁止關 drawer/重複送出。
- receipt 不導致異常立即消失；partial readback 保留 alert，terminal fresh readback 才 refresh 後消失。
- refund/subsidy-return 的 endpoint、labels、obligation type 與 completion copy 不交叉。
- keyboard/focus/role/disabled reason 可被組件測試與 Browser 觀察，無 console/schema error。

### Failure、rollback 與 evidence

- WP-A final response 與 decoder 不一致時停止，不在 UI 放寬 schema。outcome unknown 保留原 command identities，先 re-query/reconcile，不產生新命令。
- rollback 為回退本包 React composition；不需 DB cleanup。
- 保留 focused test/build summary 與去敏 DOM/network evidence；不保留 raw bank description。

## CSR-WP-C：真 API／MySQL／Browser 端到端驗收

- Objective：在真實本機 stack 證明三碼的人工修正與規則書解除判斷一致。
- Requirements：CSR-R1–R4；Acceptance：CSR-A1–A8。
- Dependencies：CSR-WP-A/B final candidates 的 focused tests PASS；Docker daemon/MySQL/FastAPI/Vite 可用；target 通過 `APP_ENV=development` 與 `lu_test_*` allowlist 回讀。
- Permission atoms：已允許本機 test DB 的 owned-row mutation/scoped cleanup；不得擴張至 schema/replacement/provider/production。
- Effect ceiling：唯一 scenario identities 的 test rows、本機 servers 與 ignored scratch evidence。

### Ordered steps

1. 啟動／健檢 Docker MySQL、FastAPI 與 Vite；回讀 environment/host/database/credential class，target 非 `lu_test_*` 即停止。
2. 以唯一 scenario identities 建立三碼各至少一條正向根事實，另建部分清償、type isolation、stale／readback failure 可控測試情境；保存 before inventory。
3. 透過真 API 與 Browser 開啟異常，核對 detail 後實點 Preview／Confirm／Apply，比對 Network typed payload、DOM、owner readback 與 alert recheck。
4. 正向：三碼各證明同碼所有義務歸零後 alert 消失；部分：證明 receipt 成功但另一筆餘額存在時 alert 仍 active。
5. 負向：證明 refund/subsidy-return 互不解除、stale/timeout/readback unavailable 不顯示完成，same-key replay 不建第二交易。
6. 以 scoped cleanup 移除僅屬本包的 owned rows，重讀無殘留；若選擇保留，在 receipt 明記 identity 與理由。

### Verification oracles

- MySQL owner rows、API detail、Browser DOM 與 anomaly active list 的 identity/version/predicate 四方一致。
- 每條 Apply 都有唯一 idempotency/correlation identity、before/after root readback 與去敏 receipt。
- 部分／外部聯絡／receipt-only／stale／readback-failure 反例都保留 alert。
- 正向終態不只是 HTTP 200；必須有 obligation remaining=0 與 alert absent 的 fresh evidence。

### Timeout、human fallback、cleanup 與 evidence

- 有限時間啟動與測試；server 無法啟動時保留 log 與明確 blocker，不以 mock 取代。Apply 結果未知時由人員使用原 identity 重讀，禁止新 key 重送。
- 不執行 reset/replacement/`--switch`；不清理其他 rows。清理前先重讀 exact target。
- final receipt 保留 environment/DB allowlist 回讀、scenario inventory、commands、test counts、predicate before/partial/full、Browser DOM/network summary 與 cleanup/readback；raw stdout 與重複 screenshots 在 final receipt 後可刪。

## Bidirectional coverage matrix

| Requirement／Acceptance | Source | Package step | Direct oracle |
|---|---|---|---|
| CSR-R1／A1 | `04` §2–3 Query/SSOT | WP-A 1、5；WP-B 2；WP-C 2–3 | owner identity/count/sum/version = API detail = DOM |
| CSR-R2／A2／A6 | `04` §6 commands，refund/subsidy-return isolation | WP-A 2；WP-B 1–4、6 | exact descriptor/dispatcher，typed payload，type isolation |
| CSR-R3／A3–A5／A7 | Global Q/P/A，`04` exact allocation | WP-A 3–5；WP-B 4–6；WP-C 3–5 | zero-write Preview，partial active，terminal absent，stale/replay/rollback |
| CSR-R4／A8 | architecture/effect ceiling | WP-A stop gate；WP-B decoder stop；WP-C 1–6 | diff inventory schema=0，real allowlisted MySQL/API/Vite Browser evidence |

## Readiness result

每個 retained step 均回指 current requirement/invariant，三包的 handoff、effect ceiling、negative paths、rollback/reconciliation、human fallback 與 direct evidence 皆完整。結果：`PACKAGE_READY`。本文不選擇 Agent 數、E-level 或 writer 拓撲；交由 DDH 依執行時的 Authority、隔離、驗證與 capability 現況決定。

## 2026-08-27 執行狀態

| Work Package | 狀態 | current evidence |
|---|---|---|
| CSR-WP-A | `completed` | 三碼 exact registry action、fresh overdue detail/predicate、owner settlement Query 與 refund/subsidy purpose isolation 已完成；final focused owner/anomaly regression `127 passed, 1 skipped`。 |
| CSR-WP-B | `completed` | strict Zod/client、exact dispatcher、Query→Preview→Confirm→Apply→fresh readback workbench與清單文案已完成；React focused `26 passed`、build PASS、lint 只有既有 warnings。 |
| CSR-WP-C | `completed` | 三碼均以真 MySQL/API/Browser 通過 owner Query→Preview→Apply→fresh rulebook recheck→active-list removal；`CLIENTPAYABLE-001` 另證明 partial retain，`RETURN-001` 證明與一般退款互斥。實測修正 payable `adjustment` loader 漂移及 MySQL `Decimal` account-version stale binding。 |

final evidence：`03_追蹤清單與證據/evidence/2026-08-27_client_settlement_anomaly_remediation_progress_receipt.md`。

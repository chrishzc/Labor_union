# 客戶應收、應付與補助退還異常 remediation 規格

- 狀態：`approved`
- convergence：`READY`
- specification status：`SPEC_READY`
- Authority digest：2026-08-26～2026-08-27 使用者明確要求每個異常都有人工修正途徑，且自動解除必須符合真實業務流程與 owner 規則書。
- codes：`RECEIVABLE-001`、`CLIENTPAYABLE-001`、`RETURN-001`
- owner：Client Finance Domain；Anomalies 只組合 typed capability，不擁有帳務根事實。
- controlling rules：`01_規格基線/00_Global_共同契約.md`、`04_Client_Finance_Domain.md` §2–3、§5–6，以及 `06_Anomalies_Domain.md` 的全異常人工 remediation 閉環。

```yaml
convergence:
  status: READY
  blockers: []
```

## 1. Scenario 與業務語意

異常中心發現同一案件尚有已逾期、`open`、正整數餘額的 Client Finance obligation 時，操作者必須看到具體義務、方向、種類、到期日、餘額、owner version、可用 canonical bank facts 與無法處理的 blocker，並能由異常頁進入同一套 Client Finance `Query → Preview → Confirm → Apply → root readback` 正式流程。

「人工修正」不代表人員可以直接把 alert 關掉，也不代表可以徒手改 obligation 餘額。當客戶以電話補充或更正資訊時，業務人員可以依電話取得的結果，在合法的 owner 工作台選取正確案件、obligation 與已匯入的 canonical bank fact，再進行 Preview／Apply。電話本身、LINE 通知送達或帳務人員的口頭確認都不是付款根事實；缺 canonical bank fact 時異常必須保留並顯示 blocker。

## 2. 三碼唯一 remediation 契約

| Code | 真實問題 | 人工 owner 流程 | 不可代替的完成條件 |
|---|---|---|---|
| `RECEIVABLE-001` | 本案尚有逾期客戶應收：`deposit/first/second/adjustment` | `QueryClientFinance` → `PreviewClientReceiptReconciliation` → `ApplyClientReceiptReconciliation`；人員選取正確 incoming bank facts 及義務 | 當前重讀時，此碼所有逾期 `receivable_from_client` 義務餘額精確為 `0` |
| `CLIENTPAYABLE-001` | 本案尚有逾期一般客戶應付：`refund/adjustment`，不含補助退還 | `QueryClientFinance` → `PreviewClientRefund` → `ApplyClientRefund`；人員選取正確 outgoing bank facts 及一般退款義務 | 當前重讀時，此碼所有逾期 `payable_to_client` 且類型為 `refund/adjustment` 的義務餘額精確為 `0` |
| `RETURN-001` | 本案尚有逾期客戶補助退還：`subsidy_return` | `QueryClientFinance` → `PreviewClientSubsidyReturn` → `ApplyClientSubsidyReturn`；只選取合法 outgoing bank facts 及 `subsidy_return` 義務 | 當前重讀時，此碼所有逾期 `subsidy_return` 義務餘額精確為 `0` |

每次正式核銷都必須完整分配所選銀行流水，且每個所選義務在同一 Apply 後精確為 `0`。少收、超收、方向錯誤、錯案、ownership 不明或部分 allocation 不得建立部分正式交易。一般退款與補助退還不得共用 entry type、reversal type、餘額或狀態 reducer，也不得互抵。

## 3. 自動化邊界與解除判斷

### 3.1 允許的自動化

- detector/projector 可在 owner Apply 提交後、相關 outbox 重放、定時掃描或異常清單重查時，自動 fresh-read 目前 obligation 根事實並重算本碼 predicate。
- 只有此碼的全部逾期、open、positive-remaining obligation 都不存在，才可投影 `active=false`，讓 alert 自當前頁面消失，且後續狀態可繼續推進。
- 同案有多筆當前義務時，單次 Apply 若只完成其中數筆，可自動更新 detail，但 alert 必須保留。

### 3.2 禁止的弱解除條件

下列事實都不能單獨解除異常：

- 人工 claim/resolve/tracking status 已改變；
- LINE、電話、email 聯絡成功，或客戶口頭表示已付款；
- Preview 成功、Apply HTTP 成功、receipt 存在、job/outbox 已受理或 delivered；
- 只有所選義務歸零，但同碼仍有其他逾期正餘額義務；
- 一般退款歸零但 `subsidy_return` 仍未清，或反之；
- owner root 重讀失敗、version 已 stale、identity 不唯一或方向／種類不一致。

上述任一情況必須 fail closed：異常保留，顯示 current blocker 與可恢復操作，不得因外部聯絡或技術 receipt 繼續被異常阻擋的流程。

## 4. Detail 與 typed action contract

### CSR-R1 — 可行動的問題明細

detail 必須來自 Client Finance current Query，至少顯示：`case_no`、本碼完整 obligation identities、payment direction、obligation type/stage、due date、remaining NTD、account version、可選 canonical bank fact 的去敏 identity/date/amount/direction 與 typed blockers。不得只顯示「有逾期帳款」、累計次數或技術 fingerprint。

### CSR-R2 — 三個 bounded form schemas

- `client_finance.receivable_reconciliation.v1`：綁定 case/account version，由 Query 選擇 incoming bank fact 與應收 obligation，呼叫 receipt Preview／Apply。
- `client_finance.client_payable_refund.v1`：綁定 case/account version，只允許 outgoing bank fact 與 `refund/adjustment` payable，呼叫 refund Preview／Apply。
- `client_finance.subsidy_return.v1`：綁定 case/account version，只允許 outgoing bank fact 與 `subsidy_return` payable，呼叫 subsidy-return Preview／Apply。

三者必須使用 immutable source bindings、strict typed response、required capability、reason、idempotency key、correlation id、expected account version 與 preview fingerprint。任一可編輯輸入變更即使 Preview 失效；Apply 必須在人工確認後才開放。不得以 definition code 臨時拼 endpoint，未知 schema/version 必須 fail closed。

### CSR-R3 — 結果調和

Apply 後必須重讀 Client Finance current root，再重查原異常 predicate。timeout、connection loss 或結果未知時，只能使用同一命令 identity/idempotency key 查回 receipt 與 owner root；不得產生第二筆 mutation。

### CSR-R4 — 零新帳務語意

本規格 reuse 已正式定義的 Client Finance obligation、ledger、allocation、Query／Preview／Apply；不新增 generic alert editor、generic adjustment、自動猜配、新付款指令或跨 Domain write。若實作發現必須變更 schema、owner 金額公式、public command、capability 或 transaction boundary，停止並回到規格／DB gate，不得自行擴張。

## 5. Acceptance

- CSR-A1：三碼各有真實 owner Query 的具體 detail，多筆 obligation 完整列出，且去敏／strict schema tests PASS。
- CSR-A2：三碼各有 Anomalies-bound Query／Preview／Confirm／Apply／readback React 工作台；不再以 tracking status 作為主要處理終點。
- CSR-A3：各正向流程以真 Client Finance root 證明本碼所有逾期義務歸零，原 alert 從 active list 消失，後續被阻擋狀態可繼續推進。
- CSR-A4：部分案例覆蓋「只處理一部分 obligation」；detail 更新但 alert 保留。
- CSR-A5：電話／LINE 聯絡成功、Preview/receipt/outbox 成功、stale version、owner readback unavailable、direction/type mismatch、under/over allocation 都不解除 alert。
- CSR-A6：`CLIENTPAYABLE-001` 與 `RETURN-001` 的 obligation、endpoint、entry type、predicate 與 UI 文案相互隔離；任一邊完成不會誤解除另一碼。
- CSR-A7：Preview 零寫入；Apply 的 stale、replay、same-key/different-payload、permission、transaction failure 與 rollback focused tests PASS。
- CSR-A8：以受控 `lu_test_*` 真 MySQL／FastAPI 及真 Vite Browser 驗證三條正向流程與 CSR-A4～A7 負向流程；mock、toast 或單一 HTTP 200 不算完成證據。

## 6. Scope、effect ceiling 與 unresolved inventory

- 允許：本機 source/tests/docs、既有 API/React composition、受控 `lu_test_*` scenario rows 的建立、修改、回讀與 scoped cleanup。
- 禁止：`union_db`、production/provider mutation、未核准 DDL/migration/seed/backfill/reset/replacement/`--switch`、通用 root editor 與人工 alert close。
- schema inventory：目前預期 `schema-only=none`、`system-seed=none`、`business-row-backfill=none`、`destructive=none`。若 diff 出現任一類 DB 變更，本評估失效並必須重走專案 DB gate。
- unresolved owner choice：`none`。三碼 owner、根事實、精確 allocation、transaction type、typed commands、fail-closed 條件與 terminal predicate 皆已由正式 Client Finance 規則書定義；本規格只封裝異常入口與驗收追溯。

## 7. Traceability

| Requirement | Formal source | Live reuse target | Acceptance |
|---|---|---|---|
| CSR-R1 | `04` §2–3 Projection/Query | Client receipt/refund query repositories，Anomalies detail | A1、A4 |
| CSR-R2 | `04` §6 typed commands | receipt reconciliation，refund/subsidy-return routes | A2、A6、A7 |
| CSR-R3 | Global Q/P/A，`04` §2 exact allocation | owner receipt/readback，anomaly projector | A3–A5、A7 |
| CSR-R4 | Global→Domain→Subsystem→Module boundary | existing Client Finance owner ports | A6–A8 |

Convergence result：`SPEC_READY`。後續只能由 task-pack 編譯成 bounded work packages，不得越過本規格自行加入帳務語意。

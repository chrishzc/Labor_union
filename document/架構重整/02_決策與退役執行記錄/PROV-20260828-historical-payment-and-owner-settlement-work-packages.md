# 歷史付款證據與 owner 結清工作包

- `package_id`: `PKG-HISTORICAL-PAYMENT-OWNER-SETTLEMENT`
- `package_status`: `PACKAGE_READY`
- `specification`: `PROV-20260828-historical-payment-and-owner-settlement-spec.md`
- `authority_digest`: 2026-08-28 使用者裁決銀行對帳單優先、pre-system historical人工fallback、付款／owner結清／Step 11分離、客戶補助退款歸Client Finance、較新更正可重開；同日後續明確指示「轉換成任務包並實作」
- `execution_authorized`: true；只授權本包effect ceiling內的程式、additive local schema、allowlisted `lu_test_*`與no-auth Browser驗收，不擴張為33種異常全部完成

## 1. Objective、dependencies 與 effect ceiling

先完成 Client Finance／Staff Payables 的歷史付款證據 Q/P/A 與owner page閉環，再讓既有
`PKG-HPROJ-SIX-OWNER-SOURCE-RUNTIME` 消費其 committed owner results。不得反向由 HPROJ、Orders status、
歷史六欄檔或 UI callback建立付款／結清。

- `dependencies`: current Finance Import canonical bank facts、Historical Orders adoption identity、Client Finance／
  Staff Payables obligations and reducers、existing Finance owner page、approved HPROJ shared source contract。
- `effect_ceiling`: source／tests／docs與additive local schema candidate；allowlisted `lu_test_*`驗收。禁止
  `union_db`／production、provider payment、existing-row rewrite/backfill、reset／switch、generic status editor／alert close。
- `safe_stop`: historical eligibility、payer/payee/direction、exact obligation set、owner transaction、source identity、
  schema baseline或later-event precedence任一不唯一時停止並回規格，不猜測。

## 2. Necessity／source basis／reuse

| Step | Necessity | Source basis | Reuse decision |
|---|---|---|---|
| 對帳單優先與historical eligibility Query | `required_now` | HPS §2；現有Finance Import與adoption roots | `reuse` canonical bank facts／historical identity，新增bounded composition |
| owner-specific manual event／receipt／projection | `required_now` | HPS §3～4；現有exact-only規則無此source kind | additive successor，禁止偽造bank allocation |
| Client Finance三方向Q/P/A | `required_now` | HPS §3.1／A3／A5 | `copy-adapt` existing owner envelope/UoW/idempotency |
| Staff Payables Q/P/A | `required_now` | HPS §3.2／A4 | `copy-adapt` existing owner envelope/UoW/idempotency |
| Owner-page embedded repair | `required_now` | HPS §5／A11；較新06 current contract | `reuse` Finance owner page；不把25個owner work item放回`#anomalies`，不新增generic editor |
| HPROJ owner envelope/adapters | `required_later` | HPS §6／A10；HPROJ §11 | 由既有six-owner runtime包接手，不在本包重複projector core |
| 歷史六欄檔新增付款、legacy auto-backfill | `remove` | HPS exclusions | `reject` |

## 3. Ordered execution contract

1. **Freeze owner contracts**：逐項固定 Client receivable、client refund、client subsidy return、staff payout 的
   payer/payee/direction、eligible historical identity、exact selected obligations、confirmation kind、unknown-date與
   later-event precedence；同步typed errors、capability及public views。
2. **Additive DB successor**：late-bind owner-specific immutable historical event／obligation links／receipt／projection
   及同UoW HPROJ envelope所需objects；同步schema part、assembly、release chain、descriptor、developer upgrade。
   Change inventory保持schema-only，無seed/backfill/destructive。
3. **Client Finance Q/P/A**：Query同時回正常bank candidates與manual eligibility；Preview按三種Client方向fresh-lock；
   Apply append owner event/links/receipt/outbox/projection，補助退款保持Client Finance，任何partial failure全rollback。
4. **Staff Payables Q/P/A**：按staff＋case＋exact obligations fresh-lock；Apply只更新Staff owner，不能從Client付款、
   Orders completed、清冊或政府撥款推定payout。
5. **Owner API／React**：Client Finance／Staff Payables owner page顯示原因、normal blocker、bank route、historical route與terminal predicate；同頁
   bounded workbench完成Query→Preview→Confirm→Apply→fresh owner readback。unknown／stale／timeout以同identity調和；
   production使用既有enabled internal frontend capability，local no-auth只作development／validation驗收。
6. **Owner verification**：Module→Subsystem→Domain focused tests；真MySQL驗A1～A9、replay、rollback、later reopen；
   API／React strict schema與no-auth真Browser驗兩owner獨立、補助退款方向及無generic close。
7. **HPROJ handoff**：只有本包owner event／receipt／outbox與source envelope exact後，才恢復
   `PKG-HPROJ-SIX-OWNER-SOURCE-RUNTIME`，把Client／Staff observations接入3→2→1→0與Step 11 oracle。
8. **DB acceptance**：完成static、descriptor、read-only plan、fresh、preserve-data、configured developer及另一台
   電腦upgrade/readback；任一必要gate未過維持`DB_CHANGE_NOT_READY`。

## 4. Verification and failure behavior

- 正向：銀行正常核銷、client manual paid/settled、staff manual paid/settled、client subsidy return、兩邊皆terminal。
- 分離：client已付而staff未付；staff已付而client未結；一邊部分obligations；Government不被誤寫。
- 負向：非歷史、未採納、cross-case／owner、方向不明、unknown action、stale、same-key different payload、
  transaction rollback、timeout/outcome unknown、later reversal／new obligation。
- reconciliation：exact replay回原receipt；commit未知只查原identity；後續銀行證據不得建立第二次payment。
- evidence：保留final contract coverage、DB gate表、owner before-after、API／Browser readback與console；敏感銀行及
  個資只保留最小去敏identity，不保存原始帳號或raw workbook內容。

## 5. Current DB change gate

使用者已授權本包實作；下表在每個material DB gate完成後更新，不能以後續測試結果回填尚未執行的gate。

| Gate | Status | Evidence／reason |
|---|---|---|
| Scope gate | `PASS` | approved HPS spec、current PACKAGE_READY write set及2026-08-28「轉換成任務包並實作」明確Authority |
| Change inventory | `PASS` | HPS §8：schema-only；system-seed／business-row-backfill／destructive皆none |
| Static release gate | `PASS` | additive 1020 schema part、manifest、fresh assembly terminal及validation release一致；owner-local與affected living baseline focused `54 passed` |
| Descriptor gate | `PASS` | 8個owner-specific tables、indexes、FK、checks與8個immutable triggers均與canonical SQL exact；無seed／backfill／existing-row rewrite |
| Read-only plan gate | `BLOCKED` | current host無`.env`、configured DB target、MySQL client／Docker或可驗證合法`lu_test_*` identity，不能形成對真target的read-only plan |
| Engine verification gate | `BLOCKED` | 同一DB test environment blocker；fresh／preserve-data MySQL均未執行，禁止改用`union_db`／production／SQLite替代 |
| Developer acceptance gate | `NOT_RUN` | 未操作configured DB或另一台電腦 |

Current conclusion：`DB_CHANGE_NOT_READY`；Static與Descriptor已通過，read-only plan與Engine受合法DB test environment阻塞，Developer acceptance未執行。

### 5.1 Current owner implementation boundary

- Client Finance與Staff Payables各自的pure rule、typed Query／Preview／Apply、fresh-lock MySQL adapter、existing
  owner receipt replay、bank-first blocker、owner-only event／links／overlay／source outbox及later-reopen readback已
  repository-local完成；canonical與既有owner regression合計`170 passed`。
- 2026-08-31最新人工裁決已解除public-contract blocker。既有Client Finance／Staff Payables routers各自新增
  authenticated bounded Query／Preview／Apply／fresh readback，沿用owner application、repository、outer UoW、
  receipt與version；fresh readback由current obligations與owner projection重新計算terminal，不由receipt或UI推定。
- canonical module與相鄰owner regression `36 passed`，production OpenAPI八個operation與Python compile passed；
  Anomalies direct DB、generic action dispatcher、跨owner writer／transaction與HPROJ語意仍未新增且不在本slice。
- 2026-08-29較新`06`已把三個付款提醒固定為owner work item並要求只顯示於owner page；原「Anomalies同頁」
  文字以`BASELINE_PROPAGATION`收斂。Finance既有Client receipts／Staff payables頁籤已各自接上strict owner
  client與bounded Query→Preview→Confirm→Apply→fresh readback；focused React `12 passed`與production build passed。

## 6. Bidirectional coverage

| Requirement／Acceptance | Package step | Direct oracle |
|---|---|---|
| HPS-01／HPS-02／HPS-A1／HPS-A2 | 1、3、4、6 | historical不自動付款；bank candidate正常核銷且manual event=0 |
| HPS-03／HPS-A3／HPS-A5／HPS-A7 | 1、3、6 | Client三方向exact；補助退款給客戶；未選obligation保持open |
| HPS-04／HPS-A4／HPS-A7 | 1、4、6 | Staff payout只改Staff owner；跨staff/case零寫入 |
| HPS-05／HPS-06／HPS-A6／HPS-A8／HPS-A9 | 2～6 | unknown date、replay、rollback、later event reopen與immutable history |
| HPS-07／HPS-A11 | 5～6 | owner page同頁typed修復、完整reason／how-to、零generic close／direct DB write／Anomalies回填 |
| HPS-08／HPS-A10 | 7 | Client terminal＋Staff open時Step11 false；全部terminal才true |
| HPS-A12 | 2、8 | DB 3.1完整gate與另一台configured developer acceptance |
| HPS-09／HPS-A13 | 5～6 | enabled internal frontend account具相同business capability；no-auth僅development驗收 |

```yaml
package_route:
  status: OWNER_UI_LOCAL_PASS
  package: PKG-HISTORICAL-PAYMENT-OWNER-SETTLEMENT
  blockers:
    - configured allowlisted lu_test_* engine environment is unavailable
```

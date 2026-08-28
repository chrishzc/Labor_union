# Task 96 HCAT Client Finance owner adapter receipt

- 日期：2026-08-28
- Package：`PKG-HCAT-ADAPTER-client-finance`
- 結果：`PASS`（source／focused）；六 owner 同 connection 真 MySQL integration 為 `NOT_RUN`。

## 1. 已完成契約

- Step 7 deposit obligation、ledger allocation、settlement與Step 11 client settlement使用 Client Finance
  owner reducer及exact lineage；多筆 allocation identity完整保留，不使用scalar collapse。
- deposit direction固定 `receivable_from_client`；ledger terminal必須具正式 incoming bank fact與receipt。
  refund／adjustment／subsidy_return不能冒充receipt allocation。
- obligation event綁定case、source identity、amount與expected version；projection可合法落後current account
  version，只要自己的event/projection lineage仍fresh-valid。
- `order_identity`必須exact `order:{case_no}`；partial allocation保持available且nonterminal。
- Step 11 root直接使用reducer `settlement_lineage_identity`，source event使用
  `allocation_lineage_identity`；cross-case、reversal、stale、malformed、ambiguous全fail closed。
- adapter使用borrowed connection，locked mode傳遞`FOR UPDATE`，不begin／commit／rollback／close。

## 2. Fail-before-fix 與驗證

- 第一輪 fresh verifier：P0=0、P1=5、P2=2；揭露direction、bank/receipt、version、identity、event、
  partial allocation與Step11 reducer lineage缺口。
- 最小修正後主代理 focused/cross regression：`125 passed`。
- 第二輪 fresh Luna/high：七項real-shaped probes全部PASS，focused/cross `86 passed`，
  P0=0、P1=0、P2=0，`changed_files=[]`。
- `py_compile`、strict UTF-8、`git diff --check`：`PASS`。

## 3. Remaining gate

本 receipt 只完成 Client Finance concrete source slice。六 owner adapters 的 dependency composition、同一
borrowed connection／lock integration、真 `lu_test_*` readback、projector、API、React與no-auth Browser
仍須另行驗收；不得由本結果外推 HCAT umbrella 完成。

本輪未修改 schema／migration、未操作 DB／port／Browser、未使用 Graphify，也未 stage／commit。

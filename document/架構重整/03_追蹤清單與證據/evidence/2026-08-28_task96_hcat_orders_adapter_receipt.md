# Task 96 HCAT Orders owner adapter receipt

- 日期：2026-08-28
- Package：`PKG-HCAT-ADAPTER-orders`
- 結果：`PASS`（source／focused）；六 owner 同 connection 真 MySQL integration 為 `NOT_RUN`。

## 1. 已完成契約

- Step 1 order、Step 10 actual start、Step 11 completion 依 Orders-owned current facts、正式 event、
  receipt 與 lifecycle version 建立 exact observation。
- 1008 合法 no-op adoption 以相同 expected/resulting version、無 lifecycle event 表示；有狀態轉換時
  只接受 canonical `historical_order_adoption` lifecycle trigger，不能把 outbox intent
  `historical_order_adopted` 當成根事實。
- adoption／terms lifecycle identity 必須為 positive integer；zero、missing、cross-case、malformed、
  stale、ambiguous 或 receipt drift 全部回 typed unavailable。
- Step 10／11 使用 exact `order:{case_no}` identity；actual-start event type、completion service transition、
  current positive version 與 receipt lineage 均 fail closed。
- adapter 使用 borrowed connection，locked mode 傳遞 `FOR UPDATE`，不 begin／commit／rollback／close。

## 2. Fail-before-fix 與驗證

- 第一輪 fresh verifier：P0=0、P1=1、P2=1；找到 outbox intent 被接受及
  `lifecycle_event_id=0` 未拒絕。
- 最小修正後主代理 focused/cross regression：`96 passed`。
- 第二輪 fresh read-only re-verifier：Orders focused `18 passed`、HCAT cross-suite `100 passed`、
  adversarial probes 6 groups，P0=0、P1=0、P2=0，`changed_files=[]`。
- `py_compile`、strict UTF-8、`git diff --check`：`PASS`。

## 3. Remaining gate

本 receipt 只完成 Orders concrete source slice。六 owner adapters 的 dependency composition、同一
borrowed connection／lock integration、真 `lu_test_*` readback、projector、API、React 與 no-auth Browser
仍須另行驗收；不得由本結果外推 HCAT umbrella 完成。

本輪未修改 schema／migration、未操作 DB／port／Browser、未使用 Graphify，也未 stage／commit。

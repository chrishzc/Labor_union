# Task 96 HCAT Contract Signing owner adapter receipt

- 日期：2026-08-28
- Package：`PKG-HCAT-ADAPTER-contract-signing`
- 結果：`PASS`（source／focused）；legacy recovery mutation與六 owner真MySQL integration為`NOT_RUN`。

## 1. 已完成契約

- current external session優先；Step 6／8只接受provider-neutral completion report、current/latest
  document set、matching receipt及accepted/active plan的exact lineage。
- staff/client reporter subject、case、staff/customer identity、document version、document-set fingerprint、
  report/receipt/session version transition與final controlled PDF全數交叉驗證。
- rejected、superseded、stale plan／document／session，以及cross-case、malformed、ambiguous evidence全fail closed。
- 無external session時，legacy manual tuple即使完整，因舊workflow未persist Preview fingerprint，固定回
  typed `contract_signing_legacy_manual_preview_fingerprint_unavailable`；不推測、不改寫、不產生terminal。
- adapter使用borrowed connection，locked mode傳遞`FOR UPDATE`，不begin／commit／rollback／close。

## 2. Fail-before-fix 與驗證

- 第一輪 fresh verifier：P0=0、P1=4、P2=0；揭露reporter subject、document currentness、
  report/session version與client plan currentness缺口。
- 最小修正後主代理 cross regression：`128 passed`。
- 第二輪 fresh Luna/high：focused `22 passed`、cross `81 passed`、external signing/PDF `41 passed`、
  adversarial probes `14 PASS`，P0=0、P1=0、P2=0，`changed_files=[]`。
- `py_compile`、strict UTF-8、`git diff --check`：`PASS`。

## 3. Remaining gates

本 receipt 不授權或完成 legacy manual recovery mutation；其 append-only recovery policy仍為
`AUTHORITY_REQUIRED`。六 owner dependency composition、同一 borrowed connection／lock integration、
真 `lu_test_*` readback、projector、API、React與no-auth Browser仍須另行驗收。

本輪未修改 schema／migration、未操作 DB／port／Browser、未使用 Graphify，也未 stage／commit。

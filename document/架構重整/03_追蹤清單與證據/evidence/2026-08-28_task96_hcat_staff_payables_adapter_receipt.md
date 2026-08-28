# Task 96 HCAT Staff Payables owner adapter receipt

- 日期：2026-08-28
- Package：`PKG-HCAT-ADAPTER-staff-payables`
- 結果：`PASS`（source／focused）；六 owner 同 connection 真 MySQL integration 為 `NOT_RUN`。

## 1. 已完成契約

- Step 11 依每個 Staff Payables typed source version 產生獨立 observation，保留多 staff account、
  obligation／event／projection／payout／allocation／bank／recovery exact row-set，不使用 `MAX` 或 scalar collapse。
- 合法 source version 0 受到支援；完整但尚未付清的 partial payment 保持 available 且 nonterminal，
  不會被誤判為完成。
- cross-case、cross-staff、duplicate、malformed、allocation／lineage incomplete及 DB fault 全部回 typed
  unavailable；permutation 不改變 identity／fingerprint。
- adapter 使用 borrowed connection，locked mode 傳遞 `FOR UPDATE`，不 begin／commit／rollback／close。

## 2. 驗證

- 主代理 focused/cross regression：`90 passed`；六 owner static suite包含本 adapter為`152 passed`。
- fresh Luna/high：focused `12 passed`、HCAT cross-suite `120 passed`、reader/schema `69 passed`，
  adversarial probes PASS，P0=0、P1=0、P2=0，`changed_files=[]`。
- `py_compile`、strict UTF-8、newline／trailing whitespace、`git diff --check`：`PASS`。

## 3. Live drift 與 remaining gate

Fresh verifier確認 canonical schema parts／release含所需 Staff Payables tables，但 compact `db/schema.sql`
未包含該組表，標記為既有 `live-drift`；本 adapter 未改 schema。六 owner dependency composition、同一
borrowed connection／lock integration、真 `lu_test_*` current-schema readback、projector、API、React與
no-auth Browser仍須另行驗收。

本輪未修改 schema／migration、未操作 DB／port／Browser、未使用 Graphify，也未 stage／commit。

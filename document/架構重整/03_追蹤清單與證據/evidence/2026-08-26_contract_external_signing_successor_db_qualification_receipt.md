# Contract external signing successor DB qualification receipt

- Work Package：`PROV-20260826-contract-external-platform-pdf-handoff-work-package`
- Current ID：`CUR-CONTRACT-01`
- 驗證日期：2026-08-26
- 結論：release 1005 全部本機 DB change gates 通過，`DB_CHANGE_READY`；application、API、React 與 fresh
  enabled-human Chrome 驗收仍在進行。

## Change inventory

release `labor-union-contract-external-signing-successor-2026-08-26-v1` 只新增 external signing session、
completion reports、final-PDF recovery task、Contract-owned final document link、closed receipt 與 append-only
triggers。資料效果為 `schema-only`；system seed、business-row backfill、destructive effect 均為 none。

## DB change gates

| Gate | 狀態 | 證據 |
|---|---|---|
| Scope | PASS | approved `CUR-CONTRACT-01` 與 in-progress Work Package |
| Change inventory | PASS | release 1005 schema-only；seed／backfill／destructive 均為 none |
| Static release | PASS | schema assembly、release／descriptor hashes、canonical chain focused tests PASS |
| Descriptor | PASS | hash-bound SQL 展開完整 columns／indexes／FK／checks／triggers；fresh 與 preserve candidate 均為 `exact`，view mismatch 0 |
| Read-only plan | PASS |正式 updater preview 回 release 1005，僅 1005 為 absent，無 partial／drift |
| Engine verification | PASS | MySQL 8.0.46 fresh bootstrap；1004 source dump → 1005 candidate → apply／verify；第 7/21 statement 真實中斷後續跑 exact |
| Developer acceptance | PASS | 正式 updater 完成 backup、candidate、same-name test-source replacement、資料／schema 等價 readback，並保留 rollback dump |

canonical qualification：
`validation/receipts/phase4/PROV-20260826-local-additive-qualification-contract-external-signing-successor.json`。
大型 dump、operation journal、intermediate plan 與 replacement receipt 只位於 ignored `scratch/contract-o2-*`。

Preserve-data readback：source 與 candidate 的 `clients=1`、`orders=1`，1005 owned object 為 `exact`。resume
candidate `lu_test_contract_o2_resume_1005_u3` 在第 7 個 durable statement 後中斷，runner 以 candidate identity 與
statement SHA-256 reconcile 後完成剩餘 17 個 recovery statements並 verify。Developer acceptance 使用
`lu_test_contract_o2_devaccept_source_u3`／`lu_test_contract_o2_devaccept_candidate_u3`，replacement receipt 為
`completed`，1004 predecessor 與 1005 successor 都為 `exact`。

## Safety boundary

本次只操作 receipt 明列的 `lu_test_*` fresh、preserve、resume 與 developer-acceptance databases。正式 updater
只替換新建的 developer-acceptance test source；未操作 `union_db`、production、正式 NAS、外部 provider、
`--switch` 或全庫 cleanup。

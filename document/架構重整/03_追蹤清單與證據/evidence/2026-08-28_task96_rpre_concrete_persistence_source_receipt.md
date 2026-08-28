# Task 96 RPRE concrete persistence source receipt

- 日期：2026-08-28
- 範圍：`PKG-RPRE-OWNER-SUCCESSOR` 的 concrete repository、same-UoW Matching successor、
  canonical package compatibility 與 exact owner readback source slice。
- 結果：`PASS`（source／focused）；真 MySQL persistence/readback `NOT_RUN`，整個 Work Package
  仍為 `in-progress`。

## 1. 已完成契約

- Apply 不接受 workflow／bundle snapshot；repository 透過同一 outer UoW 的 fresh loader 取得
  Matching source。
- fresh source 必須包含完整 13-source tuple、可重算 criteria digest、latest parent package 與
  source event。stored snapshot、parent payload／identity／version／state／digest／source tuple、
  source event 的 case／snapshot／parent binding 任一漂移，均在首次 INSERT 前停止。
- Step 2 使用既有 reader 可還原的 `candidate_pool_open` package；Step 3／4 只複用完整 typed
  candidate／segment facts，不從 count 或 root identity 造資料。
- R-01～R-04 要求既有 effective generation；同一 UoW 取消 prior marker、建立 empty effective
  successor 並 CAS aggregate。缺 prior effective generation 不合成替代資料。
- root descriptor、canonical ordinal、digest/count、Matching numeric FK、receipt、outbox 與 replay
  readback 維持 exact；adapter 不自行 commit／rollback。

## 2. Fail-before-fix 與驗證

- 初始新增契約測試：`6 failed`，涵蓋 abbreviated source、stored snapshot drift、reader payload 與
  prior effective generation 缺失。
- 第一位 fresh Luna/high verifier：`BLOCKED`，P1=1；指出 latest parent package 與 parent source
  tuple 未 exact 綁定。
- 補上 parent package mandatory fact、stored/fresh exact comparison，並新增 parent source tuple drift
  與 fresh parent identity drift zero-insert probes。
- 主代理 final cross-regression：`93 passed in 0.29s`。
- 第二位 fresh Luna/high read-only verifier：P0=0、P1=0、P2=0；獨立 focused `17 passed`，
  `py_compile`、strict UTF-8、structured headers 與 `git diff --check` 全部 `PASS`。

## 3. Frozen candidate

| Path | SHA-256 |
|---|---|
| `domains/scheduling/matching_coordination.py` | `24593c3de3a99ff203785a7b6c2c673916f87d8020cd16d33e65c18ec9612048` |
| `infrastructure/mysql/matching_successor_persistence_adapter.py` | `a0a5de19a9f234e67f621b3ca42c6d814ea744a97ff9ddbea9129b037f7ead26` |
| `infrastructure/mysql/service_before_replacement_repository.py` | `6e46e478bcb14bd3fc33637c840e3d5d0f8bcdf9f6572d2fde0dd551d4e7b13e` |
| `subsystems/scheduling/service_before_replacement_workflow.py` | `0fa8c0690eddfab50bc64228c6f2fb28cdc1c8148b28df4cdacc270352b43d01` |
| `tests/test_matching_successor_package_compatibility.py` | `1c8ed4891123f9e848d7c2fb12ce11a998f8ff0e67dcf73a3f522f66b88349b5` |
| `tests/test_service_before_replacement_persistence.py` | `742a62b2f522db9ac0d165226ddf204790567ff146b7f5485d44b400e339c5a3` |

## 4. Remaining gates

| Gate | Status | 說明 |
|---|---|---|
| source／focused contract | `PASS` | final frozen candidate 與 fresh verifier 均通過。 |
| `lu_test_*` real MySQL transaction/readback | `NOT_RUN` | 本 slice 未連線或修改 DB。 |
| API／projector／React／no-auth Browser | `NOT_RUN` | 屬後續 `PKG-RPRE-PROJECTION-UI-RUNTIME`。 |
| 另一台實體電腦 developer acceptance | `NOT_RUN` | Task96 DB 總結仍為 `DB_CHANGE_NOT_READY`。 |

本輪未修改 schema／migration、未操作 DB／port／Browser、未使用 Graphify，也未 stage／commit。

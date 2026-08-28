# Task 96 HCAT／RPRE subsystem slice receipt

- `scope`: HCAT owner-vector composition＋RPRE Query／Preview／Apply workflow
- `status`: `passed`（本 subsystem slice only）
- `authority`: 兩份 adopted `SPEC_READY` 規格與 `PACKAGE_READY` task packs
- `candidate_date`: 2026-08-28
- `database_effect`: none

## 完成內容

### HCAT owner-vector composition

- 六個 owner domain 使用明確且不可互相冒充的 typed read port；每個 catalog descriptor只讀一次。
- canonical 11-step catalog、完整 order identity、cross-case與same-version catalog tamper均fail closed。
- fresh typed unavailable、whole-vector fingerprint、server current step與repair referral由server projection產生。

### RPRE Query／Preview／Apply workflow

- Query／Preview為zero-write；Apply在fresh lock後以單一outer UoW保存bundle並以fresh readback對帳。
- exact case/scenario、version、prior identity、reason/evidence、fingerprint與idempotency均fail closed。
- receipt保存retained／superseded／created root IDs；首次Apply與same-key replay都必須精確readback。
- commit後readback未知固定回`outcome_unknown`且不得rollback已提交交易。

## Final evidence

| 驗證 | 狀態 | Final evidence |
|---|---|---|
| 主代理H/R cross-regression | `passed` | `105 passed in 0.49s`；涵蓋H/R domain、subsystem及相鄰既有workflow/API/repository regressions |
| H fresh Luna/high r4 | `passed` | focused `41 passed`＋4 adversarial probes；P0=0、P1=0 |
| R fresh Luna/high r5 | `passed` | focused `36 passed`、targeted `13 passed`＋replay/root/transaction adversarial probes；P0=0、P1=0 |
| compile／diff／UTF-8／headers | `passed` | 四個source/test可編譯、`git diff --check` PASS；各檔恰一個合法繁中structured header |
| DB／API／React／Browser | `not_run` | 本slice沒有concrete persistence、route或UI，不以pure tests冒充runtime evidence |

R r4曾發現replay未精確比對三組root IDs；該candidate已由r5修正並由新fresh verifier覆蓋，舊失敗證據不代表final candidate。

## DB change gates（下一片準備狀態）

唯讀inventory與主代理schema readback確認H projector及R replacement persistence都需要late-bind additive schema；目前未修改SQL或DB。

| Gate | HPROJ | RPRE | 證據／限制 |
|---|---|---|---|
| Scope gate | PASS | PASS | approved specs與task packs涵蓋additive owner artifacts |
| Change inventory | PASS | PASS | 只有`schema-only`；system-seed、business-row-backfill、destructive皆無 |
| Static release gate | NOT_RUN | NOT_RUN | 尚未late-bind release/artifact |
| Descriptor gate | NOT_RUN | NOT_RUN | 尚無final owned-object descriptor |
| Read-only plan gate | NOT_RUN | NOT_RUN | 尚無candidate release可供canonical runner解析 |
| Engine verification gate | NOT_RUN | NOT_RUN | fresh／preserve-data candidate尚未建立 |
| Developer acceptance gate | NOT_RUN | NOT_RUN | 前置gates尚未完成 |

總結：`DB_CHANGE_NOT_READY`。不得只把缺少契約塞進JSON，也不得先寫SQL後補release／descriptor。

## Remaining boundary

- HCAT：本次composition已完成；六個owner的concrete read adapters仍待接線，因此umbrella package保持`in-progress`。
- HPROJ：專屬immutable occurrence／successor／projector receipt及current umbrella binding仍待additive schema與projector實作。
- RPRE：Q/P/A application slice已完成；concrete repository、replacement lineage／receipt／internal outbox schema與真MySQL readback仍待完成。
- API／React／no-auth Browser均未執行，不能由本receipt外推Task96 H/R scenario完成。

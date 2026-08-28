# Task 96 LDU ordered-chain／launcher slice receipt

- `package`: `LDU-1003-CURRENT-01`
- `scope`: canonical 1003→current ordered plan/apply/current gate＋Unix no-auth launcher wiring
- `status`: `passed`（source／focused與old-DB zero-child gate；normal Browser仍待驗）
- `database_effect`: schema/data none；official launcher負向控制只重啟既有Docker MySQL container並保留volume
- `current_readback`: baseline 1003；latest 1012；9 ordered pending releases

## Completed behavior

- canonical manifests動態投影1003→latest，不硬編1009/1010；plan逐artifact輸出state、qualification與blocked reason。
- 只接受continuous exact prefix；hole、partial、drift、unknown、qualification missing/stale/conflict全部fail closed且零DDL。
- Apply逐release使用獨立qualification、backup、journal、readback後replan；中斷後從第一個absent release續跑。
- `require_current`重新對照canonical baseline/latest/top fingerprint及artifact數量、順序、name、release ID、release fingerprint、state與空pending list。
- Unix no-auth wrapper設定development/local-bypass前後端四個環境變數，再`exec` canonical Unix launcher；current gate仍位於第一個API/UI/worker child之前。
- Unix launcher尊重明確`DB_PORT`，missing `.env`時可使用process environment；不再把已運行的3306誤改為3307，也不再傳入wait helper不支援的`--port`。
- API／React／required workers納入owned process groups；任一required child失敗即停止整組，EXIT／INT／TERM會清理本次owned children。
- README已校正為FastAPI 8000、React 5173與required runtime/durable/incident workers；LINE credential缺失只skip LINE。

## Final evidence

| 驗證 | 狀態 | Evidence |
|---|---|---|
| 主代理合併回歸 | `passed` | `113 passed in 0.81s`；Python compile、`bash -n`、scoped `git diff --check` PASS |
| fresh Luna/high r3 | `passed` | ordered/current `76 passed`、launcher `18 passed`、named adversarial `10 passed`；P0=0、P1=0 |
| canonical identity negatives | `passed` | arbitrary name、stale top/artifact fingerprint、reversed order、wrong baseline與actual route均fail closed |
| launcher runtime dry-run | `blocked` | wrapper成功委派canonical preflight；本機無Docker，安全回`side_effects=none`，不冒充runtime PASS |
| MySQL engine／old-DB negative | `passed` | representative-data chain、fresh逐版與old-DB zero-child均PASS |
| 本機normal Browser | `passed` | current-1012 no-auth API／React／workers／Browser與owned cleanup PASS |
| 另一台Developer DB／Windows Browser | `not_run` | 仍需在該實體機正式驗收 |
| 2026-08-28 corrective root | `passed` | manifest-complete mysqldump、雙平台launcher、updater、ordered runner與preserve regression：`204 passed, 1 skipped`；`bash -n` PASS |
| exact-1003 zero-child negative | `passed` | canonical no-auth launcher exit 2／`schema_update_required`；8000與5173 listener identities前後不變 |

## Qualification inventory

| Release | Published qualification | Current disposition |
|---|---|---|
| 1004 | valid | canonical validator exact |
| 1005 | valid | canonical validator exact |
| 1006～1012 | valid | 逐release fresh／preserve／strict evidence、publish與validator round-trip PASS |

Deterministic builder與final engine evidence producer均已完成；supporting evidence不冒充qualification。

## DB gate result

| Gate | 狀態 | Current evidence |
|---|---|---|
| Scope | PASS | approved spec與`LDU-1003-CURRENT-01` |
| Change inventory | PASS | 1004～1012均schema-only；seed/backfill/destructive皆無 |
| Static release | PASS | canonical 51 manifests／101 artifacts；terminal readback 1012 |
| Descriptor | PASS | current per-release static與真MySQL descriptor evidence |
| Read-only plan | PASS | exact1003列出1004→1012 ordered qualification exact plan |
| Engine verification | PASS | disposable representative-data 1003→1012及fresh逐release PASS |
| Developer acceptance | NOT_RUN | 本機normal no-auth已PASS；另一台實體1003 DB／Windows Browser尚未驗收 |

總結：`DB_CHANGE_NOT_READY`。

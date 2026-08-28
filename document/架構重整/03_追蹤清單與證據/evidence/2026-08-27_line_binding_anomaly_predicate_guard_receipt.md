# LINE-001／LINE-005 canonical binding predicate guard completion receipt

- Work Package：`PROV-20260827-line-binding-anomaly-predicate-guard-work-package.md`
- Result：`passed`
- Scope：只修 current-state detector 的 auto-resolution guard；人工 remediation仍未完成。
- DB/schema effect：無 DDL、migration、seed、backfill、DB mutation 或 provider effect。

## 實作結果

`LINE-001` 只有在 Client projection 與 canonical `line_identity_bindings` 同時符合下列條件才 inactive：

- bound；
- subject type=`customer`；
- subject reference=Client technical identity；
- projection與 binding LINE identity一致；
- Orders 的 `client_id` 與 `case_no` 同時指向該 Client。

`LINE-005` 對已指派 Staff 套用同等 `bound + staff subject/reference + projection consistency` 判定。未指派
Staff 不啟動該碼。缺 binding、pending/revocation/revoked、wrong subject/reference、relation drift、空白 identity、
query failure 均不會把 alert 自動解除。

## Verification

| Gate | 結果 | Evidence |
|---|---|---|
| Focused detector＋adapter contract | `passed` | `tests/test_line_binding_anomaly_predicate_guard.py`，5 tests |
| Related anomaly regression | `passed` | 6 files，合計 `51 passed in 0.43s` |
| Compile | `passed` | `.venv/bin/python -m compileall -q` 指定三個 Python files |
| Diff check | `passed` | `git diff --check` 指定 source/tests |
| Strict UTF-8 | `passed` | `iconv -f UTF-8 -t UTF-8` 指定 source/tests |
| flake8 | `not_run` | `.venv` 未安裝 flake8；未以其他檢查冒充。 |
| Real MySQL query execution | `not_run` | 本切片無 DB mutation/schema；本機服務依使用者說明尚未啟動。 |

## DDH dynamic verification

工作只有一組緊密 source write set，DDH 採主代理單一 implementation writer＋E3 獨立驗證，避免競寫。Verifier
明確為 `gpt-5.6-luna`／`high` 且唯讀：

1. 第一輪 `FAIL`：P0=0、P1=2（Client relation drift、whitespace identity）。
2. 主代理序列修正並增加 regression。
3. 第二輪 `PASS`：P0=0、P1=0；verifier workspace effect=0。

這次 material finding 實際改變剩餘計畫與實作內容，已依使用者要求留下動態調整紀錄。

## Remaining truth

本收據只證明兩碼不會因 legacy projection 非空而誤解除；`LINE-001/005` 的 owner-specific 人工
Query／Preview／Apply、詳細 evidence、React workbench、receipt/readback仍屬
`CUR-ANOMALY-MANUAL-REMEDIATION-01` 的 `SPEC_GAP`，不得宣稱兩碼完整完成。

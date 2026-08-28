# SCHEDULE-002 generic resolve suppression guard completion receipt

- Result：`passed`
- Scope：移除 generic alert workflow resolved 對 replaced root 的 suppression。
- Non-goal：不定義 replacement／service／finance split 真正 completion，不修改任何 owner root。
- DB/schema/provider effect：無。

## Result

- 每筆 `case_staff_assignments.status='replaced'` source row均產生 `SCHEDULE-002 active=True` desired state。
- Adapter不再查詢 resolved current alerts，也不把 tracking state帶入 root predicate。
- legacy resolved projection遇到 fresh replaced root rescan時，由 canonical reducer重新開為 `open`。
- source row消失時不製造 synthetic inactive；完整 completion仍等待 Scheduling owner正式契約，現階段 fail closed。

## Verification

| Gate | 結果 | Evidence |
|---|---|---|
| Focused guard | `passed` | 3 tests：fixed active、無 suppression input/query、resolved→reopened |
| Related local regression | `passed` | 30 tests in `0.43s` |
| Compile/diff/UTF-8 | `passed` | compileall、git diff --check、iconv |
| E3 verifier | `passed` | `gpt-5.6-luna`／`high`；P0=0、P1=0、workspace effect=0 |
| Real MySQL scan | `not_run` | 本機服務依使用者說明尚未啟動；本切片零 DB mutation/schema。 |

## Remaining truth

本收據只證明 generic resolve不能把 root condition藏起來。`SCHEDULE-002` 的 owner-specific detail、
replacement target、service outcome、finance split review、Preview／Apply、receipt/readback與 React workbench仍是
`SPEC_GAP`；不得宣稱完整人工 remediation完成。

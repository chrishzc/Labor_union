# Historical Orders 六欄狀態 `0／1／2` 修正驗收 Receipt

- `receipt_date`: `2026-08-28`
- `package_id`: `PKG-HISTORICAL-ORDER-SIX-COLUMN-STATUS`
- `target`: `main@5e21129` 加本工作包精確 diff
- `scope`: Orders 六欄 status source integrity、typed counts、React observation
- `schema_change`: `none`
- `production_data_change`: `none`

## 結果

| Acceptance | 狀態 | 證據 |
|---|---|---|
| `HOS-A1` 六欄 `0／1／2` exact mapping | passed | `tests/domains/orders/subsystems/orders/modules/historical-adoption/unit/test_historical_order_adoption.py`、`tests/domains/orders/subsystems/orders/modules/historical-adoption/regression/test_historical_order_workbook_import.py` |
| `HOS-A2` numeric `0` 與 blank fingerprint 分離 | passed | `test_numeric_zero_status_has_a_distinct_source_fingerprint_from_blank` |
| `HOS-A3` 真 MySQL Apply／event／receipt | passed | `lu_test_task96_rpre_browser_r3_20260828`；focused E2E `1 passed` |
| `HOS-A4` typed contract 與 no-auth Browser 四項 counts | passed | Python／React strict tests；Browser Preview `1／1／1／1` |
| `HOS-A5` replay與different payload conflict | passed | subsystem legacy／current replay tests及既有 conflict E2E |
| fresh Luna/high 獨立複驗 | passed | HOS-A1／A2／A4／A5 source與focused tests PASS；runtime由主lane final evidence覆蓋 |

## 驗證命令與讀值

```text
.venv/bin/python -m pytest -q \
  tests/domains/orders/subsystems/orders/modules/historical-adoption/unit/test_historical_order_adoption.py \
  tests/domains/orders/subsystems/orders/modules/historical-adoption/regression/test_historical_order_workbook_import.py \
  tests/domains/orders/subsystems/orders/modules/historical-adoption/contract/test_historical_order_adoption_router.py \
  tests/domains/orders/subsystems/orders/modules/historical-adoption/contract/test_historical_order_adoption_api_client.py
=> 25 passed

npm test -- --run \
  src/tests/case_workbook_adapters.test.ts \
  src/tests/historical_order_workbook_client.test.ts \
  src/tests/data_import_case_workbooks_preview_flow.test.tsx
=> 3 files, 15 tests passed

npm run build
=> passed；只有既有 chunk-size warning

LABOR_UNION_TEST_MYSQL_DATABASE=lu_test_task96_rpre_browser_r3_20260828 \
  pytest test_six_column_workbook_applies_zero_one_two_as_distinct_order_statuses
=> 1 passed
```

真 MySQL final readback：`0→訂單取消`、`1→訂單完成`、`2→洽談中`；三個唯一 scenario
各一筆 lifecycle event與adoption receipt；same workbook replay counts相同且未增加row。

no-auth Browser使用四列驗收檔完成Preview與使用者明確要求的「確認匯入」：來源列數`4`；
取消`1`、完成`1`、洽談中`1`、無法辨識`1`。Apply receipt回讀為adopted `0`、unmatched `4`、
assignments `0`，且資料庫相符`BROWSER-STATUS-*` Orders為`0`；只留下workbook command claim／receipt。

## 資料安全與限制

- MySQL僅使用allowlisted `lu_test_*`，scenario identity由UUID隔離；未接觸`union_db`。
- 首輪engine setup在第二筆staff seed因測試identity collision失敗，未進入匯入；修正scenario suffix後
  final candidate通過。已提交的第一個唯一測試scenario保留作驗收資料，不做全庫清理。
- 本包沒有table／column／index／seed／backfill變更，因此DB change gate不適用。

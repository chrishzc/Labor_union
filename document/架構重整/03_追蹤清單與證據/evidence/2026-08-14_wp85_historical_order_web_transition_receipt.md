# WP85 訂單歷史 Web 過渡完成收據

日期：2026-08-14  
對應：`../../04_已完成與上線封存/work_packages/85_Historical_Order_Status_and_Caregiver_Evidence_Web_Transition_Work_Package.md`

## 已驗證

- 資料匯入中心已顯示「訂單狀態與月嫂歷史配對」卡，使用 Orders typed API，未呼叫 legacy CLI。
- 去敏 `.xlsx`、任意 sheet 名、單一 `case_no + client_name` 未匹配列：UI Preview 後 Apply 成功，receipt 為
  `source_row_count=1`、`unmatched_case_count=1`、其餘 mutation counts 為 0；符合 zero-mutation、zero-anomaly。
- 同一檔案與相同 command key 的第二次 UI Apply 顯示 `replayed_workbook=true`。
- 不同 digest 沿用已完成 command key 時，UI 顯示
  `historical_order_workbook_idempotency_conflict`，在任何來源列採納前 fail closed。
- matched-case 去敏 workbook 的 UI Preview 顯示 `adopted_count=1`、
  `assignment_candidate_count=1`；Apply 回條顯示 `assignments_created=1`。唯讀核對確認
  Orders 為 completed、實際開始／結束日均非空、正式 assignment 為 1；第二次 UI Apply
  顯示 `replayed_workbook=true`。
- `HISTORICAL-ORDER-001` 已人工確認由 Orders 擁有；review outbox consumer 只從 immutable review root
  取遮罩案件識別與 issue codes，並以 review identity 投影 canonical warning。unmatched case 不進 review／outbox／anomaly。
- 實際 Chrome／Streamlit 驗收：Apply 後卡片顯示「此檔有 1 筆待人工確認；已投影至異常警示中心」，
  導向「異常警示中心 → 資料匯入異常」後，畫面可見「歷史訂單匯入待人工確認」及三筆 review identity；
  畫面只顯示遮罩案件識別與 issue codes，未顯示來源 case／客戶原文。此驗收使用去敏 `.xlsx` 與測試 DB。
- 異常中心的資料匯入分頁已將 `HISTORICAL-ORDER-001` 納入白名單；這修正了 root／outbox 已正確投影、
  但 UI 以舊白名單過濾而不可見的 live defect。
- 唯讀本機升級檢查：`.venv\Scripts\python.exe -m scripts.update_local_database --require-current`
  對 disposable 測試資料庫回傳 `status=current`、release
  `labor-union-wp80-2026-08-13-v1`；本次未套用 migration、未改寫資料。
- disposable MySQL 的 `tests/test_wp85_historical_order_workbook_disposable_mysql_e2e.py` 驗證
  單月嫂 assignment、雙月嫂 evidence-only、workbook conflict 與列內 rollback：`3 passed`。
- focused regression：

```text
.venv\Scripts\python.exe -m pytest -W error tests\test_historical_order_adoption_anomaly_consumer.py tests\test_subsidy_advance_worker_wiring.py tests\test_historical_order_workbook_import.py tests\test_historical_order_adoption_router.py tests\test_historical_order_adoption_api_client.py tests\test_data_import_command_key.py tests\test_wp80_historical_order_adoption.py tests\test_wp80_disposable_mysql_e2e.py tests\test_wp85_historical_order_workbook_disposable_mysql_e2e.py --basetemp .pytest_tmp\wp85-final-mysql -q
28 passed
```

## Completion reconciliation

- 本包沒有新增或變更 schema；WP80 已以獨立 `pre-190 → part 190` assembly 完成 source-preserving
  candidate Apply／verify，完成收據為 `2026-08-14_wp80_historical_order_adoption_closeout_receipt.md`。
- 使用者已明確採用版本庫內去敏 workbook 作為完整重建後的受控來源證據。新增的 controlled-source
  MySQL case 會實際解析該 workbook、建立 matched root、Apply、再驗證 workbook replay；不再保留
  「等待真實個資來源」作為 completion gate。
- 本輪重跑 route／typed client／workbook／資料匯入中心 acceptance：`8 passed in 4.67s`；WP80／WP85
  disposable MySQL：`6 passed in 1.55s`。

## Database gate

| Gate | 狀態 | 證據 |
|---|---|---|
| Scope | PASS | WP85 §2、§5 已核准並已轉 `in-progress`。 |
| Change inventory | PASS | 本次 Web transition 未修改 DDL、seed、backfill 或既有資料。 |
| Static release | PASS | 本包無新 DDL；依賴的 WP80 strict-loader assembly 與 release contract 已通過。 |
| Descriptor | PASS | WP80 candidate 的 part 190 owned objects 為 `exact`。 |
| Read-only plan | PASS | `scripts.update_local_database --require-current` 回報 disposable 測試資料庫為 WP80 current。 |
| Engine verification | PASS | MySQL workbook、review outbox、anomaly projection 與 UI filter focused：28 passed。 |
| Developer acceptance | PASS | 使用者確認 canonical local update 成功，並採用去敏 workbook 為最終受控來源；Web UI receipt 已完成。 |

整體：`DB_CHANGE_READY`；WP85 `completed`，待本輪五包共同 archive gate。

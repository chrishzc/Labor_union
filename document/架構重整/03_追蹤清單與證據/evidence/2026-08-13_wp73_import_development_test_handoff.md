---
doc_type: operator-handoff
declared_status: active
date: 2026-08-13
owner: Case Import / Staff Historical Adoption / Orders / Finance Import
environment: development-only
---

# WP73／WP77 Import 開發測試主機交接

本文件供沒有 Git 的 Windows 開發測試主機使用。所有命令都從專案根目錄執行；本輪允許在人工指定的
開發 DB 寫入，但不授權正式資料庫、production cutover、schema 臨時修改或 File Watcher 自動觸發。

補充包只包含程式、規格、successor part 192 release與去敏測試；不包含`.env`、真實來源Excel或WP79／LINE
recovery施工。解壓前先以隨包SHA-256核對ZIP，再將`payload`內相對路徑覆蓋到專案根目錄。

## 1. 解壓與前置檢查

將交接 ZIP 直接解壓到專案根目錄，保留相對路徑。解壓後確認：

```bat
.venv\Scripts\python.exe -m scripts.imports.rehearse_case_import_workbook --help
.venv\Scripts\python.exe -m scripts.update_local_database --require-current
```

先套用 WP77 additive release，再確認 current：

```bat
.venv\Scripts\python.exe -m scripts.update_local_database
.venv\Scripts\python.exe -m scripts.update_local_database --apply --confirm-configured-database
.venv\Scripts\python.exe -m scripts.update_local_database --require-current
```

第一條必須列出 `labor-union-wp77-2026-08-14-v2` 與 successor part 192；第三條必須成功。若回
`blocked`，先停止 import，修正 `.env` 的 DB 帳密／schema readiness，不可手工貼 SQL 繞過 release。

若在連 DB 前回`release descriptor hash mismatch`，表示目標主機的release manifest、descriptor或SQL
artifact不是同一版。不得執行`--apply`或手改hash；先安裝r2 catalog hotfix，再用下列唯讀命令確認：

```bat
.venv\Scripts\python.exe -c "from scripts import migrate_preserved_database_additive_schema as m; print({'release_id':m.RELEASE_MANIFEST.release_id,'artifacts':[p.name for p in m.SCHEMA_PARTS[-8:]]})"
```

預期 chain 包含 `release_id=labor-union-wp77-2026-08-14-v2`，WP77 artifact為
`192_staff_historical_adoption_hcm_review.sql`；命令仍報hash mismatch時停止，不連 DB。

本輪建議使用獨立開發 DB：

```bat
set DB_DATABASE=union_db_import_dev
set IMPORT_ALLOWED_DATABASES=union_db_import_dev
set HISTORICAL_IMPORT_ALLOWED_DATABASES=union_db_import_dev
```

若人工決定使用目前空資料的 `union_db`：

```bat
set DB_DATABASE=union_db
set IMPORT_ALLOWED_DATABASES=union_db
set HISTORICAL_IMPORT_ALLOWED_DATABASES=union_db
```

腳本讀取的鍵名是`IMPORT_ALLOWED_DATABASES`與`HISTORICAL_IMPORT_ALLOWED_DATABASES`；只設定
`ALLOWED_DATABASES`無效。請把上述三個值寫入目標主機`.env`，或在同一CMD視窗先執行`set`。

環境變數只對目前 CMD 視窗有效。不要啟動 `scripts/file_watcher.py`，也不要把測試檔放入
`downloads\bank`，否則 Finance 可能被額外觸發。

## 2. 先跑 focused verification

```bat
.venv\Scripts\python.exe -m pytest -W error -p no:cacheprovider tests\test_hcm_import_safety_gate.py tests\test_wp73_workbook_rehearsal_cli.py tests\test_wp73_dirty_data_characterization.py tests\test_import_entry_split.py tests\test_wp77_import_contracts.py tests\test_preserved_database_plan_contract.py tests\test_verify_validation_schema_manifest.py tests\test_remote_anomaly_schedule_merge.py tests\test_finance_alerts_government_overpayment_ui_e2e.py --basetemp .pytest_tmp\wp77-import-handoff -q
```

本補充包建立時基準為`89 passed, 2 skipped, 3 xfailed`。三個xfail是正式importer尚未提供true no-write mode的已知
fail-before evidence，不可改成 skip 或刪除。

## 3. 三條 Case Import 唯讀演練

這三條不讀 `.env`、不連 MySQL、完全不寫 DB；檔名及 sheet 名稱不限，由欄位契約選表。

### 3.1 HCM

```bat
.venv\Scripts\python.exe -m scripts.imports.rehearse_case_import_workbook --lane hcm --workbook "document\資料庫、資料處理\1,HCM.xlsx"
```

### 3.2 Client BeClass

```bat
.venv\Scripts\python.exe -m scripts.imports.rehearse_case_import_workbook --lane client-beclass --workbook "document\資料庫、資料處理\3.client_beclass.xlsx"
```

### 3.3 Staff BeClass

```bat
.venv\Scripts\python.exe -m scripts.imports.rehearse_case_import_workbook --lane staff-beclass --workbook "document\資料庫、資料處理\2.staff.xlsx"
```

每次輸出都必須含：

```text
database_connections = 0
writes_performed = 0
```

`review_required` 表示來源含髒資料，不代表指令失敗。輸出不得含原始列、姓名、電話、身分證、銀行帳號、
完整檔案路徑或 sheet 名稱。只有同一 workbook 有兩張都符合 lane 欄位契約時，才使用 `--sheet` 明確指定。

## 4. Case Import 開發 DB 寫入

HCM 與 Client BeClass 可依任意順序獨立匯入；Staff lane 也可獨立執行。章節編號只沿用 lane 分類，
不代表依賴順序。缺少對方只形成 current-state anomaly，不得阻擋來源 root。

### 4.1 HCM

HCM CLI 沒有 dry-run；執行後直接使用目前 `DB_DATABASE`。`IMPORT_ALLOWED_DATABASES` 必須包含同一資料庫，否則固定回 `hcm_import_database_target_not_allowed`。工作表名稱不限，程式會依 HCM 必要欄位契約選取唯一符合的非空工作表：

```bat
.venv\Scripts\python.exe -m scripts.imports.import_client_hcm "document\資料庫、資料處理\1,HCM.xlsx"
```

HCM 本身 validation 合法時即建立 Client／Order，Client BeClass 尚未存在時 `requires_cooking=NULL`，
並投影 `BECLASS-001`。只有 HCM 來源列本身 validation／identity 失敗才建立
`case_import_hcm_review_rows` 與 outbox並投影 `IMPORT-004`。唯一配對後才以 typed Orders command補入
controlled cooking answer；缺失或歧義進 BeClass／reconciliation review，不回滾 HCM roots。

HCM防重規則：案件編號重複時只有同來源內容的成功receipt可算`exact_replay`；新案件若IP位址與姓名
同時精確命中既有Client，該列不載入，建立review並在警示中心顯示「疑似重複申請，請公會人員確認」。
只有IP相同但姓名不同視為可能共用網路，允許載入。不得用模糊姓名或電話自動合併。

同檔立即重跑一次：合法成功列應為`exact_replay`；invalid列應維持相同review/outbox筆數。去敏查核：

```sql
SELECT COUNT(*) AS clients_count FROM clients;
SELECT COUNT(*) AS orders_count FROM orders;
SELECT COUNT(*) AS hcm_review_rows FROM case_import_hcm_review_rows;
SELECT COUNT(*) AS hcm_outbox_rows FROM case_import_hcm_review_outbox;
SELECT COUNT(*) AS active_hcm_alerts
FROM anomaly_current_alerts WHERE definition_code='IMPORT-004' AND predicate_active=1;
```

### 4.2 Client BeClass historical

工作表名稱不限，程式會依 Client BeClass 必要欄位契約選取唯一符合的非空工作表：

```bat
.venv\Scripts\python.exe -m scripts.imports.import_client_beclass --historical-apply "document\資料庫、資料處理\3.client_beclass.xlsx"
```

入口同時要求 `--historical-apply` 與 `HISTORICAL_IMPORT_ALLOWED_DATABASES` 命中目前 DB；缺任一項應固定阻擋。

### 4.3 Staff BeClass historical

工作表名稱不限，程式會依 Staff BeClass 必要欄位契約選取唯一符合的非空工作表：

```bat
.venv\Scripts\python.exe -m scripts.imports.import_staff_beclass --historical-apply "document\資料庫、資料處理\2.staff.xlsx"
```

預期首次執行不再出現 `skipped_existing`：新 identity 計入 `新增`，同 identity 且姓名一致計入
`採納既有`。既有 Staff 只補空值；非空 scalar、銀行或關聯衝突保留 DB current fact 並建立 review。
非根欄位錯誤可用 `NULL` 建立／採納，但必須正交計入 `待確認`。不得預設 48-row來源的新增、採納或
待確認固定筆數；每列以 fresh identity resolution與不可變 receipt為準，exclusive outcomes總和必須等於
source rows。

首次完成後立刻原檔重跑：

```bat
.venv\Scripts\python.exe -m scripts.imports.import_staff_beclass --historical-apply "document\資料庫、資料處理\2.staff.xlsx"
```

第二次應全部進 `replay` 或既有 review replay，不得新增 Staff、銀行、關聯、review 或 receipt。

去敏核對：

```sql
SELECT outcome, COUNT(*) AS rows_count
FROM staff_historical_adoption_receipts GROUP BY outcome ORDER BY outcome;
SELECT COUNT(*) AS staff_review_rows
FROM beclass_import_review_rows WHERE source_kind='staff';
SELECT COUNT(*) AS hcm_review_rows FROM case_import_hcm_review_rows;
SELECT published_at IS NULL AS pending, COUNT(*) AS rows_count
FROM case_import_hcm_review_outbox GROUP BY published_at IS NULL;
```

只回傳 counts；不要查詢或貼出 source payload、姓名、證號、電話、地址或銀行帳號。

## 5. Historical Orders 一次性開發驗證

來源契約固定為六欄：`client_name`、`case_no`、`start_date`、`end_date`、`status`、`staff_name`。
狀態只接受 `0／1／2／空值`：

| source status | asserted status |
|---|---|
| `0` | 訂單取消 |
| `1` | 訂單完成 |
| `2` | 洽談中 |
| 空值 | 正式契約應為 `review_required`；舊腳本仍錯誤映射成取消 |

正式 CLI 已退役，以下是預期阻擋測試：

```bat
.venv\Scripts\python.exe -m scripts.import_historical_orders "document\資料庫、資料處理\假資料_歷史訂單.xlsx"
```

預期：`legacy_historical_order_writer_retired`。

本輪人工允許的開發 fixture bypass：

```bat
.venv\Scripts\python.exe -c "from scripts.import_historical_orders import process_import; print(process_import(r'document\資料庫、資料處理\假資料_歷史訂單.xlsx', fixture_write_authorized=True))"
```

此 bypass 只初始化不存在的 Order：必須先有唯一 Client；既有 `case_no` 只會 `skipped_existing`，不更新
status。它仍是 direct SQL，沒有 HistoricalOrderAdoption event／receipt／lifecycle origin，不能作為正式落地證據。

## 6. Finance Import

### 6.1 四種格式 dry-run

```bat
.venv\Scripts\python.exe -m scripts.imports.import_finance_excel --dry-run --excel-path "document\資料庫、資料處理\台新範例對帳單.xlsx" --report-path "scratch\finance-taishin-dry-run.json"

.venv\Scripts\python.exe -m scripts.imports.import_finance_excel --dry-run --excel-path "document\資料庫、資料處理\永豐範例對帳單.xlsx" --report-path "scratch\finance-sinopac-dry-run.json"

.venv\Scripts\python.exe -m scripts.imports.import_finance_excel --dry-run --excel-path "document\資料庫、資料處理\歷史對帳單.xlsx" --report-path "scratch\finance-history-dry-run.json"

.venv\Scripts\python.exe -m scripts.imports.import_finance_excel --dry-run --excel-path "document\資料庫、資料處理\帳務.xlsx" --report-path "scratch\finance-generated-dry-run.json"
```

dry-run 必須回 `transaction_outcome=not_written`。報告放 `scratch/`，不得提交或傳回含個資的 raw payload。

### 6.2 Finance apply

先選一份已通過 dry-run 的檔案：

```bat
.venv\Scripts\python.exe -m scripts.imports.import_finance_excel --excel-path "document\資料庫、資料處理\永豐範例對帳單.xlsx" --report-path "scratch\finance-sinopac-apply.json"
```

目前 CLI 使用測試 actor／`test_ingestion`，只允許開發驗收。同檔再執行一次，必須形成 replay／duplicate
occurrence，不得重複建立正式帳務交易。

### 6.3 Existing batch reprocess dry-run

將 `1` 換成實際 completed batch id：

```bat
.venv\Scripts\python.exe -m scripts.imports.reprocess_finance_import_batch --batch-id 1 --report-path "scratch\finance-batch-1-reprocess-dry-run.json"
```

這支 legacy CLI 的 `--apply` 已退役；apply 必須走 typed Preview／Apply API，不在本交接包重新開放。

## 7. Fixture snapshot importer

唯讀驗證：

```bat
.venv\Scripts\python.exe -m scripts.import_db_snapshot_fixture_v2 --fixture "fixtures\db_snapshot_v2\v3"
```

實際寫入：

```bat
.venv\Scripts\python.exe -m scripts.import_db_snapshot_fixture_v2 --fixture "fixtures\db_snapshot_v2\v3" --apply
```

目前 main 的 fixture bundle 缺 `manifest.json` 時應 fail closed；交接包不包含或重建該 bundle。

## 8. 每條 apply 的驗收順序

1. 保存執行前資料表 row count；不要輸出 raw row。
2. 執行一次 apply，保存 console summary 與去敏 report。
3. 查核 expected root／review／receipt／event 數量。
4. 同檔再執行一次，驗證 replay／skip，不得重複 root 或正式交易。
5. 修改檔案複本中的一個非敏感欄位，再以同 identity 測 conflict；原始模板保持不動。
6. 發現 exception 後核對 transaction rollback，禁止留下半套 roots。
7. 只回傳 counts、status、error code、digest 與 invariant；不要傳姓名、電話、身分證、銀行帳號或 raw workbook。

HCM另須留下四條結果：新案件成功、原檔exact replay、新案件IP＋姓名同時命中被阻擋、IP相同但姓名
不同可建立。若來源本身validation失敗，先驗review/replay，不得為了測防重而手改正式來源檔。

## 9. 停止條件

遇到下列任何一項立即停止該 lane，不順手改 schema 或資料：

- `.env` 指向非人工指定的開發 DB；
- `update_local_database --require-current` 不通過；
- unknown／multiple compatible sheet、header drift 或不可讀檔案；
- invalid required field 仍建立 Client／Order／Staff；
- replay 重複建立 root、交易或事件；
- exception 後存在 partial residual；
- HCM review enum／root mismatch；
- Staff 既有 identity 仍被無 receipt 的 `skipped_existing` 略過；
- Staff 非空 current fact 被歷史來源覆寫，或既有關聯被 delete／union；
- Historical Orders 空值被自動取消；
- historical import 覆蓋既有 current／LIFF facts。

## 10. 本交接包不包含

- `.env`、DB 密碼、token 或任何 secret；
- WP76／其他 dirty worktree 修改；
- Finance 歷史流水與銀行樣本的額外複本；測試主機沿用專案內既有檔案；
- fixture snapshot v3 缺失內容；
- schema migration、production cutover 或 Web UI。

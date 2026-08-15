# WP77 Staff Historical Adoption 與 HCM Review 驗證收據

- 日期：2026-08-13
- Work Package：`77_Staff_Historical_Adoption_and_HCM_Review_Work_Package.md`
- release id：`labor-union-wp77-2026-08-13-v1`
- 狀態：in-progress；focused／fresh／direct developer DB evidence已完成，preserve gate仍未完成

## 目標機 Staff replay／警示補充修復

- 目標測試機的 `新增 37＋採納既有 12` 與後續 `exact replay 49` 僅能由該機聚合查詢驗收；
  本機資料量不作為目標機證據。
- fail-before-fix 已證明成功 receipt 原先會略過 fresh Staff root 檢查，且 anomaly checkpoint
  會遮蔽遺失的 current projection。
- 修正後 exact replay 會 fresh-lock 唯一 Staff root並核對 receipt `staff_id`／姓名；背景 bounded
  rescan從 durable BeClass review root補建 `IMPORT-001/003`，不改寫 review或published outbox。
- focused anomaly／WP77 regression：`58 passed`；disposable MySQL 的 published outbox＋既有
  checkpoint＋遺失 current projection 重建情境：`3 passed`（同檔另含 Staff replay／HCM review）。

## 已通過

1. Staff historical scalar 採 empty-only merge；既有非空不同值保留 current fact並建立 Staff BeClass
   review。銀行與七類 legacy relations僅在既有集合為空時補入，exact no-op，非空不同值 review，
   existing path沒有 delete／union。
2. Staff created／adopted row保存 immutable adoption receipt；相同 source digest＋row replay不重複 mutation。
3. HCM 與 Client BeClass可任意順序獨立落地；HCM尚未配對時以`requires_cooking=NULL`建立 roots。
   唯一配對後才以 typed Orders command補入 controlled cooking；歧義進 BeClass reconciliation review。
   `IMPORT-004`只處理HCM來源 validation，script不再同步寫 alert。
4. part 189、descriptor、canonical release catalog與 validation full-SQL assembly互相一致；release builder
   `--check` 與 validation manifest verifier通過。
5. 最後一輪 focused suite：`66 passed`；包含source fingerprint exact replay、Staff成功receipt限定、
   HCM／BeClass對稱 anomaly、release metadata與 MySQL E2E。
6. fresh disposable `lu_test_wp77_20260813_r3`成功建立到part 189；人工授權的測試`union_db`精準套用
   part 189後，WP77 MySQL E2E為`2 passed`。
7. HCM outbox曾實際重現`anomaly_source_fact_invalid`；修正`IMPORT-004` fingerprint binding後重放為
   `2 delivered / 0 failed`，後續新事件為`1 delivered / 0 failed`。
8. 三份標準來源目前各一列：HCM=`review_required 1`，Staff=`blocked_identity 1`，Client BeClass=
   `review_required 1`；重跑Staff仍是blocked，不誤算成功exact replay。
9. 最後完整suite：`1984 passed, 92 skipped, 3 xfailed, 2 failed`；兩個failure均為verification baseline
   正確拒絕9份舊receipt的stale input digest。未重新簽發未執行的歷史receipt。
10. 2026-08-13 以人工授權的空資料`union_db`正式執行標準HCM dirty workbook：結果為新增0、
    review_required 1，Client／Order仍為0；HCM review/outbox成功投影至`IMPORT-004`。相同檔案重跑後
    review與outbox均維持6筆，證明invalid-row replay零增量。此測試以process-scoped
    `DB_DATABASE=union_db`及`IMPORT_ALLOWED_DATABASES=union_db`執行，未修改`.env`。

## 尚待目標主機執行

### Staff replay／警示補充包

本補充為 code-only，無 schema migration。將
`scratch/wp77_staff_replay_anomaly_recovery_20260813.zip` 解壓到專案根目錄並覆蓋同路徑後：

```bat
.venv\Scripts\python.exe -m pytest -q -W error tests\test_wp77_import_contracts.py --basetemp .pytest_tmp\wp77-recovery
.venv\Scripts\python.exe -m scripts.rebuild_beclass_import_anomalies --limit 100
.venv\Scripts\python.exe -c "from infrastructure.mysql.mysql_adapter import get_connection; c=get_connection(); q={'staff_total':'SELECT COUNT(*) n FROM staff','successful_receipts':'SELECT COUNT(*) n FROM staff_historical_adoption_receipts WHERE outcome IN (\'created\',\'adopted_existing\')','distinct_success_staff':'SELECT COUNT(DISTINCT staff_id) n FROM staff_historical_adoption_receipts WHERE outcome IN (\'created\',\'adopted_existing\')','staff_reviews':'SELECT COUNT(*) n FROM beclass_import_review_rows WHERE source_kind=\'staff\'','active_import_alerts':'SELECT COUNT(*) n FROM anomaly_current_alerts WHERE definition_code IN (\'IMPORT-001\',\'IMPORT-003\') AND predicate_active=TRUE'}; cur=c.cursor(); print({k:(cur.execute(v),cur.fetchone()[\'n\'])[1] for k,v in q.items()}); cur.close(); c.close()"
.venv\Scripts\python.exe -m scripts.imports.import_staff_beclass --historical-apply "C:\Users\ASUS\Desktop\獅子\測試資料\STAFF.xlsx"
```

只有當 `staff_total=49`、`successful_receipts=49`、`distinct_success_staff=49` 時，重跑顯示
`exact replay 49` 才是有效成功。否則應收到 `staff_historical_adoption_replay_root_drift`，不得再宣稱完成。

1. `.venv\Scripts\python.exe -m scripts.update_local_database` 必須列出 WP77 successor／part 192；再經
   `--apply --confirm-configured-database`與`--require-current`。
2. 以完整48-row Staff來源驗證逐列守恆；不得預設created／adopted／review固定筆數，成功來源原檔重跑
   才能計入exact replay。
3. 以合法HCM與合法Client BeClass各驗一次先到／後到、`BECLASS-001`／`IMPORT-003`自動解除，以及
   unique cooking typed Orders update；目前標準範例只有dirty review路徑。
4. 上一支援版 source→candidate已完成plan／restore／part 189 apply，但整體cutover測試在5分鐘timeout，
   未取得最終verify PASS；不得把中間receipt冒充完整preserve evidence。
5. 人工已修正HCM防重：案件編號不得重複；新案件只有IP＋姓名同時命中既有Client才阻擋並警示，
   IP相同但姓名不同可匯入。仍須在目標主機驗證new、exact replay、疑似重複申請與共用IP四條路徑。
6. `IMPORT-003`既有registry action固定查BeClass review item，但「BeClass存在、HCM缺少」是純
   current-state anomaly、沒有review root；在action契約裁決前，不能宣稱該警示的人工作業入口完成。

## DB gate

| Gate | 狀態 | 證據 |
|---|---|---|
| Scope gate | PASS | 2026-08-13 人工核准精簡 WP77、Staff保守採納與HCM own review |
| Change inventory | PASS | part 189只有schema-only；無seed、backfill或destructive change |
| Static release gate | PASS | WP77 manifest／descriptor／catalog／validation assembly與hash tests |
| Descriptor gate | PASS | 三個新表、FK、checks、indexes與immutable triggers均被descriptor覆蓋 |
| Read-only plan gate | PASS | WP77 plan列出part 189；`union_db`另因既有part 139 partial而fail closed |
| Engine verification gate | BLOCKED | fresh PASS、direct E2E PASS；上一版preserve cutover在最終verify前timeout |
| Developer acceptance gate | BLOCKED | 三份一列dirty範例已驗；仍缺完整48-row與合法HCM／Client順序/reconcile evidence |

總狀態：`DB_CHANGE_NOT_READY`。這表示不得封存或宣稱 WP77 完成；不表示需要擴張 schema。下一步只按
交接文件在目標開發主機完成 release、真實資料與 replay 驗收。

## 2026-08-14 integration supersession note

本 receipt 所記錄的 part 189／`labor-union-wp77-2026-08-13-v1` 實跑事實保持不變。不同開發者
合併後，遠端已發布 part 189／190 identities 優先保留；後續 WP77 使用 part 192 與
`labor-union-wp77-2026-08-14-v2`。任何舊 plan、partial receipt 或 journal identity 不得假裝與
successor fingerprint 相容，須重新產生 candidate plan 並重跑尚未通過的 gate。

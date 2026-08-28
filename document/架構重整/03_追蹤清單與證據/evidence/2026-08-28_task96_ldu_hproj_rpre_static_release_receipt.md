# Task 96 LDU／HPROJ／RPRE static release receipt

- `date`: `2026-08-28`
- `status`: `in-progress`
- `scope`: deterministic qualification builder、Historical Baseline Projector 1011、Service-before Replacement 1012，以及兩支 release 的 canonical assembly／cutover 整合
- `authority`: 已核准的 LDU、HPROJ、RPRE Work Packages
- `effect_boundary`: source、tests與文件；本輪未連線或修改任何 DB，未發布 qualification，未執行 Browser／provider／developer replacement

## 1. 已完成的小任務

1. `scripts/build_local_additive_qualification.py` 已完成 deterministic preview／publish builder。它會 strict 驗證 final evidence schema、backup SHA、canonical release identity／hash、完整 fresh assembly table inventory、descriptor exactness與canonical fingerprints；publish 採 allowlisted path、validator roundtrip、atomic no-overwrite。
2. `1011_historical_baseline_projector.sql` 已完成 occurrence、umbrella membership、successor、receipt與internal outbox的 additive storage contract，並註冊 manifest、descriptor、fresh assembly與cutover catalog。
3. `1012_service_before_replacement.sql` 已完成 replacement event、root disposition、successor、receipt與internal outbox的 additive storage contract，並註冊 manifest、descriptor、fresh assembly與cutover catalog。
4. canonical upgrade chain current terminal 為 1012，共 51 manifests／101 ordered upgrade artifacts；generated full release已重新產生並通過 freshness check。

## 2. 凍結 identities

| Artifact | SHA-256／identity |
|---|---|
| `db/schema_parts/1011_historical_baseline_projector.sql` | `7980b4adbe6b8ed9b058bbf7968cdb5b45f6148eefee684cb9fc0299598e5c50` |
| `db/schema_parts/1012_service_before_replacement.sql` | `e16194caca67193001eef36baccd358b996082d29826e7722b5f25730099add7` |
| fresh assembly ordered digest | `456b3a2087eca6aab96ad16b1e2bba1d3a1374f8dc0029051bb0acbbe6e4447c` |
| latest release | `labor-union-service-before-replacement-2026-08-28-v1` |

## 3. 驗證結果

- integration producer focused regression：`145 passed`
- root combined regression：`162 passed`
- final fresh Luna/high independent verification：`60 passed`，P0=0、P1=0
- full release freshness：`.venv/bin/python -m scripts.build_validation_schema_release --check` → `passed`
- full fresh assembly table inventory：358 tables，missing=0
- `git diff --check`、strict UTF-8、source header與Python compile：`passed`

Fresh verifier的結論只涵蓋 static contract與builder，不涵蓋 MySQL engine。HPROJ runtime仍須在同一UoW重算membership set digest／count並以fresh readback核對；RPRE runtime仍須由typed owner adapters fresh核對official zero-service proof、Matching reuse proof與canonical root-set digest。不得以SQL metadata或receipt欄位代替owner真實性。

## 4. DB change gate

| Gate | 狀態 | 證據／限制 |
|---|---|---|
| Scope gate | PASS | HPROJ、RPRE與LDU approved Work Packages涵蓋 additive schema、builder與本機驗收 |
| Change inventory | PASS | 1011／1012均為`schema-only`；system-seed、business-row-backfill、destructive皆為none |
| Static release gate | PASS | schema parts、manifests、descriptors、fresh assembly、cutover catalog、runner與generated full release互相引用 |
| Descriptor gate | PASS | 1011／1012 owned objects、parent columns、indexes、FK、checks與triggers由focused tests與fresh verifier核對 |
| Read-only plan gate | BLOCKED | 1006～1012尚未具備全部final engine evidence與published qualification，未執行真實DB plan |
| Engine verification gate | NOT_RUN | 未執行disposable fresh bootstrap或1003代表資料的preserve-data candidate驗證 |
| Developer acceptance gate | NOT_RUN | 前置engine gates尚未完成；未操作任何既有developer DB |

總結：`DB_CHANGE_NOT_READY`。

## 5. 下一個最高優先度執行點

在符合`lu_test_*`、development profile與source不變的前提下，取得1006～1012的disposable fresh／preserve-data final evidence並由builder發布qualification；完成後才執行1003→1012 sequential candidate apply／verify。不得使用reset、replacement、`--switch`、`union_db`或production target。

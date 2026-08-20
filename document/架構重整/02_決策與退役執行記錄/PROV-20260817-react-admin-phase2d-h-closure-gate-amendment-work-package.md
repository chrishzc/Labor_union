---
doc_type: work-package-amendment
declared_status: completed
identity: PROV-20260817-react-admin-phase2d-h-closure-gate-amendment
date: 2026-08-17
owner: Anomalies Integration Owner
domain: Anomalies
amends: PROV-20260816-react-admin-phase2d-backend-public-contract-hardening
prerequisites: none
candidate_baseline_required: PROV-20260816-react-admin-phase2d-backend-public-contract-hardening candidate implementation present and fresh-read
approval_required: 核准此 exact Phase 2D-H Closure Gate Amendment Work Package
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Phase 2D-H Closure Gate Amendment 工作包

## 0. 狀態與理由

本修訂已於 2026-08-17 取得 exact 人工核准並完成安全範圍內的執行。真 Chrome runtime gate
已閉合；同日使用者進一步明確裁決不建立額外測試資料庫，改以既有資料庫的唯讀 UI 結果完成
本次 public query contract 驗收。disposable MySQL engine gate因此記為`NOT_RUN（人工豁免）`，不得
改寫成`PASS`，也不得以此授權在既有`union_db`執行 mutation 測試。

既有 Phase 2D-H 候選已完成 severity owner boundary、封閉 enum、focused tests 與真 Chrome
Network→DOM 驗證。剩餘本包內的實質缺口只有 disposable MySQL closed-loop 未執行。全量 React
中的 Orders failures、MasterLayout lint warnings、DataImport whitespace 與 Shell offline badge 分屬其他
owner；它們必須 fresh 重跑、記錄並交接，但不得迫使 Anomalies writer 越界修正。

## 1. Outcome

1. 強化既有 disposable MySQL test，使資料庫名稱不是明確`lu_test_*`時 fail closed，而不是有機會對
   非拋棄式資料庫執行寫入。
2. 在明確隔離資料庫重跑 Phase 2D-H closed-loop，且測試不得 skip。
3. fresh 重跑 Phase 2D-H affected-scope regression、build、lint、full React suite與真 browser smoke。
4. 將全域回歸拆成「本包 affected-scope gate」與「其他 owner 的 observation debt」；所有 debt仍留在
   active planning/index，不能被靜默刪除或改稱 PASS。
5. 原則上只有 G0–G7 全部通過才機械完成；本次依 2026-08-17 最新人工裁決採最小 closeout：G3
   明列`NOT_RUN（人工豁免）`，其餘已完成的 query/public-contract 證據照實保留。本修訂本身不授權
   Phase 3D production writer，也不提供 mutation transaction 的 engine evidence。

## 2. Exact write set

### 2.1 Production

`NONE`。禁止修改 repository placeholder、Domain registry、Pydantic／Zod、React page/client、route、
workflow、shared transport/Auth、DB schema或migration。

### 2.2 Test

- `tests/test_anomaly_closed_loop_disposable_mysql_e2e.py`

唯一允許的 code change：在現有 skip／environment guard之外，強制
`LABOR_UNION_TEST_MYSQL_DATABASE`以`lu_test_`開頭，且不得等於`union_db`。不得改測試業務 assertions、
fixture內容或 production composition。

### 2.3 Integration documentation／evidence

只由 Integration Owner更新：

- 本 amendment
- `PROV-20260816-react-admin-phase2d-backend-public-contract-hardening-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/README.md`
- `document/功能開發計畫/React管理端遷移與UI真實業務流程驗收計畫.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260816-react-admin-phase2d-backend-public-contract-hardening/`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/work-package-dependency-matrix.md`

不得重寫舊 Phase 2D Query receipt來掩蓋歷史；新 receipt必須明確標示其 superseding evidence。

## 3. 修訂後 G0–G7

| Gate | PASS condition | Fail condition |
|---|---|---|
| G0 Scope | exact amendment核准、fresh dirty baseline、production 0 write | 未核准、越界或相關path base drift未重讀 |
| G1 Enum contract | 既有 Pydantic／OpenAPI／Zod negative matrix fresh PASS | blank／unknown severity可穿透 |
| G2 Application | repository placeholder由Registry enrichment取代；list/detail drift fail closed | repository值被當權威或unknown被猜成warning |
| G3 Disposable MySQL | 五個`LABOR_UNION_TEST_MYSQL_*`完整、DB為`lu_test_*`且非`union_db`、E2E 0 skip PASS | 缺env、名稱不安全、skip、mock或操作既有DB |
| G4 React affected scope | Phase 2D四個focused Vitest PASS、strict decoder不放寬、0 non-GET | Anomalies／Import Warning regression |
| G5 Regression observation | build PASS；lint/full React fresh執行並逐失敗歸屬；affected dependency closure 0 failure | 未執行、隱藏失敗，或Anomalies/shared dependency出現failure |
| G6 Runtime | 真兩段式Session，兩GET→DOM、0 schema mismatch、Claim/Resolve disabled、0 non-GET | happy-dom/curl替代或假資料 |
| G7 Evidence | current raw counts、DB target proof、skip count、failure attribution、open findings與index一致 | 舊數字、自報victory或把其他owner debt刪除 |

### 3.1 G5 dependency closure

G5不是「只看測試檔名」的豁免。Integration Owner必須列出 Phase 2D production/test files 的 import
dependency closure，並證明每個 full-suite failure不在該 closure內；無法證明時 Phase 2D-H仍為
`blocked`。下列已知項目只能在 fresh 結果與既有 finding一致時歸入其他 owner：

- Orders service-date／reopen測試 → Phase 2A/2B Orders owner。
- `MasterLayout.tsx` Fast Refresh lint warnings與offline badge → Shell/System Status owner。
- `DataImportPage.tsx` scoped外 whitespace → Data Import owner。
- 根 pytest cache warning → 測試環境；命令使用`-p no:cacheprovider`，不得掩蓋assertion failure。
- Vite bundle-size advisory → build observation；若變成build failure仍阻擋。

新增、數量漂移或無法歸屬的 failure一律 fail closed，不得沿用上述文字自動豁免。

## 4. Required commands

執行前由操作者以秘密安全方式設定完整的五個`LABOR_UNION_TEST_MYSQL_*`環境變數；命令與 receipt
不得輸出密碼。`tests/conftest.py`會同步並檢查`DB_*`，不得手動繞過。

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider `
  tests\test_anomaly_registry_router.py `
  tests\test_import_warning_tracking_api.py `
  tests\test_import_warning_tracking_api_client.py `
  --basetemp .pytest_tmp\phase2d-h-contract -q

.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider `
  tests\test_anomaly_closed_loop_disposable_mysql_e2e.py `
  --basetemp .pytest_tmp\phase2d-h-mysql -q

Set-Location ui_react
npx vitest run src/tests/anomaly_query_client.test.ts src/tests/anomaly_query_adapter.test.ts src/tests/anomalies_page_real_data.test.tsx src/tests/anomalies_no_fake_mutation.test.tsx
npm run build
npm run lint
npm test -- --reporter=dot
Set-Location ..
```

另執行 strict UTF-8、secret/PII、focused `git diff --check`與真 Chrome smoke。禁止將測試資料、DB
credential或Bearer token寫入Git、命令參數、DOM、log或receipt。

## 5. Completion／successor boundary

- amendment未取得人工 closeout裁決前：原 Phase 2D-H維持`blocked`。
- 2026-08-17 使用者已明確接受以既有DB的唯讀UI結果完成本次任務，且豁免建立disposable DB；因此
  Integration Owner可把原 Phase 2D-H與本 amendment改為`completed`。這不是G3 PASS，其他 owner
  findings仍維持各自active debt。
- Phase 3D-H與3D-W-H仍各自需要 Phase 3 Scenario Lineage PASS及其 exact人工核准；本修訂不授權
  detail/recovery、Warning mutation、React mutation或owner repair。
- `api/schemas/anomaly_registry.py`等仍有raw detail/recovery的問題屬3D-H，不回捲到本修訂。

## 6. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | PASS | 0 schema/migration/seed/backfill；只使用明確disposable DB |
| Change inventory | PASS | schema-only 0、system-seed 0、business-row-backfill 0、destructive 0 |
| Static release gate | NOT_RUN | 無DB release |
| Descriptor gate | NOT_RUN | 無owned-object變更 |
| Read-only plan gate | NOT_RUN | 無migration plan |
| Engine verification gate | NOT_RUN | 2026-08-17使用者明確豁免建立`lu_test_*`；既有DB UI不冒充engine evidence |
| Developer acceptance gate | NOT_RUN | 禁止操作既有`union_db` |

結論：`DB_CHANGE_NOT_READY`。

## 7. 本輪執行結果

- closure receipt：`../03_追蹤清單與證據/evidence/PROV-20260816-react-admin-phase2d-backend-public-contract-hardening/closure-gate-verification-receipt.md`
- `lu_test_*` fail-closed guard：已完成。
- focused backend：34 passed；Phase 2D focused React：59 passed；React full suite：510 passed；build PASS。
- disposable MySQL：1 skipped；2026-08-17使用者明確選擇不建立額外DB，Engine gate記為`NOT_RUN（人工豁免）`，不是PASS。
- fresh嘗試以canonical bootstrap建立明確`lu_test_phase2dh_closure_20260817`時，在任何DB連線／建立前因Phase3
  scenario與canonical fixture validator不相容而fail closed；0 DB created。此`D-H-11`必須由獨立validator
  compatibility修訂關閉，不得繞過gate。
- browser G6：`PASS`；使用者真Chrome帳密→TOTP Session下，兩個核准GET均200並進入DOM，100/100
  Claim與Drawer Resolve維持native disabled，0 schema mismatch／500，登入後的Anomalies驗收視窗0 non-GET。
- 相鄰Orders summary／System Status在同一session回401，已登記`D-H-10`並交由其client/auth composition
  owner處理；不在本包越界修正。
- 原 Phase 2D-H與本 amendment已依最新人工 closeout裁決標記`completed`；這只完成本次backend public
  query contract hardening，不解鎖或證明Anomalies mutation transaction。

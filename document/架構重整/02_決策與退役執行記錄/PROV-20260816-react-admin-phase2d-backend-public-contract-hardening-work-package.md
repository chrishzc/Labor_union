---
doc_type: work-package
declared_status: completed
identity: PROV-20260816-react-admin-phase2d-backend-public-contract-hardening
date: 2026-08-16
owner: Integration Owner
domain: Anomalies
subsystem: Alert Query / Import Warning Tracking / FastAPI Contract
specification: PROV-20260816-react-admin-phase2d-backend-public-contract-hardening-specification
approval_required: human-must-reply-核准此-exact-Phase2D-H-Work-Package
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
---

# Phase 2D-H Backend Public Contract Hardening 工作包（單一代理執行）

## 0. Activation gate

本包已於 2026-08-16 獲使用者明確回覆：

> 核准此 exact Phase 2D-H Work Package

因此已授權下列 production／test write set。本包由目前 Integration Owner 自己施工與驗證，不委派
其他模型。

## 1. Outcome

修復 canonical Anomalies summary的空白severity，將三組既有 Domain enum收斂成真實FastAPI public
contract，並用真Application composition與真Chrome證明React Anomalies頁可顯示；不得改DB或放寬前端。

## 2. Exact write set

### 2.1 Production

- `subsystems/anomalies/alert_workflow.py`
- `api/schemas/anomaly_registry.py`
- `api/schemas/anomaly_recovery.py`
- `api/schemas/import_warning_tracking.py`

### 2.2 Tests

- `tests/test_anomaly_registry_router.py`
- `tests/test_anomaly_closed_loop_disposable_mysql_e2e.py`
- `tests/test_import_warning_tracking_api.py`
- `tests/test_import_warning_tracking_api_client.py`

### 2.3 Documentation／evidence（Integration Owner only）

- 本 specification／Work Package
- `document/架構重整/02_決策與退役執行記錄/README.md`
- `document/功能開發計畫/React管理端遷移與UI真實業務流程驗收計畫.md`
- Phase 2D evidence directory中的matrix、verification、browser、findings、summary
- 新 evidence 子目錄：
  `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260816-react-admin-phase2d-backend-public-contract-hardening/`

其餘路徑一律禁止。特別禁止修改repository SQL／schema、React decoder/page、shared transport、Auth、
package files、Orders與其他頁面。

## 3. Implementation contract

### 3.1 Application enrichment

- `query_summaries` 逐筆以 `definition_code` require canonical definition。
- 對外severity只取 `definition.severity`；不可信任repository placeholder或snapshot。
- source domain必須與definition一致，不一致fail closed。
- `query_detail`必須重用同一helper，不能出現list/detail drift。
- 不修改project／claim／resolve transaction與UoW。

### 3.2 Pydantic contract

- `AnomalySummaryView.severity` → `AnomalySeverity`。
- summary／receipt／recovery context的workflow status → `AlertWorkflowStatus`。
- Import Warning task／preview response → `ImportWarningTrackingStatus`。
- request target使用明確Literal或專用request enum，只保留既有四個人工target。
- 所有model保持`extra="forbid"`與strip規則。

### 3.3 Fail-closed

禁止：空字串fallback、unknown→warning、try/except跳過單列、200空清單、route手寫未驗證dict、
`Any`擴張、修改React接受集合、修測試fixture掩蓋真composition。

## 4. Test plan

### G1 Contract

- Pydantic逐欄matrix：required／nullable／enum值／JSON representation。
- negative：blank、unknown、wrong type、null、extra field。
- OpenAPI schema必須列出enum；不能只靠測試中的`assert in set`。

### G2 Application

- repository-shaped summary帶`severity=None`或legacy placeholder，輸出仍來自registry。
- unknown definition與source-domain drift固定typed 422。
- list與detail共用enrichment；不增加query次數與任何write。

### G3 Backend routes

- Anomalies list/detail、Import Warning tasks的success/negative/auth/pagination。
- focused disposable MySQL closed-loop證明真repository→Application→route輸出合法severity。
- query前後projection row／workflow events／outbox計數不變。

### G4 Frontend compatibility

- 不修改React production；重跑Phase2D四檔focused Vitest。
- 嚴格decoder仍拒絕空白／unknown enum。
- 不得更新snapshot或fixture讓壞payload通過。

### G5 Static/full regression

```powershell
cd D:\project\Labor_union
.\.venv\Scripts\python.exe -m pytest tests/test_anomaly_registry_router.py tests/test_import_warning_tracking_api.py tests/test_import_warning_tracking_api_client.py --basetemp .pytest_tmp/phase2d-h-contract -q
.\.venv\Scripts\python.exe -m pytest tests/test_anomaly_closed_loop_disposable_mysql_e2e.py --basetemp .pytest_tmp/phase2d-h-mysql -q
cd ui_react
npx vitest run src/tests/anomaly_query_client.test.ts src/tests/anomaly_query_adapter.test.ts src/tests/anomalies_page_real_data.test.tsx src/tests/anomalies_no_fake_mutation.test.tsx
npm run build
npm run lint
npm test -- --reporter=dot
```

任何既有full-suite failure須誠實記錄；不得因不屬本包就宣稱G5 PASS。

### G6 Browser

使用使用者已完成TOTP登入的真Chrome Session：

1. 進入 `#anomalies`；
2. Network中兩個核准GET皆200；
3. anomaly cards／KPI與Import Warning tasks進DOM；
4. 不再出現severity schema mismatch；
5. Claim／Resolve等控制保持disabled；0 non-GET；
6. 不讀取、記錄、輸出token、帳密或TOTP。

### G7 Evidence

由同一 Integration Owner在最新working tree fresh重跑後寫：contract matrix、candidate inventory、
verification receipt、browser receipt、open findings、evidence summary。舊Phase2D receipt不得重用。

## 5. Gates

| Gate | PASS condition | Fail condition |
|---|---|---|
| G0 Scope | exact approval、dirty baseline、只改write set | 未核准／越界 |
| G1 Contract | Domain enum→Pydantic/OpenAPI逐欄閉合 | `str`或未裁決值 |
| G2 Application | registry衍生severity、list/detail一致 | placeholder穿透／猜值 |
| G3 Backend | focused＋真composition tests通過 | fake-only、query寫入 |
| G4 Frontend | strict decoder不變且focused PASS | 放寬Zod／改UI猜值 |
| G5 Regression | build/lint/full suites fresh且如實記錄 | failure或warning被隱藏 |
| G6 Runtime | 真Session Network→DOM PASS、0 mutation | happy-dom／curl替代 |
| G7 Evidence | current receipts與索引一致 | 舊數字／自報VICTORY |

原則上只有G0–G7全部PASS才可機械完成。2026-08-17使用者另行明確裁決：不建立額外測試DB，
以既有DB的唯讀UI結果完成本次public query contract任務。故本包依人工closeout標記`completed`，
但disposable engine gate必須維持`NOT_RUN（人工豁免）`，不得宣稱G3 PASS或推進Anomalies mutation。

### 5.1 2026-08-16 execution result

候選production與focused contract tests已完成；G1/G2/G4 PASS。最終focused backend為34 passed，
Phase 2D focused frontend為59 passed，full React為510 passed，build PASS。真Chrome已在重啟正確FastAPI
後完成兩query family→DOM與zero-mutation驗收。disposable MySQL E2E未執行，依2026-08-17人工裁決
記為`NOT_RUN（人工豁免）`；既有MasterLayout lint warnings與相鄰owner findings均保留。證據見
`03_追蹤清單與證據/evidence/PROV-20260816-react-admin-phase2d-backend-public-contract-hardening/`。

## 6. DB Gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | PASS | exact scope明列0 DB |
| Change inventory | PASS | schema-only／system-seed／business-row-backfill／destructive全為0 |
| Static release gate | NOT_RUN | 無migration release |
| Descriptor gate | NOT_RUN | 無DB object變更 |
| Read-only plan gate | NOT_RUN | 不需migration plan |
| Engine verification gate | NOT_RUN | disposable test僅驗既有contract |
| Developer acceptance gate | NOT_RUN | 不操作既有資料庫 |

總結：`DB_CHANGE_NOT_READY`。

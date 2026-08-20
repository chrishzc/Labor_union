---
doc_type: work-package
declared_status: superseded
identity: PROV-20260817-react-admin-phase3b-q-r-scheduling-current-query-react
date: 2026-08-17
owner: Scheduling React Integration Owner
domain: Scheduling
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260816-react-admin-phase3b1-staff-contract-hardening-selector-amendment PASS; PROV-20260817-react-admin-phase3b-q-h-scheduling-current-public-query PASS
authority: awaiting-exact-human-approval
approval_required: 核准此 exact Phase 3B-Q-R Scheduling Current Query React Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
successor: PROV-20260817-react-admin-scheduling-query-page-slice-work-package
---

# Phase 3B-Q-R：Scheduling Current Query React 接線工作包

> 2026-08-17：依逐頁精簡遷移裁決，backend query與React接線由同一Scheduling Query Page-Slice承接；
> 本文件未曾取得exact核准，現標`superseded`。

## 0. Scope

Browser/DOM驗收只能使用`validation/scenarios/react_admin_scheduling_current_query.json`與
`validation/ui_business_workflows/part_09_scheduling/`；component fixture不得代替。

以既有typed `GET /api/v1/scheduling/staff/{staff_id}/current-calendar`取代Scheduling甘特頁的
`MOCK_STAFF`、`MOCK_ORDERS`、embedded schedule與前端日期投影。保留月份、搜尋、filter、legend、staff
timeline與Drawer外觀；本包完全query-only，不啟用任何mutation。

## 1. Exact write set

- `ui_react/src/api/scheduling/scheduling_current_schemas.ts`（new）
- `ui_react/src/api/scheduling/scheduling_current_errors.ts`（new）
- `ui_react/src/api/scheduling/scheduling_current_client.ts`（new）
- `ui_react/src/adapters/scheduling/scheduling_current_adapter.ts`（new）
- `ui_react/src/pages/SchedulingPage.tsx`
- `ui_react/src/pages/SchedulingPage.css`
- `ui_react/src/tests/fixtures/scheduling/scheduling_current_contract_fixtures.ts`（new）
- `ui_react/src/tests/scheduling_current_client.test.ts`（new）
- `ui_react/src/tests/scheduling_current_adapter.test.ts`（new）
- `ui_react/src/tests/scheduling_current_page.test.tsx`（new）
- `ui_react/src/tests/scheduling_no_fake_mutation.test.tsx`
- `validation/scenarios/react_admin_scheduling_current_query.json`（new）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3b-q-r-scheduling-current-query-react/`（Integration Owner only）

本包重用Phase3B1 `staff_directory` client，不得建立第二個Staff selector或把完整staff facts複製進Scheduling
fixture。禁止修改backend、shared transport/Auth、package/lockfile與其他pages。

## 2. Query contract與request budget

1. route response依`SchedulingCurrentProjectionView` strict decode；日期、assignment lifecycle、occupancy kind、
   case version與projection token只顯示server值。
2. 首次進tab只載入一頁去敏Staff summaries；只對目前已載入且可見staff發current-calendar GET，最多20筆；
   分頁後才可追加下一批，禁止無界N+1。
3. 月份／range切換abort舊generation並丟棄stale response；每個staff row的error獨立呈現，不以空資料冒充成功。
4. duplicate staff、duplicate calendar date、range mismatch、projection token格式錯誤或nested extra欄位均fail closed。
5. filtering只作用於已載入server view並標示loaded scope；不得把loaded count稱為全系統總數。
6. UI不得重算end date、buffer、coverage、eligibility、payroll或ghost availability；缺typed projection的slot顯示unavailable。

## 3. Acceptance／anti-fake gates

- G0須保存`SchedulingPage.tsx/.css`與`scheduling_no_fake_mutation.test.tsx`的fresh baseline，證明同批其他
  Scheduling presentation writer為0；本包freeze後任何page/CSS/test drift固定`BASE_DRIFT`並重新盤點。
- client/adapter tests需由live Pydantic欄位矩陣產生兩組變動sentinel，證明DOM跟隨server而非固定literal。
- success、empty、partial-row error、401/403/404/409/503、timeout、abort、range switch及session expiry均覆蓋。
- production dependency closure為0 `mockData`、0 inline正式樣本、0 `alert/confirm/prompt`與0 non-GET。
- 既有四tabs、Drawer與mutation controls保留；所有未核准actions native disabled。
- 真TOTP browser以controlled staff/range驗Network→DOM、reload與Streamlit同range oracle；不要求query forward-write。
- build/lint/full focused React、UTF-8、檔頭、diff、PII/secret與write-set audit通過。

## 4. DB gate

未核准Scope `BLOCKED`；核准後Scope／Change inventory `PASS`（query-only、0 DB write），其餘`NOT_RUN`；
結論固定`DB_CHANGE_NOT_READY`。

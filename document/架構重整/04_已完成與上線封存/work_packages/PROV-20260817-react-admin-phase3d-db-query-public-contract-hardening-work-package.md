---
doc_type: work-package
declared_status: completed
identity: PROV-20260817-react-admin-phase3d-db-query-public-contract-hardening
date: 2026-08-17
owner: Access / Data Browser
domain: Access
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance PHASE3_SCENARIO_LINEAGE_METADATA_READY; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase3d-data-browser-part-identity-decision PASS
approval_required: 核准此 exact Phase 3D-DB-H Work Package
authority: 2026-08-22 human exact approval
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: not-applicable
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Phase 3D-DB-H：Data Browser public query contract hardening工作包

## Business scenario與限制

Controlled input固定來自`validation/scenarios/react_admin_data_browser_query.json`與其去敏
fixture/expected。Data Browser UI Part identity尚未裁決，本backend包不建UI checklist目錄。

系統管理員只能查詢核准allowlist內的去敏資料快照；Query唯讀且fail closed。本包不啟用source correction、
不接受任意table/SQL、不輸出raw row，也不變更DB schema。

## Exact production write set

- `api/schemas/data_browser.py`
- `api/routes/data_browser_admin.py`
- `subsystems/access/data_browser_maintenance.py`
- `infrastructure/mysql/data_browser_query_repository.py`（new）

## Exact test／integration write set

- `tests/test_data_browser_admin_route.py`
- `tests/test_data_browser_query_contract.py`（new）
- `tests/test_data_browser_privacy.py`（new）
- `tests/test_data_browser_query_disposable_mysql_e2e.py`（new，只有受控MySQL時執行）
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md`（Integration Owner only）
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`（Integration Owner only）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3d-db-query-hardening/`（new）

## Contract

1. allowlist以stable source identity枚舉；unknown/disabled source 404或403 typed error，不接受任意identifier。
   G1必須凍結既有六個React tab各自對應的canonical source identity；目前前端`*_archive` literals不能作權威。
2. 明確cursor/limit與穩定排序；typed column descriptor、typed/redacted cells與rows，不使用public
   `Dict[str, Any]`、`z.record()`或raw JSON。
   契約必須凍結cursor sort key、row identity及column/redaction policy，並二選一：list row已包含完整masked
   detail，或新增bounded detail GET。選後者時須先把exact route/schema/repository/test paths加入本包並重新核准，
   同時凍結404、abort、reload與每次click最多一個detail GET的request budget。
3. 電話、身分證、銀行資料、token、Authorization與其他敏感欄位由server遮罩；masking/schema drift失敗即整筆fail closed。
4. `require_system_admin`、`X-Correlation-ID`與Global typed error envelope涵蓋401/403/404/422/internal。
5. query path為0 commit、0 mutation、0 source-correction call；PATCH維持410。
6. 現存raw source-correction Preview／Apply不屬本包且使整個Data Browser boundary保持not-ready；本包只能
   宣稱masked query slice ready。`PROV-20260817-react-admin-phase3d-db-source-correction-policy-gap`未裁決前，
   source-correction routes/tests不得被query evidence靜默吸收或標READY。

## Acceptance

- route/application/repository逐欄矩陣與negative decoding tests。
- scenario同時覆蓋unknown source、schema/masking drift、detail identity mismatch，以及PII不得進list/detail/copy view。
- disposable MySQL證明allowlist、cursor、stable order、masking及0 write；無engine evidence只能local-validated。
- raw row/PII/secret scan、strict UTF-8、focused/full pytest、diff check通過。
- React wiring與entry cutover另由後續bounded WP處理。

## Completion／DB gate（2026-08-22）

六個canonical sources凍結為`orders`、`clients`、`staff`、`beclass_intake`、`hcm_review`、`bank_facts`。
cursor以各source primary key ascending排序：orders為`case_no`，其餘為positive integer `id`；row identity
分別為case number或decimal id string。選擇list row內含完整masked detail，不新增detail GET。unknown source／invalid
cursor在SQL前fail closed；Query只執行bounded SELECT，0 commit／rollback／source correction。

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | PASS | 人工exact approval；Part 17 decision PASS；0 schema |
| Change inventory | PASS | schema-only 0、system-seed 0、business-row-backfill 0、destructive 0 |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無DB object變更 |
| Read-only plan gate | NOT_RUN | 無migration |
| Engine verification gate | PASS | 真`lu_test_*`六來源、cursor、masking、SELECT-only／0 commit E2E |
| Developer acceptance gate | NOT_RUN | 無本機schema升級；未操作`union_db` |

結論：`DB_CHANGE_NOT_READY`。

final focused為12 PASS；GET-only API workflow exact 1 operation、25 events、2 successes discarded、0 failures／unique，
raw已刪除。broader scoped為79 PASS／3 FAIL；3項均是非本包MFA環境與AC／Knowledge／LINE fixture缺件，DB-H direct
selectors另重跑2 PASS。strict UTF-8/header、AST、secret/PII pattern scan與diff check PASS。本包只宣稱masked query
slice ready；legacy raw table metadata／source-correction boundary仍not-ready且不被本證據吸收。

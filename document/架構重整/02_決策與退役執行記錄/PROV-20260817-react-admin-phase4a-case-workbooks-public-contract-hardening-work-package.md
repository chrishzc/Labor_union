---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase4a-case-workbooks-public-contract-hardening
date: 2026-08-17
owner: Case Import / Orders Historical Adoption
domain: Case Import / Staff / Orders
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-case-import-workbook-policy-decision PASS
approval_required: 核准此 exact Phase 4A-CW-H Work Package
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer; required-before-writer; preserve-all-user-work
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
activation_blocker: PROV-20260817-case-import-workbook-atomicity-archive-policy-gap
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: not-applicable
---

# Phase 4A-CW-H：BeClass／Staff Historical／Historical Orders workbook public contract工作包

## Scope

分別收斂三個workbook family的typed Preview／Apply／receipt；HCM Historical維持410 retired，不在本包。
三family不得共用generic endpoint/client，亦不得假稱整本檔案atomic。本包只有在人工逐一選定以下三個值後
才可核准：`Client BeClass = WHOLE_WORKBOOK | ROW_ATOMIC_RESUMABLE`、
`Staff Historical = WHOLE_WORKBOOK | ROW_ATOMIC_RESUMABLE`、
`Historical Orders = WHOLE_WORKBOOK | ROW_ATOMIC_RESUMABLE`。

若採`ROW_ATOMIC_RESUMABLE`，必須具有`running → row_committed* → terminal_receipt`，以及
`retryable_interrupted | terminal_failed`分支；同key同canonical workbook只能續跑未terminal rows，
同key不同payload固定conflict。若既有持久層無法表達running/progress，固定`DB_SCOPE_REQUIRED`。

## Exact production write set

- `api/routes/client_beclass_import.py`
- `api/schemas/client_beclass_import.py`
- `subsystems/case_import/client_beclass_workbook_import.py`
- `infrastructure/mysql/client_beclass_workbook_import_repository.py`
- `api/routes/staff_historical_workbook.py`
- `api/schemas/staff_historical_workbook.py`
- `subsystems/case_import/staff_historical_workbook_adoption.py`
- `infrastructure/mysql/staff_historical_workbook_repository.py`
- `infrastructure/mysql/staff_historical_adoption_repository.py`
- `api/routes/historical_order_adoption.py`
- `api/schemas/historical_order_adoption.py`
- `subsystems/orders/historical_order_workbook_import.py`
- `infrastructure/mysql/historical_order_workbook_import_repository.py`
- 每family經裁決所需的source archive port／adapter只可在更新exact write set並重新核准後加入；不得用temp file或log代替。

因此若人工裁決任一family為`archive_required`，本exact工作包維持blocked，必須先修訂production write set並重新
核准；不得一面要求archive、一面讓writer在未授權路徑自行實作。

## Exact test／doc write set

- `tests/test_client_beclass_import_public_contract.py`（new）
- `tests/test_staff_historical_workbook_public_contract.py`（new）
- `tests/test_historical_order_adoption_public_contract.py`（new）
- `tests/test_data_import_workbook_atomicity.py`（new）
- `tests/test_client_beclass_workbook_import.py`
- `tests/test_client_beclass_import_api_client.py`
- `tests/test_staff_historical_workbook_api.py`
- `tests/test_wp85_historical_order_workbook_disposable_mysql_e2e.py`
- `tests/test_historical_order_adoption_router.py`
- `tests/test_beclass_warning_occurrences.py`
- `tests/test_historical_order_warning_occurrences.py`
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md`（Integration Owner only）
- `document/架構重整/01_規格基線/01_Orders_Domain.md`（Integration Owner only）
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`（Integration Owner only）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase4a-case-workbooks/`（new）

## Gates

1. 三family各自凍結逐欄Pydantic matrix、file identity、row source identity/fingerprint、target expected version、
   identity/warning disposition、PII class、archive policy與receipt selector。
2. 人工明確裁決每family為whole-workbook atomic或row-atomic with explicit partial disposition；不能靠測試猜。
3. Preview 0 write；Apply fresh validation；所有fingerprint嚴格小寫64-hex；same-key replay/conflict、stale與typed errors。
4. 任一partial path具有counts conservation、review rows、root rows與rollback/recovery receipt。
5. disposable MySQL驗Preview後root/identity/version漂移、同檔兩列競爭同root、row N成功後crash/recovery、
   duplicate root/warning/outbox零新增，以及實際root、warning、receipt與replay。
6. 若單一outer UoW需要超出write set，固定`SCOPE_EXPANSION_REQUIRED`，禁止偷偷改shared UoW/DB。
7. 每family必須裁決`archive_required`或`no_raw_archive_with_formal_port_amendment`，並凍結retention owner、
   read authorization、delete/compensation/replay；receipt/evidence不得含原檔名、path、raw row或完整PII。

DB Gate：Scope `BLOCKED`。policy推薦的三family皆為`archive_required`，但本包尚未擁有archive/recovery
persistence port／adapter，且既有tables能否表達running/progress/recovery尚未通過static inventory；必須先修訂
exact write set並重新核准。Change inventory `PASS`（目前0 schema/seed/backfill/destructive），其餘`NOT_RUN`；
`DB_CHANGE_NOT_READY`。

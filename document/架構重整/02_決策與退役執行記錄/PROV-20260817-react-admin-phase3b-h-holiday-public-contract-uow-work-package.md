---
doc_type: work-package
declared_status: completed
identity: PROV-20260817-react-admin-phase3b-h-holiday-public-contract-uow
date: 2026-08-17
owner: Scheduling
domain: Scheduling
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance PHASE3_SCENARIO_LINEAGE_METADATA_READY; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260816-react-admin-phase3b1-staff-contract-hardening-selector-amendment PASS; PROV-20260817-react-admin-phase3b2-leave-substitution-contract-outer-uow PASS
approval_required: 核准此 exact Phase 3B-H Holiday Work Package
authority: exact-human-approved-2026-08-21
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: not-applicable
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Phase 3B-H：Holiday Query／Preview／Apply public contract與outer-UoW工作包

## Business scenario

Controlled input固定來自`validation/scenarios/react_admin_holiday_policy.json`與其fixture/expected
lineage；`CACHE-READ-PROJECTION-002`只是cache補充，不能代替Holiday mutation scenario。

排班管理員在明確planning horizon查詢、預覽並套用國定假日政策。Holiday facts是Scheduling-owned
versioned root facts；`is_double_pay_default`只是相容參考，不能由UI推導薪資規則。

## Exact production write set

- `api/schemas/holidays.py`
- `api/routes/holidays.py`
- `subsystems/scheduling/holiday_maintenance.py`
- `subsystems/scheduling/holiday_query_cache.py`
- `subsystems/scheduling/holiday_calendar_query.py`
- `infrastructure/mysql/scheduling_holiday_query.py`

## Exact test／integration write set

- `tests/test_holiday_router.py`（new）
- `tests/test_holiday_public_contract.py`（new）
- `tests/test_admin_command_workflows.py`
- `tests/test_holiday_query_cache_boundary.py`
- `tests/test_holiday_preview_apply_disposable_mysql_e2e.py`（new）
- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md`（Integration Owner only）
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`（Integration Owner only）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3b-h-holiday/`（new）

## Contract

G1 必須先產出並凍結 Query / Preview / Apply / Receipt / Error 逐欄矩陣，列出 exact Pydantic
path、required/nullable、version、fingerprint、planning horizon 與顯示分級；不接受 raw dict、
optional catch-all 或「至少」字段清單。

### G1 frozen public contract matrix（2026-08-21 人工核准後）

| Surface | Exact Pydantic path | Required／nullable | Version／fingerprint／horizon | 顯示分級 |
|---|---|---|---|---|
| Query | `HolidayCalendarView` → `HolidayHorizonView` + `HolidayRowView[]` | ranged Query 的 `from_date/to_date`成對；rows closed/non-null | `calendar_version`、`source_identity`、完整 planning horizon | authoritative read projection |
| Preview input | `HolidayPreviewRequest` | action/date required；upsert name required；legacy單日request由server正規化成單日horizon | 不接受client version；server fresh-read產生 | command candidate |
| Preview output | `HolidayPreviewView` → `HolidayPreviewCommandView` | before nullable；其餘required | command帶`expected_calendar_version`、horizon；output帶`preview_fingerprint` | preview-only／0 write |
| Apply input | `HolidayApplyRequest` | expected version、fingerprint、trimmed reason required；headers另要求idempotency/correlation | 必須與Preview同horizon/version/fingerprint | mutation request |
| Receipt | `HolidayReceiptView` | 全部required | previous/resulting version、preview fingerprint、receipt key、horizon | committed outcome；與re-query分離 |
| Errors | `GlobalTypedErrorResponseView`（Global handler） | stable code required；field errors closed | correlation由Global boundary覆寫為request identity | validation/not_found/conflict/unavailable/internal |

無參數`GET /api/v1/holidays`只保留既有Streamlit typed-row-list compatibility；Phase3B-H-R
React與正式驗收必須使用成對horizon Query。不得從相容路徑推導Apply version。

1. Query明確接受`from_date/to_date`；輸出typed HolidayRow/CalendarView與calendar version/source identity。
2. Preview零寫入；Query/Preview/Apply使用同一planning horizon與versioned Holiday Query port。
3. Apply fresh-read並以現有`SchedulingHolidayQuery(..., lock=True)`鎖定完整horizon，驗fingerprint與expected version。
4. reason trim後1–500；Apply要求Idempotency-Key與X-Correlation-ID；同key同payload replay原receipt，
   不同payload回conflict。
5. Receipt與re-query分離；cache只作read projection，invalidate失敗不得把已commit Domain結果偽造成失敗。
6. stable errors至少含`holiday_calendar_unavailable`、`stale_preview`、`idempotency_key_conflict`、
   `holiday_not_found`，全部使用Global typed envelope。
7. 僅一個outer UoW/commit owner；不得hidden commit、前端日期／雙倍薪推導或raw dict public response。
8. Query/Preview 必須0 commit；Apply 的 fact/version/receipt/cache-invalidation intent 交易邊界必須
   精確凍結。Cache refresh 是 commit 後 observation，不得 hidden commit 或改寫 receipt outcome。

## Acceptance

- `api/routes/holidays.py`使用既有`require_admin`的enabled-principal policy，不保留
  `require_system_admin`造成的角色差異；root-only例外不得擴張到Holiday。
- route negative tests：auth、range、reason、fingerprint、stale、replay/conflict、timeout/internal。
- TestClient 真實觸發 malformed body/query/header 並驗 Global envelope；不只測 route helper。
- disposable MySQL證明Preview 0 write、horizon lock、Apply atomicity、replay及cache failure post-commit語意。
- negative scan與transaction tests必須證明現行`AdminCommandRepository`／holiday repository hidden commit已消除；
  任一repository commit/rollback或第二UoW都fail closed。
- 若現有table無法提供要求的version/horizon exactness，固定`DB_SCOPE_REQUIRED`並另立DB WP，不能本包加schema。
- React Scheduling wiring另案；本包完成不解鎖Phase5 entry。

## DB gate

| Gate | Status | Evidence／reason |
|---|---|---|
| Scope gate | PASS | 2026-08-21 使用者兩次明確核准exact phrase；只使用既有holiday／admin_command_receipts tables |
| Change inventory | PASS | schema-only=0、system-seed=0、business-row-backfill=0、destructive=0；runtime Apply僅改單一holiday row並新增immutable receipt，cache invalidation為commit後記憶體 observation |
| Static release gate | NOT_RUN | 無schema release |
| Descriptor gate | NOT_RUN | 無owned-object變更；若現表不足則DB_SCOPE_REQUIRED |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | PASS | `lu_test_phase3bh_20260821a` fresh bootstrap；Preview 0 write、uncommitted Apply外部不可見、rollback 0/0、commit 1 holiday/1 receipt、same-key replay exact；finally cleanup後schema count=0 |
| Developer acceptance gate | NOT_RUN | 不操作既有資料庫 |

總結固定`DB_CHANGE_NOT_READY`。

## Completion record（2026-08-21）

- exact approval：使用者兩次明確輸入`核准此 exact Phase 3B-H Holiday Work Package`。
- closed Pydantic Query／Preview／Apply／Receipt、Global typed errors與`require_admin`已接線。
- Apply 只有route持有commit/rollback；repository與subsystem沒有hidden transaction owner。
- existing Streamlit無參數GET／單日Preview相容保留；React ranged horizon另由Phase3B-H-R施工。
- focused 29 PASS；disposable MySQL 1 PASS；api-test-workflow exact GET 2 success／0 failure／0 unique。
- 本包0 schema／seed／backfill／destructive、0既有DB write；schema gates未觸發，故不宣稱DB change ready。

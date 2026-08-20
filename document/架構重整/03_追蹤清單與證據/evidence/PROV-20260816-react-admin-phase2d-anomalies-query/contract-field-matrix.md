# Phase 2D Integration Contract Field Matrix (SUPERSEDED BY PHASE 2D-H CANDIDATE)

**Status**: SUPERSEDED_BY_PHASE2D_H_CANDIDATE_AWAITING_RUNTIME  
**Timestamp**: 2026-08-16T19:32:00+08:00  
**Baseline Commit**: `8615225481c8f72a9629289285516189b270cb36` (branch: `main`)  
**Scope**: Read-Only Query Integration for Anomalies & Import Warning Tracking

> Phase 2D-H候選已將severity由Domain registry衍生，並把severity、workflow與tracking status收斂為
> Pydantic/OpenAPI封閉enum；focused backend 34 passed。canonical freeze現由Phase 2D-H evidence目錄擁有；
> 本舊矩陣僅同步欄位處置，不再作freeze owner。真Chrome尚未取得200→DOM，前端decoder維持原strict集合。

---

## 1. Approved Production Endpoints
1. `GET /api/v1/anomalies?include_snapshot=false`
   - Controller: `api/routes/anomaly_registry.py::query_anomalies`
   - Response Model: `BaseResponse[list[AnomalySummaryView]]` (`api/schemas/anomaly_registry.py`)
   - Mandatory Query Params: `include_snapshot=false`, `active_only=true` (or boolean), `limit` (1..200), `offset` (>=0)
2. `GET /api/v1/import-warning-tracking/tasks`
   - Controller: `api/routes/import_warning_tracking.py::query_tasks`
   - Response Model: `BaseResponse[list[ImportWarningTaskView]]` (`api/schemas/import_warning_tracking.py`)
   - Mandatory Query Params: `active_only=true` (or boolean), `limit` (1..200), `offset` (>=0)

*All other endpoints, mutations (POST/PUT/DELETE/PATCH), claim/resolve endpoints, detail endpoints returning raw dicts, and scan/repair endpoints are strictly OUT_OF_SCOPE.*

---

## 2. Field-by-Field Mapping & UI Slot Disposition Matrix

| UI Slot / Control ID | UI Section | Mock Field | Live Endpoint | Live JSON Path | Live Type | Disposition | Render / Transformation Rule |
|---|---|---|---|---|---|---|---|
| `anomalies.kpi.critical` | KPI Grid | `criticalCount` | `GET /api/v1/anomalies` | `data[].severity` | `AnomalySeverity` | `READY_TYPED_DISPLAY_RUNTIME_PENDING` | 只計`blocking`；未知／空白由backend與Zod fail closed |
| `anomalies.kpi.warning` | KPI Grid | `warningCount` | `GET /api/v1/anomalies` | `data[].severity` | `AnomalySeverity` | `READY_TYPED_DISPLAY_RUNTIME_PENDING` | 只計`warning`；未知／空白由backend與Zod fail closed |
| `anomalies.kpi.open` | KPI Grid | `openCount` | `GET /api/v1/anomalies` | `data[].workflow_status` | `AlertWorkflowStatus` | `READY_TYPED_DISPLAY_RUNTIME_PENDING` | 只計`open` |
| `anomalies.kpi.claimed` | KPI Grid | `claimedCount` | `GET /api/v1/anomalies` | `data[].workflow_status` | `AlertWorkflowStatus` | `READY_TYPED_DISPLAY_RUNTIME_PENDING` | 只計`claimed` |
| `anomalies.filter.category` | Category Bar | `categories` | `GET /api/v1/anomalies` | `data[].source_domain` | string | `READY_TYPED_DISPLAY` | Map: `case_import`/`finance_import` -> 匯入資料; `line`/`line_integration`/`matching` -> 媒合推播; `scheduling`/`assignments` -> 排班調度; `client_finance` -> 客戶帳務; `staff_payables`/`payroll` -> 月嫂薪資; `government_subsidy` -> 政府補助; other -> 其他 |
| `anomalies.filter.status` | Status Pills | `selectedStatusFilter` | `GET /api/v1/anomalies` | `data[].workflow_status` | string | `READY_TYPED_DISPLAY` | Client filter for loaded anomalies: `all` \| `open` \| `claimed` \| `resolved` |
| `anomalies.card.code` | Anomaly Card | `code` | `GET /api/v1/anomalies` | `data[].definition_code` | string | `READY_TYPED_DISPLAY` | Render string as-is (e.g. `SCHEDULE-001`) |
| `anomalies.card.title` | Anomaly Card | `title` | `GET /api/v1/anomalies` | N/A | N/A | `BACKEND_GAP` | Render `"後端尚未提供 typed 顯示摘要"` |
| `anomalies.card.severity` | Anomaly Card | `severity` | `GET /api/v1/anomalies` | `data[].severity` | `AnomalySeverity` | `READY_TYPED_DISPLAY_RUNTIME_PENDING` | 直接顯示server enum；不得猜測 badge |
| `anomalies.card.status` | Anomaly Card | `status` | `GET /api/v1/anomalies` | `data[].workflow_status` | `AlertWorkflowStatus` | `READY_TYPED_DISPLAY_RUNTIME_PENDING` | 直接顯示server enum |
| `anomalies.card.related_entity` | Anomaly Card | `relatedEntity` | `GET /api/v1/anomalies` | N/A | N/A | `BACKEND_GAP` | Render `"後端尚未提供"` (`source_identity` internal only) |
| `anomalies.card.description` | Anomaly Card | `description` | `GET /api/v1/anomalies` | N/A | N/A | `BACKEND_GAP` | Render `"後端尚未提供 typed 顯示摘要"` |
| `anomalies.card.suggested_action` | Anomaly Card | `suggestedAction` | `GET /api/v1/anomalies` | N/A | N/A | `BACKEND_GAP` | Render `"後端尚未提供"` |
| `anomalies.card.claim` | Anomaly Card | button `🔵 認領此案` | N/A | N/A | N/A | `MUTATION_LOCKED` | Keep slot, native `disabled`, `data-control-id="anomalies.card.claim"`, no-op |
| `anomalies.card.drawer_open` | Anomaly Card | button `排查處置抽屜 ➔` | N/A | N/A | N/A | `PRESENTATION_UI_STATE` | Opens Drawer with selected anomaly summary |
| `anomalies.drawer.overview_meta` | Drawer | metadata box | `GET /api/v1/anomalies` | `source_domain`, `source_version`, `workflow_version`, `predicate_active` | string, int, int, bool | `READY_TYPED_DISPLAY` | Displays domain, versions, predicate active status |
| `anomalies.drawer.root_evidence` | Drawer | `triggerEvidence` | N/A | N/A | N/A | `BACKEND_GAP` | Render `"後端 typed detail/recovery contract 尚未開放"` |
| `anomalies.drawer.recovery_action` | Drawer | navigation button | `GET /api/v1/anomalies` | `data[].staff_calendar_navigation` | `{staff_id, target_date} \| null` | `READY_TYPED_DISPLAY` | If navigation exists, link to `#scheduling` (date/staff context); else `"後端 typed detail/recovery contract 尚未開放"` |
| `anomalies.drawer.resolve_reason` | Drawer | textarea | N/A | N/A | N/A | `MUTATION_LOCKED` | Keep slot, native `disabled`, `data-control-id="anomalies.drawer.resolve-reason"` |
| `anomalies.drawer.resolve` | Drawer | button `確認排除異常` | N/A | N/A | N/A | `MUTATION_LOCKED` | Keep slot, native `disabled`, `data-control-id="anomalies.drawer.resolve"`, no-op |
| `anomalies.import_warnings.lane` | Import Warnings | N/A | `GET /api/v1/import-warning-tracking/tasks` | `data[].owning_lane` | string | `READY_TYPED_DISPLAY` | Lane badge (HCM, BeClass, Historical Orders, Finance) |
| `anomalies.import_warnings.code` | Import Warnings | N/A | `GET /api/v1/import-warning-tracking/tasks` | `data[].logical_code` | string | `READY_TYPED_DISPLAY` | Logical code badge (e.g. `HCM-FIELD-001`) |
| `anomalies.import_warnings.field` | Import Warnings | N/A | `GET /api/v1/import-warning-tracking/tasks` | `data[].field_path` | string | `READY_TYPED_DISPLAY` | Target field path (e.g. `身分證字號`) |
| `anomalies.import_warnings.subject` | Import Warnings | N/A | `GET /api/v1/import-warning-tracking/tasks` | `data[].masked_subject` | string | `READY_TYPED_DISPLAY` | Masked subject (e.g. `A12****789`) |
| `anomalies.import_warnings.issue_codes` | Import Warnings | N/A | `GET /api/v1/import-warning-tracking/tasks` | `data[].issue_codes` | `string[]` | `READY_TYPED_DISPLAY` | Issue code tags |
| `anomalies.import_warnings.status` | Import Warnings | N/A | `GET /api/v1/import-warning-tracking/tasks` | `data[].tracking_status` | `ImportWarningTrackingStatus` | `READY_TYPED_DISPLAY_RUNTIME_PENDING` | 六個Domain enum值；unknown由backend與Zod fail closed |
| `anomalies.import_warnings.version` | Import Warnings | N/A | `GET /api/v1/import-warning-tracking/tasks` | `data[].tracking_version` | integer >= 1 | `READY_TYPED_DISPLAY` | Version badge (e.g. `v1`) |
| `anomalies.import_warnings.evidence_ref` | Import Warnings | N/A | `GET /api/v1/import-warning-tracking/tasks` | `data[].evidence_reference` | `string \| null` | `READY_TYPED_DISPLAY` | Evidence reference string if present |
| `anomalies.import_warnings.message` | Import Warnings | N/A | `GET /api/v1/import-warning-tracking/tasks` | `data[].display_message` | string (1..200) | `READY_TYPED_DISPLAY` | Display message text |
| `anomalies.import_warnings.navigation` | Import Warnings | N/A | `GET /api/v1/import-warning-tracking/tasks` | `data[].navigation_action` | enum (5 actions) \| null | `READY_TYPED_DISPLAY` | Link to `#data-import` if present |

---

## 3. Strict Decoder & Safety Rules
1. **Zod Strictness**:
   - `anomaly_query_schemas.ts` must use `z.object({...}).strict()`.
   - Forbidden: `z.any`, `z.unknown`, `z.record`, `.passthrough()`, `.catch()`, `.default()`, `.coerce`, `.preprocess()`, `.transform()`, `as any`, `unknown as`.
2. **Error Taxonomy**:
   - `ANOMALY_QUERY_UNAUTHENTICATED` (401)
   - `ANOMALY_QUERY_FORBIDDEN` (403)
   - `ANOMALY_QUERY_VALIDATION_ERROR` (422 / schema mismatch)
   - `ANOMALY_QUERY_SERVICE_UNAVAILABLE` (503 / 500)
   - `ANOMALY_QUERY_NETWORK_ERROR` (fetch failure)
   - `ANOMALY_QUERY_ABORTED` (AbortController)
3. **No Mutations**:
   - Zero POST / PUT / PATCH / DELETE calls.
   - Zero alert / confirm / prompt dialogs.
   - Zero client-side simulated mutations.
4. **File Ownership by Lane**:
   - **Lane B (Backend Test Writer)**: `tests/test_anomaly_registry_router.py`, `tests/test_import_warning_tracking_api.py`
   - **Lane C (Frontend Client Writer)**: `ui_react/src/api/anomalies/*`, `ui_react/src/tests/fixtures/anomalies/*`, `ui_react/src/tests/anomaly_query_client.test.ts`
   - **Lane D (Frontend Adapter Writer)**: `ui_react/src/adapters/anomalies/*`, `ui_react/src/tests/anomaly_query_adapter.test.ts`
   - **Lane E (Frontend Presentation Writer)**: `ui_react/src/pages/AnomaliesPage.tsx`, `ui_react/src/pages/AnomaliesPage.css`, `ui_react/src/tests/anomalies_page_real_data.test.tsx`, `ui_react/src/tests/anomalies_no_fake_mutation.test.tsx`

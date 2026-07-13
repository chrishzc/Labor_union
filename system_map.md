# Master System Map (Version 53.0)

> **ADAD 分層子地圖架構 (Sub-Maps Architecture)**:
> 1. **UI 介面層子地圖**: [`ui/ui_system_map.yaml`](file:///c:/Users/chris/Desktop/project/Labor_union/ui/ui_system_map.yaml) | [`ui/ui_system_map.md`](file:///c:/Users/chris/Desktop/project/Labor_union/ui/ui_system_map.md)
> 2. **Services 服務層子地圖**: [`services/services_system_map.yaml`](file:///c:/Users/chris/Desktop/project/Labor_union/services/services_system_map.yaml) | [`services/services_system_map.md`](file:///c:/Users/chris/Desktop/project/Labor_union/services/services_system_map.md)
> 3. **API 服務層子地圖**: [`api/api_system_map.yaml`](file:///c:/Users/chris/Desktop/project/Labor_union/api/api_system_map.yaml) | [`api/api_system_map.md`](file:///c:/Users/chris/Desktop/project/Labor_union/api/api_system_map.md)

---

## Environment
- State: validated
- Services: [db]

---

### 🏛️ 全局巨觀架構 (Master Hierarchy)

##### Module: Main
- Source: `main.py`
- Type: entrypoint
- Description: 系統主程式入口。
- Observability: not_required

##### Module: UILayer
- Type: sub_system_layer
- State: `validated`
- Source: `ui/app.py`
- Description: 使用者介面層，包含 Streamlit 各個頁面與元件。
- Observability: not_required

##### Module: APILayer
- Type: sub_system_layer
- State: `validated`
- Source: `api/main.py`
- Description: FastAPI 應用程式介面層，負責處理 HTTP 請求。
- Observability: not_required

##### Module: ServicesLayer
- Type: sub_system_layer
- State: `validated`
- Source: `services/db_service.py`
- Description: 後端服務與資料庫操作層，處理核心商業邏輯與資料庫存取。
- Observability: not_required

##### Module: GenerateFakeData
- Source: scripts/generate_fake_data.py
- Type: script
- Description: 假資料統一生成器。採用「時間軸推進演算法 (Sequential Timeline Generator)」，為每位月嫂維護獨立時間軸游標，確保同月嫂的案件排班前後接續、絕對獨佔且零重疊 (Zero Overlap)。
- Observability: not_required
- Complexity: medium
- Input:
  - reference_date: optional YYYY-MM-DD generation baseline
  - seed: optional deterministic integer
  - scenario_counts: optional lifecycle scenario count overrides
- Output:
  - generation_summary: counts by lifecycle, payment state, and boundary fixture
  - validation_result: pass or explicit invariant failures
- Algorithm:
  - Accept a configurable `reference_date` and deterministic random seed; use the same reference date for all lifecycle calculations.
  - Generate clients with unique `case_no`, then generate orders from a scenario matrix: new inquiry, matching in progress, deposit received awaiting service, in service, completed awaiting settlement, closed, and cancelled.
  - For new inquiries, enforce `status = 洽談中`, no `staff_id`, no actual service dates, no matching or schedule rows, and `start_date >= reference_date + 14 days`.
  - For matching scenarios, generate 2–5 matching records with a mixture of pending, declined, and accepted replies, without assigning a final staff member or generating a schedule.
  - For assigned scenarios, generate staff assignment, payments, and non-overlapping schedules only when the lifecycle state allows them; derive actual dates only for in-service or completed cases.
  - Generate notes from scenario-specific templates, including empty, routine administrative, follow-up, and boundary-data notes.
  - Add explicit boundary fixtures for cross-month/year dates, February, weekends, holidays, custom rest dates, adjacent and intentionally conflicting staff schedules, cancellation/refund combinations, partial payments, and missing optional LINE or BeClass data.
  - Validate relational integrity and lifecycle invariants before committing; roll back or fail with a summary if any invariant is violated.
- Invariants:
  - `洽談中` orders have no assigned staff, actual service dates, matching record, or staff schedule, and start at least 14 days after `reference_date`.
  - `服務中` and `訂單完成` orders have an assigned staff member and actual start date; cancelled orders have a cancel reason and no future active schedule.
  - Every payment uses an existing `clients.case_no`; `payments` never contains `order_id`.
  - Normal assigned schedules for one staff member must not overlap; intentionally conflicting fixtures must be explicitly marked as conflict-test data.
  - Generated note content must be compatible with the lifecycle state.
- Verification:
  - case: {"input": {"scenario": "new_inquiry", "reference_date": "2026-07-13"}, "expect": {"status": "洽談中", "staff_id": null, "actual_start_date": null, "min_start_date": "2026-07-27"}}
  - case: {"input": {"scenario": "matching_in_progress"}, "expect": {"staff_id": null, "matching_record_count_min": 2, "schedule_count": 0}}
  - case: {"input": {"scenario": "cancelled"}, "expect": {"cancel_reason_required": true, "future_schedule_count": 0}}

##### Module: FixScheduleConflicts
- Source: `scripts/fix_schedule_conflicts.py`
- Type: script
- Description: 月嫂檔期衝突檢測與自動修復工具。
- Observability: not_required

##### Module: StartScript
- Source: `start.bat`
- Type: script
- Description: 一鍵啟動與部署環境初始化腳本。啟動 Docker、初始化 MySQL、產生並匯入假資料，最後並行啟動 FastAPI 與 Streamlit。
- Observability: not_required
- Invariants:
  - INV-START-01: 腳本必須使用 Python 輪詢確認 MySQL 連線已可被接受，始可開始執行 init_db.py 防止連線逾時崩潰。

##### Module: OnlineScript
- Source: `online.bat`
- Type: script
- Description: 一鍵啟動上線服務腳本。啟動 Docker、等待 MySQL 連線就緒，但不執行資料庫初始化與假資料生成，最後以並行方式啟動 FastAPI、Streamlit 網頁端以及地端檔案自動監控服務 (file_watcher.py)。
- Observability: not_required
- Invariants:
  - INV-START-01: 腳本必須使用 Python 輪詢確認 MySQL 連線已可被接受，始可開始啟動後端與監控服務防止連線逾時崩潰。

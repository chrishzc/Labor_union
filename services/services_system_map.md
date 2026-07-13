# Services Functional Layer Sub-System Map (Version 35.0)

> **Scope**: `services/` 數據服務層  
> **Master Reference**: [`../system_map.yaml`](file:///c:/Users/chris/Desktop/project/Labor_union/system_map.yaml)

---

### 🏛️ Services 功能層模組全覽表

##### Module: DbService
- Source: `services/db_service.py`
- Type: service
- State: `validated`
- Description: 主資料庫與 CRUD 操作服務，提供 `v_order_details` 視窗查詢、36 欄位安全 mapping、safe_int 與 safe_date 防護、`update_order_full_details` 全量更新。
- Invariants:
  - `INV-SVC-03`: `DbService` 必須自動辨識與解析 `notes` / `care_details` 欄位中的 JSON 結構，解開完整 15 項產婦照顧與環境細節欄位，打平注入訂單字典中。

##### Module: RecommendService
- Source: `services/db_service.py::get_recommended_staff_for_order`
- Type: service
- State: `validated`
- Description: 月嫂與客戶條件智慧粗篩比對引擎。比對 `clients.city`/`address` 與 `staff.service_regions` (如香山區/北區/東區)，自動掃描檔期時間衝突 (包含 7 天預留備用期)，並精算匹配分數與推薦列表。
- Invariants:
  - `INV-SVC-05`: 檔期衝突掃描必須將月嫂既有訂單之結束日自動加上 7 天預留備用期 `[start_date, end_date + 7天]`，嚴禁在備用期內重複指派。

##### Module: CalendarService
- Source: `services/db_service.py::calculate_attendance_schedule`
- Type: service
- Description: 排班與行事曆精算引擎。包含出勤天數精算、每週預設排休帶入、動態休假順延計算與國定假日加給計費。
- Invariants:
  - `INV-SVC-01`: `calculate_attendance_schedule` 必須依據 `service_mode` 自動鎖定週休1日 (週日) 或週休2日 (週六日) 的每週排休。
  - `INV-SVC-02`: `custom_holiday_rest_dates` 為 None 時，預設將服務區間內所有國定假日全數納入放假順延。

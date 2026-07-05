# Services Functional Layer Sub-System Map (Version 37.1)

> **Scope**: `services/` 數據服務層  
> **Master Reference**: [`../system_map.yaml`](file:///c:/Users/chris/Desktop/project/Lobar_union---solo/system_map.yaml)

---

### 🏛️ Services 功能層模組全覽表

##### Module: DbService
- Source: `services/db_service.py`
- Type: service
- State: `validated`
- Description: 主資料庫與 CRUD 操作服務，提供 `v_order_details` 視窗查詢、36 欄位安全 mapping、safe_int 與 safe_date 防護，以及 **15大照護細節 (產婦過敏、飲食酒油喜忌、烹煮工具、洗澡水、哺乳方式、三節與胎數) 之 JSON 備註自動解包解析器 (JsonNotesParser Engine)**。
- Invariants:
  - `INV-SVC-03`: `DbService` 必須自動辨識與解析 `notes` / `care_details` 欄位中的 JSON 結構，解開完整 15 項產婦照顧與環境細節欄位，打平注入訂單字典中。
- Todo:
  - [ ] 檢查 global_stats 的全域統計運算邏輯與邊界條件 (INV-SVC-04)

##### Module: CalendarService
- Source: `services/db_service.py::calculate_attendance_schedule`
- Type: service
- Description: 排班與行事曆精算引擎。包含出勤天數精算、每週預設排休帶入、動態休假順延計算與國定假日加給計費。

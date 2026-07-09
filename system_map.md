# Master System Map (Version 53.0)

> **ADAD 分層子地圖架構 (Sub-Maps Architecture)**:
> 1. **UI 介面層子地圖**: [`ui/ui_system_map.yaml`](file:///c:/Users/chris/Desktop/project/Lobar_union---solo/ui/ui_system_map.yaml) | [`ui/ui_system_map.md`](file:///c:/Users/chris/Desktop/project/Lobar_union---solo/ui/ui_system_map.md)
> 2. **Services 服務層子地圖**: [`services/services_system_map.yaml`](file:///c:/Users/chris/Desktop/project/Lobar_union---solo/services/services_system_map.yaml) | [`services/services_system_map.md`](file:///c:/Users/chris/Desktop/project/Lobar_union---solo/services/services_system_map.md)
> 3. **API 服務層子地圖**: [`api/api_system_map.yaml`](file:///c:/Users/chris/Desktop/project/Lobar_union---solo/api/api_system_map.yaml) | [`api/api_system_map.md`](file:///c:/Users/chris/Desktop/project/Lobar_union---solo/api/api_system_map.md)

---

### 🏛️ 全局巨觀架構 (Master Hierarchy)

##### Module: Main
- Source: `main.py`
- Type: entrypoint
- Description: 系統主程式入口。

##### Module: UILayer (Referencing `ui/ui_system_map.yaml`)
- Type: sub_system_layer
- State: `validated`
- Sub-Map: [`ui/ui_system_map.yaml`](file:///c:/Users/chris/Desktop/project/Lobar_union---solo/ui/ui_system_map.yaml)

##### Module: APILayer (Referencing `api/api_system_map.yaml`)
- Type: sub_system_layer
- State: `validated`
- Sub-Map: [`api/api_system_map.yaml`](file:///c:/Users/chris/Desktop/project/Lobar_union---solo/api/api_system_map.yaml)

##### Module: ServicesLayer (Referencing `services/services_system_map.yaml`)
- Type: sub_system_layer
- State: `validated`
- Sub-Map: [`services/services_system_map.yaml`](file:///c:/Users/chris/Desktop/project/Lobar_union---solo/services/services_system_map.yaml)

##### Module: GenerateFakeData
- Source: `scripts/generate_fake_data.py`
- Type: script
- Description: 假資料統一生成器。採用「時間軸推進演算法 (Sequential Timeline Generator)」，為每位月嫂維護獨立時間軸游標，確保同月嫂的案件排班前後接續、絕對獨佔且零重疊 (Zero Overlap)。

##### Module: FixScheduleConflicts
- Source: `scripts/fix_schedule_conflicts.py`
- Type: script
- Description: 月嫂檔期衝突檢測與自動修復工具。

##### Module: StartScript
- Source: `start.bat`
- Type: script
- Description: 一鍵啟動與部署環境初始化腳本。啟動 Docker、初始化 MySQL、產生並匯入假資料，最後並行啟動 FastAPI 與 Streamlit。
- Invariants:
  - INV-START-01: 腳本必須使用 Python 輪詢確認 MySQL 連線已可被接受，始可開始執行 init_db.py 防止連線逾時崩潰。

##### Module: OnlineScript
- Source: `online.bat`
- Type: script
- Description: 一鍵啟動上線服務腳本。啟動 Docker、等待 MySQL 連線就緒，但不執行資料庫初始化與假資料生成，最後以並行方式啟動 FastAPI、Streamlit 網頁端以及地端檔案自動監控服務 (file_watcher.py)。
- Invariants:
  - INV-START-01: 腳本必須使用 Python 輪詢確認 MySQL 連線已可被接受，始可開始啟動後端與監控服務防止連線逾時崩潰。



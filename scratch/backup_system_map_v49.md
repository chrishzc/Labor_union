# Master System Map (Version 49)

> **ADAD 分層子地圖架構 (Sub-Maps Architecture)**:
> 1. **UI 介面層子地圖**: [`ui/ui_system_map.yaml`](file:///c:/Users/chris/Desktop/project/Lobar_union---solo/ui/ui_system_map.yaml) | [`ui/ui_system_map.md`](file:///c:/Users/chris/Desktop/project/Lobar_union---solo/ui/ui_system_map.md)
> 2. **Services 服務層子地圖**: [`services/services_system_map.yaml`](file:///c:/Users/chris/Desktop/project/Lobar_union---solo/services/services_system_map.yaml) | [`services/services_system_map.md`](file:///c:/Users/chris/Desktop/project/Lobar_union---solo/services/services_system_map.md)

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
- Todo:
  - [ ] 審核 Master System Map 的架構內容，進行全面擴充與層級描述精緻化

##### Module: ServicesLayer (Referencing `services/services_system_map.yaml`)
- Type: sub_system_layer
- State: `validated`
- Sub-Map: [`services/services_system_map.yaml`](file:///c:/Users/chris/Desktop/project/Lobar_union---solo/services/services_system_map.yaml)

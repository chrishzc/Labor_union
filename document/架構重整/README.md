# 後端分層架構重整規格

## 目的

本目錄把既有規格書中已確認的業務場景轉成可實作、可測試的
`Global → Domain → Subsystem → Module` 架構契約。

`15`～`18` 已於 2026-08-03 經人工整體確認為正式架構基線。這項確認只授權
Inventory v2；production code、pytest、schema、資料、外部平台及移除工作仍須另立
並人工確認 Work Package。

2026-08-03 已把 `document/文件整併工作區` 中尚未收斂的月結、退款、
BreezySign、LINE、管理權限、部署與治理語彙集中到 `15`～`18`。這四份文件目前是
`approved-architecture-baseline`；核准本身不構成 production mutation 或外部副作用授權。

## 權威順序

1. 人工最新明確裁決。
2. 經人工整體確認的 `15`～`18` 正式規格 package。
3. 既有業務規格、狀態機規則與欄位權威性文件，作為來源追溯。
4. 本目錄其他分層架構文件。
5. live DB schema、production code、API 與 UI 僅代表現況，不得用現況漂移推翻規格。

`15`～`18` 明載的 supersede／裁決條款優先於歷史來源。任何超出已核准 Inventory v2
範圍的實作必須停止並另取人工授權；不得讓測試或現況程式自行決定業務規則。

## 資料夾結構

本目錄依文件性質分為三類子資料夾；分類僅為整理排序，不改變任何文件的規格
內容或權威順序：

- `01_規格基線/` —— 定義目標架構的規格文件（原 `00`～`18`，內容與編號不變）。
- `02_決策與退役執行記錄/` —— 依時間序記錄已核准的退役／修復決策與其驗收證據
  （原 `19`～`30`）。
- `03_追蹤清單與證據/` —— legacy finding 盤點清單、過期文件候選清單、可刪暫存
  清單，以及對應的原始 `evidence/`。

## 文件

- `01_規格基線/00_Global_共同契約.md`
- `01_規格基線/01_Orders_Domain.md`
- `01_規格基線/02_Assignments_Scheduling_Domain.md`
- `01_規格基線/03_Payroll_Domain.md`
- `01_規格基線/04_Client_Finance_Domain.md`
- `01_規格基線/05_Staff_Payables_Export_Domain.md`
- `01_規格基線/06_Anomalies_Domain.md`
- `01_規格基線/07_跨Domain交易與pytest驗收架構.md`
- `01_規格基線/08_ADAD卸載與Legacy資料邊界.md`
- `01_規格基線/09_Finance_Import_Domain.md`
- `01_規格基線/10_Global_保留資料Migration與Cutover_Subsystem.md`
- `01_規格基線/11_架構總審矩陣與實作切片.md`
- `01_規格基線/12_Global_效能與UX體感架構.md`
- `01_規格基線/13_規格實作完成度矩陣.md`
- `01_規格基線/14_Government_Subsidy_Domain.md`
- `01_規格基線/15_正式規格索引與裁決總表.md`
- `01_規格基線/16_Staff_Payables與Client_Refund正式規格.md`
- `01_規格基線/17_External_Integration_LINE_Access正式規格.md`
- `01_規格基線/18_Global_Deployment與治理正式規格.md`

`15` 是本輪正式收斂入口；`16`～`18` 分別補齊帳務衝突、外部整合／權限及
Deployment／治理。`document/文件整併工作區` 保留來源追溯，不再作為直接施工入口。

`02_決策與退役執行記錄/` 與 `03_追蹤清單與證據/` 各自有獨立的 `README.md`
索引（含一句話摘要，`02` 另附機器可讀 `doc_type`／`declared_status`）；本節僅
列出規格基線，避免執行記錄的增修頻率拖累規格索引的穩定性。

## 實作門檻

每個 Domain 必須先具備：

- 明確的責任與 non-goals；
- 根事實、不可變事件、目前投影及查詢模型的 SSOT；
- Subsystem 與 Module 清單；
- typed input、output、errors 與 ports；
- Preview／Apply、版本、冪等、衝突及交易邊界；
- production writer inventory 與 legacy 退出策略；
- Module、Subsystem、Domain、Global 四層 pytest 責任。

所有 Domain 完成後，才能依相依順序切出實作批次。程式與測試可在同一個已確認契約下平行撰寫；任一層測試失敗時，該層整體視為未完成並回到該層契約與實作共同修正。

# 後端分層架構重整規格

> 快速入口：先閱讀 [00_開發者與Agent導覽.md](00_開發者與Agent導覽.md)，再依需求進入正式規格與
> 對應 Work Package。本 README 說明文件權威與目錄分工；快速導覽不取代本文件定義的權威順序。

## 目的

本目錄把既有規格書中已確認的業務場景轉成可實作、可測試的
`Global → Domain → Subsystem → Module` 架構契約。

`15`～`18` 已於 2026-08-03 經人工整體確認為初始正式架構基線；後續納入 `19`～`26`
各項正式補充裁決。目前正式規格入口與有效範圍以 `15` 的
裁決總表為準，涵蓋 `15`～`26`。後續 production code、pytest、schema、資料、外部平台與
退役作業，必須以個別 Work Package、驗收證據與人工決策記錄追溯；不得把單一基線核准或
live 現況誤讀成所有後續變更的授權。

2026-08-03 已把 `document/文件整併工作區` 中尚未收斂的月結、退款、
LINE、管理權限、部署與治理語彙集中到當時的 `15`～`18`；`19`～`26` 是後續正式補充裁決。
這些正式文件目前均納入 `15` 的索引與權威順序；核准本身不構成 production mutation 或
外部副作用授權。

## 權威順序

1. 人工最新明確裁決。
2. 經人工整體確認的正式規格 package；目前由 `15` 索引 `16`～`26`。
3. 既有業務規格、狀態機規則與欄位權威性文件，作為來源追溯。
4. 本目錄其他分層架構文件。
5. live DB schema、production code、API 與 UI 僅代表現況，不得用現況漂移推翻規格。

`15`～`26` 明載的 supersede／裁決條款優先於歷史來源；較新的明確裁決優先於較舊摘要。
任何超出已核准 Inventory v2
範圍的實作必須停止並另取人工授權；不得讓測試或現況程式自行決定業務規則。

## 資料夾結構

本目錄依文件性質分為三類子資料夾；分類僅為整理排序，不改變任何文件的規格
內容或權威順序：

- `01_規格基線/` —— 定義 current Global／Domain 架構契約；`15` 是正式索引與裁決入口。
- `02_決策與退役執行記錄/` —— 只保留current register、仍有約束力的decision，以及
  proposed／blocked／in-progress Work Package。
- `03_追蹤清單與證據/` —— 只保留current review queue、release／migration gate、aggregate receipt與
  目前回歸仍需要的`evidence/`。
- `04_已完成與上線封存/` —— Git歷史復原入口；不在工作樹維持歷史文件副本。

## 文件

- `00_開發者與Agent導覽.md`：重整後程式碼入口、分層責任、Domain 定位、開發與驗證安全界線。

- `01_規格基線/00_Global_共同契約.md`
- `01_規格基線/01_Orders_Domain.md`
- `01_規格基線/02_Assignments_Scheduling_Domain.md`
- `01_規格基線/03_Payroll_Domain.md`
- `01_規格基線/04_Client_Finance_Domain.md`
- `01_規格基線/05_Staff_Payables_Export_Domain.md`
- `01_規格基線/06_Anomalies_Domain.md`
- `01_規格基線/07_跨Domain交易與pytest驗收架構.md`
- `01_規格基線/09_Finance_Import_Domain.md`
- `01_規格基線/10_Global_保留資料Migration與Cutover_Subsystem.md`
- `01_規格基線/12_Global_效能與UX體感架構.md`
- `01_規格基線/14_Government_Subsidy_Domain.md`
- `01_規格基線/15_正式規格索引與裁決總表.md`
- `01_規格基線/16_Staff_Payables與Client_Refund正式規格.md`
- `01_規格基線/17_External_Integration_LINE_Access正式規格.md`
- `01_規格基線/18_Global_Deployment與治理正式規格.md`
- `01_規格基線/19_Global_Entry_Point_Governance.md`
- `01_規格基線/20_LINE客服與月嫂自助服務正式規格.md`
- `01_規格基線/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md`
- `01_規格基線/22_銀行流水匯入與帳務異常處理正式規格.md`
- `01_規格基線/23_LINE身分管理與解除正式規格.md`
- `01_規格基線/24_Staff_Matching_Preferences與不可服務期間正式規格.md`
- `01_規格基線/25_Access_Control_Production_Cutover與External_Security_Alert正式規格.md`
- `01_規格基線/26_LINE四大模組Eraser流程圖轉錄與驗收基線.md`

`15` 是正式收斂入口；`16`～`26` 分別補齊帳務衝突、外部整合／權限及
Deployment／治理，`19` 定義 API／Streamlit／CLI entry point 的逐項治理，`22` 定義銀行流水、
帳務異常固定處置與管理端入口，`24` 定義 Staff Matching Preferences 與不可服務期間，`25` 定義
Access Control production cutover與外部安全告警，`26` 定義LINE四大模組流程圖驗收基線。
`document/文件整併工作區` 只保留仍被欄位權威稽核讀取的 `06` 盤點；其餘歷史合併稿由 Git
歷史追溯，不再作為直接施工入口。

`02_決策與退役執行記錄/` 與 `03_追蹤清單與證據/` 各自有獨立的 `README.md`
索引（含一句話摘要，`02` 另附機器可讀 `doc_type`／`declared_status`）；本節僅
列出規格基線，避免執行記錄的增修頻率拖累規格索引的穩定性。

已完成且不再擁有 current contract 的歷史規格（08 ADAD／Legacy 邊界、11 架構總審矩陣、
13 規格實作完成度矩陣）已自目前工作樹移除，需要時依 `04_已完成與上線封存/README.md`
從 Git 歷史精準取回。
現行語意由 `15`、個別 Domain／Global 規格、AGENTS.md 與 `03` 的 current evidence 承接。

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

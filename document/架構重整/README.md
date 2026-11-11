# 後端分層架構重整規格

> 快速入口：先閱讀 [00_開發者與Agent導覽.md](00_開發者與Agent導覽.md)，依任務需要定位正式規格。
> 是否需要 Work Package 與最小交付，依 [Agent 任務分級與交付規範](00_Agent任務分級與交付規範.md) 判定。
> 本 README 說明文件權威與目錄分工；快速導覽不取代本文件定義的權威順序。

## 目的

本目錄把已確認的業務場景轉成可實作、可測試的
`Global → Domain → Subsystem → Module` 架構契約。

`01_規格基線/` 全數檔案遵守 [規格書撰寫與生命週期規範](00_規格書撰寫與生命週期規範.md) 之 **Living Current Truth（唯一現行契約）** 與單一所有權（SSOT）原則，由 [正式規格索引與裁決總表](01_規格基線/15_正式規格索引與裁決總表.md) 統一路由；後續 production code、pytest、schema、資料、外部平台與退役作業，依 [Agent 任務分級與交付規範](00_Agent任務分級與交付規範.md) 的 T0–T3 分級決定必要交付與追溯方式，不一律建立個別 Work Package。驗收與執行授權仍須對應 current task；不得把單一基線核准或 live 現況誤讀成所有後續變更的授權。

## 權威順序

1. 人工最新明確裁決。
2. 經人工整體確認的 `01_規格基線/` 唯一 owning current spec（以 `15_正式規格索引與裁決總表.md` 作為純路由入口）。
3. 既有業務規格、狀態機規則與欄位權威性文件，作為來源追溯。
4. 本目錄其他分層架構文件。
5. live DB schema、production code、API 與 UI 僅代表現況，不得用現況漂移推翻規格。

不得讓測試或現況程式自行決定業務規則；超出現行授權範圍的實作必須停止並另取人工授權。

## 資料夾結構

本目錄依文件性質分為四類子資料夾；分類僅為整理排序，不改變任何文件的規格
內容或權威順序：

- `01_規格基線/` —— 定義 current Global／Domain／正式 UI integration 架構契約；以 `15_正式規格索引與裁決總表.md` 為統一路由入口。
- `02_決策與退役執行記錄/` —— 只保留current register、仍有約束力的decision，以及
  proposed／blocked／in-progress Work Package（開發期間之契約 Delta 亦暫置於此，結案後同步回主規格並移出）。
- `03_追蹤清單與證據/` —— 只保留current review queue、release／migration gate、aggregate receipt與
  目前回歸仍需要的`evidence/`。
- `04_已完成與上線封存/` —— Git歷史復原入口；不在工作樹維持歷史文件副本。

## 文件

- `00_規格書撰寫與生命週期規範.md`：Living Current Truth 撰寫規則、Delta → Sync 生命週期與自動化檢核規範。
- `00_Agent任務分級與交付規範.md`：T0–T3 任務分級、P0 engineering guards 與最小交付規範。
- `00_開發者與Agent導覽.md`：重整後程式碼入口、分層責任、Domain 定位、開發與驗證安全界線。

### 正式規格基線（`01_規格基線/`，共 40 份）

- `01_規格基線/00_Global_共同契約.md`
- `01_規格基線/01_Orders_Domain.md`
- `01_規格基線/01A_訂單看板與事前日期及歷史採納規格.md`
- `01_規格基線/02_Assignments_Scheduling_Domain.md`
- `01_規格基線/02A_媒合候選池與客戶決定及通勤規格.md`
- `01_規格基線/03_Payroll_Domain.md`
- `01_規格基線/04_Client_Finance_Domain.md`
- `01_規格基線/05_Staff_Payables_Export_Domain.md`
- `01_規格基線/06_Anomalies_Domain.md`
- `01_規格基線/07_跨Domain交易與pytest驗收架構.md`
- `01_規格基線/09_Finance_Import_Domain.md`
- `01_規格基線/10_Global_保留資料Migration與Cutover_Subsystem.md`
- `01_規格基線/10A_NAS_Fresh初始化與維護復原規格.md`
- `01_規格基線/12_Global_效能與UX體感架構.md`
- `01_規格基線/14_Government_Subsidy_Domain.md`
- `01_規格基線/15_正式規格索引與裁決總表.md`
- `01_規格基線/16_Staff_Payables與Client_Refund正式規格.md`
- `01_規格基線/16A_Accounts_Payable_Export與現金需求清冊規格.md`
- `01_規格基線/17_External_Integration_LINE_Access正式規格.md`
- `01_規格基線/17A_LINE_Gateway_Inbox與通知投遞正式規格.md`
- `01_規格基線/17B_Case_Import與非市民Redis待審正式規格.md`
- `01_規格基線/18_Global_Deployment與治理正式規格.md`
- `01_規格基線/19_Global_Entry_Point_Governance.md`
- `01_規格基線/20_LINE客服與月嫂自助服務正式規格.md`
- `01_規格基線/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md`
- `01_規格基線/22_銀行流水匯入與帳務異常處理正式規格.md`
- `01_規格基線/22A_案件帳務三方案與補助流向正式規格.md`
- `01_規格基線/22B_帳務差額處置與工作台UI正式規格.md`
- `01_規格基線/23_LINE身分管理與解除正式規格.md`
- `01_規格基線/24_Staff_Matching_Preferences與不可服務期間正式規格.md`
- `01_規格基線/24A_Staff_Roster_Case_Preference_Read_Model正式補充契約.md`
- `01_規格基線/24B_Staff_Roster_Case_Preference_Ownership_Clarification.md`
- `01_規格基線/25_Access_Control_Production_Cutover與External_Security_Alert正式規格.md`
- `01_規格基線/26_LINE四大模組Eraser流程圖轉錄與驗收基線.md`
- `01_規格基線/27_歷史訂單生命週期與服務天數帳務正式規格.md`
- `01_規格基線/29_LINE服務說明、客服互動與選單角色正式規格.md`
- `01_規格基線/30_Controlled_File_Storage_NAS正式規格.md`
- `01_規格基線/31_MultiCaregiver_Admin_UI正式規格.md`
- `01_規格基線/33_案件與月嫂整合名冊正式規格.md`
- `01_規格基線/34_營運報表與統計口徑正式規格.md`

`document/文件整併工作區` 只保留仍被欄位權威稽核讀取的 `06` 盤點，以及仍由正式索引直接引用的 `08_非Markdown附件索引.md`；其餘歷史合併稿由 Git 歷史追溯，不再作為直接施工入口。

`02_決策與退役執行記錄/` 與 `03_追蹤清單與證據/` 各自有獨立的 `README.md`
索引（含一句話摘要，`02` 另附機器可讀 `doc_type`／`declared_status`）；本節僅
列出規格基線，避免執行記錄的增修頻率拖累規格索引的穩定性。

已退役且不再擁有 current contract 的歷史文件（08 ADAD／Legacy 邊界、11 架構總審矩陣、
13 規格實作完成度矩陣、15A/15B closeout 與 32 功能盤點紀錄）已自目前工作樹移除，需要時依 `04_已完成與上線封存/README.md`
從 Git 歷史精準取回。
現行業務語意由 `15_正式規格索引與裁決總表.md` 路由之個別 Domain／Global／正式 UI integration 規格承接；工作路由依 `AGENTS.md` 與任務分級規範，`03` 的 current evidence 只供驗證與追溯。

## 實作門檻

建立或修改 Domain 契約時，確認 current scope 所涉及的下列面向：

- 明確的責任與 non-goals；
- 根事實、不可變事件、目前投影及查詢模型的 SSOT；
- Subsystem 與 Module 清單；
- typed input、output、errors 與 ports；
- Preview／Apply、版本、冪等、衝突及交易邊界；
- production writer inventory 與 legacy 退出策略；
- Module、Subsystem、Domain、Global 四層 pytest 責任。

依既有且足夠的契約實作或局部修正時，只核對 current task 的 owner 與直接依賴，不以所有 Domain 重新完成規格檢核為前置條件。是否建立 Work Package、最小交付與驗證範圍依上述 T0–T3 規範，不另設整體重整 gate。程式與測試可在同一個已確認契約下平行撰寫；測試失敗時釐清受影響的契約或實作，只有實際 failure signal 或整合風險才擴大驗證。

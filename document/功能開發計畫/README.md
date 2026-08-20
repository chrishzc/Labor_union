# 功能開發計畫索引

本目錄只保留尚在規劃、待確認、已核准但未取得實作授權，或仍有未完成範圍的 initiative。
功能計畫不是正式規格或 production mutation 授權；正式 owner 與業務語意以
[`15_正式規格索引與裁決總表.md`](../架構重整/01_規格基線/15_正式規格索引與裁決總表.md)
及其指向的 Domain／Global 規格為準。

## Active 計畫

| 文件 | 狀態 | 下一個 gate |
|---|---|---|
| [Cloud Run＋單一 Cloud VPN 雲端部署測試計畫](Cloud_Run_單一Cloud_VPN_部署測試計畫.md) | `proposed` | 指定隔離 cloud project／NAS DB、operator、預算與故障注入範圍後，另立 exact-scope Work Package。 |
| [Cloud Run Durable Job Worker Supervision](Durable_Job_Worker_Supervision_延後開發計畫.md) | `proposed`／`deferred` | 指定隔離 cloud test project／NAS DB、OIDC、operator、故障注入與雲端測試 gate。 |
| [UI 真實業務流程測試資料與驗收主計畫](UI真實業務流程測試資料與驗收主計畫.md) | `approved-planning` | 各 Part 個別完成規格與人工 activation gate。 |
| [Part 00 全域測試資料治理與 Scenario 契約](Part_00_全域測試資料治理與Scenario契約.md) | `proposed` | 人工確認 Part 00 後才可建立執行 Work Package。 |
| [React 管理端遷移與 UI 真實業務流程驗收](React管理端遷移與UI真實業務流程驗收計畫.md) | `proposed` | 已確認三項 Orders SOP 業務裁決；仍待確認整體架構與第一包 Access＋System Status exact write set。 |

## 已完成或被取代的計畫

下列文件已通過封存 gate，不再留在 active 目錄。歷史 identity、digest、evidence 與 restore trigger
以 [`archive_manifest.json`](../架構重整/04_已完成與上線封存/archive_manifest.json) 為準：

| 原計畫 | 封存結果 | Current successor |
|---|---|---|
| 契約整合與正常測試資料鏈 | [superseded spec](../架構重整/04_已完成與上線封存/superseded_specs/契約整合與正常測試資料鏈_決策草案.md) | [21 Contract Signing 正式規格](../架構重整/01_規格基線/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md) |
| UI 工作區測試資料情境矩陣 | [completed matrix](../架構重整/04_已完成與上線封存/work_packages/UI工作區測試資料情境矩陣.md) | [21 Contract Signing 正式規格](../架構重整/01_規格基線/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md) |
| 休假代班天數精算與 Calendar Preview | [superseded plan](../架構重整/04_已完成與上線封存/superseded_specs/00_P0_最高優先_休假代班天數精算與行事曆差異預覽修復計畫.md) | [02 Assignments／Scheduling](../架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md) |
| 單月嫂預設與預計服務日期表傳送 | [superseded plan](../架構重整/04_已完成與上線封存/superseded_specs/00_P0_月嫂配對中心_單月嫂預設與預計服務日期表傳送改善計畫.md) | [02 Assignments／Scheduling](../架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md) |
| 月嫂配對中心剩餘功能 | [completed plan](../架構重整/04_已完成與上線封存/superseded_specs/00_P0_月嫂配對中心_剩餘功能收斂計畫.md) | [24 Staff Matching Preferences 正式規格](../架構重整/01_規格基線/24_Staff_Matching_Preferences與不可服務期間正式規格.md) |
| Scheduling 月嫂請假申請待辦 | [superseded plan](../架構重整/04_已完成與上線封存/superseded_specs/Scheduling_月嫂請假申請待辦與管理端處理開發計畫.md) | [02 Assignments／Scheduling](../架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md)；實作 evidence 為 [ARCH-20260815-099](../架構重整/04_已完成與上線封存/work_packages/PROV-20260815-scheduling-line-staff-leave-intake-work-package.md)。 |
| ADR-001 Import Architecture Refactor | [superseded ADR](../架構重整/04_已完成與上線封存/superseded_specs/ADR-001-import-architecture-refactor.md) | 現行匯入語意由 [15 正式規格索引](../架構重整/01_規格基線/15_正式規格索引與裁決總表.md) 與各 Domain 規格擁有；入口退役待辦已移至 [active work package](../架構重整/02_決策與退役執行記錄/Import_Entry_and_Legacy_Writer_Retirement_工作包.md)。 |

`completed` 不代表自動封存。只有 current successor 已完整承接語意、evidence 與 inbound links
可追溯，且原文件不再擁有 active blocker、操作入口或 rollback 責任時，才可移入封存區。

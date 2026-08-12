# 決策與退役執行記錄索引

依編號（時間序）記錄已核准的退役／修復決策與其驗收證據。每份文件開頭都有
`doc_type`／`declared_status`／`date`（如原文有明確標示）的 YAML frontmatter，
可供腳本快速篩選；文字內容才是唯一權威來源，frontmatter 只是索引輔助。

`doc_type` 意義：`decision-package`（已核准但可能尚未授權實作/移除）、
`receipt`（已完成並驗收的執行記錄）、`gap-package`（記錄現況與目標的落差，
非退役性質）、`contract`（單一場景的正式規格補充）。

本索引以 active、blocked、awaiting execution／release 與 current recovery 文件為主。不再 active
的 completed Work Package、已有 successor 的 superseded 舊規格與 closed release／receipt，通過
`../04_已完成與上線封存/README.md` 的 archive gate 後移出本表，僅保留必要的一行 archive
pointer。2026-08-11 已完成多輪保守封存；歷史文件以
[`archive_manifest.json`](../04_已完成與上線封存/archive_manifest.json) 精準查找，不再列入日常索引。

| 檔案 | doc_type | declared_status | 一句話摘要 |
|---|---|---|---|
| [19 Legacy Retirement Wave 1（封存）](../04_已完成與上線封存/work_packages/19_Legacy_Retirement_Wave_1_Decision_Package.md) | decision-package | `completed` | Wave 1A target 已歷史移除，2026-08-12 完成 fresh caller/replacement reconciliation。 |
| [24 MySQL Adapter Mutation Exit（封存）](../04_已完成與上線封存/work_packages/24_MySQL_Adapter_Mutation_Exit_Decision_Package.md) | decision-package | `completed` | `mysql_adapter.py` mutation exit 與 fresh v3 disposition reconciliation 已驗收；347 筆 owner review 改由 WP63 承接。 |
| [33 G05 服務完成時刻與請假／代班競爭契約（封存）](../04_已完成與上線封存/work_packages/33_G05_服務完成時刻與請假代班競爭契約.md) | contract | `completed` | current 語意已由 Orders 與 Scheduling 正式基線承接，G05 evidence 維持 proven。 |
| [35 LINE Ingress Convergence（封存）](../04_已完成與上線封存/work_packages/35_LINE_Ingress_Developer_Experience_Convergence_Contract.md) | contract | `completed` | canonical ingress、legacy direct-writer exit 與 rollback guard 已驗收。 |
| [42 Client Finance 銀行根事實與逾期提醒（封存）](../04_已完成與上線封存/work_packages/42_Client_Finance_Bank_Fact_and_Overdue_Reminder_Decision.md) | architecture-decision | `completed` | current 政策已由正式規格 `20` 完整承接，實作與 focused evidence 已驗收。 |
| [44 Finance Import CLI Test Adapter（封存）](../04_已完成與上線封存/superseded_specs/44_Finance_Import_CLI_Test_Adapter_Work_Package.md) | work-package | `superseded` | adapter 邊界與退役工作已整併至 `document/功能開發計畫/ADR-001-import-architecture-refactor.md`。 |
| [49 LINE Provisional Registration（封存）](../04_已完成與上線封存/work_packages/49_LINE_Provisional_Registration_Typed_Replacement_Decision.md) | work-package | `completed` | Case Import consume／merge 已完成；保留作 LINE 與 Case Import 歷史追溯。 |
| [52 LINE Review／Rich Menu／Admin Session Policy（封存）](../04_已完成與上線封存/work_packages/52_LINE_Review_Rich_Menu_and_Admin_Session_Policy_Decision.md) | architecture-decision | `completed` | current 政策已由正式規格 `17` 完整承接，實作與驗收證據已完成。 |
| [55 Finance Amendment Executable Contracts（封存）](../04_已完成與上線封存/work_packages/55_Finance_Amendment_Executable_Contracts_Work_Package.md) | gap-package | `completed` | 差額／追償與 typed dispatcher 已由正式規格及 focused evidence 承接。 |
| [56 Contract Signing 與 UI Validation（封存）](../04_已完成與上線封存/work_packages/56_Contract_Signing_and_UI_Validation_Work_Package.md) | gap-package | `completed` | 2026-08-12 closeout 已驗證簽約、exact conversion、archive/schema 與八個 UI scenario。 |
| [57 Finance Amendment validation closeout（封存）](../04_已完成與上線封存/work_packages/57_Finance_Amendment_Production_Release_Readiness.md) | validation-closeout | `completed` | 已完成 isolated-test UI 與 focused regression 驗收；production deployment 不在此包範圍。 |
| [58_未實作_未落地_未上線規格總表.md](58_未實作_未落地_未上線規格總表.md) | gap-register | `completed` | 已確認正式規格的未實作、已實作未落地、已驗證未上線與刻意不自動化之集中盤點。 |
| [59_UI_Navigation_Convergence_Work_Package.md（封存）](../04_已完成與上線封存/work_packages/59_UI_Navigation_Convergence_Work_Package.md) | work-package | `completed` | 封存：單一業務導覽、固定頁面註冊與訂單／帳務 UI 邊界收斂（移入封存索引）。 |
| [61 LINE Ingress Phase 1（封存）](../04_已完成與上線封存/work_packages/61_LINE_Ingress_Convergence_Phase_1_Work_Package.md) | work-package | `completed` | canonical Service Help owner workflow 已驗收，後續 canonical cutover 亦已完成。 |
| [62 LINE Ingress Phase 2（封存）](../04_已完成與上線封存/work_packages/62_LINE_Ingress_Convergence_Phase_2_Rulebook_and_Legacy_Characterization_Work_Package.md) | work-package | `completed` | 規則書對齊與 union-menu／`esc` characterization 已驗收；canonical 行為仍待人工裁決。 |
| [63 Global Writer Inventory v3 Owner Review（封存）](../04_已完成與上線封存/work_packages/63_Global_Writer_Inventory_v3_Owner_Review_Work_Package.md) | work-package | `completed` | 1,027 筆 disposition 已完整 review；`needs_decision=0`、`approved_to_remove=0`。 |
| [64_LINE_Menu_Command_Canonical_Replacement_Work_Package.md（封存）](../04_已完成與上線封存/work_packages/64_LINE_Menu_Command_Canonical_Replacement_Work_Package.md) | work-package | `completed` | 封存：union menu 與 `esc` 已保留並改走 canonical identity gate、outbox 與 Rich Menu worker（移入封存索引）。 |
| [65 LINE Ingress Canonical Cutover Completion（封存）](../04_已完成與上線封存/receipts/65_LINE_Ingress_Canonical_Cutover_Completion_Receipt.md) | completion-receipt | `completed` | runtime default 已切至 canonical；current 契約由正式規格 `17` 承接。 |
| [66 Scheduling Leave Substitution Calendar Preview（封存）](../04_已完成與上線封存/work_packages/66_Scheduling_Leave_Substitution_Calendar_Preview_Work_Package.md) | work-package | `completed` | Scheduling-only candidate、cross-domain Apply gate 與 Chrome UI Preview 驗收已完成。 |
| [67 Scheduling Leave/Substitution Calendar Precision Completion（封存）](../04_已完成與上線封存/work_packages/67_Scheduling_Leave_Substitution_Calendar_Precision_Completion_Work_Package.md) | work-package | `completed` | 服務日基線、請假／代班精算與行事曆 UI 驗收已完成；Holiday contract 由 WP69 及 Scheduling 正式基線承接。 |
| [68 Matching Center Single-Caregiver Default](68_Matching_Center_Single_Caregiver_Default_Work_Package.md) | work-package | `in-progress` | 單月嫂預設、typed coverage、confirmed service dates 與日期表雙方確認／指派 gate 已進入 focused 驗收；完整 worker/UI closeout 尚未完成。 |
| [69 Scheduling Canonical Holiday Query Contract（封存）](../04_已完成與上線封存/work_packages/69_Scheduling_Canonical_Holiday_Query_Contract_Work_Package.md) | work-package | `completed` | Preview／Apply 共用的版本化 Holiday Query 已完成，國定假日預設休假、扣除服務日並順延。 |
| [70 Scheduling Calendar Action Mode Persistence Fix（封存）](../04_已完成與上線封存/work_packages/70_Scheduling_Calendar_Action_Mode_Persistence_Fix_Work_Package.md) | work-package | `completed` | Chrome 驗證新 session 預設精算，且精算與訂單匹配模式在年月切換後均保留。 |
| [71 LEGACY_SHARED_KEY Retirement（封存）](../04_已完成與上線封存/work_packages/71_INTERNAL_API_KEY_Retirement_Work_Package.md) | work-package | `completed` | 已移除 legacy shared key；完成測試與 Chrome UI read-path 驗收，詳見 `ARCH-20260812-052`。 |

> `29_` 原本被三份文件重複使用（無明確時間序，只能靠檔名區分），2026-08-07
> 已重新編號為 `32`～`34`（依原檔名字母序指派，不代表已還原真實時間序）。
> 之後新增文件請直接使用下一個未用過的整數（目前最大為 `59`）。

> 注意：本表不是只保留字面上的 `in-progress`。仍需實作、等待 release／migration、保留人工操作
> 邊界、缺少 completion evidence，或仍約束現行操作的文件都屬 active working set。已完成但尚與 active
> release gate 綁定的 `55`，以及作為目前缺口 SSOT 的 `58`，依封存規則暫留。

2026-08-12 人工指示暫緩 Durable Job Worker 主機 supervision；原 `41` 已降級並移至
[`document/功能開發計畫/Durable_Job_Worker_Supervision_延後開發計畫.md`](../../功能開發計畫/Durable_Job_Worker_Supervision_延後開發計畫.md)，
不再構成 active deployment contract 或主機操作授權。

2026-08-12 人工選定 Scheduling 請假方案三；原 `60` 已改寫並移至
[`document/功能開發計畫/Scheduling_月嫂請假申請待辦與管理端處理開發計畫.md`](../../功能開發計畫/Scheduling_月嫂請假申請待辦與管理端處理開發計畫.md)。
LINE 申請只建立待辦 evidence，正式排班仍由既有 leave-substitution Preview／Apply 擁有；目前尚未授權實作。

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
| [33_G05_服務完成時刻與請假代班競爭契約.md](33_G05_服務完成時刻與請假代班競爭契約.md) | contract | — | G05 場景：服務完成時刻判定與請假／代班的競爭不變量正式規格。 |
| [35 LINE Ingress Convergence（封存）](../04_已完成與上線封存/work_packages/35_LINE_Ingress_Developer_Experience_Convergence_Contract.md) | contract | `completed` | canonical ingress、legacy direct-writer exit 與 rollback guard 已驗收。 |
| [41_Durable_Job_Worker_Supervision_Deployment_Decision.md](41_Durable_Job_Worker_Supervision_Deployment_Decision.md) | architecture-decision | current | Windows Task Scheduler worker supervision 的現行操作契約。 |
| [42_Client_Finance_Bank_Fact_and_Overdue_Reminder_Decision.md](42_Client_Finance_Bank_Fact_and_Overdue_Reminder_Decision.md) | architecture-decision | `human-confirmed` | Client Finance 銀行根事實與逾期提醒裁決。 |
| [44_Finance_Import_CLI_Test_Adapter_Work_Package.md](44_Finance_Import_CLI_Test_Adapter_Work_Package.md) | work-package | approved；仍為 active adapter | 測試期 Finance Excel CLI adapter 邊界，待 Web 匯入取代後退役。 |
| [49 LINE Provisional Registration（封存）](../04_已完成與上線封存/work_packages/49_LINE_Provisional_Registration_Typed_Replacement_Decision.md) | work-package | `completed` | Case Import consume／merge 已完成；保留作 LINE 與 Case Import 歷史追溯。 |
| [52_LINE_Review_Rich_Menu_and_Admin_Session_Policy_Decision.md](52_LINE_Review_Rich_Menu_and_Admin_Session_Policy_Decision.md) | architecture-decision | current | LINE review、Rich Menu 與管理員 session 政策。 |
| [55_Finance_Amendment_Executable_Contracts_Work_Package.md](55_Finance_Amendment_Executable_Contracts_Work_Package.md) | gap-package | `completed` | 2026-08-11 已核准的差額／追償與 typed dispatcher 實作範圍及驗收。 |
| [56 Contract Signing 與 UI Validation（封存）](../04_已完成與上線封存/work_packages/56_Contract_Signing_and_UI_Validation_Work_Package.md) | gap-package | `completed` | 2026-08-12 closeout 已驗證簽約、exact conversion、archive/schema 與八個 UI scenario。 |
| [57 Finance Amendment validation closeout（封存）](../04_已完成與上線封存/work_packages/57_Finance_Amendment_Production_Release_Readiness.md) | validation-closeout | `completed` | 已完成 isolated-test UI 與 focused regression 驗收；production deployment 不在此包範圍。 |
| [58_未實作_未落地_未上線規格總表.md](58_未實作_未落地_未上線規格總表.md) | gap-register | `completed` | 已確認正式規格的未實作、已實作未落地、已驗證未上線與刻意不自動化之集中盤點。 |
| [59_UI_Navigation_Convergence_Work_Package.md](59_UI_Navigation_Convergence_Work_Package.md) | work-package | `completed` | 單一業務導覽、固定頁面註冊與訂單／帳務 UI 邊界收斂。 |
| [60_Scheduling_Leave_Review_and_LINE_Command_Ownership_Decision.md](60_Scheduling_Leave_Review_and_LINE_Command_Ownership_Decision.md) | architecture-decision | `human-confirmed; scheduling-api-implementation-blocked-by-live-drift` | 請假審核歸 Scheduling，三個既有 LINE aliases 保留 binding 語意；legacy service drift 不掛入 FastAPI。 |
| [61_LINE_Ingress_Convergence_Phase_1_Work_Package.md](61_LINE_Ingress_Convergence_Phase_1_Work_Package.md) | work-package | `completed` | canonical Service Help 已改經 Customer Service owning workflow；runtime default 與 production cutover 仍屬後續 phase。 |
| [62 LINE Ingress Phase 2（封存）](../04_已完成與上線封存/work_packages/62_LINE_Ingress_Convergence_Phase_2_Rulebook_and_Legacy_Characterization_Work_Package.md) | work-package | `completed` | 規則書對齊與 union-menu／`esc` characterization 已驗收；canonical 行為仍待人工裁決。 |
| [63_Global_Writer_Inventory_v3_Owner_Review_Work_Package.md](63_Global_Writer_Inventory_v3_Owner_Review_Work_Package.md) | work-package | `in-progress` | 347 筆 `needs_decision` writer identity 的唯一 active owner／transaction-boundary review queue。 |
| [64 LINE Menu Command Canonical Replacement](64_LINE_Menu_Command_Canonical_Replacement_Work_Package.md) | work-package | `completed` | union menu 與 `esc` 已保留並改走 canonical identity gate、outbox 與 Rich Menu worker。 |
| [65 LINE Ingress Canonical Cutover Completion](65_LINE_Ingress_Canonical_Cutover_Completion_Receipt.md) | completion-receipt | `completed` | runtime default 已切至 canonical；legacy 僅保留受控 rollback。 |

> `29_` 原本被三份文件重複使用（無明確時間序，只能靠檔名區分），2026-08-07
> 已重新編號為 `32`～`34`（依原檔名字母序指派，不代表已還原真實時間序）。
> 之後新增文件請直接使用下一個未用過的整數（目前最大為 `59`）。

> 注意：本表不是只保留字面上的 `in-progress`。仍需實作、等待 release／migration、保留人工操作
> 邊界、缺少 completion evidence，或仍約束現行操作的文件都屬 active working set。已完成但尚與 active
> release gate 綁定的 `55`，以及作為目前缺口 SSOT 的 `58`，依封存規則暫留。

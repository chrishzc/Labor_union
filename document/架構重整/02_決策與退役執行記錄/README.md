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
| [24_MySQL_Adapter_Mutation_Exit_Decision_Package.md](24_MySQL_Adapter_Mutation_Exit_Decision_Package.md) | decision-package | `decision-ready; no code removal in this package` | `mysql_adapter.py` 內部 mutation 函式的退役排程，本包不含任何刪除。 |
| [33_G05_服務完成時刻與請假代班競爭契約.md](33_G05_服務完成時刻與請假代班競爭契約.md) | contract | — | G05 場景：服務完成時刻判定與請假／代班的競爭不變量正式規格。 |
| [35_LINE_Ingress_Developer_Experience_Convergence_Contract.md](35_LINE_Ingress_Developer_Experience_Convergence_Contract.md) | contract | `decision-complete-implementation-deferred` | LINE 薄 ingress、Domain command 與 durable delivery 的收斂契約；新增功能採 intent registry 範本。 |
| [41_Durable_Job_Worker_Supervision_Deployment_Decision.md](41_Durable_Job_Worker_Supervision_Deployment_Decision.md) | architecture-decision | current | Windows Task Scheduler worker supervision 的現行操作契約。 |
| [42_Client_Finance_Bank_Fact_and_Overdue_Reminder_Decision.md](42_Client_Finance_Bank_Fact_and_Overdue_Reminder_Decision.md) | architecture-decision | `human-confirmed` | Client Finance 銀行根事實與逾期提醒裁決。 |
| [44_Finance_Import_CLI_Test_Adapter_Work_Package.md](44_Finance_Import_CLI_Test_Adapter_Work_Package.md) | work-package | approved；仍為 active adapter | 測試期 Finance Excel CLI adapter 邊界，待 Web 匯入取代後退役。 |
| [49 LINE Provisional Registration（封存）](../04_已完成與上線封存/work_packages/49_LINE_Provisional_Registration_Typed_Replacement_Decision.md) | work-package | `completed` | Case Import consume／merge 已完成；保留作 LINE 與 Case Import 歷史追溯。 |
| [52_LINE_Review_Rich_Menu_and_Admin_Session_Policy_Decision.md](52_LINE_Review_Rich_Menu_and_Admin_Session_Policy_Decision.md) | architecture-decision | current | LINE review、Rich Menu 與管理員 session 政策。 |
| [55_Finance_Amendment_Executable_Contracts_Work_Package.md](55_Finance_Amendment_Executable_Contracts_Work_Package.md) | gap-package | `completed` | 2026-08-11 已核准的差額／追償與 typed dispatcher 實作範圍及驗收。 |
| [56_Contract_Signing_and_UI_Validation_Work_Package.md](56_Contract_Signing_and_UI_Validation_Work_Package.md) | gap-package | `completed` | 2026-08-12 closeout 已驗證簽約、exact conversion、archive/schema 與八個 UI scenario；production deployment、正式 LINE 與 cutover 不在範圍。 |
| [57 Finance Amendment validation closeout（封存）](../04_已完成與上線封存/work_packages/57_Finance_Amendment_Production_Release_Readiness.md) | validation-closeout | `completed` | 已完成 isolated-test UI 與 focused regression 驗收；production deployment 不在此包範圍。 |
| [58_未實作_未落地_未上線規格總表.md](58_未實作_未落地_未上線規格總表.md) | gap-register | `completed` | 已確認正式規格的未實作、已實作未落地、已驗證未上線與刻意不自動化之集中盤點。 |
| [59_UI_Navigation_Convergence_Work_Package.md](59_UI_Navigation_Convergence_Work_Package.md) | work-package | `completed` | 單一業務導覽、固定頁面註冊與訂單／帳務 UI 邊界收斂。 |

> `29_` 原本被三份文件重複使用（無明確時間序，只能靠檔名區分），2026-08-07
> 已重新編號為 `32`～`34`（依原檔名字母序指派，不代表已還原真實時間序）。
> 之後新增文件請直接使用下一個未用過的整數（目前最大為 `59`）。

> 注意：本表不是只保留字面上的 `in-progress`。仍需實作、等待 release／migration、保留人工操作
> 邊界、缺少 completion evidence，或仍約束現行操作的文件都屬 active working set。已完成但尚與 active
> release gate 綁定的 `55`，以及作為目前缺口 SSOT 的 `58`，依封存規則暫留。

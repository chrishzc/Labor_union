# 決策與退役執行記錄索引

依編號（時間序）記錄已核准的退役／修復決策與其驗收證據。每份文件開頭都有
`doc_type`／`declared_status`／`date`（如原文有明確標示）的 YAML frontmatter，
可供腳本快速篩選；文字內容才是唯一權威來源，frontmatter 只是索引輔助。

`doc_type` 意義：`decision-package`（已核准但可能尚未授權實作/移除）、
`receipt`（已完成並驗收的執行記錄）、`gap-package`（記錄現況與目標的落差，
非退役性質）、`contract`（單一場景的正式規格補充）。

| 檔案 | doc_type | declared_status | 一句話摘要 |
|---|---|---|---|
| [19_Legacy_Retirement_Wave_1_Decision_Package.md](19_Legacy_Retirement_Wave_1_Decision_Package.md) | decision-package | `decision-complete-removal-not-authorized` | 第一波 legacy 退役候選盤點，裁決完成但未授權實際刪除。 |
| [20_Legacy_Retirement_Wave_2_Decision_Package.md](20_Legacy_Retirement_Wave_2_Decision_Package.md) | decision-package | `decision-complete-no-qualified-remove-candidate` | 第二波盤點，結論是沒有符合資格的可移除候選。 |
| [21_Legacy_Retirement_Wave_2B_Anomalies_Caller_Migration_Decision_Package.md](21_Legacy_Retirement_Wave_2B_Anomalies_Caller_Migration_Decision_Package.md) | decision-package | `decision-complete-caller-exit-not-authorized` | Anomalies caller 遷移裁決完成，caller 退出尚未授權。 |
| [22_Legacy_Retirement_Wave_2B_1_Anomalies_Caller_Exit_Receipt.md](22_Legacy_Retirement_Wave_2B_1_Anomalies_Caller_Exit_Receipt.md) | receipt | — | 2026-08-03，Anomalies caller 退出已執行完成的驗收記錄。 |
| [23_Legacy_Retirement_Wave_2B_2_Finance_Alert_Module_Removal_Receipt.md](23_Legacy_Retirement_Wave_2B_2_Finance_Alert_Module_Removal_Receipt.md) | receipt | — | 2026-08-03，正式移除 `api/routes/finance_alerts.py` 與三個 legacy finance-alert service，canonical 替代為 `subsystems/anomalies/alert_workflow.py`。 |
| [24_MySQL_Adapter_Mutation_Exit_Decision_Package.md](24_MySQL_Adapter_Mutation_Exit_Decision_Package.md) | decision-package | `decision-ready; no code removal in this package` | `mysql_adapter.py` 內部 mutation 函式的退役排程，本包不含任何刪除。 |
| [25_Client_Refund_Completion_Decision_Package.md](25_Client_Refund_Completion_Decision_Package.md) | decision-package | — | 客戶退款完成度落差；記錄 `subsidy_return` 交易模型已被 `subsidy_advance` 取代、舊 writer 不得重新引入。 |
| [26_Durable_Job_Completion_Decision_Package.md](26_Durable_Job_Completion_Decision_Package.md) | decision-package | — | Durable job（跨 web process 重啟仍存活的排隊工作）現況落差與實作計畫，不授權 schema/production 變更。 |
| [27_Finance_Import_Historical_Reprocess_Completion_Decision_Package.md](27_Finance_Import_Historical_Reprocess_Completion_Decision_Package.md) | decision-package | `partial` | Finance Import 歷史重匯功能完成度為 partial，舊 reprocess 已 fail-closed。 |
| [28_Global_E2E_Acceptance_Gap_Package.md](28_Global_E2E_Acceptance_Gap_Package.md) | gap-package | — | 定義「什麼才算通過 Global E2E」的驗收規則，並列出目前只有摘要層級證據的場景缺口。 |
| [30_Finance_Import_Legacy_Import_Path_Repair_Receipt.md](30_Finance_Import_Legacy_Import_Path_Repair_Receipt.md) | receipt | — | 2026-08-07，修正「架構重整」合併遺留的 20 處 import 路徑漂移，並將無替代品的 `client_subsidy_return` dispatch 改為 fail-closed。 |
| [31_Finance_Alert_Orphan_Route_Retirement_Receipt.md](31_Finance_Alert_Orphan_Route_Retirement_Receipt.md) | receipt | — | 2026-08-07，補記錄他人 commit `b4ec13b` 重建異常警示中心 5-tab UI 的過程，並退役最後兩個孤兒路由（`finance_alerts.py`／`system_alerts.py`）與其 client/schema/測試，實際啟動服務並在瀏覽器驗證 5 個分頁皆正常。 |
| [32_Client_Refund_Return_Anomaly_Package.md](32_Client_Refund_Return_Anomaly_Package.md) | gap-package | — | 一般客戶退款的銀行退回異常判斷根因與待補現況。 |
| [33_G05_服務完成時刻與請假代班競爭契約.md](33_G05_服務完成時刻與請假代班競爭契約.md) | contract | — | G05 場景：服務完成時刻判定與請假／代班的競爭不變量正式規格。 |
| [34_Preserve_Data_Runner_Completion_Decision_Package.md](34_Preserve_Data_Runner_Completion_Decision_Package.md) | decision-package | — | Preserve-data runner（保留資料遷移執行器）完成度落差。 |
| [35_LINE_Ingress_Developer_Experience_Convergence_Contract.md](35_LINE_Ingress_Developer_Experience_Convergence_Contract.md) | contract | `decision-complete-implementation-deferred` | LINE 薄 ingress、Domain command 與 durable delivery 的收斂契約；新增功能採 intent registry 範本。 |
| [36_Durable_Job_Assignment_Plan_Work_Package.md](36_Durable_Job_Assignment_Plan_Work_Package.md) | gap-package | `implementation-complete; isolated-mysql-e2e-proven` | Assignment Plan 已遷移至 server-side durable queue，隔離 MySQL crash/replay 與 same-key replay 證據已完成；不含 UI、部署或 schema 套用。 |
| [37_Durable_Job_Payroll_Rebuild_Work_Package.md](37_Durable_Job_Payroll_Rebuild_Work_Package.md) | gap-package | `implementation-complete; isolated-mysql-e2e-proven` | Payroll Rebuild 已遷移至 server-side durable queue，隔離 MySQL crash/replay 與 same-key replay 證據已完成；不含 UI、部署或 schema 套用。 |
| [38_Form_Management_Legacy_List_Caller_Migration_Receipt.md](38_Form_Management_Legacy_List_Caller_Migration_Receipt.md) | receipt | `completed` | Form Management 已改用 bounded Orders Summary、全域統計與單案 context typed Query，不再讀全量 Orders／Clients。 |
| [39_Durable_Job_Staff_Payout_Work_Package.md](39_Durable_Job_Staff_Payout_Work_Package.md) | gap-package | `proven` | Payout、Return、Reversal 已遷移至 server-side durable queue，三種完整根事實鏈皆具隔離 MySQL crash/replay 證據。 |
| [40_Durable_Job_Government_Subsidy_Work_Package.md](40_Durable_Job_Government_Subsidy_Work_Package.md) | gap-package | `proven` | 五種 Government Subsidy Apply 已遷移至 server-side durable queue，claim、receipt、reversal 根事實鏈均有隔離 MySQL crash/replay 證據。 |

> `29_` 原本被三份文件重複使用（無明確時間序，只能靠檔名區分），2026-08-07
> 已重新編號為 `32`～`34`（依原檔名字母序指派，不代表已還原真實時間序）。
> 之後新增文件請直接使用下一個未用過的整數（目前最大為 `36`）。

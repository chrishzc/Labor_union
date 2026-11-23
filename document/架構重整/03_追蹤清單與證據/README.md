# 追蹤清單與證據索引

本目錄只保存仍有 current consumer 的 review queue、release／migration gate、aggregate final receipt 與目前回歸需要的 evidence。這些資料提供可驗證事實，不建立業務 Authority；正式 owner、contract 與 current status 仍由 `.arch-map/requirements/`、最新人工裁決及 current successor register 擁有。

一般 T1／T2 工作不按 slice 建立 tracked receipt；依 [00_Agent任務分級與交付規範.md](../00_Agent任務分級與交付規範.md) 的 artifact 邊界，不按 slice 建 tracked receipt。Intermediate plan、handoff、progress note、raw log、HTTP dump、重複 candidate receipt 與已關閉 defect摘要應放在 ignored `scratch/`，或在完成後由 Git 歷史保存。大型 raw evidence、個資、secret、DB dump 與不必要 payload 不加入 Git。

## 目前常用入口

| 文件 | 用途 |
|---|---|
| [正式規格索引](../../../.arch-map/requirements/15_正式規格索引與裁決總表.md) | current正式規格、owner、Task 96／97 terminal boundary與裁決入口；Task 96 excluded／deferred項目只能由新的current successor重新啟動。 |
| [Task 97 repository-local closeout receipt](evidence/task97_repository_local_closeout_receipt_a48caa8.md) | 2026-08-30 Task 97 repository-local完成的歷史 aggregate receipt；只能證明其綁定 source revision 的結案事實，不得作為後續 source revision 或新增 writer 的持續核准 Authority。production、DB engine與external acceptance仍不得外推。 |
| [HCAT／RPRE aggregate receipt](evidence/2026-08-28_task96_hcat_rpre_aggregate_final_receipt.md) | 歷史分類／remediation projection的整合證據與未完成gate。 |
| [LDU 1003→1012 aggregate receipt](evidence/2026-08-28_task96_ldu_1003_to_1012_final_receipt.md) | 限定於1003→1012的歷史release證據；不得外推為current preserve-upgrade PASS。 |
| [Rich Menu schema gate receipt](evidence/2026-08-20_rich_menu_option_b_schema_gate_receipt.md) | Rich Menu saga schema／release static gate與尚未完成的provider／DB邊界。 |
| [Contract external-signing DB qualification](evidence/2026-08-26_contract_external_signing_successor_db_qualification_receipt.md) | external-signing successor的DB qualification證據。 |
| [Controlled-file foundation progress](evidence/2026-08-26_controlled_file_storage_foundation_progress_receipt.md) | Controlled Files基礎與尚未完成的Browser／NAS acceptance。 |
| [LINE legacy non-return regression source](LINE_merge功能未移植_history_20260811.md) | 目前仍由LINE第一版回歸測試讀取；只作禁止舊路徑復活的test oracle，不是產品SSOT。 |

上表不是 `evidence/` 的完整檔案清單。日常工作只讀任務直接命中的單一 evidence；不得整個目錄載入上下文，也不得因一份歷史 receipt仍存在就重新開啟 completed工作。Task 97 已完成；其 aggregate receipt 只供歷史結案追溯，不得重新視為 current task 或持續核准來源。

## 通知事項驗證進度

- LINE 共用處理投影、單筆與批次結清已實作。依 [LINE 結清契約](../../../.arch-map/requirements/17A_LINE_Gateway_Inbox與通知投遞正式規格.md#41-共用待辦判定與操作資格)，已用原生 MySQL synthetic 資料及正式 HTTP 路由驗證同來源完整範圍、處理中阻擋、原因與權限、原鍵重送及來源結清後禁止重建；另完成瀏覽器結清、批次選取及回應遺失後恢復。沒有操作既有測試庫積存事項，也沒有實際寄送 LINE。
- 歷史案件通知接續資格與舊逾期款截止邊界已實作；依 [歷史案件通知接續責任分界](../../../.arch-map/requirements/27_歷史訂單生命週期與服務天數帳務正式規格.md#81-歷史案件接續通知的責任分界) 驗證 owner Query、通知查詢 count/items 及付款資格。完整實際開始日確認、正式排班、完工的產品操作流程尚未端到端驗證，不能以 synthetic fixture 狀態轉換替代；下一責任人為整合驗證負責人。
- 分類已改為「款項與群組」，直接相關 UI 測試與桌面瀏覽器核對通過。桌面 14／手機 13 類入口由既有投影與測試覆蓋；本次隔離資料未逐類建立完整案件，手機實機及全部來源的完整瀏覽器流程尚未驗證，下一責任人為整合驗證負責人。

## 2026-09-01 清理批次

第一批已移除只有歷史／中間用途、且沒有 current consumer的文件：Task 97 pre-slimming report、被整合receipt取代的Anomalies來源lane receipt，以及數份Task 96 spec-ready／handoff／已修復defect中間receipt。需要稽核時，從清理前基準 commit `1f7c9cd7d90895f7846333c48cdb37c95da4caad` 精準取回單一檔案。

第二批再移除已被正式規格、canonical tests或aggregate evidence承接的Task 96 per-slice progress receipts；
release／migration gate、current writer inventory、Task 97 aggregate closeout與仍有external／NAS consumer的
receipts保留。Task 97 aggregate closeout只作歷史結案證據，不提供新 revision 的核准。需要追溯第二批文件時，從基準commit
`06b1c72de2a49bebfeb6d75fe6ef077f98fafd4d`精準取回。

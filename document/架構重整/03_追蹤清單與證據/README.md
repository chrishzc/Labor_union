# 追蹤清單與證據索引

本目錄只保存仍有 current consumer 的 review queue、release／migration gate、aggregate final receipt 與目前回歸需要的 evidence。這些資料提供可驗證事實，不建立業務 Authority；正式 owner、contract 與 current status 仍由 `01_規格基線/`、最新人工裁決及 current successor register 擁有。

一般 T1／T2 工作不按 slice 建立 tracked receipt；依 [00_Agent任務分級與交付規範.md](../00_Agent任務分級與交付規範.md) 的 artifact 邊界，不按 slice 建 tracked receipt。Intermediate plan、handoff、progress note、raw log、HTTP dump、重複 candidate receipt 與已關閉 defect摘要應放在 ignored `scratch/`，或在完成後由 Git 歷史保存。大型 raw evidence、個資、secret、DB dump 與不必要 payload 不加入 Git。

## 目前常用入口

| 文件 | 用途 |
|---|---|
| [Task 96 terminal register](../02_決策與退役執行記錄/96_Current_剩餘代辦任務總表.md) | Task 96已達repository-local acceptance；verified LIFF／provider、NAS、production／deployment與1019 preserve-upgrade仍維持明示`not_run`／deferred。 |
| [正式規格索引](../01_規格基線/15_正式規格索引與裁決總表.md) | current正式規格、owner與裁決入口。 |
| [LINE／Anomalies整合 aggregate receipt](evidence/PROV-20260830-line-anomalies-slimming-integration-receipt.md) | PR #63 repository-local整合結果及未完成外部邊界。 |
| [Task 97 repository-local closeout receipt](evidence/task97_repository_local_closeout_receipt_a48caa8.md) | Task 97 aggregate architecture結果；production、DB engine與external acceptance仍不得外推。 |
| [HCAT／RPRE aggregate receipt](evidence/2026-08-28_task96_hcat_rpre_aggregate_final_receipt.md) | 歷史分類／remediation projection的整合證據與未完成gate。 |
| [LDU 1003→1012 aggregate receipt](evidence/2026-08-28_task96_ldu_1003_to_1012_final_receipt.md) | 限定於1003→1012的歷史release證據；不得外推為current preserve-upgrade PASS。 |
| [Rich Menu schema gate receipt](evidence/2026-08-20_rich_menu_option_b_schema_gate_receipt.md) | Rich Menu saga schema／release static gate與尚未完成的provider／DB邊界。 |
| [Contract external-signing DB qualification](evidence/2026-08-26_contract_external_signing_successor_db_qualification_receipt.md) | external-signing successor的DB qualification證據。 |
| [Controlled-file foundation progress](evidence/2026-08-26_controlled_file_storage_foundation_progress_receipt.md) | Controlled Files基礎與尚未完成的Browser／NAS acceptance。 |
| [LINE legacy non-return regression source](LINE_merge功能未移植_history_20260811.md) | 目前仍由LINE第一版回歸測試讀取；只作禁止舊路徑復活的test oracle，不是產品SSOT。 |
| [entry-point review queue](evidence/entrypoint_review_queue_v1.jsonl) | current generated entry治理清單；由對應generator／validator維護。 |

上表不是 `evidence/` 的完整檔案清單。日常工作只讀任務直接命中的單一 evidence；不得整個目錄載入上下文，也不得因一份歷史 receipt仍存在就重新開啟 completed工作。

## 2026-09-01 清理批次

第一批已移除只有歷史／中間用途、且沒有 current consumer的文件：Task 97 pre-slimming report、被整合receipt取代的Anomalies來源lane receipt，以及數份Task 96 spec-ready／handoff／已修復defect中間receipt。需要稽核時，從清理前基準 commit `1f7c9cd7d90895f7846333c48cdb37c95da4caad` 精準取回單一檔案。

第二批再移除已被正式規格、canonical tests或aggregate evidence承接的Task 96 per-slice progress receipts；
release／migration gate、current generated inventory、Task 97 aggregate closeout與仍有external／NAS consumer的
receipts保留。需要追溯第二批文件時，從基準commit
`06b1c72de2a49bebfeb6d75fe6ef077f98fafd4d`精準取回。

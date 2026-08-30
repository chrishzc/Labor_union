# 追蹤清單與證據索引

盤點清單、候選清單與原始證據。這裡的文件**不構成規格授權**——多份文件本身
明文警告其 `status`／`disposition` 欄位只是起始提案，不能被當作可直接刪檔、
移除功能的授權依據，實際決策要看 `02_決策與退役執行記錄/`。

本目錄只保留 active review queue、current release gate 與目前回歸需要的 evidence。已結案且
沒有 current consumer 的摘要直接從工作樹移除，由 Git 歷史保存；大型 raw evidence、個資、
secret、DB dump 與 validation canonical assets 不加入 Git。Agent 日常只讀任務命中的 evidence，
不得整個 `evidence/` 載入上下文。

依 [Agent 任務分級與交付規範](../00_Agent任務分級與交付規範.md)，一般 T1／T2 的 command 與 source
state 直接在交付訊息回報，不按 slice 建 tracked receipt。只有 release／migration／rollback／incident／
external effect／audit 或明確 current consumer 才保存 aggregate final receipt；intermediate plan、raw log、
HTTP dump、重複 candidate receipt 與 cache 放 ignored `scratch/`，完成摘要後依 inbound／retention gate 清理。

| 檔案 | 一句話摘要 |
|---|---|
| [evidence/PROV-20260830-line-anomalies-slimming-integration-receipt.md](evidence/PROV-20260830-line-anomalies-slimming-integration-receipt.md) | PR #63整合receipt：LINE #62→Anomalies #61→LINE-004 consumer→shared governance；repository-local regression與14項CI全綠，deferred owner／DB／production邊界保持不變。 |
| [evidence/PROV-20260830-current-state-anomalies-parallel-repository-local-receipt.md](evidence/PROV-20260830-current-state-anomalies-parallel-repository-local-receipt.md) | PR #61來源lane receipt；其`WAIT_PEER_LINE_CONTRACT`與shared drift已由PR #63收斂，其餘14個owner gap仍deferred。 |
| [evidence/task97_repository_local_closeout_receipt_a48caa8.md](evidence/task97_repository_local_closeout_receipt_a48caa8.md) | Task 97 repository-local architecture aggregate receipt：`REPO_LOCAL_BLOCKER=0`；production、DB engine與external evidence明確`NOT_RUN`／deferred，不能推導deployment或DB mutation Authority。 |
| [evidence/2026-08-27_anomaly_necessity_migration_runtime_receipt.md](evidence/2026-08-27_anomaly_necessity_migration_runtime_receipt.md) | Task 96 ANM-NM-A／producer cutover：typed API、三個真 MySQL remediation 情境與 `SCHEDULE-005` 停產證據 PASS；DB release 1009 developer replacement 因受控 credential 未注入而 NOT_RUN。 |
| [evidence/2026-08-26_task96_p0_import_anomaly_staff_receipt.md](evidence/2026-08-26_task96_p0_import_anomaly_staff_receipt.md) | Task 96：歷史訂單 review zero-mutation 與 Staff cursor 第二頁實機驗收已完成；歷史 anomaly UI safety 證據保留，但因使用者要求全異常人工 remediation 而重開。 |
| [evidence/2026-08-27_historical_order_review_remediation_runtime_receipt.md](evidence/2026-08-27_historical_order_review_remediation_runtime_receipt.md) | Task 96 Historical Orders 人工 remediation：1008 no-op constraint、fresh/preserve-data MySQL、Apply/replay/outbox 與 active-list removal PASS；enabled-human Browser 與 developer replacement 仍 NOT_RUN。 |
| [evidence/2026-08-28_task96_hcat_rpre_aggregate_final_receipt.md](evidence/2026-08-28_task96_hcat_rpre_aggregate_final_receipt.md) | Task 96 HCAT／RPRE aggregate：catalog-v2、六 owner adapters／composition、RPRE persistence／API／projector／no-auth runtime 的 accepted invariants、owner boundaries、MySQL／Browser evidence與未完成 gates 收斂於單一 receipt。 |
| [evidence/2026-08-28_task96_ldu_1003_to_1012_final_receipt.md](evidence/2026-08-28_task96_ldu_1003_to_1012_final_receipt.md) | Task 96 LDU 1003→1012 aggregate：ordered engine qualification、launcher、macOS runtime、Windows source與static release gate收斂；後續1013／1014另保留，整體DB結論仍`DB_CHANGE_NOT_READY`。 |
| [evidence/2026-08-27_hcm_multi_occurrence_umbrella_resolution_receipt.md](evidence/2026-08-27_hcm_multi_occurrence_umbrella_resolution_receipt.md) | `IMPORT-004` 同 review 問題逐筆解除，最後一筆才收旂 umbrella；focused 84 與 Luna High E3 PASS，真 MySQL/service runtime NOT_RUN。 |
| [evidence/2026-08-26_controlled_file_storage_foundation_progress_receipt.md](evidence/2026-08-26_controlled_file_storage_foundation_progress_receipt.md) | CUR-FILE-NAS-01 typed storage 與 DB release 1004 的 progress receipt；全部 DB gates、Python 115、React 15 PASS，enabled human Session fresh Chrome 正向仍 NOT_RUN。 |
| [模組正式位置對照表.md](模組正式位置對照表.md) | 舊 `services.*` 模組路徑 → 現在正式路徑（`domains`／`subsystems`／`infrastructure`）的查詢表，含已遷移、已退役無替代、仍在用未退役三類。 |
| [legacy_active_201_可追蹤清單.md](legacy_active_201_可追蹤清單.md) / [.csv](legacy_active_201_可追蹤清單.csv) | 201 筆依 path pattern 產生的 legacy finding 初步分類清單；status 欄不是執行授權。 |
| [evidence/2026-08-20_rich_menu_option_b_schema_gate_receipt.md](evidence/2026-08-20_rich_menu_option_b_schema_gate_receipt.md) | Rich Menu Option B 三張 immutable saga tables、release／descriptor／assembly static gates；disposable MySQL 未配置，結論 `DB_CHANGE_NOT_READY`。 |
| [LINE_merge功能未移植_history_20260811.md](LINE_merge功能未移植_history_20260811.md) | 第一版刻意不移植的 merge legacy 行為，以及未來重新評估前必須補足的架構條件。 |
| [evidence/](evidence/) | 上述決策包／收據對應的原始 evidence 產物（JSON／SQL／receipt）。 |
| [evidence/2026-08-28_task96_anomaly_category_ux_spec_receipt.md](evidence/2026-08-28_task96_anomaly_category_ux_spec_receipt.md) | 異常分類數量與匯入待辦區隔的 SPEC_READY／PACKAGE_READY 收錄證據。 |
| [evidence/2026-08-28_task96_matching_event_enum_receipt.md](evidence/2026-08-28_task96_matching_event_enum_receipt.md) | Matching coordination released event enum 對齊、unsupported command fail-closed 與 fresh Luna/high 複核證據。 |

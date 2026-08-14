# 追蹤清單與證據索引

盤點清單、候選清單與原始證據。這裡的文件**不構成規格授權**——多份文件本身
明文警告其 `status`／`disposition` 欄位只是起始提案，不能被當作可直接刪檔、
移除功能的授權依據，實際決策要看 `02_決策與退役執行記錄/`。

本目錄優先保留 active review queue、current release gate 與目前回歸需要的 evidence。已結案且
不再被 current gate／runbook 使用的 receipt 或 evidence 摘要，只有通過
`../04_已完成與上線封存/README.md` 的 archive gate 後才可搬移；大型 raw evidence、個資、
secret、DB dump 與 validation canonical assets 不因封存而加入 Git。Agent 日常只讀任務命中的
evidence，不得整個 `evidence/` 載入上下文。

| 檔案 | 一句話摘要 |
|---|---|
| [模組正式位置對照表.md](模組正式位置對照表.md) | 舊 `services.*` 模組路徑 → 現在正式路徑（`domains`／`subsystems`／`infrastructure`）的查詢表，含已遷移、已退役無替代、仍在用未退役三類。 |
| [legacy_active_201_可追蹤清單.md](legacy_active_201_可追蹤清單.md) / [.csv](legacy_active_201_可追蹤清單.csv) | 201 筆依 path pattern 產生的 legacy finding 初步分類清單；status 欄不是執行授權。 |
| [過期文件候選清單_20260803.md](過期文件候選清單_20260803.md) | `document/文件整併工作區`、`document/架構重整` 範圍內可能過期文件的候選清單（第一版）。 |
| [31_可刪暫存清單.md](31_可刪暫存清單.md) | 可丟棄測試產物（MySQL test evidence／pytest basetemp 等）的盤點，同樣不授權直接刪除。 |
| [import_warning_type_review_queue.md](import_warning_type_review_queue.md) | WP88 已採用的 HCM、Client／Staff BeClass、Historical Orders 與 Finance Import 警示顯示、後續處理、LINE 邊界及解除條件矩陣；正式語意仍由 owning 規格擁有。 |
| [evidence/2026-08-11_finance_amendment_focused_regression_receipt.md](evidence/2026-08-11_finance_amendment_focused_regression_receipt.md) | 四項 finance amendment 的 focused regression、schema release check 與 interactive browser evidence。 |
| [Finance Amendment validation closeout receipt（封存）](../04_已完成與上線封存/receipts/2026-08-11_finance_amendment_release_preflight_receipt.md) | Finance Amendment isolated-test schema、UI Preview／Apply 與 focused regression 的結案收據。 |
| [evidence/2026-08-11_ui_navigation_convergence_receipt.md](evidence/2026-08-11_ui_navigation_convergence_receipt.md) | 單一業務導覽、lazy page registry、訂單／帳務拆分的 focused regression 與 browser smoke。 |
| [evidence/2026-08-11_active_package_closeout_receipt.md](evidence/2026-08-11_active_package_closeout_receipt.md) | 25／28／32／43／45 收尾，以及 26／46／49 收斂的 fresh focused validation 與逐項裁決。 |
| [evidence/2026-08-12_line_ingress_phase_1_service_help_receipt.md](evidence/2026-08-12_line_ingress_phase_1_service_help_receipt.md) | LINE ingress Phase 1：canonical Service Help 委派至 Customer Service owning workflow 的 focused regression。 |
| [LINE ingress Phase 2 receipt（封存）](../04_已完成與上線封存/receipts/2026-08-12_line_ingress_phase_2_rulebook_reconciliation_receipt.md) | 規則書對齊與 union-menu／`esc` characterization 已驗收；未授權的 canonical behavior 留待人工裁決。 |
| [evidence/2026-08-12_line_menu_command_canonical_replacement_receipt.md](evidence/2026-08-12_line_menu_command_canonical_replacement_receipt.md) | 已裁決的 union menu／`esc` canonical identity gate、outbox replacement 與 focused regression。 |
| [WP68 matching-center receipt（封存）](../04_已完成與上線封存/receipts/2026-08-12_wp68_matching_schedule_confirmation_receipt.md) | Candidate Contact Pool、日期表 Preview／人工覆核與正式方案建立已完成 Chrome UI 驗收；未觸發 LINE 外送。 |
| [WP72 matching receipts（封存）](../04_已完成與上線封存/receipts/2026-08-13_wp72_matching_preferences_staff_availability_receipt.md) / [residual closeout（封存）](../04_已完成與上線封存/receipts/2026-08-13_matching_residual_closeout_receipt.md) | WP72 與月嫂配對 residual plan 已完成 local Browser／regression 驗收；正式行為仍由規格 24 擁有。 |
| [WP74 developer-local DB receipt（封存）](../04_已完成與上線封存/receipts/2026-08-13_developer_local_database_maintenance_receipt.md) | 空 schema 升級與目前 DB 備份副本升級均完成真實 MySQL 驗收；來源 DB 未修改。 |
| [WP75 launcher receipt（封存）](../04_已完成與上線封存/receipts/2026-08-13_startup_launcher_convergence_receipt.md) | Windows canonical launcher 實跑、LINE optional credential gate、PID／port cleanup 與 focused regression 已完成。 |
| [evidence/2026-08-13_wp76_migration_release_integrity_readiness_receipt.md](evidence/2026-08-13_wp76_migration_release_integrity_readiness_receipt.md) | WP76 full-chain hash、part 61／153、disposable source→candidate 與目標主機 launcher readiness 驗收均已通過。 |
| [evidence/2026-08-13_wp73_import_development_test_handoff.md](evidence/2026-08-13_wp73_import_development_test_handoff.md) | 無 Git 開發主機的 Import 唯讀／apply／replay 測試順序、指令、停止條件與交接包邊界。 |
| [evidence/2026-08-13_wp77_staff_adoption_hcm_review_receipt.md](evidence/2026-08-13_wp77_staff_adoption_hcm_review_receipt.md) | WP77完成收據：較新Staff快照覆寫／姓名追溯、去敏workbook Preview／Apply／replay及pre-189 preserve candidate全數PASS。 |
| [evidence/2026-08-13_wp78_knowledge_partial_local_database_recovery_receipt.md](evidence/2026-08-13_wp78_knowledge_partial_local_database_recovery_receipt.md) | Knowledge 148／163 partial recovery 的 focused、disposable MySQL 與待開發者驗收 DB gate。 |
| [evidence/2026-08-13_wp79_line_runtime_release_catalog_recovery_receipt.md](evidence/2026-08-13_wp79_line_runtime_release_catalog_recovery_receipt.md) | LINE 179／184／185／186 catalog 恢復、hash 驗證與待 engine／開發者驗收 DB gate。 |
| [evidence/2026-08-13_wp78_wp81_legacy_compatibility_receipt.md](evidence/2026-08-13_wp78_wp81_legacy_compatibility_receipt.md) | Knowledge unsigned legacy FK 相容與 Rich Menu 精確空設定修復的 focused evidence、DB gate 與 operator 邊界。 |
| [evidence/2026-08-13_wp84_legacy_knowledge_empty_schema_recovery_receipt.md](evidence/2026-08-13_wp84_legacy_knowledge_empty_schema_recovery_receipt.md) | exact 且全空的歷史 Knowledge schema 在 candidate 重建之 Docker engine evidence 與 fail-closed 邊界。 |
| [65 LINE canonical cutover receipt（封存）](../04_已完成與上線封存/receipts/65_LINE_Ingress_Canonical_Cutover_Completion_Receipt.md) | canonical runtime default、rollback guard 與 focused cutover regression。 |
| [LINE_merge功能未移植_history_20260811.md](LINE_merge功能未移植_history_20260811.md) | 第一版刻意不移植的 merge legacy 行為，以及未來重新評估前必須補足的架構條件。 |
| [evidence/](evidence/) | 上述決策包／收據對應的原始 evidence 產物（JSON／SQL／receipt）。 |
| [evidence/2026-08-14_wp85_historical_order_web_transition_receipt.md](evidence/2026-08-14_wp85_historical_order_web_transition_receipt.md) | Orders historical workbook Web card 的去敏 Preview／Apply／review／replay／conflict、MySQL rollback與完成證據。 |
| [evidence/2026-08-14_wp80_historical_order_adoption_closeout_receipt.md](evidence/2026-08-14_wp80_historical_order_adoption_closeout_receipt.md) | WP80 去敏 workbook、atomic Apply／replay／rollback與 pre-190 → part 190 source-preserving candidate 的完成收據。 |
| [evidence/2026-08-14_wp83_data_import_center_closeout_receipt.md](evidence/2026-08-14_wp83_data_import_center_closeout_receipt.md) | WP83 五個 typed 匯入 lane 的去敏 workbook、disposable MySQL、Finance 真實格式、內建瀏覽器與 canonical DB plan 完成收據。 |

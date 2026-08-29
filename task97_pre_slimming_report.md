# Task 97 前置 Repository 瘦身報告

## Summary

- files before：3,327 個 durable tracked paths（以 HEAD 為基線，排除 generated cache／pytest 暫存）
- files after：3,300 個 logical durable paths
- deleted count：30
- merged count：2 個 canonical aggregate final receipts
- rehomed count：2 個 regression test files
- net reduction：27 個 durable paths（30 刪除－2 aggregate－1 本報告；rehome 淨變化為 0）
- test result：collection 24 tests PASS；新位置測試 `15 passed, 9 skipped`；相鄰 regression `17 passed`；保留的 WP77 測試 `36 passed`；governance validator PASS
- runtime／production behavior：未修改 production code、schema、migration、dependency、Streamlit 或外部效果

## MERGED

### HCAT／RPRE → `document/架構重整/03_追蹤清單與證據/evidence/2026-08-28_task96_hcat_rpre_aggregate_final_receipt.md`

承接 20 份同系列 receipt：

- `2026-08-28_task96_hcat_rpre_domain_slice_receipt.md`
- `2026-08-28_task96_hcat_rpre_subsystem_slice_receipt.md`
- `2026-08-28_task96_hcat_rpre_spec_pipeline_correction_receipt.md`
- `2026-08-28_task96_hcat_catalog_v2_authority_receipt.md`
- `2026-08-28_task96_hcat_orders_adapter_receipt.md`
- `2026-08-28_task96_hcat_matching_adapter_receipt.md`
- `2026-08-28_task96_hcat_staff_payables_adapter_receipt.md`
- `2026-08-28_task96_hcat_client_finance_adapter_receipt.md`
- `2026-08-28_task96_hcat_contract_signing_adapter_receipt.md`
- `2026-08-28_task96_hcat_six_owner_composition_mysql_receipt.md`
- `2026-08-28_task96_hcat_catalog_v2_domain_receipt.md`
- `2026-08-28_task96_hcat_catalog_v2_vector_receipt.md`
- `2026-08-28_task96_hcat_adapter_boundary_receipt.md`
- `2026-08-28_task96_hcat_scheduling_adapter_receipt.md`
- `2026-08-28_task96_rpre_concrete_persistence_source_receipt.md`
- `2026-08-28_task96_rpre_mysql_persistence_receipt.md`
- `2026-08-28_task96_rpre_api_authority_receipt.md`
- `2026-08-28_task96_rpre_pure_projector_receipt.md`
- `2026-08-28_task96_rpre_api_contract_receipt.md`
- `2026-08-28_task96_rpre_noauth_browser_runtime_receipt.md`

Aggregate 保留 current authority、21-descriptor／六 owner boundary、RPRE Q/P/A、borrowed-UoW、MySQL／API／Browser evidence、rollback policy 與所有未完成 gates。

### LDU 1003→1012 → `document/架構重整/03_追蹤清單與證據/evidence/2026-08-28_task96_ldu_1003_to_1012_final_receipt.md`

承接本批指定的 11 份 LDU receipt：

- `2026-08-28_task96_ldu_ordered_chain_launcher_slice_receipt.md`
- `2026-08-28_task96_ldu_1006_engine_qualification_receipt.md`
- `2026-08-28_task96_ldu_1007_engine_qualification_receipt.md`
- `2026-08-28_task96_ldu_1008_engine_qualification_receipt.md`
- `2026-08-28_task96_ldu_1009_engine_qualification_receipt.md`
- `2026-08-28_task96_ldu_1010_engine_qualification_receipt.md`
- `2026-08-28_task96_ldu_1011_engine_qualification_receipt.md`
- `2026-08-28_task96_ldu_1012_engine_qualification_receipt.md`
- `2026-08-28_task96_ldu_local_noauth_runtime_receipt.md`
- `2026-08-28_task96_windows_runtime_supervision_source_receipt.md`
- `2026-08-28_task96_ldu_hproj_rpre_static_release_receipt.md`（已合併內容，但檔案因 Task 97 inbound reference 保留）

Aggregate gate table 明確限定 1003→1012；不誤稱 repository current terminal，並保留後續 1013／1014 evidence 的分界。

## REHOMED

- `tests/test_wp80_historical_order_adoption.py` → `tests/domains/orders/test_historical_order_adoption.py`；全部 15 tests collection／execution 保留。
- `tests/test_wp85_historical_order_workbook_disposable_mysql_e2e.py` → `tests/integration/test_historical_order_workbook.py`；全部 9 MySQL-gated tests 保留 skip condition，collection／execution 通過。

## DELETED_NOW

每一檔均已先完成 repository-wide filename、relative path、symbol/import、Markdown、README/index、AGENTS、test、script、CI/config、rollback／audit 與 Task 97 dependency search；aggregate successor 存在，刪除後 exact path 不存在且沒有殘留 inbound reference（不計本報告的 provenance mapping 表）。未刪內容由 Git history 保留。

| Deleted file | Successor | Zero-reference evidence | Validation |
|---|---|---|---|
| `2026-08-28_task96_hcat_rpre_domain_slice_receipt.md` | HCAT／RPRE aggregate | repository-wide exact search = 0 | aggregate present；index/WP links updated |
| `2026-08-28_task96_hcat_rpre_subsystem_slice_receipt.md` | HCAT／RPRE aggregate | repository-wide exact search = 0 | aggregate present；index/WP links updated |
| `2026-08-28_task96_hcat_rpre_spec_pipeline_correction_receipt.md` | HCAT／RPRE aggregate | repository-wide exact search = 0 | aggregate present；index/WP links updated |
| `2026-08-28_task96_hcat_catalog_v2_authority_receipt.md` | HCAT／RPRE aggregate | repository-wide exact search = 0 | aggregate present；index updated |
| `2026-08-28_task96_hcat_orders_adapter_receipt.md` | HCAT／RPRE aggregate | repository-wide exact search = 0 | aggregate present；index updated |
| `2026-08-28_task96_hcat_matching_adapter_receipt.md` | HCAT／RPRE aggregate | repository-wide exact search = 0 | aggregate present；index updated |
| `2026-08-28_task96_hcat_staff_payables_adapter_receipt.md` | HCAT／RPRE aggregate | repository-wide exact search = 0 | aggregate present；index updated |
| `2026-08-28_task96_hcat_client_finance_adapter_receipt.md` | HCAT／RPRE aggregate | repository-wide exact search = 0 | aggregate present；index updated |
| `2026-08-28_task96_hcat_contract_signing_adapter_receipt.md` | HCAT／RPRE aggregate | repository-wide exact search = 0 | aggregate present；index updated |
| `2026-08-28_task96_hcat_six_owner_composition_mysql_receipt.md` | HCAT／RPRE aggregate | repository-wide exact search = 0 | aggregate present；index updated |
| `2026-08-28_task96_hcat_catalog_v2_domain_receipt.md` | HCAT／RPRE aggregate | repository-wide exact search = 0 | aggregate present；index updated |
| `2026-08-28_task96_hcat_catalog_v2_vector_receipt.md` | HCAT／RPRE aggregate | repository-wide exact search = 0 | aggregate present；index updated |
| `2026-08-28_task96_hcat_adapter_boundary_receipt.md` | HCAT／RPRE aggregate | repository-wide exact search = 0 | aggregate present；index updated |
| `2026-08-28_task96_hcat_scheduling_adapter_receipt.md` | HCAT／RPRE aggregate | repository-wide exact search = 0 | aggregate present；index updated |
| `2026-08-28_task96_rpre_concrete_persistence_source_receipt.md` | HCAT／RPRE aggregate | repository-wide exact search = 0 | aggregate present；WP links updated |
| `2026-08-28_task96_rpre_mysql_persistence_receipt.md` | HCAT／RPRE aggregate | repository-wide exact search = 0 | aggregate present；WP links updated |
| `2026-08-28_task96_rpre_api_authority_receipt.md` | HCAT／RPRE aggregate | repository-wide exact search = 0 | aggregate present；index updated |
| `2026-08-28_task96_rpre_pure_projector_receipt.md` | HCAT／RPRE aggregate | repository-wide exact search = 0 | aggregate present；index updated |
| `2026-08-28_task96_rpre_api_contract_receipt.md` | HCAT／RPRE aggregate | repository-wide exact search = 0 | aggregate present；index updated |
| `2026-08-28_task96_rpre_noauth_browser_runtime_receipt.md` | HCAT／RPRE aggregate | repository-wide exact search = 0 | aggregate present；WP links updated |
| `2026-08-28_task96_ldu_ordered_chain_launcher_slice_receipt.md` | LDU 1003→1012 aggregate | repository-wide exact search = 0 | aggregate gate table present |
| `2026-08-28_task96_ldu_1006_engine_qualification_receipt.md` | LDU 1003→1012 aggregate | repository-wide exact search = 0 | 1006 qualification summarized |
| `2026-08-28_task96_ldu_1007_engine_qualification_receipt.md` | LDU 1003→1012 aggregate | repository-wide exact search = 0 | 1007 qualification summarized |
| `2026-08-28_task96_ldu_1008_engine_qualification_receipt.md` | LDU 1003→1012 aggregate | repository-wide exact search = 0 | 1008 qualification summarized |
| `2026-08-28_task96_ldu_1009_engine_qualification_receipt.md` | LDU 1003→1012 aggregate | repository-wide exact search = 0 | 1009 qualification summarized |
| `2026-08-28_task96_ldu_1010_engine_qualification_receipt.md` | LDU 1003→1012 aggregate | repository-wide exact search = 0 | 1010 qualification summarized |
| `2026-08-28_task96_ldu_1011_engine_qualification_receipt.md` | LDU 1003→1012 aggregate | repository-wide exact search = 0 | 1011 qualification summarized |
| `2026-08-28_task96_ldu_1012_engine_qualification_receipt.md` | LDU 1003→1012 aggregate | repository-wide exact search = 0 | 1012 qualification summarized |
| `2026-08-28_task96_ldu_local_noauth_runtime_receipt.md` | LDU 1003→1012 aggregate | repository-wide exact search = 0 | macOS runtime summarized |
| `2026-08-28_task96_windows_runtime_supervision_source_receipt.md` | LDU 1003→1012 aggregate | repository-wide exact search = 0 | Windows source gate summarized |

## DEFERRED_TO_TASK97

- `document/架構重整/02_決策與退役執行記錄/97_架構一致性修復與全域驗收計畫.md`、`96_Current_剩餘代辦任務總表.md`、Task 97 production inventory／writer／entry／authority evidence：保留，未修改。
- `2026-08-28_task96_ldu_hproj_rpre_static_release_receipt.md`：aggregate 已承接內容，但因受保護 `task97_production_script_inventory_v1.json` 直接引用而保留。
- `tests/test_wp77_import_contracts.py`：Task 97 production inventory 直接引用，未搬移；原測試 36 passed。
- repository current baseline 中的 1013／1014 release evidence：不納入本批，避免把 1003→1012 historical slice 誤當 current terminal。

## DEFERRED_TO_STREAMLIT_RETIREMENT

- 無可安全刪除候選；`.streamlit/config.toml`、`ui/app.py`、`ui/nav_helper.py`、`ui/request_state.py`、`ui/pages/**`、`ui/components/**`、`ui/api_clients/**`、Streamlit dependencies 與 regression tests 均保留且未修改。

## BLOCKED

- `2026-08-28_task96_ldu_hproj_rpre_static_release_receipt.md`：unique current inbound reference from protected Task 97 inventory；刪除會削弱 Task 97 baseline。
- `tests/test_wp77_import_contracts.py`：same protected Task 97 inventory reference；rehome 會造成 baseline path drift，故保留。
- `PROV-20260827-import006-source-version-source-only-work-package.md`：`proposed`／`AUTHORITY_REQUIRED`，仍代表 unresolved live-drift contract。
- `PROV-20260826-contract-external-platform-pdf-handoff-work-package.md`：`in-progress`，仍有 current acceptance／operator work 與 active index reference。
- `PROV-20260827-historical-order-business-scenario-gap-matrix.md`：仍被 scenario／successor specs 引用，且包含未完成 `MISSING`／`PARTIAL_GAP` obligations。
- LDU 1013／1014 及 HPROJ 後續 evidence：不屬本批 exact deletion set，且與 current release boundary／Task 97 baseline 有關，保留。

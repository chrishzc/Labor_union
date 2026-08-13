---
doc_type: evidence-receipt
declared_status: program-fix-completed
date: 2026-08-13
owner: Global Migration / LINE Integration
work_packages:
  - ../../02_決策與退役執行記錄/78_Knowledge_Partial_Local_Database_Recovery_Work_Package.md
  - ../../02_決策與退役執行記錄/81_LINE_Rich_Menu_Empty_Configuration_Recovery_Work_Package.md
---

# WP78 / WP81 Legacy Compatibility 修復證據

## 已驗證程式行為

- Preserve-data runner 只接受 `knowledge_items.id` 為 `BIGINT` 或 `BIGINT UNSIGNED`；後者建立 Knowledge child FK 時採相同 unsigned 型別，其他型別 fail closed。
- `bootstrap_line_configuration.py --apply --repair-empty-rich-menus` 僅在既有 canonical Rich Menu current revision 精確等於 `{}` 時，透過既有 UoW、CAS、idempotency 與 audit 追加修復 revision。
- `line/setup_rich_menus.py` 保留舊名稱但不讀本機設定、不建立發布工作；直接執行會導向 authenticated Preview／Apply。

## 驗證命令與結果

| Command | Result |
|---|---|
| `.venv\Scripts\python.exe -m pytest tests/test_wp78_local_database_partial_recovery.py tests/line/subsystems/test_line_message_configuration_stage5.py tests/test_production_module_caller_graph.py -q --basetemp .pytest_tmp/wp81-final` | PASS — 21 passed |
| `.venv\Scripts\python.exe -m compileall -q scripts/migrate_preserved_database_additive_schema.py scripts/bootstrap_line_configuration.py subsystems/line/configuration_application.py line/setup_rich_menus.py` | PASS |
| `.venv\Scripts\python.exe line/setup_rich_menus.py` | PASS — exit 1 with replacement guidance; no config/DB/provider operation |
| `.venv\Scripts\python.exe -m pytest tests/test_wp78_partial_recovery_disposable_mysql.py -q -rs --basetemp .pytest_tmp/wp81-disposable-mysql-reason` | NOT_RUN — 2 skipped; disposable MySQL container 未明確設定 |

## DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | WP78 scope amendment、WP81 與 2026-08-13 使用者修復授權 |
| Change inventory | PASS | WP78／WP81 inventory |
| Static release | PASS | 既有 148／163 release identity 未變；focused runner regression 通過 |
| Descriptor | PASS | known signed／unsigned contract unit regression；unknown type fail closed |
| Read-only plan | NOT_RUN | 未提供可安全操作的目標 DB 環境 |
| Engine verification | NOT_RUN | disposable MySQL container 未設定 |
| Developer acceptance | NOT_RUN | 未操作既有 `union_db` |

結論：程式修復已完成；任何實際 DB 更新維持 `DB_CHANGE_NOT_READY`，須由 operator 以 source backup → candidate → apply → verify 保存 receipt。

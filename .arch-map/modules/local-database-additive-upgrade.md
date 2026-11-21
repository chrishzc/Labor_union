# Module: local-database-additive-upgrade

## Parent
- boundary: `Global migration governance`

## Responsibility
提供 local preserved-data ordered additive upgrade 的唯讀 schema 分類、資格檢查、backup、apply、journal 與 exact readback；不擁有任何 Domain schema 或 business rule。
Apply 的前置驗證、DDL、更新後驗證獨立計時：驗證階段各 300 秒，DDL 保留最多 30 秒，等鎖最多 5 秒。驗證讀取使用有界連線並在查詢前後檢查階段期限；所有原備份、鎖後 fresh-read 與 row fingerprint 檢查保留。成功 receipt／journal 保存去敏 phase_timings，失敗保留階段 code 與已驗證進度，不以 timeout 自動重播未知 DDL。
Apply 重播遇到 exact schema 但同 release journal 尚未 completed，回 verification_incomplete；結構完成不能替代更新後驗證，沿用既有明確 recovery 入口核對原備份與進度。

## Implementation
- primary: `scripts/migrate_preserved_database_additive_schema.py`
- transport: `scripts/update_local_database.py`

## Verification
- integration_root: `tests/test_local_database_additive_runner.py`
- `test_slow_readonly_phases_do_not_consume_ddl_budget`：在模擬的前置和更新後驗證各耗至少 90 秒時，DDL 仍在獨立 30 秒預算內完成。完成事件與成功收據記錄同一份階段計時。
- `test_validation_deadline_stops_without_success_receipt`：前置、更新後驗證各自逾時時，回傳對應的 `preparation_duration_exceeded` 或 `verification_duration_exceeded`，不產生成功收據或完成事件。前置逾時不執行 DDL；後驗逾時不抹去先前執行的 DDL。
- `test_exact_schema_after_verification_timeout_is_not_a_successful_replay`：更新後驗證逾時，後續讀回結構雖然已符合，直接 runner 和 updater 都仍回傳 `verification_incomplete`，不額外執行 DDL，也不產生成功收據。

## Provenance
- Existing flat test is a higher-boundary migration/developer-upgrade contract — `architecture_declared` — `.arch-map/index.md` verification routing.

## Change triggers
- Reconcile when the local upgrade entrypoint, release-state classifier, qualification, backup/apply boundary, journal, or canonical higher-boundary test changes.

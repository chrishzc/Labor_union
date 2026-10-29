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

## Provenance
- Existing flat test is a higher-boundary migration/developer-upgrade contract — `architecture_declared` — `.arch-map/index.md` verification routing.

## Change triggers
- Reconcile when the local upgrade entrypoint, release-state classifier, qualification, backup/apply boundary, journal, or canonical higher-boundary test changes.

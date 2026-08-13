# WP84 Legacy Knowledge Empty Schema Recovery Receipt

- date: 2026-08-13；developer acceptance 更新於 2026-08-14
- source revision: working tree based on `4d3107b`
- authorization: 使用者明確核准建立 WP84，並要求修復後完成本機同名 DB update
- scope: exact legacy Knowledge schema；保留 canonical-exact requests/jobs，只在 candidate 重建空 roots

## Gate 結果

| Gate | 狀態 | 證據 |
|---|---|---|
| Scope | PASS | `84_Legacy_Knowledge_Empty_Schema_Recovery_Work_Package.md` |
| Change inventory | PASS | WP84 的 schema-only／system-seed／business-row-backfill／destructive inventory |
| Static release | PASS | canonical 148／163、release chain 與 `labor-union-wp72-2026-08-13-v1` identity 未變；唯讀 plan 列出兩者 resumable |
| Descriptor | PASS | runner 完整比對 legacy columns、indexes、FK、checks、triggers；unknown metadata drift 測試阻擋 |
| Read-only plan | PASS | `.venv\Scripts\python.exe -m scripts.update_local_database` exit 0；未寫入 DB |
| Engine verification | PASS | Docker MySQL：WP84 `5 passed`；updater focused regression `71 passed, 1 skipped`；最終群組 `79 passed, 1 failed` 後，唯一完整 cutover 案例修正並重跑 `1 passed` |
| Developer acceptance | PASS | `scratch/local_database_updates/union_db_local_20260813162514/`：source dump、candidate verify、replacement receipt；`--require-current` 回報 current |

## Failure model evidence

- fail-before-fix：legacy fixture 原本被 148／163 判為 drift，2 tests failed。
- exact legacy：candidate 重建後 148／163 exact；requests/jobs 各 20 rows，更新前後 checksum 與 PK hash 完全一致。
- nonempty：read-only plan 以 `legacy Knowledge tables are not empty` 阻擋。
- metadata drift：新增未知欄位時固定判為 drift。
- external reference：bounded context 外 inbound FK 於 read-only plan 阻擋。
- release 153：只接受 source 零筆的已宣告 retirement table；非空於 read-only plan 阻擋。
- lifecycle backfill：只允許宣告的 control events/state 且 verify exit 0、review_required=0。
- replacement：同名 `union_db` 完成，release current；Knowledge rows 為 `0 / 0 / 20 / 20`。

## 結論

七項 gate 全部通過；本機 `union_db` 已完成同名替換與 current-release 驗證，結論為
`DB_CHANGE_READY`。

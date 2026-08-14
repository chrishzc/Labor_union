# Remote Merge Release Chain Reconciliation Receipt

日期：2026-08-14
狀態：candidate static reconciliation complete；DB engine gates pending

## 人工裁決

- 保留遠端已發布 part 189／190 SQL、manifest、descriptor 與歷史 receipt bytes。
- 新增 part 191 修復 `government_subsidy_outbox.intent_type`；舊 4-value enum 為待升級、目標
  8-value enum 為 exact，任何其他型態為 drift。
- WP77／WP80 使用新 release identities 與 part 192／193；active Web transition 改為 WP86。
- 舊 manifest 保持不變；不同開發者留下的舊 shape、跨-release dependency 與 mutable backfill
  hash 由 strict successors、versioned archive、baseline 與 catalog order 收斂。
- default catalog 不排程未重新授權的歷史 backfill；explicit manifest selection 仍保留其 backfill
  契約。shared strict loader、hash、descriptor 與 unique ordinal gate 均未放寬。

## Final static evidence

- default runner import：latest `labor-union-wp80-2026-08-14-v2`；尾端 artifact 為 188～193。
- 20 份 default manifests 逐份 strict parser：`20 PASS / 0 FAIL`。
- `tests/test_preserved_database_plan_contract.py`、WP77、WP80、validation manifest：`74 passed`。
- 歷史 v2～v9 metadata regression：`10 passed`；原 manifest bytes 未被 successor 覆寫。
- WP77／WP80 disposable MySQL E2E：`4 skipped`，因未設定明確 `lu_test_*` database。
- 正式 read-only updater 使用主工作區 `.env`：BLOCKED；既有 source 的 part 153 為 partial、part
  186 為 drift。額外唯讀 classification 顯示 189～193 全部 exact，未執行 `--apply`。

## DB gate

| Gate | 狀態 | 證據 |
|---|---|---|
| Scope gate | PASS | 使用者逐項核准 191／192／193、WP86、strict successors 與 dependency 語意 |
| Change inventory | PASS | 191／192／193 均為 schema-only；無新增 seed、business-row-backfill 或 destructive change |
| Static release gate | PASS | 20 manifests strict PASS；default unique ordered chain；111-part validation manifest／full-SQL |
| Descriptor gate | PASS | 191 typed enum classifier與192／193 owned descriptors；focused tests通過 |
| Read-only plan gate | BLOCKED | source 既有 part 153 partial、part 186 drift；189～193 唯讀 classification 為 exact |
| Engine verification gate | NOT_RUN | disposable E2E 因未配置明確 `lu_test_*` database 而 skip |
| Developer acceptance gate | NOT_RUN | 未執行 updater apply；未修改既有 `union_db` |

總狀態：`DB_CHANGE_NOT_READY`。

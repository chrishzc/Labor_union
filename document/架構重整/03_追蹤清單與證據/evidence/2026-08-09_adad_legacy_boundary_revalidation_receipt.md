---
scope: 08_ADAD卸載與Legacy資料邊界
status: verified
verified_at: 2026-08-09
---

# ADAD 卸載與 Legacy 資料邊界驗證收據

- 封存規格：`../../04_已完成與上線封存/superseded_specs/08_ADAD卸載與Legacy資料邊界.md`
- 追溯決策：19、20、43 號決策／Work Package。
- `.agents/skills/adad-workflow` 不存在；Git hooks 只有 `.sample`，且 `.gitignore`
  忽略 `history/adad/`。legacy `system_map*` 保留為歷史檔案，production roots 沒有載入它們。
- legacy Finance Import reprocess 的 `--apply` 與 service apply 在取得 DB connection 前
  fail-closed；正式寫入只能走 typed Preview／Apply。
- Writer Inventory v3 scan roots 含 `services/`；validator 完整覆蓋 658 個 identity，
  `approved_to_remove=0`，缺 disposition 會 fail-closed。

```text
pytest reprocess / retirement / writer inventory focused suite
15 passed in 1.97s
validate_writer_inventory_v3_dispositions.py
records=658 approved_to_remove=0
```

## 2026-08-09 current-source revalidation

- Runtime Python source no longer carries retired-workflow labels. The only remaining
  `system_map*` occurrences are preserved historical provenance and are not scanned or
  loaded as runtime code.
- The frozen fake-data entrypoint remains fail-closed, but now directs future fixture work
  to an independent script and tests rather than a retired workflow.
- Disposable schema names used by Finance Import recovery and preserved-database cutover
  are neutral operational names; they do not encode a retired process.
- 當時的 UI API／DB migration 歷史草案已於文件整併時刪除；它不是現行實作 gate，現行
  UI／API 邊界以正式基線與 active Work Package 為準。

```text
pytest legacy boundary / frozen generator / Finance Import recovery / preserved cutover
52 passed, 2 skipped in 1.88s
```

The two skips require an explicitly configured disposable MySQL container; neither uses a
production database. `git diff --check` for this improvement unit is clean.

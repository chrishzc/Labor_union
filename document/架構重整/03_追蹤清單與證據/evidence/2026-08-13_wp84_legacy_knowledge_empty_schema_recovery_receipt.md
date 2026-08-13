# WP84 Legacy Knowledge Empty Schema Recovery Receipt

- date: 2026-08-13
- source revision: working tree based on `27c2a63e`
- authorization: 使用者明確核准建立 WP84
- scope: exact、全空、無外部 inbound FK 的 legacy Knowledge schema，只在 candidate 重建

## Gate 結果

| Gate | 狀態 | 證據 |
|---|---|---|
| Scope | PASS | `84_Legacy_Knowledge_Empty_Schema_Recovery_Work_Package.md` |
| Change inventory | PASS | WP84 的 schema-only／system-seed／business-row-backfill／destructive inventory |
| Static release | PASS | canonical 148／163 與 release identity 未變；唯讀 plan 顯示兩者 exact；working tree 的未提交 WP80 catalog 不屬於本 WP84 commit |
| Descriptor | PASS | runner 完整比對 legacy columns、indexes、FK、checks、triggers；unknown metadata drift 測試阻擋 |
| Read-only plan | PASS | `.venv\Scripts\python.exe -m scripts.update_local_database` exit 0；未寫入 DB |
| Engine verification | PASS | Docker MySQL：WP84 + WP78 共 21 passed；source→dump→candidate→apply→verify 與既有 partial recovery 均通過 |
| Developer acceptance | NOT_RUN | 無法存取回報問題之開發者本機 DB；尚未執行其同名替換 |

## Failure model evidence

- fail-before-fix：legacy fixture 原本被 148／163 判為 drift，2 tests failed。
- exact empty：candidate 重建後 148／163 exact，source schema SHA-256 不變。
- nonempty：read-only plan 以 `legacy Knowledge tables are not empty` 阻擋。
- metadata drift：新增未知欄位時固定判為 drift。
- external reference：bounded context 外 inbound FK 於 read-only plan 阻擋。
- regression：`tests/test_preserved_database_plan_contract.py` 18 passed。

## 結論

程式與 disposable engine evidence 已完成；其他開發者的實際 DB 尚未執行 developer acceptance，
因此整體 gate 結論為 `DB_CHANGE_NOT_READY`，不得宣稱該機器已完成升級。

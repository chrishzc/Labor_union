---
doc_type: evidence-receipt
declared_status: awaiting-engine-and-developer-acceptance
date: 2026-08-13
owner: Global Migration / LINE
work_package: ../../02_決策與退役執行記錄/79_LINE_Runtime_Release_Catalog_Recovery_Work_Package.md
---

# WP79 LINE runtime release catalog 恢復證據

## 結果

- preserve-data catalog 已依 ordinal 收錄 179、184、185、186。
- 補齊 184 descriptor artifact 原先缺少的 SHA-256；SQL 與 descriptor 內容未修改。
- catalog、客服與身分管理 focused regression：`43 passed`。
- 更新 `.env` 後本機唯讀 plan 通過；186 被辨識為已發布 legacy shape 並列入 `parts_to_resume`。
- 186 未知欄位型別的 negative test 維持 fail closed。
- disposable MySQL 8.4 已完成 source dump → candidate restore → 186 apply → exact，來源仍維持 partial。

## DB gate

| Gate | 狀態 | 證據 |
|---|---|---|
| Scope | PASS | WP79 與 2026-08-13 人工修復指示 |
| Change inventory | PASS | WP79 DB change inventory |
| Static release | PASS | 四個 manifest hash 與 focused catalog tests |
| Descriptor | PASS | 179／184／185／186 descriptor hash 載入成功 |
| Read-only plan | PASS | `parts_to_resume` 包含 186；185 列入 `parts_to_apply` |
| Engine verification | PASS | disposable MySQL 8.4：`1 passed` |
| Developer acceptance | NOT_RUN | 尚未操作開發者目標 DB |

總結：`DB_CHANGE_NOT_READY`，仍需在開發者環境執行 updater 並保存實際 replacement receipt。

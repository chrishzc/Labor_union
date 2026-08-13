# WP76 Migration Release Integrity 與 Readiness 驗證收據

- 日期：2026-08-13
- Work Package：`76_Migration_Release_Integrity_and_Local_Startup_Readiness_Repair_Work_Package.md`
- target policy：實作驗證使用 `lu_test_*`／一次性 Docker MySQL；最終 Developer acceptance 由使用者
  在另一台無 Git 的本機開發主機執行，該主機確認無需保留業務資料後重建 `union_db`
- release id：`labor-union-wp72-2026-08-13-v1`

## 已通過

1. part 61 恢復為 published strict UTF-8/LF bytes；SHA-256：
   `5844bef63d2eb05c5fd612cf8f585c7ccae06eb9db292591c41cebfca7230986`。
2. part 153 保持唯一 retirement artifact；fresh canonical MySQL 最終不存在退役 table。
3. default release chain 的 descriptor 與所有 schema artifact 都執行 exact hash 驗證。
4. `scripts.update_local_database` catalog error 為 bounded JSON、exit code 2；不再於 import-time 顯示 raw traceback。
5. Windows launcher 與 smoke-test 均在第一個 service 前執行 `--require-current`。
6. 最後 source/header 編輯後的 WP73／WP76 focused regression：`109 passed, 2 skipped, 3 xfailed`；兩個 skip
   均要求明確 disposable container，三個 xfail 是 WP73 true no-write fail-before evidence。
7. 指定 `mysql_db` 後，WP74 source → candidate → apply → verify：`1 passed`。
8. 一次性 MySQL `union_db` default preview：`parts_to_apply=[]`、`parts_to_resume=[]`，part 153
   位於 `exact_parts`；`--require-current` 回 `status=current`。兩個一次性容器均以 `--rm` 移除。
9. `scripts/build_validation_schema_release.py --check` 與 `git diff --check` 通過。

## 未完成／限制

- 目標主機驗收由使用者人工回報，未保存或偽造該主機原始 log；回報內容為 `--require-current`、
  FastAPI `/docs`、Streamlit `:8501` 與 launcher 全部正常，無 1146 missing-table 訊息。
- 完整 pytest 在最後 readiness edge-case 修正前的診斷結果為 `1934 passed, 88 skipped, 3 failed`；
  不作為 final-state 通過證據。三項失敗為既有 verification
  receipts／writer inventory freshness gate：八份 receipt 指向已更新的 validation manifest／release，
  但其 DB runners 在目前環境有十個 skip；另 entrypoint queue 與 writer candidate hash drift 在本次
  tracked diff 之外。未手改舊 receipt digest，也未批次重建不相關 inventory。

## DB gate

| Gate | 狀態 | 證據 |
|---|---|---|
| Scope gate | PASS | 2026-08-13 人工核准 release integrity／readiness，另核准恢復 part 61 |
| Change inventory | PASS | published artifact restore；無 seed、backfill、business row 或 destructive target change |
| Static release gate | PASS | full-chain exact hash、validation manifest 與 generated release check |
| Descriptor gate | PASS | fresh MySQL 與 part 61 → part 153 retirement classification |
| Read-only plan gate | PASS | 一次性 `union_db` default preview 與 `--require-current` |
| Engine verification gate | PASS | fresh bootstrap 及 `lu_test_*` source → candidate → apply → verify |
| Developer acceptance gate | PASS | 2026-08-13 使用者於無 Git 目標主機完成 readiness、API、UI 與 missing-table 症狀驗收 |

總狀態：`DB_CHANGE_READY`；WP76 可標記 completed。既有 stale verification receipts 仍不得冒充重跑，
但不阻擋本次 migration／readiness 修復的 Developer acceptance。

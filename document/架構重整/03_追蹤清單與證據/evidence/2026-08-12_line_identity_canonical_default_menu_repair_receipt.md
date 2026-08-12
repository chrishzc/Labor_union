---
scope: LINE Identity Management canonical default menu repair
status: implementation-complete-local-deployed-live-proven
verified_at: 2026-08-12
work_package: 55_LINE_Identity_Canonical_Default_Menu_Repair_Work_Package.md
---

# LINE 身分解除 canonical default menu 修復驗收收據

## Live-drift 證據

2026-08-12 對目前設定資料庫執行唯讀交易，未保存任何變更，結果如下：

- `line_configuration_current` rich menu revision 10 的 `default_menu` 為
  「服務登記／服務說明」。
- `line_rich_menu_publication_tasks` 已有 revision 8、9 的新版 `default_menu` published task。
- legacy `line_rich_menu_publications` 的 current `default_menu` 仍是 2026-08-09 publication 1，
  按鈕為「訂單查詢／尋找專員」。
- 診斷時最近三筆解除 request 均完成且指向 legacy publication 1。

證據只保留 menu revision／publication 與去敏狀態，不包含 LINE User ID、姓名、電話或 token。

## 修復內容

- `MySqlLineIdentityManagementRepository.default_menu_publication()` 改從
  `line_rich_menu_publication_tasks` 選擇最新 published `default_menu`。
- stage 13 新增 `canonical_default_menu_publication_id` FK；新 request 不再寫 legacy
  `default_menu_publication_id`。
- legacy FK 改為 nullable，並以 check constraint 保證每筆 request 只能擁有 legacy 或
  canonical 其中一種 publication source。
- read model 使用 canonical-first `COALESCE`，既有 legacy request 維持可讀且不回填、不改寫。
- release manifest 明確要求 API、LINE worker、Streamlit 同版 restart；本收據不授權套用 migration、
  restart 或呼叫 LINE provider。

## 驗證結果

- 聚焦身分解除：`13 passed in 0.82s`。
- 相鄰 Rich Menu／migration：`8 passed in 1.20s`。
- 擴大 LINE 身分、Rich Menu、客服與 release，warnings-as-errors：
  `29 passed, 1 deselected in 1.33s`。
- schema loader／disposable bootstrap／既有 v9 release：`8 passed in 1.36s`。
- disposable MySQL 完整 bootstrap 至
  `168_line_identity_canonical_menu_publication.sql` 成功；legacy 與 canonical FK 均存在，
  兩欄皆允許兼容歷史的 `NULL`。
- disposable MySQL rollback E2E：legacy publication ID 101 與 canonical publication task ID 2
  同時存在時，新 request 選 ID 2、legacy FK 為 `NULL`、canonical FK 為 2、provider menu 為
  canonical；另一筆 stage 12 legacy request ID 101 可正確讀回 completed 狀態。
- `git diff --check`、Python compile、JSON strict UTF-8 與敏感資訊 pattern scan 通過。
- disposable 測試庫 `lu_test_line_identity_menu_20260812` 已於驗證後刪除。

## 2026-08-12 本機部署與 live smoke

- 使用者明確授權套用新版供直接測試；部署目標經 preflight 確認為本機 `union_db`、
  MySQL 8.0.46，套用前為 exact stage 12、canonical stage 13 欄位不存在。
- maintenance window 開始時 API、Streamlit 與 LINE worker 均未執行；只有 MySQL／Redis 容器存活。
- 套用前建立全庫 single-transaction dump，含 routines、events、triggers 與 hex blob：
  `scratch/line-identity-stage13-deploy-20260812/union_db_pre_line_stage13_20260812.sql`；
  size 1,562,815 bytes，SHA-256
  `d9ded96dc7455af630e03fe9532ad7ef95dbcdfa2397a291d01078d1c84acc55`。該 artifact 位於
  Git ignored scratch，含受保護資料，不得提交或外傳。
- 備份已還原至 disposable `lu_test_line_stage13_backup_verify`；來源與還原庫均為 222 張 base
  table，所有逐表 row count 完全一致。驗證後 disposable database 已刪除。
- stage 13 manifest hash 驗證通過後，對 `union_db` 執行單一 atomic `ALTER TABLE`；3 筆既有
  revocation history 保留，legacy FK、canonical FK 與 publication-source XOR constraint 均通過
  post-schema verification。
- 啟動同一工作樹版本 API、canonical LINE worker 與 Streamlit。live smoke：API HTTP 200、
  Streamlit HTTP 200、worker canonical heartbeat age 1 秒、`last_error_code=NULL`、未 stopped，
  runtime stderr error scan 通過。
- 依使用者授權修正最新 completed revocation request 3：不改寫 binding／revocation history，
  只透過 LINE Rich Menu provider 把該帳號明確 link 至 canonical publication 5；provider
  readback 回傳同一 Rich Menu，確認外部副作用成功。

## 既有非本次失敗

- 未排除時，`test_line_customer_service_first_release.py` 的既有安全測試發現
  `line/static/staff_order_search.html` 仍含 `userId`；本次 write set 未包含該檔，未順帶修正。
- Global schema 全檔測試另發現既有重複 `101_` prefix，以及 `init_db.main()` 測試未隔離 pytest
  argv；part 168 的 prefix、loader、完整 MySQL bootstrap 與 release metadata 均已另行通過。

## 部署後邊界

- 本次是本機測試環境 deployment，不是 Git commit／push 或其他主機 release；未 stage、commit、
  push，也未操作其他資料庫或帳號。
- 僅修正最新 completed revocation request 3；較早的歷史 request 1、2 未執行額外 provider relink。

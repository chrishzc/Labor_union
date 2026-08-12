# 52. LINE 審核、Rich Menu 發布與管理員 Session 政策決策

## 決策來源

- 決策日期：2026-08-09
- 決策者：系統業務負責人
- 對應基線：`01_規格基線/17_External_Integration_LINE_Access正式規格.md`

## 已採用政策

### LINE 身分／綁定審核

月嫂身分認證與客戶 LINE 重新綁定，從送件起持續留在 `pending` 待辦佇列；不設到期日、
不標示逾期、不自動核准或拒絕，也不以時間驅動轉派。只有具審核能力的真人管理員明確
approve、reject 或取消，才會改變案件狀態。

### Rich Menu 對外發布

不採雙人覆核。單一具 `line.menu.publish` 的管理員必須依序：

1. 查看目前設定版本的預覽；
2. 取得同一設定版本的 server-side preview receipt；
3. 勾選二次確認後才 Apply。

receipt 必須綁定管理員、menu、設定 revision 與 fingerprint；設定已變或 receipt 已使用時，
Apply 固定拒絕，必須重看預覽。

### 管理員 Session

每次有效請求將閒置期限滑動更新為 30 分鐘；首次登入起算最多 8 小時。即使管理員持續
操作，8 小時 absolute deadline 到達後仍必須重新輸入密碼。

## 未採用／待決項目

- 不啟用 Rich Menu 雙人覆核。
- 不啟用 LINE review 的 timeout、escalation 或 automatic decision。
- 不採用 Break-glass credential；不建立緊急帳號、繞過 API、權限復原捷徑或演練流程。
- Security Audit policy：任何已登入的管理員都可查最近兩年的 audit 摘要，不需
  `admin.audit.read` capability。清單遮罩 IP；所有回傳明細遮罩 token、password、Authorization、
  LINE user ID、電話與身分證；所有已登入管理員可直接查看已遮罩明細。兩年以上紀錄每日
  移至受限 archive，archive 不自動刪除。查看此唯讀明細不必填原因，也不產生另一筆 Domain
  decision audit；原因僅屬會改變資料或核准結果的 Command。

## 實作與驗證對照

- `subsystems/line/identity_review_workflow.py`
- `subsystems/line/rich_menu_publication_workflow.py`
- `subsystems/access/authentication_session.py`
- `db/schema_parts/150_line_publication_confirmation_and_session_expiry.sql`
- `db/schema_parts/151_admin_security_audit_retention.sql`
- `api/routes/admin_audit.py`
- `subsystems/access/security_audit_query.py`
- `db/migration_releases/labor_union_2026_08_09_v4.json`
- `tests/test_line_access_policy_boundaries.py`
- `tests/test_migration_release_v4_metadata.py`

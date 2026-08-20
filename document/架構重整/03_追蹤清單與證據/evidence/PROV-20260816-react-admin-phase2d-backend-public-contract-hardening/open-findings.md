# Phase 2D-H Open Findings

| ID | Finding | Status | Required closure |
|---|---|---|---|
| D-H-01 | repository severity placeholder曾穿透Application | RESOLVED_IN_CODE | registry enrichment與focused regression已通過 |
| D-H-02 | Anomalies／Recovery／Import Warning public schema使用寬鬆`str` | RESOLVED_IN_CODE | Domain enum與OpenAPI enum test已通過 |
| D-H-03 | 真disposable MySQL closed-loop未執行 | ACCEPTED_RISK_NOT_RUN | 2026-08-17使用者明確豁免建立額外DB；既有`union_db`只用於唯讀UI驗證，不跑mutation |
| D-H-04 | 舊FastAPI程序未載入Phase 2D-H候選 | RESOLVED_RUNTIME | 精確重啟port 8000後，同一TOTP Session完成兩query family Network→DOM |
| D-H-05 | 全前端suite有12個既有Orders failures | OPEN_BLOCKER_OUT_OF_SCOPE | 由Orders owner另案修復；本包禁止越界修改 |
| D-H-06 | MasterLayout有2個既有lint warnings | OPEN_BLOCKER_OUT_OF_SCOPE | 由Shell owner另案處理；本包禁止越界修改 |
| D-H-07 | pytest cache因根`.pytest_cache`權限產生warning | OPEN_ENVIRONMENT | 修正測試環境cache配置；不影響34個focused assertions結果 |
| D-H-08 | global `git diff --check`命中既有DataImport三處trailing whitespace | OPEN_BLOCKER_OUT_OF_SCOPE | DataImport owner另案處理；本包scoped source diff無trailing whitespace |
| D-H-09 | API healthy且頁面query成功後，Shell仍顯示「系統離線」 | OPEN_OUT_OF_SCOPE | System Status／Shell owner檢查polling與refresh；不得在Anomalies包越界修正 |
| D-H-10 | 同一帳密→TOTP Session下，Orders summary與System Status GET回401，但Anomalies兩個bounded clients均回200 | OPEN_OUT_OF_SCOPE | Auth/shared transport與各bounded client owner檢查fresh in-memory token composition；不得在Anomalies包複製token或越界修正 |
| D-H-11 | canonical disposable schema bootstrap在連線／建立DB前，因Phase3新增scenario不符合既有scenario/fixture validator contract而`KeyError: test_kinds` | DEFERRED_UPSTREAM | 已另立Phase3 Scenario Canonical Validator Compatibility amendment；本次依人工裁決停止bootstrap，不繞過gate或操作`union_db` |

未知或未執行項目沒有標成resolved。Phase 2D-H依人工closeout標記`completed`；Phase 2D Query與任何
mutation successor仍依各自工作包狀態判定，不由本回執自動完成或解鎖。

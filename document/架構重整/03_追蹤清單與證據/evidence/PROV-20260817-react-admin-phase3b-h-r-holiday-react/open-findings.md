# Phase 3B-H-R open findings

日期：2026-08-22

1. `BLOCKED_SPEC_DRIFT`：canonical Holiday scenario revision 1仍為query-only／zero-write、replay
   not-applicable及no-browser-execution，未涵蓋已核准H-R mutation。由
   `PROV-20260822-react-admin-phase3b-h-r-holiday-mutation-scenario-lineage-successor`承接。
2. `NOT_RUN_BROWSER_VARIANTS`：same-key replay、stale、conflict與rollback已有adapter／backend focused與MySQL
   evidence，但本輪未逐項做Chrome browser mutation，不冒充browser PASS。
3. `AUTH_LIMITATION`：採development local bypass；真TOTP未執行。
4. `AUTOMATION_LIMITATION`：Chrome程式化date fill未可靠提交React change；本輪Apply使用預設日期。一般使用者
   原生date picker未見UI錯誤，且unit test覆蓋state request identity。

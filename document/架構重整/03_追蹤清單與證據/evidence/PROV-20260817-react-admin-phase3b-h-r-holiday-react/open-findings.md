# Phase 3B-H-R open findings

日期：2026-08-22

1. `RESOLVED_SPEC_DRIFT`：canonical Holiday scenario已由核准successor升為revision 2，涵蓋controlled
   mutation、same-key replay、stale、conflict、rollback與outcome-unknown recovery；此結果只解除metadata blocker。
2. `RESOLVED_BROWSER_VARIANTS`：stale、rollback、same-key replay、conflicting-draft pre-transport guard及
   server-side 409 typed DOM均有Chrome＋真FastAPI＋MySQL evidence；controlled deterministic UUID僅存在於
   已刪除的臨時Vite config，production source與transport response未修改。
3. `ACCEPTED_AUTH_LIMITATION`：依最新人工裁決採development local bypass；真TOTP未執行，狀態為
   `NOT_RUN_ACCEPTED_DEVELOPMENT_BYPASS`，不冒充真TOTP PASS。
4. `AUTOMATION_LIMITATION`：Chrome程式化date fill未可靠提交React change；本輪Apply使用預設日期。一般使用者
   原生date picker未見UI錯誤，且unit test覆蓋state request identity。

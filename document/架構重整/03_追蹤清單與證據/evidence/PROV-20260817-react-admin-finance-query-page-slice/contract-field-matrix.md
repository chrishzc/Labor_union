# Finance Query Page-Slice Contract Matrix

Status: frozen-local-candidate（2026-08-17）

| Query | Strict data | UI rule |
|---|---|---|
| Client Receipt | case/account version、bank facts、obligations | 不從金額推導settled |
| Staff Payables | staff/version、obligations、events、server payout_status | 不從balance推導paid |
| Accounts Payable | target date、count/total、server-masked rows | 完整bank/id card禁止JSON/DOM |
| Finance Import | batches、manifest、review rows、reprocess runs | status/actions原字顯示，0Apply推導 |

四組clients均fresh memory bearer、GET-only、strict envelope/nested decode、AbortSignal、identity/cursor/aggregate fail-closed。


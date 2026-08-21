# Phase 3B-H-R browser smoke receipt

日期：2026-08-22

狀態：`BUSINESS_FLOW_PASS / DEVELOPMENT_AUTH_BYPASS / CLEANUP_PASS`

## Existing development DB

- Chrome URL：`http://127.0.0.1:5174/admin/#scheduling`。
- Holiday Query顯示source `mysql:holidays/v1`、version與16筆server root facts。
- zero-write Preview顯示server fingerprint與`none` impacts；未點Apply，既有DB writes=0。

## Owned disposable DB

- database：`lu_test_phase3bhr_browser_20260822a`；credential class root；development allowlist。
- Query為空calendar，Preview upsert `2026-08-22`／`Phase3B-H-R controlled holiday`。
- Apply receipt idempotency key：`holiday-apply-8dc0270b-5a0c-45d5-b80b-927ff8651bda`。
- post-commit re-query為`observed`，calendar列出新增holiday，receipt仍顯示於DOM。
- DB readback為holiday 1 row、receipt 1 row；cleanup後`exists_after_cleanup=false`。
- 原development服務恢復：health=200、Holiday GET=200／16 rows、Chrome online/query-ready。

## Auth and automation limitation

依全域人工裁決使用development `ACCESS_CONTROL_PROFILE=local_bypass`，沒有執行或聲稱真TOTP。Chrome對
`input[type=date]`的程式化fill沒有可靠提交React change，因此controlled Apply採頁面預設日期；名稱、reason、
Preview、Apply與re-query均由可見UI操作完成。

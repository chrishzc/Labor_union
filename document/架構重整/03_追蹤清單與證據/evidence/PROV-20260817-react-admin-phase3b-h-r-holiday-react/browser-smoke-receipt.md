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

## 2026-08-22 controlled browser variants

- owned DB：`lu_test_phase3bhr_browser_variants_20260822b`；development allowlist／root credential class。
- Chrome在fresh Preview後，由另一個正式Holiday subsystem command建立8/23 root fact；再按Apply得到
  DOM state `stale`及typed `stale_preview` alert。readback：8/22 target rows=0、setup rows=1、receipts=1，
  證明拒絕與rollback零partial write。
- fresh re-query後8/22 Apply成功，DOM=`observed`並顯示receipt
  `holiday-apply-04108f2f-113b-4c4c-88c2-7146840af31a`；再次按Apply仍為同receipt。readback：
  holidays=2、receipts=2（含setup）、browser key receipts=1，same-key replay未重複寫入。
- 將已observed draft改成不同名稱後，UI立即清除receipt、回`query_ready`並停用Apply；合法UI無法帶舊key
  送不同payload。server-conflict 409 DOM未以偽造transport執行，維持`NOT_RUN`。
- disposable API停止後，current 8000恢復`.env` DB；health=200、Holiday GET=200／16 rows；owned DB
  scoped drop readback `EXISTS_AFTER_CLEANUP=0`。Chrome已恢復current Scheduling query-ready。

## 2026-08-22 server conflict closure

- owned DB：`lu_test_phase3bhr_conflict_20260822a`；fresh bootstrap release v9 PASS。
- 只在驗收用且已刪除的臨時Vite config加入pre-transform，將Holiday flow UUID固定；未修改production source、
  request body、server response或FastAPI handler。
- 同一Chrome UI先Apply `Phase3B-H-R deterministic winner`，receipt key為
  `holiday-apply-11111111-1111-4111-8111-111111111111`；再Preview／Apply不同名稱但相同key。
- 真FastAPI access log為`POST /api/v1/holidays/apply 409 Conflict`；DOM state=`conflict`，alert為
  `[idempotency_key_conflict] 國定假日變更請求未通過契約驗證。`。
- 唯讀readback：`holiday_name=Phase3B-H-R deterministic winner`、receipts=2（含前一個獨立key）、
  deterministic key count=1，證明conflicting payload沒有partial write或重複receipt。
- owned DB cleanup readback `EXISTS_AFTER_CLEANUP=0`；臨時Vite config已刪除。current 8000 `/health`=200、
  Holiday GET=200／16 rows，5174與Chrome current query-ready均恢復。
- true-TOTP未執行；依最新人工裁決採`NOT_RUN_ACCEPTED_DEVELOPMENT_BYPASS`，不宣稱真TOTP PASS。

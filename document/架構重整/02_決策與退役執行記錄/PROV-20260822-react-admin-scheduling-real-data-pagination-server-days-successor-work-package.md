---
doc_type: work-package
declared_status: completed
identity: PROV-20260822-react-admin-scheduling-real-data-pagination-server-days-successor
date: 2026-08-22
owner: Scheduling / React Integration Owner
domain: Scheduling
authority: latest-explicit-human-operations-frontend-priority
db_change: none
---

# Scheduling真實資料續頁與server days successor

## Business scenario

工會人員以真實名冊操作排班日曆時，名冊可能超過首個bounded page，月曆日期也必須以Scheduling server
projection為準。React不得只顯示前50人，也不得在server `days[]`之外自行生成看似存在的日期狀態。

## Scope與不變量

- Staff selector每頁固定20筆，依`next_cursor`／`after_id`明確載入更多，追加時依Staff identity去重。
- calendar header、weekday、occupancy grid與span寬度只使用selected Staff的server `days[]`；未回傳日期不補值。
- 今日顯示使用`Asia/Taipei`，不得受操作者browser local timezone影響。
- Leave substitution request的`substitute_staff_id`、`is_double_pay`、`leave_request_id`與
  `expected_leave_request_version`皆為required typed fields（值可依契約為null）；缺欄位在fetch前fail closed。
- 不改API public contract、Domain規則、mutation授權、DB、entry switch或production host。

## 驗收結果

- `scheduling_current_page.test.tsx`覆蓋page size 20、cursor續頁、追加Staff與只呈現3個server days。
- Leave client覆蓋缺required resolution/link identity fields零fetch拒絕。
- focused React：7 files／41 PASS；production build PASS。
- 既有`SchedulingPage` entry測試仍有一則React `act` warning，未影響斷言；後續測試清理另行收斂。
- fixture gate PASS；`lu_test_*`真MySQL/API/browser與工會主機真實資料均尚未執行。

DB gate：Scope／Change inventory `PASS`（0 DB）；其餘`NOT_RUN`，結論`DB_CHANGE_NOT_READY`。

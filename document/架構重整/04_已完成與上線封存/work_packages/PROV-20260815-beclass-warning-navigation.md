---
doc_type: work-package
declared_status: completed
date: 2026-08-15
owner: Case Import / Anomalies
priority: P0
---

# Client／Staff BeClass 警示中心導航 Work Package

## 範圍

承接 WP90 與使用者的異常中心薄層裁決。BeClass immutable review outbox 在 `review_opened` 時，僅將
已於 warning type 審核佇列登錄、可由 source kind 與 issue code 唯一判定的問題投影為 field-level
tracking task。異常中心只能顯示去敏內容、更新 tracking status，並以 UI-neutral action 導向既有
Client／Staff BeClass 匯入業面；不再嵌入或呼叫 corrected-payload review UI。

## 已採用 mapping

- Client：`姓名`、`行動電話` → `CLIENT-BECLASS-SOURCE-001`。
- Staff：`身分證字號` → `STAFF-BECLASS-IDENTITY-001`；`姓名` →
  `STAFF-BECLASS-NAME-001`；`duplicate_identity_card` → `IDENTITY-002`；
  `identity_name_mismatch` → `NAME-002`；`staff_field_invalid:<field>` → `FIELD-002`。
- `duplicate_query_no`、client candidate／source conflict 與未登錄 legacy code 不建立 task 或 action，
  保留 canonical anomaly，直到 owning Domain 補齊唯一業務語意。

## 不變量與驗收

projection 使用 review root 的 immutable source event、masked identifier 與 bounded source metadata；replay
零新增。resolved review 不會由此消費者自動把 tracking task 標成資料已修正。沒有 schema、migration、
Client／Staff root command、React runtime 或 LINE side effect。需通過 focused、disposable MySQL replay、
UI navigation 及 no-raw-payload evidence 後才可結案。

## Closure

WP90 completion receipt 已覆蓋 BeClass warning projection、typed navigation、replay 與 no-raw-payload
驗收；本文件不再保有 active write set。

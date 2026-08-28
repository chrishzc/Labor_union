# Anomaly case binding read model 規格缺口

- `doc_type`: specification-gap
- `declared_status`: proposed
- `authority_status`: REQUIRED
- `owner`: Anomalies projection
- `consumer`: Orders cancellation／historical operational workbench
- `current_package`: WP-HOB-D

## 1. 問題與不可接受的替代方案

WP-HOB-D 要求取消 Apply 後回讀 Orders、Client Finance、Staff Payables 與該案件仍 active 的異常。
現行 `anomaly_current_alerts` 沒有 canonical case binding；`source_identity` 依 definition 使用不同格式，
`display_snapshot` 只是顯示資料。以下做法固定禁止：

- React 下載全域 active alerts 後自行比對文字或 JSON；
- SQL 使用 `source_identity LIKE` 猜案件；
- 把 `display_snapshot.case_no` 當不可漂移的 owner root；
- 在 current alert 只加一個 `case_no`，因排班 overlap 等一筆異常可能同時涉及兩個案件。

## 2. 建議裁決 ACB1：多對多 current binding projection

建議新增 rebuildable `anomaly_current_alert_case_bindings`：

- 主鍵／唯一鍵為 `(alert_fingerprint, case_no)`，FK 指向 `anomaly_current_alerts.fingerprint` 與
  `orders.case_no`，刪除／更新皆 `RESTRICT`；
- index 至少涵蓋 `(case_no, alert_fingerprint)`；active／workflow 狀態仍只由 current alert擁有，
  binding table不複製狀態；
- 每次 canonical projector create／update／resolve／reopen 時，在同一 projection UoW 以 producer 提供的
  typed、排序、去重 `case_bindings` 更新 current binding；不得由 snapshot事後解析；
- 一筆 alert可綁0、1或多個案件。非案件型 Finance／LINE／Staff alert可為0；Scheduling overlap可為2；
- historical rebuild是明確 bounded Command，按 definition owner重新讀根事實；不得把舊snapshot backfill
  當成 canonical evidence。無法唯一還原的既有 alert列入unresolved review並保持全域可見；
- authenticated `GET /api/v1/anomalies/cases/{case_no}` 只透過binding join查詢，支援active-only與穩定cursor；
  不提供generic resolve，也不修改owner root。

這是 derived read model，不改變異常 active predicate、fingerprint、owner、人工修正方式或取消公式。

### 2.1 ACB1尚待固定的exact contract

1. 每個definition在registry明確宣告case cardinality：`0`、`0..1`、`exactly 1`或`0..N`，
   並固定`N`上限；不得由projector在runtime自行放寬。
2. 明確區分`resolved_zero_cases`與`unresolved_case_binding`；沒有binding row不足以代表兩者任一。
3. typed binding是否需`binding_role`由definition宣告；Scheduling雙案overlap不得丟失兩側語意。
4. `ProjectAlertRequest`必須包含`source_version`、`source_event_identity`、sorted unique
   `case_bindings`與binding resolution state；checkpoint／replay fingerprint必須包含完整binding payload。
5. binding集合變更固定由同一projection UoW建立新current set；歷史lineage不得以
   無版本`DELETE + INSERT`消失，必須可重放、可rollback且可證明source event。
6. historical rebuild需逐definition列canonical producer root與unresolved policy；HCM可使用既有
   `case_import_hcm_review_case_bindings`，BeClass／Historical review若無canonical root不得從snapshot猜。

### 2.2 不新增schema的短期WP-HOB-D邊界

可為取消工作台先建definition-specific、唯讀typed case resolver：每個resolver直接查canonical
owner root，並使用producer的pure identity builder精確對應alert；無法唯一解析的alert僅留在
全域清單，case-scoped query不顯示也不猜。此方案：

- 不修改`anomaly_current_alerts`、不backfill、不建generic resolver；
- 只能覆蓇已證明canonical case root的definition，每個resolver有獨立focused oracle；
- 可作WP-HOB-D取消後readback的過渡解，不能宣稱已完成ACB1通用多對多投影。

2026-08-27 source execution snapshot：definition-specific readback已對
`RECEIVABLE-001`、`CLIENTPAYABLE-001`、`RETURN-001`與`SCHEDULE-006`建立唯讀candidate，
主代理複驗`18 passed`。Client Finance必須由caller傳入BusinessClock的`as_of`，並精確比對
`daily_root_source_version(as_of, aggregate_version)`；Scheduling精確比對aggregate version。單一
definition的alert／owner／checkpoint使用同一SQL statement snapshot；多definition在無共享
snapshot／UoW時回`consistent_snapshot_required`，其餘definition回明確unavailable。本候選尚未發布
API／UI／DB runtime，也不改變ACB1的`AUTHORITY_REQUIRED`／`DB_CHANGE_NOT_READY`。

## 3. Acceptance

1. 單案件、雙案件與零案件 alert binding皆可機械區分，跨案件不混入。
2. 同一projection replay不重複binding；binding集合漂移與alert更新在同一UoW。
3. resolve後active-only查詢不列入，history/detail仍可由fingerprint讀取。
4. existing alert backfill有dry-run、count/fingerprint、unresolved review、replay與rollback evidence。
5. cancellation outcome確認後依序回讀receipt、Orders/card/stage、case-bound active anomalies；readback不可用不顯示假成功。

## 4. Database change gates

| Gate | 結果 | 證據／原因 |
|---|---|---|
| Scope gate | `BLOCKED` | ACB1尚未取得人工架構確認；WP-HOB-D只證明需要case-scoped readback，未固定binding storage。 |
| Change inventory | `BLOCKED` | 候選含schema-only binding table及既有alert business-row-backfill；需先核准ACB1與unresolved policy。 |
| Static release gate | `NOT_RUN` | 尚無合法release candidate。 |
| Descriptor gate | `NOT_RUN` | 尚未固定owned object。 |
| Read-only plan gate | `NOT_RUN` | 尚無release artifact。 |
| Engine verification gate | `NOT_RUN` | 前置gate未通過。 |
| Developer acceptance gate | `NOT_RUN` | 前置gate未通過。 |

總結：`DB_CHANGE_NOT_READY`。核准前不得新增欄位／表、回填既有alert或發布case-scoped endpoint。

```yaml
convergence:
  status: NOT_READY
  blockers:
    - ANOMALY-CASE-BINDING-ACB1
```

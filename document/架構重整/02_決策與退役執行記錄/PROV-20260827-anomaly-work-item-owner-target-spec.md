---
doc_type: specification-gap
declared_status: proposed
date: 2026-08-27
owner: Orders / Matching / LINE / Anomalies
current_item: CUR-ANOMALY-MANUAL-REMEDIATION-01
---

# 六個一般工作項的 owner target 契約

## 1. Objective 與 Authority

2026-08-27 人工已裁決 `ORDER-001`～`ORDER-004`、`DOC-SEND-001`、`LINE-002`
是 owner work item，不是 active anomaly。本規格只收旂既有 alert 如何安全移轉到真正可操作的
owner root；不改變 Orders／Matching／LINE 的業務完成條件，不以導覽、provider `sent`、任意
webhook、tracking status 或遷移 receipt 冒充完成。

## 2. Common observable contract

- `ANM-WI-01`：migration Query 只列出六碼 current active alerts，不修改 source Domain root。
- `ANM-WI-02`：Preview 必須回傳唯一 `target_domain / target_reference / target_version`、owner
  action link、根事實摘要、blockers 與 preview fingerprint；零寫入。
- `ANM-WI-03`：Apply 在同一 outer UoW 鎖定 alert 與 owner root，重讀 current version 並重算
  candidate。missing／ambiguous／stale／readback unavailable 固定零寫入且舊 alert 維持 active。
- `ANM-WI-04`：Apply 只 append immutable `reclassified_to_owner_work_item` disposition／receipt 並使
  legacy alert inactive；owner work item 本身維持可讀、可操作，history 可從舊 alert 導向 current root。
- `ANM-WI-05`：producer 只在 target query／migration／completion sweep 全部 PASS 後停止產生六碼；
  不得先停 producer 導致正常待辦消失。

## 3. Per-code proposed target

| Code | Proposed owner root | Canonical identity | Canonical version | Completion remains owned by |
|---|---|---|---|---|
| `ORDER-001` | Candidate Contact Pool | `case_no + pool_id` | 新增的 pool aggregate version；不得用 `max(event.id)` | candidate coverage／info-1 owner events |
| `ORDER-002` | Candidate Contact Pool | `case_no + pool_id + candidate_id` | 同一 pool aggregate version | accepted candidate 的 info-2 owner event |
| `ORDER-003` | Matching Plan communication | `case_no + plan_id + current recipient` | existing `communication_version` | current recipient-bound willingness |
| `ORDER-004` | Matching Plan communication | `case_no + plan_id` | existing `communication_version` | current customer decision event |
| `DOC-SEND-001` | Matching intent + canonical LINE delivery task | `intent_id + task_id + recipient + object digest` | 新增 task aggregate version | fixed object／digest／recipient terminal durable receipt |
| `LINE-002` | Canonical LINE delivery task + typed response root | `task_id + recipient + response root` | 新增 task aggregate version | recipient-bound typed response；不接受同 user 任意 webhook |

## 4. Failure, compatibility 與 exclusions

- legacy `matching_records`、`line_tasks`、`line_webhook_events` 可作 migration evidence，不是 target SSOT。
- 找不到唯一 current pool／plan／intent／task／response 時，舊 alert 留 active 並顯示具體 blocker；
  不建立假 target，不自動插入 owner root。
- 本包不發送 LINE、不重建 matching plan、不改客戶決定，不刪除舊 occurrence。
- `SCHEDULE-005` 為獨立 false-positive retirement，無 owner target，不受本契約的 schema 決策影響。

## 5. Acceptance

- `ANM-WI-A1`：六碼每一 active alert 都可唯一導向 current owner root，Preview 可讀取 exact
  version；沒有 target 時舊 alert 不消失。
- `ANM-WI-A2`：Apply 後 Anomalies active list 不再顯示 legacy code，Orders／Matching／LINE owner
  queue 仍顯示同一件待辦並可繼續操作。
- `ANM-WI-A3`：owner version drift、recipient 改變、plan superseded、task 重建、old response、任意
  webhook、provider success／unknown 全部 fail closed。
- `ANM-WI-A4`：same-key same-payload replay 回原 receipt；same-key different-payload conflict；partial
  batch 不影響其他 item，completion sweep 精確為零後才停 producer。
- `ANM-WI-A5`：React／Browser 從舊 history 進入 owner workbench，顯示 current root／version／
  action；不提供 generic anomaly resolve。

## 6. Source map 與待裁決

| Decision | Evidence | Owner |
|---|---|---|
| `ANM-WI-POOL-VERSION` | Candidate pool 可 `for_update=True`，但 current manual preview 以 `max(event.id)` 推導版本，不是正式 aggregate contract | Orders／Matching 規則書／人工確認 |
| `ANM-WI-LINE-TASK-VERSION` | canonical `line_delivery_tasks` 可鎖定 task，但 current snapshot 無 aggregate version | LINE 正式規格／人工確認 |
| `ANM-WI-ORDER12-TARGET` | ORDER-001／002 可導向 operational timeline 或 Candidate Contact Pool；兩者會產生不同 schema／action contract | 人工選擇；建議 Candidate Contact Pool |

```yaml
convergence:
  status: NOT_READY
  blockers:
    - ANM-WI-POOL-VERSION: owner 與人工需確認 Candidate Contact Pool canonical aggregate version；回到 Orders/Matching 規則書後編譯 additive schema package
    - ANM-WI-LINE-TASK-VERSION: owner 與人工需確認 canonical LINE task aggregate version；回到 LINE 規格後編譯 additive schema package
    - ANM-WI-ORDER12-TARGET: 人工需選擇 ORDER-001/002 的 owner root；建議 Candidate Contact Pool
```

`terminal_status`: `AUTHORITY_REQUIRED`

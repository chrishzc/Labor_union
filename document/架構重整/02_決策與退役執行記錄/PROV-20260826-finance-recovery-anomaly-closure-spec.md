# 三類財務追償／溢撥異常閉環規格

- 狀態：`SPEC_READY`
- spec identity：`PROV-20260826-finance-recovery-anomaly-closure-spec`
- Authority：2026-08-26 使用者明確要求每個異常均有人工修正，且自動解除必須符合正式規則書的真實業務流程。
- canonical owners：Government Subsidy、Client Finance、Staff Payables；Anomalies 只組合 typed capability 與投影。
- codes：`GOVSUB-006`、`client_over_refund_recovery_open`、`staff_overpayment_recovery_open`。
- controlling rules：`01_規格基線/06_Anomalies_Domain.md` 全異常人工 remediation；
  `14_Government_Subsidy_Domain.md` §4.5.1；
  `16_Staff_Payables與Client_Refund正式規格.md` §2.4.2、§3.5.1。

## Objective 與 observable outcome

操作者在異常中心看見上述任一 active alert 時，必須先看懂來源案件／人員、目前 remaining、觸發規則、
可用處置與完成條件，再由固定 source bindings 走 owning Domain Query／Preview → Confirm → Apply →
immutable receipt／root readback → anomaly recheck。部分處理更新同一 active alert；完整業務 predicate 成立
才自動解除並從 active list 消失。

## Requirements

### FRAC-R1：正確的異常生命週期

- `GOVSUB-006` 在 overpayment `pending_review` 時 active；authorized offset 或 return disposition 已提交且
  fresh readback 顯示不再 `pending_review` 時 inactive。後續 return payable 的實際付款進度不是本碼的
  disposition predicate，由既有政府退款單流程負責。
- client/staff recovery root 一建立且 remaining > 0 時，對應 recovery-open alert 即 active；不得等到銀行
  入款 matching 才建立。
- client/staff 每次合法 cash recovery 或 authorized adjustment 後，以 current owner root 的 remaining/status
  重新投影；cash recovery 後 remaining > 0 時保持 active 並更新 amount/version，
  `recovered|adjusted` 且 remaining=0 才 inactive。Client adjustment 可部分處理；Staff adjustment
  依 `16` 的 state machine 與 owner Domain oracle 必須一次等於全部 remaining，不存在部分
  staff adjustment 的中間狀態。
- projector 事件必須使用 monotonic source version、exact replay、immutable receipt；不能讀 anomaly workflow
  `resolved` 決定 active。

### FRAC-R2：真實規則與可理解 detail

每碼的 recovery/detail 至少顯示去敏 owner identity、current remaining NTD、current root status/version、
來源銀行／matching identity 的去敏 reference、觸發規則、合法分支、blocked reason 與完成 predicate。
PII、完整帳號、raw bank payload 不得穿透。Anomalies 不重算金額；值由 owner query／committed root 投影提供。

- Government Subsidy Query 必須提供 current overpayment、唯一 payer、合法 offset targets（claim item、batch、
  outstanding、version）與 return-recipient readiness；沒有合法 target 或 recipient account 時顯示 typed blocker。
- Client／Staff recovery Query 必須提供 current remaining/status/version 與既有 matched bank fact；沒有 matching
  時仍顯示 open recovery，並提供 owner workbench 的 matching／authorized adjustment 路徑，不可顯示假完成。

### FRAC-R3：人工 Preview／Apply

- `GOVSUB-006` 使用有限 `offset|return` disposition；offset 只接受 Query 回傳的合法 targets 與整數金額，
  return 使用 current payer receiving account snapshot、due date、reason、evidence。Apply 鎖定 fresh overpayment、
  target／recipient、version 與 Preview fingerprint。
- client/staff cash collection 只接受已驗證 canonical incoming bank fact 與唯一 recovery matching；authorized
  adjustment 需對應 owner capability、非空 reason/evidence 與 adjustment amount，不能偽造現金。
  Client adjustment amount 可小於 remaining 並繼續 active；Staff adjustment amount 必須精確等於
  fresh remaining，否則 fail closed。
- Apply 使用 stable idempotency key；same key/different payload、stale version、wrong owner、cross payer/staff/case、
  amount exceeded、used bank fact、missing evidence 全部零正式寫入並回 typed error。
- client/staff authorized adjustment 的 `evidence_reference` 必須是獨立 typed field，不得塞入
  `reason`。Apply 必須在同一 outer UoW 將它寫入不可變 recovery event／與事件唯一關聯的
  immutable receipt；command fingerprint 與 replay 必須納入該值。電話、現場或紙本通知只能作為
  evidence reference，不得被建構成虛構銀行入款。

### FRAC-R3A：Owning Domain recovery Query

- Government Subsidy 必須以 overpayment identity 回傳 current status/remaining/version、固定 payer、
  合法 offset targets 與 return-recipient readiness；target eligibility 由 owner 計算。
- Client Finance 必須以 case/recovery identity 回傳 current status/remaining/recovery version/account version，
  以及可選的 current matching；Staff Payables 以 staff/recovery identity 提供等價 typed view。
- Query 必須唯讀、strict closed schema 且去敏；不存在、owner mismatch、多筆 current matching、
  target/recipient 不可用時回 typed blocker，不得由 React 或 anomaly snapshot 推算。

### FRAC-R4：React typed dispatcher

- Dispatcher 只依已註冊 `form_schema_key` 選 typed renderer，不由 definition code 拼 endpoint。
- 三個 renderer 只使用各自 bounded owner client；source bindings readonly。輸入變更使 Preview 失效；Apply 在
  Preview 成功前 disabled。Apply timeout／unknown 必須以同 key 查已存在 receipt/readback，不盲目重送。
- terminal Apply 後重新 Query owner root 與 anomaly。只有 predicate inactive 才顯示「異常已解除」並移除；
  partial outcome 顯示新 remaining 並保留 alert；successor 則顯示明確 relation 與下一步。

### FRAC-R5：既有行為與界線

- 只允許為 client/staff recovery 不可變 evidence 所必需的 additive schema/release；不變更金額
  公式、status 語意或現有 identity。必須完整通過本機 fresh／preserve-data／descriptor 與 developer
  acceptance gate；不操作 `union_db`／production／provider，不建立通用 root editor。
- 保留 Finance Import correction 與 legacy Streamlit 行為；React 新 renderer 不重用 raw dict 或 legacy API client。
- claim、tracking、generic resolve、HTTP 200、outbox delivered、Preview success 或 Apply receipt 本身都不是解除條件。

### FRAC-R6：Projector poison event 人工復原

- 三個 finance recovery projector 的同一 event 最多自動嘗試 3 次；達上限後保留
  `failed` 及去敏錯誤、停止自動 claim，並必須繼續處理後續 event。
- dead-letter Query 只由 static allowlist 讀取 government/client/staff 投影 intent，回傳 owner domain、
  event id/type、attempt count、retry readiness、去敏 error code 與可用 action，不回 raw payload／PII。
- `retry_after_source_correction` 必須 Preview 重讀當前 dead-letter 與 owner root availability；Apply
  驗證 expected attempt count、fingerprint、reason、獨立 evidence reference、capability 與 idempotency，
  在同一 UoW 將該 event 重排並寫 `admin_command_receipts`。
- `supersede` 只在較高 source version 已成功投影且 fresh owner root/current alert readback 等價時開放；
  否則 typed blocker。它不將舊 outbox 偽裝成 delivered，也不解除業務 alert。
- retry/supersede 後必須重讀 owner root 與 anomaly；只有 FRAC-R1 各碼的業務 predicate
  成立才可顯示已解除。

## Current evidence／live-drift source map

| Code | 正式完成條件 | Current evidence | 必修 drift |
|---|---|---|---|
| `GOVSUB-006` | status 離開 `pending_review` 進合法 offset／return branch | registry descriptor、owner Preview／Apply／receipt 已存在 | consumer 只消費 `government_subsidy_overpayment_established`，不消費 offset／return outbox；detail 只有 identity/zero amount，React 無 renderer，operator inputs 未完整聲明 target／due date。 |
| `client_over_refund_recovery_open` | remaining=0 且 status=`recovered|adjusted` | owner collection／adjustment Preview／Apply／receipt 與 matched consumer 已存在 | alert 等 matching 才建立；open root 尚無 alert；partial update/readback 與具體 remaining detail 不完整；React 無 renderer。 |
| `staff_overpayment_recovery_open` | remaining=0 且 status=`recovered|adjusted` | owner collection／adjustment Preview／Apply／receipt 與 matched consumer 已存在 | alert 等 matching 才建立；`staff_overpayment_recovery_updated` 未被 anomaly consumer 消費；具體 remaining detail與 React renderer 缺失。 |

Evidence paths：

- `domains/anomalies/registry.py`
- `domains/anomalies/root_fact_projection.py`
- `subsystems/anomalies/government_overpayment_anomaly_consumer.py`
- `subsystems/anomalies/client_over_refund_recovery_anomaly_consumer.py`
- `subsystems/anomalies/staff_overpayment_recovery_anomaly_consumer.py`
- `infrastructure/mysql/government_subsidy_repository.py`
- `infrastructure/mysql/client_refund_reversal_repository.py`
- `infrastructure/mysql/client_over_refund_recovery_repository.py`
- `infrastructure/mysql/staff_payout_repository.py`
- `infrastructure/mysql/staff_overpayment_recovery_repository.py`
- `api/routes/government_subsidy.py`
- `api/routes/client_refund_reversal.py`
- `api/routes/staff_payout.py`
- `ui_react/src/pages/AnomaliesPage.tsx`

## Acceptance

- `FRAC-A1`：三碼各自從 owner root 建立 active alert；open recovery 未 matching 也可見。
- `FRAC-A2`：detail 顯示 current remaining、具體規則與合法 action/blocker，無 raw PII／完整帳號。
- `FRAC-A3`：Preview 零寫入；stale、permission、invalid target、used bank fact、amount exceeded 與 evidence missing
  均 0 mutation。
- `FRAC-A4`：Apply replay 回同一 receipt；same key/different payload conflict；transaction failure 無 partial root／
  event／outbox／receipt。
- `FRAC-A5`：Government disposition 後 projector 將原 alert inactive；client/staff partial recovery 更新 remaining
  且保持 active；full recovery/adjustment 才 inactive。
- `FRAC-A6`：React 三個 typed renderer 完成正向與錯誤流程；partial、unknown、stale 不顯示已解除。
- `FRAC-A7`：真 FastAPI＋Vite Browser 證明 Network request、Preview impact、Apply receipt、owner readback 與 active
  list re-query；mock-only 不構成完成。
- `FRAC-A8`：client/staff adjustment 缺 evidence 零寫入；同一 evidence replay 回原 receipt，同 key 更換
  evidence conflict；event/readback 可追溯去敏 evidence reference。
- `FRAC-A9`：三個 owner Query 由 committed root 回傳 current predicate 與合法 actions；missing／ambiguous／
  unavailable 均 fail closed，Query 無 DB 寫入。
- `FRAC-A10`：poison event 第 3 次失敗後停止自動 claim 且後續 event 可繼續；
  人工 retry 缺 reason/evidence、stale attempt、same-key/different-payload 均零寫入，合法 retry
  有 immutable receipt。無較高成功 source version 或 readback 時 supersede 固定拒絕。

## Exclusions／stop conditions

- 不處理其餘 39 codes；不改其他 owner 規則、金額公式、schema、migration、provider 或 production。
- 若實作發現 current owner Query 無法提供正式規格要求的 target／remaining/root version，停止受影響 code，
  回本規格補 typed Query contract；不得從 UI、alert details 或 SQL 自行拼值。
- 除 FRAC-R3 明列的 additive recovery evidence 外，若還需其他 schema、改 public owner semantics 或
  擴張 capability，回 Authority／DB gate，不沿用本規格推定。

## Source map／coverage

| Requirement／Acceptance | Authority／rule | Direct oracle |
|---|---|---|
| FRAC-R1／A1／A5 | `06` root predicate；`14` overpayment state machine；`16` recovery state machines | owner event → projection integration tests，active/partial/inactive readback |
| FRAC-R2／A2 | `06` detail contract；`14`／`16` root facts | strict API schema tests＋redaction tests |
| FRAC-R3／A3／A4 | Global Q/P/A、version、idempotency；`14`／`16` command rules | owner focused tests＋rollback/replay tests |
| FRAC-R3／A8 | `16` 獨立 reason/evidence 與 authorized adjustment | schema descriptor，request/fingerprint/event/receipt replay tests |
| FRAC-R3A／A9 | `14` §4.6；`16` recovery Query contracts | strict API Query tests，missing/ambiguous/zero-write tests |
| FRAC-R4／A6／A7 | `06` React dispatcher boundary | typed client/component tests＋真 API/Vite Browser |
| FRAC-R5 | current Authority/effect ceiling | diff inventory、DB gate NOT_APPLICABLE、provider call=0 |

```yaml
convergence:
  status: READY
  blockers: []
```

結果：`SPEC_READY`。

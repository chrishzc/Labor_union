# 跨 Domain 交易與 pytest 驗收架構

## 1. Domain 依賴

```text
Orders
  ├─讀取 Contract completion fact
  ├─委派 Scheduling 重建
  ├─委派 Client Finance 重算
  ├─委派 Payroll 重算
  └─發出 Anomaly facts/outbox

Scheduling
  ├─讀取 Orders Terms
  ├─輸出 official service facts
  ├─輸出 actual end／hours impacts
  └─委派 Payroll／Orders lifecycle 重評

Payroll
  ├─讀取 Orders Terms
  ├─讀取 Scheduling official service facts
  └─輸出 Staff Payable obligations

Client Finance
  ├─讀取 Orders／Scheduling 根事實
  ├─輸出 Client settlement facts
  └─觸發 Orders service-data-lock predicate

Staff Payables
  ├─讀取 Payroll obligations
  ├─透過 Finance Import port 讀取 canonical outgoing bank facts
  └─輸出 payout anomaly facts

Finance Import
  ├─擁有 bank batch／canonical row／occurrence／classification／reprocess audit
  ├─輸出 typed dispatch intent 給 Client Finance／Staff Payables
  ├─輸出逐 canonical row 的 finance manual-review intent 給 Anomalies
  └─只為匯入完整性故障輸出 bounded batch blocker desired state

Anomalies
  └─只讀各 Domain facts/outbox，不被任何 Domain 當成門禁 SSOT

Government Subsidy
  ├─擁有政府 claim、submission／approval、receipt／reversal ledger 與 allocation
  └─接受 Finance Import typed dispatch；不與 Client Finance 互相抵銷

LINE Integration
  ├─擁有 LINE identity、inbox、delivery task、review、publication 與 media
  └─只負責平台互動；不得直接改 Orders、Scheduling 或 Finance

Access Control
  └─提供 AdminPrincipal、session、operation capability 與 security audit

Case Import
  ├─擁有 source identity、candidate、validation、review 與 mapping
  └─透過 owning-Domain typed ports 建立正式 Client／Order／Scheduling roots

Knowledge Retrieval
  ├─擁有 source provenance、review／publish、index freshness 與 retrieval receipt
  └─只輸出 non-authoritative answer；不得觸發業務 Domain mutation
```

## 2. Global workflow coordinator

跨 Domain command 由 application workflow coordinator 擁有 outer Unit of Work。各 Domain 只提供 typed candidate、validation 及 persistence ports，不自行 commit。

### Orders Terms Apply

```text
lock Orders + Scheduling + unreconciled Finance/Payroll facts
→ fresh Terms candidate
→ Scheduling cancel-old/create-new candidate
→ Client Finance impact candidate
→ Payroll impact candidate
→ 驗證 coverage、ownership、hours、money、freeze、version、fingerprint
→ append Terms event
→ persist Scheduling replacement
→ persist Client Finance 未核銷 projection／adjustment intents
→ persist Payroll 未核銷 projection／adjustment intents
→ reevaluate Orders lifecycle／service-data lock
→ append audit、outbox、idempotency receipt
→ one commit
```

### Actual Start Apply

```text
確認 actual start 根事實
→ 以新根點重建 assignments／service days
→ actual end／hours
→ Client Finance／Payroll 日期與未核銷投影
→ lifecycle／anomaly facts
→ one commit
```

延遲訂金後不得沿用過期 actual start；必須重新確認。舊日期到新日期間不補造服務。

### Deposit receipt／reversal lifecycle impact

```text
Client Finance lock deposit obligation + ledger
→ append receipt or reversal + allocations
→ reduce net deposit + settlement identity
→ Orders lifecycle reevaluation
→ delayed new settlement 時建立 actual-start reconfirm blocker
→ finance／lifecycle outbox + receipt
→ one commit
```

服務前 reversal 阻擋進入服務；已開始／完成後不倒退服務狀態、不取消 assignment、
不解除服務資料鎖。reversal 後的新核銷使用新 settlement identity，不能重放舊
actual-start reconfirmation。

### Cancellation Apply

只適用於全部約定服務完成前：

```text
逐日實際服務日期＋owner confirmation
→ 驗證尚未完整履約
→ cancel old assignments／future schedules／buffers
→ 依已服務事實 create new assignments
→ actual hours／floor-fee
→ Client receivable／over-receipt／refund-or-supplement
→ Payroll／Staff Payables
→ cancellation lifecycle
→ audit／outbox／receipt
→ one commit
```

完整履約後回 typed blocker 並零寫入，月嫂薪資與服務結算不變。

### Leave／Substitution Apply

只重建 affected assignment family，但在 commit 前重新驗證全案 coverage、ownership、hours、occupancy、floor-fee、Finance／Payroll impacts 及 lifecycle。

### Finance reconciliation

Client receipts/refunds 與 Staff payouts 各自使用獨立 ledger transaction。每次核銷都要求
所選銀行 rows 完整 allocation。Client receipt 與 Staff payout 的所選 obligation 必須
精確歸零；Client refund 可以逐筆部分清償，重算明確 remaining amount，只有 remaining
為零才進 `refunded`。Projector 透過 outbox 非同步更新 Anomalies。

Finance Import 只擁有銀行根事實與 classification；正式 allocation／ledger 由 owning
Finance Domain 擁有。`FI-DEC-001` 已確認：File Watcher 只自動 ingestion 與產生
Preview，不得自動 dispatch 正式帳務；人員確認 Preview 後才可 Apply。

帳務區人工修正並入帳同樣由 application workflow coordinator 擁有 outer Unit of Work：

```text
lock canonical bank fact + active finance alert + selected obligations
→ fresh correction impact candidate
→ 驗證來源事實未變、銀行金額完整 allocation；
  receipt／staff payout 精確歸零，refund 則不得超過 remaining amount
→ append Finance Import classification event
→ persist owning Client Finance／Staff Payables ledger + allocations
→ append reconciliation receipt + finance alert resolved event + outbox
→ one commit
```

此流程允許普通待確認列不阻擋同批其他有效候選；但 fingerprint collision、缺列、
occurrence 缺失、partial batch 或狀態矛盾屬批次完整性 blocker。UI 不得直接寫 DB，
任一 persistence point 失敗都不得留下 partial classification、ledger 或警示解除。

### 異常 recovery

跨 Domain 異常一律先投影給人員，不由系統猜測 recovery：

```text
Domain 根事實不一致
→ anomaly fact／outbox
→ 異常中心顯示完整事件鏈與 available actions
→ 人員確認實際情況
→ owning Domain Preview／Apply
→ 新增正式更正事件
→ Alert 自動更新／解除
```

Anomalies 不直接寫 Orders、Scheduling、Client Finance、Payroll 或 Staff Payables。可唯一且安全計算的正常投影仍由 owning Domain 自動執行；原因或處理方法不唯一時必須等待人員。

## 3. Schema 架構要求

實作前必須先形成一份 additive migration plan，至少包含：

- Orders Terms event、actual-start event、cancellation/reopen event、lifecycle event、aggregate version、idempotency receipt、service-data-lock fact。
- assignment／schedule generation 或 effective-version 模型。
- assignment rebuild event 與 old/new M:N lineage。
- service interval lock 與 buffer lock 的明確分類及獨立 lifecycle。
- Client obligation、immutable ledger、transaction allocation、adjustment allocation。
- Staff payout event 與直接連結 canonical Payroll obligation identity 的完整 links；
  `staff_payments` 只可作 compatibility projection。
- Anomaly definition registry、current-state projection、finance occurrence、workflow events 及 outbox checkpoint。

所有 migration 先在隔離新資料庫驗證，保留現有資料；legacy monthly tables、dirty fixtures 及既有事件不得在本輪刪除。

## 4. pytest 分層

### 歷史 activation guard

上述限制是本基線最初的授權狀態。`46_Six_Remaining_Gaps_Completion_Architecture.md`
於 2026-08-09 已取得實作授權，後續 Domain work package 已可依本章進行 production
實作、pytest 與 isolated-MySQL 驗收；不得再將此歷史 guard 當作禁止修正已發現跨域缺口
的理由。

目前每個 Global scenario 是否完成，仍只可由「現行 source hash 對應的 isolated-MySQL
E2E」證明。舊 manifest／收據是可追溯的歷史證據，程式或測試來源變動後必須重新執行並
更新 source hash，不能以舊綠燈取代現況驗證。

### Module

責任：單一公式、Value Object、predicate、canonicalization 與 typed error。

要求：

- 純輸入輸出；
- 不讀 DB、不取現在時間；
- 規格有固定案例時直接 assertion 固定結果；
- 其他情況驗證守恆、不可變性、單調性與 deterministic；
- 不在測試內複製 production calculator。

### Subsystem

責任：同一業務能力內的 Module 編排、狀態機、Preview／Apply、replay、stale、transaction 及 ports。

每個 Subsystem final suite 至少覆蓋：

- success；
- validation/domain blocker；
- Preview 零寫入；
- exact replay；
- idempotency payload mismatch；
- stale version/fingerprint；
- partial failure rollback；
- transient retry；
- typed error mapping。

### Domain

責任：完整業務場景與 Domain SSOT 是否可運作。

Domain 測試使用隔離的正式 MySQL schema，驗證 FK、unique constraint、row lock、transaction、rollback 及 append-only。Mock 只能協助 Module／Subsystem，不能作為 Domain 完成證據。

### Global

只保留高價值跨 Domain 場景：

1. Terms change → Scheduling rebuild → Client Finance／Payroll → lifecycle 一致；若重建後存在 coverage 風險，由 Scheduling coverage scan 建立 anomaly，Terms Apply 不直接建立 alert。
2. Actual Start 更正全鏈原子性。
3. 多月嫂中途取消及雙端各自核銷歸零。
4. 全部服務完成後取消零寫入、月嫂完整薪資不變。
5. leave／substitution 與完成時刻競爭。
6. service-data lock 形成後退款／reversal 不解鎖。
7. API timeout 後全鏈 exact replay 不重複。
8. 在每個跨域 persistence point 注入 failure，證明沒有 partial commit。
9. Streamlit 與直接 API client 得到相同 typed result，且 UI 無業務 fallback。
10. Anomaly projector 暫停／恢復，不影響正式 Domain transaction。
11. 普通 Finance Import 待確認逐列進入帳務區，不與 `IMPORT-006` 重複投影。
12. 人工修正並入帳在 classification、ledger、allocation、receipt、alert resolve 任一點
    failure 時全數 rollback；exact retry 不重複正式交易。
13. 兩個 staff 集合順序相反的 Scheduling commands 仍依 canonical mutex order 完成或
    typed conflict，不 deadlock、不形成重複占用。
14. Deposit reversal 在服務前／服務後的 lifecycle 結果分離；新 settlement identity
    使舊 actual-start reconfirmation 失效。
15. cache 僅用於非權威唯讀 projection；正式 Apply 不得讀取 cache，必須以 fresh locked facts 重算，且 stale Preview 仍 conflict。
16. 202 durable job duplicate delivery／worker crash／通知遺失不重複正式 command。
17. UI 立即顯示 pending 但不提前顯示正式成功；timeout 後以同一 idempotency identity
    查詢 receipt。

## 5. 測試與程式平行策略

只有未來另立且人工核准的 production／pytest Work Package 才開始；架構基線核准
本身不啟用下列施工。

- 同一已確認 contract 下，production module 與其 pytest 可平行撰寫。
- 不同實體 Source、無相依的 Modules 才能平行。
- 共用 aggregate、transaction owner 或同一 Source 的工作串行。
- Module fail：整體修正 Module contract／implementation。
- Subsystem fail：整體修正狀態機、ports、replay 或 transaction。
- Domain fail：回查該 Domain 的 SSOT、資料所有權與完整場景。
- Global fail：回查跨 Domain invariant 與 transaction，不在 UI 或 repository 打補丁。

## 6. 實作順序

架構總審通過且相應 production Work Package 另行核准後：

1. Global contracts、MoneyNTD、typed errors、clock、UnitOfWork、idempotency，以及效能
   telemetry、payload、pagination、single-flight、cache／durable-job ports。
2. 各 Domain 純 Modules 與 Module pytest。
3. Domain ports、repository contracts、隔離 MySQL fixture。
4. Orders Terms／Lifecycle 與 Scheduling candidate builders。
5. Client Finance／Payroll candidates。
6. 跨 Domain workflow coordinator 與 Subsystem tests。
7. Cancellation／Actual Start／Leave transaction flows。
8. Staff Payables／Export／Anomaly projectors。
9. typed FastAPI adapters。
10. Streamlit caller 遷移。
11. legacy writer inventory 全部關閉或固定 Gone。
12. Domain 與 Global final suites。

## 7. 總審時需確認的技術提案

下列不阻擋文件完成，但必須在開始實作前於整體架構總審一次確認：

已確認：

1. assignment／schedule 採 `generation + effective` 模型：舊 generation 永久保留，新 Apply 建立唯一 effective generation，目前排班、工時、檔期與薪資只讀 effective generation。
2. 禁止 reversal-of-reversal。疑似錯誤 reversal 先觸發異常，只有人員確認後才能由 owning Finance Domain 以 Preview／Apply 新增反方向 adjustment；系統不得自動修復。
3. 正常薪資根事實全部為整數；不支援分時／半日或小數每日時數。非整數輸入是資料異常，不以每日或 assignment 四捨五入自動修復。
4. Staff formal payout ledger 只保存實際成功的 payout／return／reversal；失敗嘗試留在 staging／anomaly。
5. 不能唯一證明的 legacy partial payments 保持 legacy read-only＋anomaly，由人員確認 recovery action，不自動轉換。
6. Accounts Payable archive 預設永久保留且不得自動刪除；權限治理本輪暫緩，不影響 `YYYY/` 與原子留存設計。

目前目標範圍內沒有仍會改變 Domain／Subsystem contract 的未裁決業務問題。未來若新增半日服務、分時交接、不同幣別或新退款型態，必須先回到完整架構總審，不得在實作期自行擴張。

# 跨 Domain 交易與 pytest 驗收架構

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Global Architecture / Cross-Domain Verification
- 單一負責範圍：跨 Domain 依賴圖、Global workflow coordinator 的 Unit of Work 原子邊界、Schema 基礎設施要素與四層 pytest 驗收責任分層。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Anomalies Domain](06_Anomalies_Domain.md)、[Global Deployment 與治理](18_Global_Deployment與治理正式規格.md)

## 2. Domain 依賴

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
  ├─輸出 typed dispatch intent 給 Client Finance／Staff Payables／Government Subsidy
  ├─輸出逐 canonical row 的 finance manual-review intent
  └─只為匯入完整性故障輸出 bounded batch blocker desired state

Anomalies
  └─只讀各 Domain facts/outbox，不被任何 Domain 當成門禁 SSOT

Government Subsidy
  ├─擁有政府整期入款、receipt／reversal ledger 與 allocation
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

## 3. Global workflow coordinator

跨 Domain command 由 application workflow coordinator 擁有 outer Unit of Work。各 Domain 只提供 typed candidate、validation 及 persistence ports，不自行 commit。

### 3.1 Orders Terms Apply

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

### 3.2 Actual Start Apply

```text
確認 actual start 根事實
→ 以新根點重建 assignments／service days
→ actual end／hours
→ Client Finance／Payroll 日期與未核銷投影
→ lifecycle／anomaly facts
→ one commit
```

延遲訂金後不得沿用過期 actual start；必須重新確認。原預期日到實際開工日間不補造服務。

### 3.3 Deposit receipt／reversal lifecycle impact

```text
Client Finance lock deposit obligation + ledger
→ append receipt or reversal + allocations
→ reduce net deposit + settlement identity
→ Orders lifecycle reevaluation
→ delayed new settlement 時建立 actual-start reconfirm blocker
→ finance／lifecycle outbox + receipt
→ one commit
```

服務前 reversal 阻擋進入服務；已開始／完成後不倒退服務狀態、不取消 assignment、不解除服務資料鎖。reversal 後的新核銷使用新 settlement identity，不能重放原 actual-start reconfirmation。

既有測試定位：`tests/test_g14_deposit_reversal_disposable_mysql_e2e.py` L93–108 的服務前沖正案例，以同一請求重試後讀回同一收據，確認只新增一筆對原收據的沖正，並核對原訂金義務重開的金額、狀態與版本。這是既有斷言，未在本次文件核對執行。

### 3.4 Cancellation Apply

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

### 3.5 Leave／Substitution Apply

只重建 affected assignment family，但在 commit 前重新驗證全案 coverage、ownership、hours、occupancy、floor-fee、Finance／Payroll impacts 及 lifecycle。

### 3.6 Finance reconciliation

Client receipts/refunds 與 Staff payouts 各自使用獨立 ledger transaction。每次核銷要求所選銀行 rows 完整 allocation。Client receipt 與 Staff payout 的所選 obligation 依對應 Finance 規格歸零（含手續費內扣差額核銷規則）；Client refund 可以逐筆部分清償，重算明確 remaining amount，只有 remaining 為零才進 `refunded`。Projector 透過 outbox 非同步更新後續投影。

Finance Import 只擁有銀行根事實與 classification；正式 allocation／ledger 由 owning Finance Domain 擁有。File Watcher 只自動 ingestion 與產生 Preview，不得自動 dispatch 正式帳務；人員確認操作後才可 Apply。

帳務人工修正／補登並入帳同樣由 application workflow coordinator 擁有 outer Unit of Work：

```text
lock canonical bank fact + active finance alert + selected obligations
→ fresh correction impact candidate
→ 驗證來源事實未變、銀行金額完整 allocation
→ append Finance Import classification event
→ persist owning Client Finance／Staff Payables ledger + allocations
→ append reconciliation receipt + finance alert resolved event + outbox
→ one commit
```

普通待確認列不阻擋同批其他有效候選；但 fingerprint collision、缺列、occurrence 缺失、partial batch 或狀態矛盾屬批次完整性 blocker。UI 不得直接寫 DB，任一 persistence point 失敗都不得留下 partial classification、ledger 或警示解除。

### 3.7 跨 Domain 異常處理邊界

跨 Domain 異常不猜測自動修復，需由 owning Domain 提供完整事件鏈與合法處置入口，經人員確認後走 owning Domain Apply 新增正式更正事件。Anomalies 不直接寫 Orders、Scheduling、Client Finance、Payroll 或 Staff Payables。

## 4. Schema 架構要求

任何 additive migration plan 須涵蓋並維持下列根表與約束邊界：

- Orders Terms event、actual-start event、cancellation/reopen event、lifecycle event、aggregate version、idempotency receipt、service-data-lock fact。
- assignment／schedule generation 或 effective-version 模型。
- assignment rebuild event 與 old/new M:N lineage。
- service interval lock 與 buffer lock 的明確分類及獨立 lifecycle。
- Client obligation、immutable ledger、transaction allocation、adjustment allocation。
- Staff payout event 與直接連結 canonical Payroll obligation identity 的完整 links；`staff_payments` 只可作 compatibility projection。
- Anomaly definition registry、current-state projection、finance occurrence、workflow events 及 outbox checkpoint。

## 5. pytest 分層

日常 PR 從最低受影響邊界驗證，不因 Module、Subsystem、Domain 或 Global 的分類名稱而要求 MySQL。只驗改動觸及的契約；跨 Domain 的業務規則可透過替身 port 實測，不必把相同業務案例在 MySQL 重跑一遍。需要引用真實環境證據時，須標明受測版本、入口及範圍；未跑的環境不宣稱通過。

### 5.1 Module

責任：單一公式、Value Object、predicate、canonicalization 與 typed error。

- 純輸入輸出；不讀 DB、不取系統現在時間；
- 規格有固定案例時直接 assertion 固定結果；
- 其他情況驗證守恆、不可變性、單調性與 deterministic；
- 不在測試內複製 production calculator。

### 5.2 Subsystem

責任：同一業務能力內的 Module 編排、狀態機、Preview／Apply、replay、stale、transaction 及 ports。

每個 Subsystem suite 至少覆蓋：success、validation/domain blocker、Preview 零寫入、exact replay、idempotency payload mismatch、stale version/fingerprint、partial failure rollback、transient retry、typed error mapping。

### 5.3 Domain

責任：驗證完整業務場景與 Domain 的正式資料來源。業務規則及交接用替身 port／repository 驗證，可覆蓋計算、資格、狀態、指令參數與預期副作用；替身不證明實際 SQL 或資料庫行為。

**MySQL 驗證邊界**：只有變更觸及 SQL、欄位映射、schema／migration，或依賴 MySQL 保證的交易行為時，才跑對應的隔離案例。只驗受影響的讀寫契約，例如型別、NULL、精度、FK／唯一性、鎖、交易原子性、rollback 或重送防重。不把套用規則、畫面顯示等與資料庫實作無關的場景重跑一遍。跨域重送若需確認資料庫真的只留一筆，就保留一個從受影響入口讀回實際結果的案例。

### 5.4 Global

以下保留高價值跨 Domain 場景，作為依風險選測的目錄，**不是每次 PR 的必跑清單**。跨 Domain 業務流程先用替身隔離驗證；若改到共享交易、正式接線或 schema，且最低層案例無法覆蓋，才新增或執行受影響的整合／端到端案例。發布或遷移若另有正式驗收契約，照該契約執行，不因本節省略。

1. Terms change → Scheduling rebuild → Client Finance／Payroll → lifecycle 一致；若重建後存在 coverage 風險，由 Scheduling coverage scan 建立後續處理，Terms Apply 不直接寫入 alert。
2. Actual Start 更正全鏈原子性。
3. 多月嫂中途取消及雙端各自核銷歸零。
4. 全部服務完成後取消零寫入、月嫂完整薪資不變。
5. leave／substitution 與完成時刻競爭。
6. service-data lock 形成後退款／reversal 不解鎖。
7. API timeout 後全鏈 exact replay 不重複。
8. 在每個跨域 persistence point 注入 failure，證明沒有 partial commit。
9. React 管理端與直接 API client 得到相同 typed result，且 UI 無業務 fallback。
10. Projector 暫停／恢復，不影響正式 Domain transaction。
11. 普通 Finance Import 待確認逐列進入帳務待核對，不與匯入批次完整性異常混用。
12. 人工修正並入帳在 classification、ledger、allocation、receipt、alert resolve 任一點 failure 時全數 rollback；exact retry 不重複正式交易。
13. 兩個 staff 集合順序相反的 Scheduling commands 仍依 canonical mutex order 完成或 typed conflict，不 deadlock、不形成重複占用。
14. Deposit reversal 在服務前／服務後的 lifecycle 結果分離；新 settlement identity 使舊 actual-start reconfirmation 失效。
15. cache 僅用於非權威唯讀 projection；正式 Apply 不得讀取 cache，必須以 fresh locked facts 重算，且 stale 仍回 conflict。
16. 202 durable job duplicate delivery／worker crash／通知遺失不重複正式 command。
17. UI 立即顯示 pending 但不提前顯示正式成功；timeout 後以同一 idempotency identity 查詢 receipt。

## 6. 測試與程式開發策略

- 同一已確認 contract 下，production module 與其 pytest 可平行撰寫。
- 不同實體 Source、無相依的 Modules 才能平行；共用 aggregate、transaction owner 或同一 Source 的工作串行。
- 交付列出業務測試、MySQL 契約測試與未執行項目。若擴大到整套 MySQL，交代理由與受影響的持久化邊界；不以全跑代替選測。
- 依失敗層級定位修復：Module fail 修正 Module；Subsystem fail 修正狀態機／ports／replay／transaction；Domain fail 回查該 Domain SSOT；Global fail 回查跨 Domain 不變量與 transaction，不在 UI 或 repository 打補丁。

## 7. 已定案技術架構原則

1. assignment／schedule 採 `generation + effective` 模型：保留歷史 generation，新 Apply 建立唯一 effective generation，目前排班、工時、檔期與薪資只讀 effective generation。
2. 禁止 reversal-of-reversal。疑似錯誤 reversal 需經人員確認後，由 owning Finance Domain 新增反方向 adjustment；系統不得自動修復。
3. 正常薪資根事實為整數日薪或合法約定單位；非合法輸入屬資料異常，不以每日或 assignment 擅自四捨五入自動修復。
4. Staff formal payout ledger 只保存實際成功的 payout／return／reversal；失敗嘗試留在 staging／異常記錄。
5. 無法唯一證明的歷史部分付款保持唯讀並由人員確認人工處理方式，不自動猜測轉換。
6. Accounts Payable archive 預設永久保留且不得自動刪除。

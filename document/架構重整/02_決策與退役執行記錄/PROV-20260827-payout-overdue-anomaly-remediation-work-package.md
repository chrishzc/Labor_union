# PAYOUT-001 逾期月嫂應付款異常人工核銷工作包

- 狀態：`approved`
- package status：`PACKAGE_READY`
- controlling spec：`PROV-20260827-payout-overdue-anomaly-remediation-spec.md`
- code：`PAYOUT-001`

## Entry 與 reuse 決策

| Candidate | Classification | 決策 |
|---|---|---|
| Staff Payables owner Query/Preview/Apply | `required_now` | reuse 既有正式 Q/P/A、durable job 與 immutable ledger，不新增帳務命令。 |
| anomaly detail/action binding | `required_now` | minimal glue；綁定 current `staff_id`/`obligation_identity`，缺失 fail closed。 |
| React payout remediation workbench | `required_now` | copy-adapt 既有 strict finance workbench interaction pattern，使用 payout 專屬 schemas/client。 |
| job terminal observation + owner readback | `required_now` | reuse `/api/v1/jobs/{job_id}` 與 `QueryStaffPayables`；receipt-only 不完成。 |
| generic alert close／付款建立器 | `remove` | 會繞過真實根事實或造成外部付款語意。 |
| PAYOUT-002/003 | `required_later` | owner remediation 尚未完成規格收斂，不混入本包。 |
| schema/provider/production | `remove` | 超出 effect ceiling。 |

Research status：`NO_RESEARCH`；重要決策已有 current 正式規格與 live owner contracts 支持。

## POA-WP-A：Backend exact action binding

- Objective：把 `PAYOUT-001` detail 綁到既有 Staff Payables owner action，並以 current snapshot fail-closed 提供 immutable action context。
- Scope：`domains/anomalies/registry.py`、`subsystems/anomalies/alert_workflow.py`、focused tests。
- Exclusions：改 payout 金額公式、API public contract、repository/schema、generic resolve、PAYOUT-002/003。

### Steps

1. registry descriptor 宣告 spec 的 exact owner/action/form/query/preview/apply/operator inputs/completion predicate。
2. detail assembler 只從 current display snapshot 綁定 positive `staff_id` 與 canonical `obligation_identity`；不合法時 action 留 unbound/不可執行。
3. 測試 valid binding、missing/blank/wrong type、owner mismatch 與 descriptor exactness。

### Oracle

action bindings 與 detail 顯示的同一 current snapshot 完全一致；不得從 query string、舊 tracking record 或 UI input 重建 source identity。

## POA-WP-B：React bounded remediation workbench

- Objective：由異常頁完成人工核銷與真實終態調和。
- Dependency：WP-A exact descriptor contract PASS。
- Scope：payout 專屬 strict schemas/client/component/tests、exact dispatcher composition。
- Exclusions：raw dict、code-based dynamic endpoint、receipt-only completion、銀行付款 provider。

### Steps

1. strict decode staff-payables Query、Preview、Apply job accepted 與 job observation responses。
2. 依 immutable bindings fresh Query 並顯示原 obligation；人員輸入 Finance Import row IDs 與 reason。
3. Preview 後明確確認；輸入變更使 Preview 失效，Apply 鎖定且禁止 double submit。
4. poll job 至 terminal；failed/cancelled/timeout 保留異常。
5. succeeded 後 fresh Query 原 obligation，只有 balance=0/completed 才 refresh anomaly list，否則顯示仍未解除。
6. 覆蓋 strict schema、client、component、dispatcher、accessibility 與負向 tests。
7. payout target 只由 typed detail 的 exact bound action 建立；recovery 404／空 actions 是合法 partial
   failure，不阻擋工作台。detail/recovery identity 衝突、unbound action 或 exact contract 漂移時 fail closed。
8. owner Query lifecycle 必須通過 React StrictMode effect replay；opaque bank version 必須為 JavaScript safe
   integer，避免成功 Query 永久 loading 或 Browser round trip 固定誤判 stale。

### Integration decision

- `reuse`：`GET /api/v1/anomalies/{fingerprint}` 的 current detail/action binding。
- `copy-adapt`：把既有 recovery action exact-contract validator 的共同檢查套用到 payout detail action，
  但輸入型別仍維持 closed `AnomalyDetailView`，不接受 raw object。
- `minimal-glue`：`AnomaliesPage` 同時保存 detail 與 recovery；PAYOUT dispatcher 接收 detail，Finance recovery
  dispatcher 仍接收 recovery，兩者不得互相假造 context。
- `reject`：擴張 Finance-only root snapshot、對 PAYOUT 寫 snapshot、以 recovery 404 觸發 generic fallback、
  從 anomaly code 拼接 owner endpoint。

### Oracle

DOM、typed request、job status、fresh owner obligation 與 anomaly refresh identity 一致；HTTP 202 或 job succeeded 本身不觸發完成 UI。

## POA-WP-C：Final validation

- Objective：以 final candidate 證明規則書正向與負向行為。
- Dependencies：WP-A/B focused tests PASS；真 stack 僅在使用者服務已啟動且 target 通過 `APP_ENV=development`/`lu_test_*` allowlist 時執行。

### Steps and evidence

1. Python focused tests、React focused tests/typecheck/build、`git diff --check`、strict UTF-8。
2. 正向 exact payout：owner balance=0/completed 後 alert inactive。
3. integration 正向：detail 200 + recovery 404 仍顯示 exact payout 工作台；不得出現「沒有可用處理方式」。
4. 負向：accepted/queued/running、receipt-only、partial/over/cross-staff、stale、timeout/readback unavailable 仍 active；
   detail identity／owner／schema／contract 漂移不顯示工作台。
5. 真 MySQL/API/Browser 若服務未啟動，狀態明記 `NOT_RUN`，不得用 mock 冒充。
6. E3 independent verifier 檢查 P0/P1、規則書漂移、跨 lane 整合與未授權副作用。

### Runtime command sequence

1. 以 versioned `PAYOUT-001-EXACT-001` scenario 及正式 owner commands prepare；禁止直接 insert alert、
   payable projection、payout event/link/receipt/outbox/job。
2. 啟動／沿用 development no-auth FastAPI＋Vite，先回讀 `APP_ENV`、DB identity 與 allowlist。
3. Browser 從 active alert 實點 Drawer，核對 detail 200、recovery 404 與 payout workbench 同時成立。
4. Browser 填入 scenario canonical outgoing Finance Import row ID 與 reason，依序 Preview、人工確認、Apply。
5. 讀回 202 job；queued/running 階段截取 alert 仍 active 的證據。只由正式 durable worker 執行一次 job。
6. Browser 觀察 terminal succeeded，再由工作台 fresh Query；只有原 obligation completed／balance 0 才刷新清單。
7. 重跑原 PAYOUT scanner，scenario verifier 讀回 alert inactive/resolved、owner root、ledger／receipt／job lineage。
8. 同一 command key replay 不重複；完成 focused tests、build、diff/UTF-8 與 fresh Luna/high read-only verifier。

### Safe stop conditions

- runtime target 不是 development `lu_test_*`、需要 schema／API public contract／provider 變更，立即停止本包。
- detail action 不完整時回到 WP-A；owner Q/P/A 或 job terminal 契約漂移時回到 controlling spec，不在 React 補 business fallback。
- Browser 已送出 Apply 後若結果未知，只以同一 idempotency identity reconcile，不建立第二筆 command。

## DDH 執行投影與動態調整紀錄

| 時點 | material change | 拓撲／模式調整 | 理由 |
|---|---|---|---|
| 2026-08-27 candidate audit | PAYOUT/GOVSUB/LINE 三組規則證據完成 | E4 三條唯讀稽核 lane 收斂為 PAYOUT-001 | LINE task ownership 與 GOVSUB anomaly binding 仍需新 Authority；PAYOUT-001 可由 current 規則完整裁決。 |
| 2026-08-27 package ready | write set 可隔離 | E4 backend writer + React writer；parent 唯一 shared integrator | 兩條新/既有檔案集合可分離，`AnomaliesPage.tsx` 與 shared dispatcher 保留 parent 避免競寫。 |
| final candidate | 需要獨立反證 | 切換 E3 read-only verifier | writer 不自證 terminal business oracle。 |
| E3 round 1 | action可達性與 stale恢復 material drift | 切回 parent 單一 integration writer | verifier發現 detail/recovery路徑不一致的P0與 stale循環P1。 |
| E3 round 2 | recovery空 action metadata仍與工作台矛盾 | 保持單一 writer做最小修正 | 只在 recovery actions非空時優先，否則使用已綁定detail action。 |
| E3 round 3 | P0/P1清零 | 停止本包 source mutation | 同一Luna High/high verifier PASS；進入runtime evidence待環境階段。 |

## Coverage

| Acceptance | Package evidence |
|---|---|
| POA-A1 | WP-A descriptor/binding tests |
| POA-A2 | WP-B component/dispatcher flow tests |
| POA-A3 | WP-B readback + WP-C exact payout evidence |
| POA-A4 | WP-B/WP-C negative terminal tests |
| POA-A5 | existing owner Q/P/A regression + WP-B double-submit/reconciliation |
| POA-A6 | diff inventory、DB gate table、E3 verifier |
| POA-A7 | WP-B detail-only dispatcher tests + WP-C detail 200/recovery 404 Browser oracle |
| POA-A8 | repository safe-integer regression + 真 Browser Preview/worker fresh-lock terminal evidence |

Readiness result：`PACKAGE_READY`。

## Spec Pipeline revision 2 package gate

- controlling spec：revision 2、`SPEC_READY`、`convergence.status=READY`。
- necessity：本 revision 只保留 PAYOUT detail dispatcher 與 runtime terminal closure；API/projector/schema
  方案已移除。
- source basis：`NO_RESEARCH (R0)`；typed detail binding、Finance-only recovery schema、runtime 404 與既有
  owner Q/P/A 是直接 project evidence。
- effect ceiling：只允許 React composition/tests、scenario/runtime evidence 與必要文件同步；既有 source
  predicate/payroll due-date修正只有在 focused regression 仍需要時保留，不擴張新功能。
- handoff：交給 DDH 時先單一 integration writer完成最小 detail dispatcher patch，再由 fresh Luna/high
  read-only verifier反證；Agent topology仍由 DDH 決定，本文件不建立執行 Authority。

Package status：`PACKAGE_READY`。

## 2026-08-27 執行狀態

| Work Package | 狀態 | Evidence |
|---|---|---|
| POA-WP-A | `completed` | exact descriptor、current snapshot binding、missing/blank/type/owner/identity drift fail closed；Python final related `71 passed`。 |
| POA-WP-B | `completed` | strict Query/Preview/Apply/Job client、detail exact dispatcher、terminal + fresh owner readback、stale fresh Query、unknown same-key retry、無死路 UI；React final focused `23 passed`、build PASS。 |
| POA-WP-C source | `completed` | compile、strict UTF-8、`git diff --check` PASS；runtime 後 fresh `gpt-5.6-luna`／`high` 抓到 terminal label 遮蔽正餘額 P1，依 root-truth oracle 修正後再由另一位 fresh Luna/high 以 `76 passed`、P0=0/P1=0 獨立驗證。 |
| POA-WP-C runtime | `completed` | canonical `lu_test_task96_scenarios_20260827`、no-auth 8016/5183 真 Browser完成 detail 200/recovery 404、Query/Preview/Apply、正式 DurableJobWorker、fresh owner readback與 scanner recheck；alert由 active 6 降為5，原 fingerprint resolved。 |

final receipt：`03_追蹤清單與證據/evidence/2026-08-27_payout_overdue_anomaly_remediation_receipt.md`。

# PAYOUT-001 逾期月嫂應付款異常人工核銷規格

- 狀態：`approved`
- convergence：`SPEC_READY`
- Authority：2026-08-27 使用者要求每種異常都有人工修正方式，且自動解除必須依真實業務規則書重新判斷。
- 範圍：只處理 `PAYOUT-001`；`PAYOUT-002`、`PAYOUT-003` 維持各自的規格缺口。

## 1. 業務情境與唯一 owner

`PAYOUT-001` 表示一筆 `payable_to_staff` 義務已過應付日，且目前仍有正餘額。Staff Payables 是唯一 mutation owner；Finance Import 的 `CanonicalOutgoingBankFactPort` 是實際銀行出款唯一根事實，異常與 React 不得直接修改 payable projection、銀行 raw fact 或正式 ledger。

本人工修正不是「現在替月嫂匯款」，而是會計已從其他管道確認款項已匯，且銀行流水已匯入系統後，把正確的 canonical outgoing bank fact 精確核銷到該逾期義務。若銀行流水尚未存在，人員只能先完成銀行匯入，不能在異常頁偽造出款或強制解除。

## 2. 規則書 oracle

### 2.1 Active predicate

下列條件同時成立時，`PAYOUT-001` 必須保持 active：

- obligation direction 為 `payable_to_staff`；
- due date 早於本次掃描業務日；
- current balance 大於 0；
- obligation status 與 Staff Payables current projection 均不是 `cancelled`。

`current balance` 是是否仍欠款的根事實。舊的 `amount_due_ntd=0`、obligation `settled` 或 projection
`completed` 標籤都不得遮蔽正餘額；此類不一致仍須保持 active，直到 owner root readback 證明 balance 精確為
`0`。取消狀態不屬本逾期付款流程，維持 inactive 並交由其 owning flow 處理。

detail 至少顯示 `staff_id`、`obligation_identity`、due date、amount due、current balance 與 current root/source version；不能只顯示代碼、追蹤狀態或技術 fingerprint。

### 2.2 唯一合法人工修正

固定 owner flow：

1. `QueryStaffPayables(staff_id)` fresh-read 義務與 `staff_payables_version`；
2. 人員輸入或選取一個以上已存在、屬同一月嫂的 canonical outgoing Finance Import row identity，並填寫 reason；
3. `PreviewStaffPayout` 以固定的 `obligation_identity` 驗證銀行列、主帳戶 owner、完整義務與金額精確相等，Preview 零寫入；
4. 人工確認後 `ApplyStaffPayout`，帶入 Preview 的 staff/bank versions、fingerprint、reason、correlation id 與 idempotency key；
5. Apply 只表示 durable job 被接受。必須等 job terminal `succeeded`，再 fresh Query owner root 並重跑原異常 predicate。

一般 payout 仍是 exact-only。部分付款、超付、混 staff、重複／已使用銀行列、帳戶 owner 不唯一、銀行方向錯誤或未完整選取義務，都不得建立正式 payout。

### 2.3 Terminal completion

只有 fresh owner readback 同時證明下列事實，異常 projector 才能投影 `active=false`：

- 原 `obligation_identity` 仍屬綁定的 `staff_id`；
- current balance 精確為 `0`；
- current projection/status 為 `completed`；
- 重跑 `PAYOUT-001` 規則書 predicate 為 false。

人工 claim/resolve/tracking status、電話或 LINE 聯絡成功、Preview 成功、HTTP 202、job queued/running、outbox delivered、receipt 存在或只有其中一筆義務完成，都不能單獨解除異常。timeout、結果未知、stale、owner Query 失敗或 identity 漂移一律 fail closed，保留異常並使用原 idempotency identity 調和，不得盲目重送。

## 3. Exact action contract

| 欄位 | 值 |
|---|---|
| code | `PAYOUT-001` |
| owner | `staff_payables` |
| action key | `reconcile_overdue_staff_payable` |
| form schema | `staff_payables.payout_reconciliation.v1` |
| source bindings | `staff_id`, `obligation_identity` |
| operator inputs | `finance_import_row_ids`, `reason` |
| query | `QueryStaffPayables` |
| preview | `PreviewStaffPayout` |
| apply | `ApplyStaffPayout` |
| completion predicate | `staff_payable_obligation_settled` |
| action contract version | `1` |

source bindings 必須來自 anomaly current display snapshot，且 identity 缺失、型別錯誤、空白、owner mismatch 或未知 schema/version 時不提供 action。UI 不得由 anomaly code 臨時拼 endpoint，也不得 fallback 到 tracking close。

## 4. React 人工處理流程

工作台需顯示具體逾期義務、解除條件與「不會發動銀行匯款」提示。人員填入 canonical Finance Import row IDs 與 reason 後先 Preview；任一輸入改變即使 Preview 失效。Apply 期間禁止重複送出；job terminal 前不得顯示已解除。

job succeeded 後 fresh Query 原義務：若已 completed/zero balance，重新載入異常清單；若仍有餘額或 owner readback 失敗，保留 drawer 與警示，顯示 current blocker。未知 action schema、binding 或 response 必須 fail closed。

### 4.1 Action context 的唯一來源與 partial failure

`PAYOUT-001` 的可執行 action 固定來自 `/api/v1/anomalies/{fingerprint}` typed detail，而不是
`/api/v1/anomaly-recovery/{fingerprint}`：

1. detail assembler 以同一筆 current `display_snapshot` 綁定 `staff_id` 與
   `obligation_identity`；React 只能使用這份 server-bound action，不能由 anomaly code、URL、表單或
   recovery 404 重建 identity。
2. React 的 payout dispatcher 必須同時核對 detail summary 的 `definition_code=PAYOUT-001`、
   `source_domain=staff_payables`、`predicate_active=true`、`source_identity=obligation_identity`，以及 action 的
   owner、schema、operation、capability、binding keys、operator inputs、completion predicate 與 contract version。
   任一不符即不渲染工作台。
3. `/api/v1/anomaly-recovery` 目前是 Finance root-fact snapshot public contract；PAYOUT detail 成功而 recovery
   回 404 是合法 partial failure，不得因此隱藏已通過上述核對的 payout 工作台，也不得顯示「目前沒有可用的
   系統處理方式」。
4. recovery 若成功但沒有可用 action，PAYOUT 仍只使用 exact detail action；若 recovery 與 detail identity
   衝突，固定 fail closed 並顯示 typed unavailable，不得任選其中一份。
5. 本 slice 禁止為了消除 recovery 404 而修改 root-fact projector repository、Finance-only snapshot schema、
   recovery API response 或資料表，也不得為 PAYOUT 偽造 finance import row／batch identity。

這項決策是 observable integration contract，不是可替換的實作偏好；只有 Anomalies public recovery contract
另經正式規格擴充為跨 owner typed variant 時才可修訂。

### 4.2 跨 JSON／JavaScript 的版本安全

`staff_payables_version` 與 `bank_facts_version` 都是 opaque concurrency token，不是資料庫 identity。API 保持
nonnegative integer contract，但任何會進入 Browser Preview／Apply round trip 的 version 必須同時滿足
`Number.isSafeInteger(version)`。後端不得產生超過 53-bit 的整數後要求 JavaScript 原值回傳；否則即使根事實
未變也會形成永久 stale。version 算法調整後，Preview fingerprint 必須隨之重算，既有已接受 command 仍依其
持久化 payload／idempotency 狀態完成或 fail closed，不得改寫。

## 5. Acceptance

- `POA-A1`：detail/action 綁定正確 `staff_id` 與 `obligation_identity`；缺失或漂移不提供 mutation。
- `POA-A2`：React 完成 `Query → Preview → Confirm → Apply → job terminal → fresh owner readback → anomaly recheck`，且清楚顯示哪筆義務、多少金額與何時到期。
- `POA-A3`：exact canonical outgoing bank fact 核銷後，fresh root 證明原義務 balance=0/completed，alert 才消失。
- `POA-A4`：HTTP 202、queued/running/succeeded receipt-only、部分／超額／跨 staff、stale、timeout、readback failure 都不解除 alert。
- `POA-A5`：Preview 零寫入；Apply replay、same-key/different-payload、permission、transaction rollback 與 double-submit focused tests PASS。
- `POA-A6`：不得新增付款指令、generic alert editor、generic adjustment、schema、seed、backfill 或 provider side effect。
- `POA-A7`：真 API 中 detail 200、recovery 404 時，Drawer 仍從 exact detail action 顯示 PAYOUT 工作台；
  detail/action identity、owner、schema 或 contract 任一漂移時工作台不可出現。
- `POA-A8`：真 Browser round trip 的 staff/bank versions 皆為 JavaScript safe integer；Preview 後未改變根事實時，
  worker fresh-lock 不得因數值精度損失誤判 stale。
- `POA-A9`：任何正 `current balance` 不得被 `amount_due_ntd=0`、obligation `settled` 或 projection `completed`
  遮蔽；balance=0、未到期或 cancelled 則不得誤報 PAYOUT-001。

## 6. Effect ceiling 與 DB inventory

- 允許：本機 source/tests/docs、既有 Staff Payables API 與 React composition、受控 `lu_test_*` owned rows 驗收。
- 禁止：`union_db`、production/provider mutation、發動銀行匯款、未核准 DDL/migration/seed/backfill/reset/replacement/`--switch`。
- DB inventory：`schema-only=none`、`system-seed=none`、`business-row-backfill=none`、`destructive=none`。diff 若出現任一 DB 變更，本規格停止並重走 DB gate。

## 7. Traceability

| Requirement | 正式規則書 | Live reuse |
|---|---|---|
| active/terminal predicate | `05_Staff_Payables_Export_Domain.md` §2、§5 | `staff_payables_anomaly_source.py` |
| exact payout | `05` §3；`16_Staff_Payables與Client_Refund正式規格.md` §2.3 | payout Domain/subsystem/repository |
| Query/Preview/Apply | `05` §9；`16` §2.2–2.3 | `api/routes/staff_payout.py` |
| no external transfer | `16` §1 | canonical bank fact read + immutable payout ledger |
| payout action context | 本規格 §4.1；`06` public detail partial-failure boundary | typed anomaly detail current action；Finance recovery API 不擴張 |

## 8. Spec Pipeline 收斂紀錄（revision 2）

- consumer：Task 96 `PAYOUT-001` runtime closure；不涵蓋其餘 32 個 active anomaly。
- research：`NO_RESEARCH (R0)`；current spec、typed detail source、React adapter 與真 runtime 404 已足以裁決。
- evidence-supported decision：使用 detail-bound action，保留 recovery partial failure；不改 API/projector/schema。
- assumptions：canonical scenario DB 仍為 `lu_test_task96_scenarios_20260827`，runtime 維持 no-auth development。
- non-blocking unknown：`PAYOUT-002/003` owner remediation 尚未收斂，不影響本規格。
- stop condition：A1～A8 全部有 final-candidate evidence即停止本包；不得順手施工其他 anomaly code。

```yaml
convergence:
  status: READY
  blockers: []
```

Terminal status：`SPEC_READY`。

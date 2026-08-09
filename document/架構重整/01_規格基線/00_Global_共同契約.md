# Global 共同契約

## 1. Global 的責任

Global 只定義跨 Domain 不得被破壞的不變量及共用技術契約，不擁有任何特定業務公式，也不形成可任意呼叫的巨大 Service。

共同契約包括：

- `ActorContext`
- `ExpectedVersion`
- `IdempotencyKey` 與 `IdempotencyReceipt`
- `PreviewFingerprint`
- `TypedResult` 與 `TypedError`
- `UnitOfWork`
- `BusinessClock`
- `CorrelationId`
- transactional outbox

## 2. 跨 Domain 不變量

1. 所有正式業務規則只存在後端；Streamlit 不得計算日期、狀態、工時、金額或帳務結果。
2. Query 為唯讀，不修資料、不持久化重算結果、不轉移狀態。
3. Preview 零寫入；Apply 必須在鎖定 fresh facts 後使用同一 candidate builder 重算。
4. Apply 必須驗證 aggregate version 與 Preview fingerprint；任一過期即零寫入 conflict。
5. 相同 idempotency key 與相同 canonical payload 回傳原 receipt；相同 key 搭配不同 payload 固定拒絕。
6. 正式收款、付款、退款、adjustment、reversal、服務更正及狀態事件一律 append-only。
7. 所有金額為整數新台幣。相容的 `DECIMAL(...,2)` 欄位不得讓新流程產生小數義務。
8. 客戶與月嫂是兩套獨立帳務，不要求兩端總額相等。每筆被選銀行 row 必須完整
   allocation；Staff payout 所選 obligation 必須完整核銷。Client refund 可以逐筆部分
   清償，allocation 後允許保留明確 remaining amount，但不得超額或留下不明銀行差額。
9. `actual_hours = 有效 assignment-owned 正式服務日數 × orders.service_hours_per_day`；不得 fallback 到 `planned_hours` 或 `orders.staff_id`。
10. cancelled assignment 保留歷史，但不得參與目前排班、檔期、日期、工時或薪資。
11. 服務資料鎖只在「訂單完成且客戶全部正式應付款結清」後形成，形成後不可逆。
12. 全部約定服務完成後不得取消訂單；即使服務資料鎖尚未形成也相同。月嫂薪資與服務結算按完整履約計算。
13. 所有服務日期、完成時刻及到期日政策固定以 `Asia/Taipei` 解讀；測試必須注入 clock。
14. Alert workflow 不是 Domain 門禁。Domain 直接檢查根事實；Alert 只投影同一 predicate。
15. 任何無法從根事實唯一判定原因或修復方式的異常，都必須先產生異常投影通知人員；系統不得自行猜測並自動更正根事實、建立 adjustment／reversal、改差額或改狀態。
16. 異常中心必須提供足以判斷的來源事實、影響範圍、關聯事件、建議合法操作及 Preview 入口。人員確認後，異常中心只能呼叫 owning Domain 的 typed command；不得直接寫 Domain 資料。
17. 人工處理異常的正式操作仍須遵守 Preview／Confirm／Apply、版本、fingerprint、冪等、權限、完整稽核與交易門禁。人工 resolve 只管理待辦，不代表修復已完成。
18. UI 可立即顯示 local draft、loading 或 pending，但正式 Apply 只有收到 server receipt
    才能顯示成功；不得以 optimistic UI 冒充正式帳務、排班或狀態已完成。
19. Cache、read model、HTTP conditional response 與 background notification 都不是 SSOT。
    Apply 永遠鎖定 fresh facts 重算，cache unavailable 只能影響速度。
20. 長任務可回 `202 Accepted` 與 durable job identity，但 worker 仍執行同一原子
    application command；不得把 ledger、allocation、lifecycle 或 receipt 拆成多次 commit。

## 3. 依賴方向

```text
Streamlit
  → typed API client
    → FastAPI adapter
      → Application Workflow Coordinator
        → owning Domain typed Commands / Queries
          → Domain Modules
          → typed Ports
            ← Persistence / Provider / Queue / Cache adapters
```

- Module 不得 import FastAPI、Streamlit、requests 或資料庫 driver。
- Domain 不得 import UI 或 concrete repository。
- 跨 Domain 協調只能由 workflow/application coordinator 透過 typed ports 完成。
- 同一資料庫內要求原子性的跨 Domain 操作，共用外層 `UnitOfWork`；內層 adapter 不得自行 commit。
- Alert、通知及外部平台採 outbox，可在正式交易後重試；不得把外部呼叫放進核心交易。

## 4. Typed errors

所有 API 使用相同 error envelope：

```text
category
code
message
field_errors
domain_blockers
retryable
correlation_id
current_version
```

`category` 固定為：

- `validation`
- `forbidden`
- `not_found`
- `domain_blocked`
- `conflict`
- `idempotency_mismatch`
- `unavailable`
- `internal`

只有 `unavailable` 可提示以相同 idempotency key 重試。`conflict` 必須重新 Query／Preview；不得自動 Apply。UI 不得依 message 字串判斷流程。

## 5. SSOT 類型

每個欄位或狀態必須明確歸入下列一種：

- `root_fact`：經正式命令或外部事件確認的原始事實。
- `immutable_event`：記錄曾發生的命令、付款、服務或狀態轉移。
- `derived_projection`：可由根事實重建的目前值。
- `compatibility_projection`：只服務舊 caller，禁止新流程形成依賴。
- `query_view`：跨 Domain 顯示模型，不具寫入權威。

不得把 Alert、UI session state、Excel、SQL View 或 compatibility 欄位升格為根事實。

## 6. 全域完成定義

只有同時具備下列證據，架構才可進入實作：

Activation guard：下列是 architecture readiness／future acceptance condition，不是
自動施工授權。目前只允許 Inventory v2；production code、pytest 或其他 mutation
仍須另立 exact-scope Work Package 並取得人工核准。

- 十三個 Domain（Orders、Assignments／Scheduling、Payroll、Client Finance、
  Staff Payables、Government Subsidy、Finance Import、Anomalies、Contract Integration、
  LINE Integration、Access Control、Case Import、Knowledge Retrieval）的 SSOT 與
  typed ports 不互相重疊；
- Migration、Deployment、Release、Runtime Supervision／Observability、Performance／UX
  及 Accounts Payable Export 等 Global Subsystem 不得被誤建成業務 Domain；
- 跨 Domain transaction sequence 無隱藏 commit；
- production writers 都有唯一歸屬與退出策略；
- success、failure、replay、stale、partial failure、rollback 均有對應 pytest 層級；
- live MySQL 可在隔離資料庫驗證 schema、constraint、lock、rollback 及 idempotency；
- Streamlit 只呼叫 typed API；
- 所有人工未裁決問題均不會改變即將施工的 contract。
- frontend、network、backend／DB、cache 與 background job 都有可量測 baseline、
  release budget、typed degradation 與分層驗收。

## 7. Human-assisted recovery 共同模式

```text
根事實或正式事件出現不一致
→ source Domain 產生 typed anomaly fact／blocker
→ outbox
→ Anomalies 顯示來源、影響與可執行操作
→ 人員確認實際情況
→ 呼叫 owning Domain Preview
→ 人員確認
→ owning Domain Apply
→ 新增更正／adjustment／reversal／root-fact correction event
→ projector 依新根事實自動解除或更新警報
```

- 若規格可唯一決定安全結果，Domain 可在原正式 command 內自動完成計算。
- 若原因、歸屬或修復動作不唯一，必須停在 anomaly／review，不自動選答案。
- Anomalies Domain 只組合 recovery capability，不擁有實際帳務、排班、薪資或 Orders correction。
- 每個異常代碼都必須列出 owning Domain、可用操作、必要輸入、是否阻擋及解除 predicate。

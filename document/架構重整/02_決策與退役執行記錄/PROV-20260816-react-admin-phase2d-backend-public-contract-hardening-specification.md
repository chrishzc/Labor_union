---
doc_type: implementation-specification
declared_status: approved
identity: PROV-20260816-react-admin-phase2d-backend-public-contract-hardening
date: 2026-08-16
owner: Integration Owner
domain: Anomalies
subsystem: Alert Query / Import Warning Tracking / FastAPI Contract
approval_required: human-must-reply-核准此-exact-Phase2D-H-Work-Package
supersedes: none
repairs: PROV-20260816-react-admin-phase2d-anomalies-query
---

# Phase 2D-H：Anomalies Backend Public Contract Hardening 規格

## 0. 狀態與授權

本文件與同 identity 的 exact Work Package 已由使用者於 2026-08-16 明確回覆
「核准此 exact Phase 2D-H Work Package」。本次由 Integration Owner 單一代理自行實作，
不使用子代理或 DDH。

## 1. Business scenario

內部管理人員完成帳密與 TOTP 登入後進入「異常中心」。Import Warning tasks 能顯示，但
`GET /api/v1/anomalies` 的每筆 summary 回傳空白 `severity`，React strict decoder 因此 fail closed，
整個 canonical anomaly lane 無法顯示。

管理端需要的不是寬鬆字串，而是可由後端證明的有限狀態：

- severity：`warning | blocking`；
- anomaly workflow：`open | claimed | resolved`；
- import-warning tracking：`open | awaiting_external_confirmation | response_recorded |
  reimport_requested | closed | auto_resolved`。

未知、空白或不合法值必須在 backend boundary fail closed，不能由 React 猜測或 fallback 成 warning。

## 2. Root cause 與 owner

### 2.1 Root fact

- `anomaly_current_alerts` 保存 definition code、source identity/version、predicate、workflow status/version
  與 display snapshot。
- severity 不屬於資料列；唯一 owner 是 `domains/anomalies/registry.py` 的
  `AnomalyDefinition.severity: AnomalySeverity`。
- workflow status 的唯一 owner 是 `AlertWorkflowStatus`。
- Import Warning tracking status 的唯一 owner 是 `ImportWarningTrackingStatus`。

### 2.2 Live drift

`infrastructure/mysql/anomaly_registry_repository.py::_summary()` 目前建立 `AnomalySummary` 時把 severity
寫成空字串。`AnomalyApplication.query_summaries()` 又直接回 repository 結果，未以 registry enrich。
這是 Subsystem composition 缺口，不是 DB 資料修復問題。

API schema 同時把上述 enum 欄位宣告為一般 `str`，使 OpenAPI／Pydantic 無法阻止不合法值；Phase 2D
route tests又使用自製 fake summaries，沒有走真 Application＋repository shape，因此形成假綠。

## 3. 正式責任邊界

1. Repository 只讀 persisted projection，不擁有或推導 severity。
2. Anomaly Application 必須依每筆 `definition_code` 查詢 canonical registry，再建立對外 summary。
3. Registry 找不到 definition、source domain 與 definition 不一致、repository 出現不合法 workflow
   status時，query 必須 fail closed為 typed data-integrity error；不得跳過單列或降級成 warning。
4. FastAPI success schemas 必須使用 Domain `StrEnum` 或等價的封閉 Literal，不接受空字串／未知狀態。
5. Import Warning route已由 Domain enum輸出；本波只收斂其 public schemas，不改狀態機。
6. React strict Zod enum維持不變；它是偵測 drift 的最後一道 boundary，不是 normalization owner。

## 4. Success contracts

### 4.1 Anomaly summary／detail／workflow receipt

- `severity: AnomalySeverity`
- `workflow_status: AlertWorkflowStatus`
- list/detail 共用同一 enrich helper，不能只有 list 修好。
- `include_snapshot=false` 仍回 `display_snapshot: null`。
- fingerprint、source identity、version、predicate、navigation語意不變。

### 4.2 Anomaly recovery context

`AnomalyRecoveryContextView` 的 severity／workflow status必須使用相同 enum contract，避免另一條 API
再次把 raw string 當正式狀態。

### 4.3 Import Warning

- task／preview response status 使用 `ImportWarningTrackingStatus`。
- mutation request target只允許既有人工可達的四個狀態，不得因此開放 `open`、`auto_resolved`。
- navigation action allowlist維持不變。

## 5. Error contract

| Condition | HTTP | Code | Retryable |
|---|---:|---|---|
| definition code不存在 | 422 | `anomaly_definition_not_found` | false |
| persisted source domain與definition不一致 | 422 | `anomaly_projection_data_integrity_violation` | false |
| persisted workflow status不合法 | 422 | `anomaly_projection_data_integrity_violation` | false |
| repository暫時不可用 | 503 | 既有 `projector_unavailable`／`transaction_failed` | 依既有規則 |

不得把 contract drift轉成200 empty list、跳過壞列、中文 message branching或500 generic success failure。

## 6. 相容性

- 對合法既有 caller：JSON字串值不變，只是OpenAPI/Pydantic變嚴格。
- 對不合法 caller／fixture：由原本可能通過改為422或model validation failure，屬預期 hardening。
- Streamlit typed client與React decoder不需改 business mapping。
- 無 route path、auth、pagination、entrypoint、transaction或external side effect變更。

## 7. Out of scope

- Claim／Resolve／Recovery mutation接線。
- display snapshot、timeline、recovery action typed化。
- 修改 Domain severity定義或新增第三種severity。
- DB schema、migration、seed、backfill、正式資料修復。
- UI重新設計、放寬Zod、解析raw dict。
- 修復Orders full-suite failures或MasterLayout lint warnings。

## 8. Acceptance

1. Repository-shaped summary即使severity缺省／None，Application也只由registry產生合法severity。
2. 假definition、source-domain drift、unknown workflow status均fail closed。
3. list與detail都回相同合法enum；workflow receipt亦strict。
4. Import Warning六狀態皆可strict response validate，未知值失敗；request target仍只允許四種。
5. focused API/Application tests、Phase2D frontend tests、build/lint與真Chrome Network→DOM fresh pass。
6. 真Chrome顯示canonical anomaly cards與Import Warning tasks，無schema mismatch、無non-GET。
7. 不得以單元fake fixture取代真 Application composition或browser evidence。

## 9. DB Gate

| Gate | Status | Reason |
|---|---|---|
| Scope gate | PASS | public read contract hardening；明確0 DB變更 |
| Change inventory | NOT_RUN | 無schema／seed／backfill |
| Static release gate | NOT_RUN | 無release artifact |
| Descriptor gate | NOT_RUN | 無owned object變更 |
| Read-only plan gate | NOT_RUN | 不執行migration |
| Engine verification gate | NOT_RUN | 可用既有disposable integration test讀取，不改schema |
| Developer acceptance gate | NOT_RUN | 不操作既有DB |

總結：`DB_CHANGE_NOT_READY`，且本工作不需要 DB change。

# LINE 身分管理與解除正式規格

## 1. 文件狀態

- 狀態：`approved-implementation-baseline`
- 人工確認日期：2026-08-11
- 上位契約：`17_External_Integration_LINE_Access正式規格.md`
- 關聯契約：`20_LINE客服與月嫂自助服務正式規格.md`

## 2. Global 與 Domain 邊界

1. `line_identity_bindings` 是 LINE User ID 與 customer、staff、admin subject 關係的 SSOT。
2. `clients.line_user_id`、`staff.line_user_id`、`admin_users.linked_line_user_id` 是 owner projection，不得取代 binding root fact。
3. 解除不刪除個人、訂單、排班、客服、審核或歷史事件；只停用 binding，並在 Rich Menu 回復成功後清除 owner projection。
4. 外部 LINE API 與 MySQL 不能假設原子交易；解除採 durable saga，不把 provider call 包進 DB transaction。
5. Streamlit 只呼叫 Identity Binding bounded API 並顯示 typed views，不直接讀寫 binding 或 owner table。

## 3. 根事實與狀態機

根事實包含 LINE User ID、subject type/reference、binding version、解除請求 ID、預期版本、操作者、原因、default menu publication/provider ID、attempt、error、requested/menu-reset/completed timestamps 與 idempotency/correlation ID。

```text
bound
  └─ request revoke → revocation_pending
                           ├─ menu reset succeeded → revoked
                           ├─ retryable failure → revocation_pending
                           └─ nonretryable failure → revocation_pending + manual entry
```

`revocation_pending` 從建立時即不是有效授權身分；owner projection 暫留 User ID，只供 saga 完成與人工追蹤。完成時先確認 default Rich Menu provider 成功，再清除 owner projection、轉為 `revoked` 並追加事件。

## 4. Commands、Queries 與 typed errors

Queries：binding list、binding detail、revocation detail。Commands：replacement preview/apply、revocation preview/apply、retry、manual complete。第一版 replacement 只允許同 subject type 修正 subject reference，不允許直接把 customer 改成 staff 或 admin。

Typed errors：

- `line_identity_binding_not_found`
- `line_identity_binding_version_conflict`
- `line_identity_revocation_in_progress`
- `line_identity_default_menu_not_published`
- `line_identity_owner_projection_conflict`
- `line_identity_menu_reset_failed`
- `line_identity_manual_completion_forbidden`

## 5. 交易、冪等、retry 與 conflict

1. 解除 apply：鎖 binding，驗證 `bound` 與 expected version，建立解除 root、轉 `revocation_pending`、追加事件/audit/outbox，同交易 commit。
2. worker：以解除 request ID claim；對該 User ID 明確 link 最新已發布 `default_menu`。timeout、429、5xx retry；validation、missing publication 與權限錯誤 fail closed。
3. 完成：鎖 request、binding 與 owner projection；驗證仍為原 subject/version；清除 owner User ID、轉 `revoked`、追加 event/audit、完成 request，同交易 commit。
4. provider 成功後 process crash 可安全 replay；重複 link 同一 menu 後再完成 DB。
5. 所有 command 使用 caller idempotency key；相同 key 不同 payload回 conflict。stale version 不自動 retry。
6. 人工完成只供 `line.identity.binding.override`，必須在 nonretryable/重試耗盡後填寫原因並留下 audit。
7. retryable 錯誤由 outbox next-attempt 驅動；nonretryable 或耗盡時 request 轉 `menu_reset_failed`，管理 UI 顯示 error code/message、retry 與 override 入口，既有 outbox dead-letter／runtime health 監控負責異常警示。

## 6. Rich Menu 與 configuration SSOT

1. revoked 身分明確 link canonical current publication 的 `default_menu`，不依賴 legacy unlink 或 LINE 全域隱含狀態。
2. `config/line_menu.json` 只提供 bootstrap source；既有環境由 MySQL `line_configuration_current` 指向的 revision 決定管理中心預設值。
3. 舊「訂單查詢／尋找專員」只能在 current fingerprint 符合已知舊版時，以 expected revision 與 idempotent upgrade 追加新 revision，更新為「服務登記／服務說明」。人工已修改的 divergent revision 必須阻擋，不得覆蓋。
4. 新解除請求的 publication root 必須指向 `line_rich_menu_publication_tasks`；
   `line_rich_menu_publications` 只保留 stage 12 以前的 legacy 解除歷史參照，不得參與新請求的
   default menu 選擇。既有 legacy request 必須保持可讀，且不得藉 migration 改寫其 provider receipt。

## 7. 管理 UI 與權限

- `line.identity.binding.read`：查詢所有綁定與歷史狀態。
- `line.identity.binding.manage`：replacement preview/apply、正常解除及 retry。
- `line.identity.binding.override`：人工完成 provider 永久失敗的解除。

LINE 管理中心新增「身分管理」，並將「LINE 下方選單」改名「Rich Menu」、「LINE 表單」改名「LIFF 表單」。解除操作必須顯示預覽、原因、binding version 與 default menu blocker。

## 8. 驗收

1. 所有 bound User ID 可依 user、subject type、subject name/status 查詢。
2. 解除建立後專屬 API 立即拒絕該身分。
3. default menu 成功套用前，owner projection User ID 不清除。
4. 成功後 binding 為 revoked，owner projection 為 NULL，解除時間、actor、reason 與事件可追溯。
5. retry、provider-success/process-crash replay、stale version、owner conflict 與 manual override 均有測試。
6. canonical Rich Menu current revision 顯示「服務登記／服務說明」；divergent 人工 revision 不被自動覆蓋。

# LINE 身分管理與解除正式規格

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：LINE Integration（Identity / Revocation / Role Scope）
- 單一負責範圍：`line_identity_role_bindings` role-scoped binding、目前選定角色狀態、綁定失敗計數、解除 saga（含 default Rich Menu 回復）與 Orders 結案自動回復月嫂選單契約。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[External Integration / Access Control](17_External_Integration_LINE_Access正式規格.md)、[Case Import 與非市民待審](17B_Case_Import與非市民Redis待審正式規格.md)、[LINE 客服與月嫂自助服務](20_LINE客服與月嫂自助服務正式規格.md)、[LINE 服務說明與選單角色](29_LINE服務說明、客服互動與選單角色正式規格.md)

## 2. Global 與 Domain 邊界

1. `line_identity_role_bindings` 與 role binding events 是 LINE User ID 與 `customer`、`staff`、`admin` subject 關係的 SSOT（由 LINE Identity application 作唯一 writer）。
2. `clients.line_user_id`、`staff.line_user_id`、`admin_users.linked_line_user_id` 僅作 owner projection，不得取代 binding root fact。
3. 解除不刪除個人、訂單、排班、客服、審核或歷史事件；只停用 binding，並在 Rich Menu 回復成功後清除 owner projection。
4. 外部 LINE API 與 MySQL 不能假設原子交易；解除採 durable saga，不把 provider call 包進 DB transaction。
5. 管理端 UI 只呼叫 Identity Binding bounded API 並顯示 typed views，不直接讀寫 binding 或 owner table。
6. 同一 LINE User ID 可同時具有 `customer` 與 `staff` 兩個 active binding，雙角色合法且不構成 conflict 或 `LINE-004`；每個 binding 以各自的 subject type/reference、version、capability 與 owner projection 獨立驗證，request context 必須明確選定角色，不得合併或反向繼承權限。只有同一 subject type 指向互斥／多個 active subject、owner projection 不一致或 replacement lineage 斷裂時才是 binding conflict。
7. 需求問卷 registration 由 Case Import 擁有，儲存與清除依 [Case Import 與非市民待審](17B_Case_Import與非市民Redis待審正式規格.md)（核准前不進 MySQL）；onboarding 是 binding projection outcome，不得直接提升角色或覆蓋其他 Domain root。

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

## 4. Role-Scoped 身分與角色選擇

### 4.1 唯一 root 與共用契約

1. LINE Identity 以 `(line_user_id, subject_type)` 為 role-scoped binding identity；`customer` 與 `staff` 可同時各有一個 active binding，同一 subject type 僅允許一個 active subject，`admin` 與 `customer`/`staff` 維持互斥。
2. 所有角色共用一套 typed Query／Preview／Apply／receipt／fresh readback，差異只由 `subject_type` 與既有 owner projection port 表達；不得依角色拆建平行 repository 或 event type。
3. 每個 role binding 擁有獨立 version、status、subject reference 與 event lineage；查詢同一 LINE User ID 必須回傳全部 role bindings。
4. 月嫂身分證明只有在唯一配對且該 staff subject 尚無其他有效 LINE binding 時，才可在同一 outer UoW 直接建立 `bound` binding 與 owner projection（不另設人工審核）；若已綁定其他 LINE 帳號則 fail closed 回 typed conflict。
5. 客戶於 `/line-bind` 核對姓名與電話後：未綁定者完成綁定；已綁定同一帳號者顯示「您已完成綁定，可直接返回 LINE 使用」；需改綁者點選「申請重新綁定」建立 pending review，核准前保留原綁定。月嫂選單與對話指令統一使用「月嫂認證／月嫂身分綁定」及「我是月嫂」（加入好友歡迎訊息改由 LINE 官方帳號設定，系統不另發送）。

### 4.2 目前選定角色與聊天室切換

1. 目前選定角色由 LINE Identity 擁有，每個 LINE User ID 至多有一個 nullable `customer | staff` 狀態；它不是一般 session 或多裝置設定。
2. 同時具有 active `customer` 與 `staff` binding 時，request 必須明確選定角色；未選定時 fail closed 並要求選擇，不得依訂單或排班猜測。若只剩單一 active 角色，後續操作使用該唯一角色並產生對應 menu intent。
3. 一對一聊天室使用「切換客戶／切換月嫂」或「切換選單」進行選擇，於 webhook outer UoW fresh-read、驗版本、保存 selected role／audit／receipt 及 menu intent；重播冪等，工會管理員切選單視角不取得客戶／月嫂業務授權。
4. 綁定成功須驗合法 status、非空 receipt identity 與相同 preview fingerprint（pending review 另須有效審核編號）；新連結優先於過期暫存，保留 15 分鐘有效期與一次性限制。

### 4.3 綁定失敗與人工協助

1. 每個 LINE User ID 最多保留一筆 current binding-failure streak（count 上限 2，保存 opaque fingerprint，不存 raw proof）。
2. 綁定失敗不得自動建立客服案件、escalation、hold 或告警；失敗畫面只顯示資料核對提示及「返回修改／呼叫專員」。
3. 只有使用者明確點選「呼叫專員」或在官方聊天室提出需求才由客服流程受理；綁定成功清除同 scope 失敗計數，但不刪除既有客服案件。

## 5. Commands、Queries 與 typed errors

- Queries：binding list、binding detail、revocation detail、`GET /api/v1/line/identity-bindings/replacement-candidates`（依 `subject_type` 查同角色可替換候選，排除已有 active binding 者）。
- Commands：replacement preview/apply（同 subject type 修正 subject reference）、revocation preview/apply、retry、manual complete。
- Typed errors：`line_identity_binding_not_found`、`line_identity_binding_version_conflict`、`line_identity_revocation_in_progress`、`line_identity_default_menu_not_published`、`line_identity_owner_projection_conflict`、`line_identity_menu_reset_failed`、`line_identity_manual_completion_forbidden`。

## 6. 解除交易、冪等、Retry 與 Rich Menu SSOT

1. **解除 apply**：鎖 binding，驗證 `bound` 與 expected version，建立解除 root、轉 `revocation_pending`、追加事件/audit/outbox，同交易 commit。
2. **worker 與 retry**：以解除 request ID claim，link 最新已發布 `default_menu`；timeout／429／5xx retry；明確 retry 須在交易內重讀最新 canonical `default_menu` publication，不重送已失效之 provider ID。
3. **完成與 crash replay**：provider 成功後鎖 request、binding 與 owner projection，清除 owner User ID、轉 `revoked` 並完成 request；crash replay 可重複 link 同一 menu 後再完成 DB。
4. **人工緊急覆寫**：限 `line.identity.binding.override` 於後端在 nonretryable／重試耗盡後填寫原因並留存 audit，不在一般管理 UI 呈現；只撤銷系統授權，後續重新發布可用 `default_menu` 時仍可再排入選單修復。
5. **Rich Menu publication SSOT**：`config/line_menu.json` 僅供 bootstrap；既有環境由 MySQL `line_configuration_current` 決定。新解除請求固定指向 `line_rich_menu_publication_tasks`，訪客選單依 [LINE 服務說明與選單角色 §5](29_LINE服務說明、客服互動與選單角色正式規格.md) 四格名稱維護；已由人工修改之 divergent revision 不得自動覆蓋。

## 7. Orders 結案自動回復與 Staff 退役連動

### 7.1 Staff 退役連動

Staff 退役時於同一 Staff outer UoW 透過 typed port 僅解除 `staff` role；若仍有 active `customer` role，以 revocation request ID 冪等建立 customer menu intent（不與原 role-bind intent 碰撞），否則回復 `default_menu`。

### 7.2 Orders terminal closure auto-restore

Orders 在其 lifecycle aggregate outer UoW 提交 terminal closure event／receipt 時建立對 LINE Identity 的 outbox handoff（identity 由 `case_no`、`terminal_kind` 與 Orders lifecycle version 組成）。

- LINE consumer 核對 source subject、Orders 版本與 capability：一般客戶無 staff binding（含 source subject 為 NULL 且案件 owner 未綁定 LINE）時保存 `noop_not_staff` receipt（若 owner 已有非空 LINE User ID 而 source subject 為 NULL，則屬 subject mismatch 零寫入）。
- 存在有效 staff binding 時，僅在 (1) staff binding 仍為 `active`、(2) 該 LINE User ID 所有 active client-role case 皆經 owner readback 證明 terminal、(3) source event 未處理且版本一致時，才建立一次 `staff_default_restore` menu intent／receipt；任一條件不滿足則保存對應 typed decision（`blocked_active_client_case`、`blocked_revoked_staff`、`noop_replay`）。
- 已保存 receipt 的 source 不再重複喚醒；不阻擋 [LINE 客服與月嫂自助服務 §4.4](20_LINE客服與月嫂自助服務正式規格.md) 原案件群組完工通知。

## 8. 管理 UI 與驗收標準

### 8.1 權限與操作介面

- 權限分層：`line.identity.binding.read`（查詢）、`line.identity.binding.manage`（replacement／正常解除／retry）、`line.identity.binding.override`（僅後端緊急覆寫）。
- 管理端以「身分綁定／待審核／待配對」分頁呈現，一次僅掛載目前任務，依使用者點選列傳遞 `subject_type`，LINE User ID 僅於明細遮罩顯示；審核不預選核准，申請受理、系統停用與選單回復完成分開呈現。

### 8.2 驗收標準

1. 同一 LINE User ID 可同時建立獨立的 `customer` 與 `staff` bindings；同 type 衝突與 admin 互斥 fail closed；雙角色未選角色不得越權，聊天室切換角色 replay 冪等。
2. 解除建立後專屬 API 立即拒絕該身分；default menu 成功套用前 owner projection 不清除；成功後 binding 轉 `revoked` 且 owner projection 為 NULL。
3. 綁定連續失敗僅記錄上限 2 筆 streak，不自動開單或告警；只有明確「呼叫專員」才建客服單。
4. Staff retirement 與 staff-role 解除同一 commit 提交並保留 customer role；Orders 結案自動回復嚴格驗證全部 active client case 皆 terminal，replay 回原 decision receipt。
5. 管理工作區搜尋／分頁由 server 執行，角色隔離、replace candidate 查詢零寫入，且不預選核准或於未知結果時盲目重送。

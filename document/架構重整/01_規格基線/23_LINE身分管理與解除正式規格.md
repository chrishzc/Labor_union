# LINE 身分管理與解除正式規格

## 1. 文件狀態

- 狀態：`approved-implementation-baseline`
- 人工確認日期：2026-08-11
- 上位契約：`17_External_Integration_LINE_Access正式規格.md`
- 關聯契約：`20_LINE客服與月嫂自助服務正式規格.md`
- 2026-08-21 M1 Alternative A amendment：`line_identity_bindings` 唯一 writer、Case Import 擁有 provisional
  registration、onboarding 是 binding projection outcome 而非 role promotion；implementation、schema／DB、
  provider 與真實 E2E 仍須另案 gate。
- 2026-08-30 M1 role-scoped amendment：customer／staff 共用同一 binding root、event stream、
  readback 與 application contract；只新增一個 LINE-owned 目前角色狀態與一筆 bounded
  binding-failure streak。不建立平行 customer／staff 架構、session／preference framework
  或 generic escalation engine。

## 2. Global 與 Domain 邊界

1. `line_identity_bindings` 是 LINE User ID 與 customer、staff、admin subject 關係的 SSOT。
2. `clients.line_user_id`、`staff.line_user_id`、`admin_users.linked_line_user_id` 是 owner projection，不得取代 binding root fact。
3. 解除不刪除個人、訂單、排班、客服、審核或歷史事件；只停用 binding，並在 Rich Menu 回復成功後清除 owner projection。
4. 外部 LINE API 與 MySQL 不能假設原子交易；解除採 durable saga，不把 provider call 包進 DB transaction。
5. Streamlit 只呼叫 Identity Binding bounded API 並顯示 typed views，不直接讀寫 binding 或 owner table。
6. 同一 LINE User ID 可以同時具有 customer 與 staff 兩個 active binding；雙角色本身不是 conflict 或 anomaly。每個 binding 仍以自己的 subject type/reference、version、capability 與 owner projection 獨立驗證，request context 必須明確選定角色，不得把 customer 權限合併成 staff 權限或反向繼承。只有同一 subject type 指向互斥／多個 active subject、owner projection 不一致或 replacement lineage 斷裂時才是 binding conflict。

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

## 2026-08-21 M1 ownership amendment

- `line_identity_bindings` 與 binding events 由 LINE Identity application 作唯一 writer；`clients.line_user_id`、`staff.line_user_id`、`admin_users.linked_line_user_id` 只作 owner projection。
- `provisional_client_registrations` 的 provisional registration 由 Case Import 擁有；LIFF onboarding 成功只表示 binding／projection outcome，不得直接 promotion customer／staff／admin role，也不得覆蓋其他 Domain root。
- legacy direct writers、舊 approve writer 與 `bind.html` 必須 guarded／readonly 或 `410`，逐 caller 建立 replacement、focused regression 與 restore trigger 後退出。Customer Service 的 `binding_failed_assistance` 可提供人工協助；dual-role 依 §2 明定為合法多 binding，後續實作必須補角色選擇、同 type conflict 與 two-failure escalation，不得把雙角色本身投影為 `LINE-004`。
- 真實 verified-token／LIFF browser／registration／binding／Rich Menu E2E 仍需 sandbox config；本正式規格同步不把現況 evidence 宣稱為 PASS，也不授權 provider、schema／DB 或 route cutover。

## 9. 2026-08-30 M1 role-scoped identity amendment

### 9.1 唯一 root 與共用契約

1. LINE Identity 以 `(line_user_id, subject_type)` 為 role-scoped binding identity。customer 與 staff
   可同時各有一個 active binding；同一 subject type 仍只允許一個 active subject。admin
   沿用同一 persistence／event／readback contract，但與 customer／staff 維持既有互斥規則。
2. customer／staff 不得各自新增 repository、application、event type 或 read model。所有角色
   共用一套 typed Query／Preview／Apply／receipt／fresh readback，差異只由
   `subject_type` 與既有 owner projection port 表達。
3. 每個 role binding 擁有自己的 version、status、subject reference 與 event lineage。查詢同一
   LINE User ID 必須回傳全部 role bindings，不再以單一 root row 代表雙角色。
4. additive successor 只從舊 canonical binding root 搬運已有角色與版本；不得從
   `clients.line_user_id`、`staff.line_user_id` 或 admin projection 自動補造第二個 root。無法由舊 root
   唯一重建的狀態維持 fail closed，留給既有 review／reconciliation 邊界處理。
5. 舊 `line_identity_bindings` 只得作 migration／compatibility surface，不得成為第二個
   writer 或角色判定來源。

### 9.2 目前選定角色

1. 目前選定角色由 LINE Identity 擁有，每個 LINE User ID 最多只有一個 nullable
   `customer | staff` 狀態。它不是一般 session、偏好、多裝置或任意 key-value 設定。
2. 只有同時具有 active customer 與 staff binding 時才需明確選擇。雙角色且未選擇時
   fail closed 並要求選擇；Orders、Scheduling、LIFF route、worker 或 Rich Menu adapter 不得根據
   訂單、排班、前一頁或 provider 現況猜測角色。
3. 選擇 Apply 必須重讀該 role binding 仍為 active 後，在既有 LINE outer Unit of Work
   寫入狀態、audit／receipt 與必要 Rich Menu binding intent。不新增 public route／entry point，
   也不改 Rich Menu provider transport／worker boundary。
4. 選定角色已不再 active 時，readback 不得把 stale 狀態當授權；若只剩一個
   customer／staff role，後續的 canonical LINE application 使用該唯一角色並產生對應
   menu intent。這項適配不改變既有解除 saga 狀態機、retry、manual completion 或
   provider-success 判定。

### 9.3 雙次失敗的 bounded streak

1. LINE Identity 每個 LINE User ID 最多保留一筆 current binding-failure streak。scope 固定為
   同一 verified identity flow 與同一 candidate `(subject_type, subject_reference)`；尚未解析出
   root reference 的 not-found 路徑以 normalized proof fingerprint 作為 opaque candidate scope，
   不保存 raw proof。更換 scope 時取代舊 current streak，不累積歷史、window 或通用規則。
2. 第一次失敗只將 count 記為 `1`。同 scope 的第二次連續失敗將 count 記為 `2`，
   並且只呼叫既有 Customer Service `CreateHumanEscalation` typed application 一次；不建立
   generic escalation engine。
3. 同 scope 的綁定成功將 count 歸零並推進單一 streak generation。第二次失敗
   的 ticket source identity／idempotency key 由 scope 與 generation 決定；replay 只回傳原 ticket，
   不重複開單。
4. 原 binding Apply 失敗仍 rollback。失敗記錄使用既有 LINE-owned failure-recording outer
   Unit of Work，在同一 commit 更新 streak 並透過既有 Customer Service typed gateway 建立
   幂等客服單，不新增 provider side effect 或 hidden commit。
5. failure event 與 escalation context 只保存 masked evidence／fingerprint、flow purpose、candidate
   subject type 與 policy version；不寫入姓名、電話、身分證、raw LIFF payload 或 token。既有
   Customer Service ticket root 仍依其 owner contract 保存 canonical requester LINE User ID，
   本 amendment 不另造匿名 ticket schema 或第二套客服 identity。

### 9.4 本 amendment 的非目標與驗收

- 不變更既有解除 saga 的 retry、provider-success、manual-completion 狀態判定、Rich Menu provider
  boundary、`LINE-006`或其他 M1～M4 語意。Staff retirement 只能由 Staff owner 的正式 transition
  在同一 outer Unit of Work 呼叫既有 LINE revocation application contract；只解除 staff role。
- staff role 解除完成後，若仍有 active customer role，LINE 追加以 revocation request ID 冪等識別的
  customer menu intent；否則既有 default-menu reset 即為 terminal menu。不得重用較早 role-bind intent
  identity 而讓恢復選單被去重。
- 不新增 public API／entry point／LIFF route／legacy `line/line_bot.py` workflow，不實作
  provider qualification、production／`union_db` 變更或 deployment。
- 最低驗收：同一 User ID 的 customer／staff 可同時建立、獨立 version／event／readback；
  同 type conflict 與 admin 互斥 fail closed；雙角色未選擇不能越權；選擇 replay 幂等且只產生
  一個 menu intent；失敗 `1 → 2` 只建一張客服單，success reset 後的新 streak
  可在再次兩次失敗時建立新單；Staff retirement 與 staff-role解除同一 commit，customer role保留且
  successor menu intent不與舊bind intent碰撞；既有 revocation／provider／`LINE-006` focused
  regression 不退步。

### 9.5 Orders terminal closure auto-restore（2026-09-01 Task96 contract）

Orders 是案件 terminal closure source owner。只有 Orders 在其 lifecycle aggregate 的單一
outer Unit of Work 內提交 terminal closure event／receipt 時，才可建立對 LINE Identity 的
committed outbox handoff；事件 identity 固定由 `case_no`、`terminal_kind` 與 resulting
Orders lifecycle version 組成，並保存 source subject、producer reference、occurred time、
correlation 與 idempotency identity。事件不得由 LINE、UI、worker 或付款／通知 adapter 猜測或
直接建立；若退款／歸檔由其他 owner 完成，Orders 只攜帶該 owner 的 typed receipt reference，
不得跨域直寫其 root。

LINE Identity consumer 收到事件後必須 fresh-read 同一 LINE User ID 的所有 role-scoped
bindings 與 client-role active-case Query。只有同時滿足以下條件，才可在既有 LINE Identity
outer Unit of Work 內建立一次 `staff_default_restore` menu intent／receipt：

1. staff binding 仍為 `active`；
2. 該 LINE User ID 的每一個 active client-role case 都已由其 owner readback 證明 terminal；
3. source event identity／Orders lifecycle version 尚未處理，且 current binding version、
   target menu revision 與 capability 均一致。

任一 active client case 未 terminal 時，必須保存 typed no-op readback，不得 restore。staff
retirement 或 revocation 已進行／完成時優先於 restore；已 `revoked` 的 staff role 永不得
被此 consumer 恢復。restore 不改 Orders、Client、Staff 或 Scheduling root，也不繞過既有
Rich Menu provider boundary。

同一 source event／idempotency key replay 必須回原 restore 或 no-op receipt；不同 payload、
stale Orders／binding／menu version、subject mismatch 或 capability mismatch 固定 typed
failure 並零寫入。storage transient failure 可 bounded retry；其餘 failure 只能由 LINE
Identity Query／既有人工 review reconcile，必要時建立 manual recovery reference，不得盲目
重播。Readback 必須回 source event identity、Orders version、binding version、case-scope
decision（`restored | blocked_active_client_case | blocked_revoked_staff | noop_replay`）、
menu intent／receipt 與 typed failure。

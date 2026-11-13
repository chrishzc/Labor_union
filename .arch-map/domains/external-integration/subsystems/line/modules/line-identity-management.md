# Module: line-identity-management

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
持久化同一套 role-scoped canonical LINE identity binding、event、readback 與 application contract；customer／staff 可並存，admin 維持排他。同類客戶案件替換只更新 customer role，保留 staff role，並由LINE Identity正常流程完成；不追加LINE-004 anomaly recheck。此 Module 只擁有一個 nullable selected-role 狀態與一個 bounded binding-failure streak，失敗只記錄 bounded count，不自動建立客服需求；客戶改綁需明確申請並沿既有審核，核准前保留原綁定。

## Implementation
- query transport: `api/routes/line_identity_management.py` — role-scoped detail／Preview／Apply 與 bounded replacement-candidates reader。
- 個人選單修復入口為 `POST /api/v1/line/identity-bindings/{line_user_id}/menu/resync`，由身分管理 application 驗證目前有效角色並入列既有選單工作。
- 停用綁定刪除入口為 `POST /api/v1/line/identity-bindings/{line_user_id}/delete-revoked`，由身分管理 application 驗證角色與版本，並在同一交易刪除對應綁定及其紀錄。
- schema: `api/schemas/line_identity_management.py`
- 待審核與待配對分別由原管理 API 驗證狀態、版本及權限後永久刪除申請或登記；NAS 透過限域刪除程序執行。
- contract: `subsystems/line/identity_management_contracts.py`
- review query contract: `subsystems/line/review_contracts.py` — bounded numbered review search，審核 state machine 不變。
- review transport projection: `api/schemas/line_identity.py` — 審核對象姓名、案件及 canonical 綁定的唯讀展示欄位。
- primary:
  - `line/static/identity.html` — 月嫂及工會帳號 LIFF 身分核對與綁定結果，並提供客戶綁定導流。
  - `line/static/bind.html` — 客戶綁定／已綁定／改綁申請分流、取消與明確呼叫專員。
  - `domains/line/identity_binding.py`
  - `subsystems/line/identity_application.py`
  - `subsystems/line/identity_review_application.py` — 正式身分審核 Preview／Apply；通過後按實際 subject_type 讀取該身分成功文案，沿原 UoW 入列通知。
  - `subsystems/line/identity_contracts.py`
  - `api/dependencies/line_identity.py` — NAS 管理員 credential binding 使用內部 access profile；外部客戶／月嫂仍用 LINE profile。
  - `subsystems/line/webhook_identity_handlers.py` — webhook identity dispatch 與未注入 canonical Service Help application 時的 bounded guidance fallback。
  - `subsystems/line/menu_command_application.py` — 既有一對一切換指令接 role-selection application，共用 webhook outer commit，雙角色選擇與事件重播保護。
  - `subsystems/line/identity_management_application.py`
  - `subsystems/line/identity_management_contracts.py`
  - `subsystems/line/staff_retirement_effect.py`
  - `subsystems/line/identity_revocation_worker.py`
  - `infrastructure/mysql/line_identity_review_repository.py`
  - `infrastructure/mysql/line_identity_management_repository.py`
  - `infrastructure/mysql/line_identity_owner_adapters.py` — canonical owner-projection adapters, including active role-scoped admin binding readback for staff LIFF.
  - `infrastructure/mysql/customer_service_repository.py` — shared adapter file containing the canonical staff-subject self-service reader.
  - `subsystems/line/terminal_closure_contracts.py`
  - `subsystems/line/terminal_closure_application.py`
  - `subsystems/line/terminal_closure_worker.py` — canonical LINE worker bridge for the read-only Orders handoff.
  - `subsystems/line/rich_menu_binding.py` — 個人選單 outbox worker，依最新有效工作與 LINE 讀回確認同步。
  - `subsystems/line/outbox_contracts.py` — 共用 LINE outbox 工作契約，含個人選單工作期限、嘗試上限及同步結果。
  - `infrastructure/mysql/line_receipt_outbox_audit.py` — 共用 LINE outbox 租約及帳號選單操作鎖，個人選單領取時保存嘗試次數，完成時保存讀回證據。
  - `infrastructure/mysql/orders_terminal_closure_source.py` — read-only Orders outbox handoff adapter; LINE never acknowledges or mutates Orders.
  - `db/schema_parts/1019_line_identity_role_scope.sql`
  - `db/releases/labor_union_validation_schema_v1.sql` — generated Global validation composition; listed as an exact touched artifact, not LINE-owned business semantics.
  - `scripts/migrate_preserved_database_additive_schema.py` — existing Global migration runner with this release's exact registration/descriptor only.
- entrypoints:
  - `MySqlLineIdentityRepository.replace_subject`
  - internal typed applications only; no new public route or provider entrypoint.

## Dependencies
- outbound: `external-integration/line` — implements the LINE identity typed repository port used by the identity management application.
- outbound: `staff/module:staff-retirement` — binding-reminder query reads the current lifecycle projection to exclude paused/retired staff even when the legacy Staff status still says active; never writes Staff state.
- inbound: `subsystems/line/identity_management_application.py` — coordinates replacement validation, owner projections, audit and the outer Unit of Work.
- outbound: `anomalies` — LINE identity replacement不產生LINE-004 anomaly；LINE-006另由notification-failure typed readback提供必要 owner facts，Anomalies不寫LINE root。
- inbound: `staff/module:staff-retirement` — only after a committed Staff retirement candidate, through the typed effect port and shared outer UoW.

## Contracts
- `binding_reminders(LineIdentityCandidateQuery)` — existing identity application/repository owns bounded unbound current-customer and active-staff reminder query; typed name/phone/case projection excludes active canonical claims and creates no state or delivery task. Notification workbench uses the original binding-read capability.
- `document/架構重整/01_規格基線/23_LINE身分管理與解除正式規格.md` §9 — one role-scoped contract, selected-role state and bounded failure streak.
- `document/架構重整/01_規格基線/23_LINE身分管理與解除正式規格.md` §9.5 — Orders terminal closure is the source; LINE fresh-reads role bindings and active client cases before a single staff default-menu intent.
- `domains/line/identity_binding.py` — role-scoped claim/snapshot plus bounded streak transition.
- `db/schema_parts/1019_line_identity_role_scope.sql` — additive shared root/event successor, selected-role column and streak root.
- Staff retirement committed receipt 在同一 outer UoW 建立 staff-role revocation／default-menu intent；只有 current `staff.retirement.committed` rule 有效且退役前 binding 可核對時，才由 notification registry 建立 source／decision／intent／delivery task，不由 effect 自建 rule 或 template。

## Verification
- layout_status: `custom_current`
- layout_basis: LINE identity frontend adapter tests mirror this module under the React test domain tree. Python tests use the existing module root and the two existing focused files for personal menu binding and its outbox lease.
- static:
  - `python -m py_compile domains/line/identity_binding.py subsystems/line/identity_application.py subsystems/line/identity_management_application.py infrastructure/mysql/line_identity_review_repository.py infrastructure/mysql/line_identity_management_repository.py`
- test_root: `tests/domains/external-integration/subsystems/line/modules/line-identity-management/`
- higher_boundary: `tests/domains/external-integration/subsystems/line/integration/test_line_friend_feedback_regressions.py` — 由上位 LINE Subsystem 擁有；canonical webhook friend-state（follow 不再開啟流程或發送歡迎訊息）、binding link 與客服 feedback continuation 的交易 regression。
- regression: `tests/domains/external-integration/subsystems/line/subsystems/test_line_menu_command_application.py` — 既有 scoped menu command／admin 視角與訪客回復 regression；雙角色選擇的新驗證沿用本 Module contract root。
- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_line_rich_menu_binding.py` — 個人選單讀回與有限重試。
- test_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_outbox_intent_claim.py` — 個人選單工作領取、嘗試上限與租約回收。
- test_root: `ui_react/src/tests/domains/external-integration/subsystems/line/modules/line-identity-management/` — identity presentation adapter masking and strict typed-state coverage.

## Provenance
- `line_identity_role_bindings` and `line_identity_role_binding_events` are the single shared role-scoped successor; legacy roots/events are migration/compatibility input only — `architecture_declared` — `document/架構重整/01_規格基線/23_LINE身分管理與解除正式規格.md` §9.
- Role selection, bounded streak and same-type replacement tests are owned by this Module test root — `source_observed` — `tests/domains/external-integration/subsystems/line/modules/line-identity-management/`.
- Terminal closure ordinary-customer no-staff no-op（含 source subject NULL 且 owner 未綁定時，先驗版本／terminal／capability 再記原 noop receipt）／receipt-filtered pending scan and restore/replay/stale/revocation tests are owned by this Module test root — `source_observed` — `tests/domains/external-integration/subsystems/line/modules/line-identity-management/contract/test_terminal_closure_restore.py`.

## Change triggers
- Reconcile this module when role-scoped binding ownership, selected-role state, bounded streak, replacement constraints, Staff retirement adaptation, persistence implementation root, Customer Service typed dependency, or canonical module test root changes.

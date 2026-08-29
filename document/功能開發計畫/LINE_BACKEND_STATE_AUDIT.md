---
doc_type: execution-inventory
task_id: CUR-LINE-BACKEND-SLIMMING-01
declared_status: blocked-by-task97-priority
owner: LINE / Integration
baseline_head: eaca24903197400343e72342e5f03970e0fda078
inventory_date: 2026-08-29
---

# LINE Backend State Audit

本表是 S0／S1 的 current inventory。`delete` 只代表通過 caller／registration／retention gate 後的目標，
不授權刪除 public entry、schema、migration chain 或歷史資料。Task 97 dirty paths 保留，不把未提交變更誤寫成 release fact。

| item | current path | current owner | real owner | class | action | evidence |
|---|---|---|---|---|---|---|
| Canonical webhook inbox、lease、completion、security receipt | `domains/line/webhook.py`; `subsystems/line/webhook_intake.py`; `subsystems/line/webhook_event_consumer.py`; `line_inbox_events`; `line_webhook_security_receipts` | LINE | LINE | intrinsic | keep-owner | 正式規格 17 §2.1、§3.2；public webhook 已委派 `canonical_line_webhook` |
| Legacy webhook event store | `subsystems/line/webhook_inbox.py`; dead source in `line/line_bot.py`; `line_webhook_events` | LINE legacy | LINE canonical inbox | dead/legacy | delete | `line_webhook()` 在 direct-writer source 前已 return；default runtime 是 canonical；schema/history retention另列 blocker |
| Platform user／friend state | `domains/line/platform_user.py`; `line_platform_users`; `line_friend_state_events` | LINE | LINE | intrinsic | keep-owner | 拿掉 LINE 即無存在意義；正式規格 17 §3.1 |
| Legacy single-role projection | `subsystems/line/user_lifecycle.py`; `line_users.role`; `_update_legacy_line_user_projection` | LINE legacy | canonical identity binding／role-specific request context | duplicated-business | rewrite | 正式規格 23 允許 customer＋staff 多 binding；單一 role 不得成為 business authority |
| Canonical identity binding／review／revocation | `domains/line/identity_binding.py`; `domains/line/review.py`; `subsystems/line/identity_application.py`; `identity_review_application.py`; `identity_management_application.py`; `line_identity_*`; `line_review_*` | LINE | LINE | intrinsic | keep-owner | 正式規格 17 §3.1、23 §2～§5 |
| Owner binding projections | `infrastructure/mysql/line_identity_owner_adapters.py`; `clients.line_user_id`; `staff.line_user_id`; `admin_users.linked_line_user_id` | LINE UoW adapters | Client／Staff／Access projections driven by LINE binding root | adapter | keep-adapter | 正式規格 23 §2 明定為 owner projection；只允許 typed port、fresh lock、同一 outer UoW，不得成為 client/staff lifecycle owner |
| Legacy client binding／review workflow | `subsystems/line/client_binding_application.py`; `subsystems/line/identity_review_workflow.py`; guarded routes in `line/line_bot.py` | LINE legacy | canonical LINE Identity application＋owner projection ports | duplicated-business | delete | canonical `/api/v1/line/identity/**` 已存在；舊 public routes目前多為 410，但 external entry本身保留至 item gate |
| LIFF platform verification／identity flow | `domains/line/identity_flow.py`; `subsystems/line/liff_identity_verification.py`; `line_identity_flows` | LINE | LINE | intrinsic | keep-owner | server-side ID token與 flow token 是 LINE-specific technical state |
| Provisional client registration | legacy `/api/line/register`; `subsystems/case_import/provisional_registration_application.py`; provisional tables | LINE entry／Case Import application | Case Import | adapter | keep-adapter | 正式規格 23 §8：Case Import owns provisional registration；LINE 只傳 verified identity intent |
| Delivery task／attempt／receipt | `domains/line/delivery.py`; `subsystems/line/delivery_worker.py`; `infrastructure/line/messaging_api_adapter.py`; `line_delivery_tasks`; `line_delivery_attempt_events` | LINE | LINE | intrinsic | keep-owner | 正式規格 17 §3.3；canonical provider send path |
| Notification source／decision／intent | `subsystems/line/notification_*`; `line_notification_source_events`; `line_notification_decisions`; `line_notification_intents` | LINE side-channel | source Domain owns fact；LINE owns routing intent／delivery state | transient | keep-owner | source adapters只接受 owner events；payload不得變成 business root |
| Legacy delivery queue／worker | `subsystems/line/delivery_task_workflow.py`; `line/worker.py`; `line_tasks`; `line_task_attempts` | LINE legacy | canonical delivery task／worker | duplicated-business | rewrite | canonical worker is default；legacy mode仍是 registered rollback path，code deletion尚未過 gate |
| Messaging provider calls | `infrastructure/line/messaging_api_adapter.py` plus direct calls in `line/worker.py` | canonical＋legacy | LINE provider adapter | adapter | rewrite | production message send paths目前為 2：canonical adapter與legacy worker；目標為 1 |
| Rich Menu draft／revision | `domains/line/rich_menu_draft.py`; `domains/line/configuration.py`; `line_configuration_*` | LINE | LINE | intrinsic | keep-owner | LINE Product；正式規格 17 §3.1、23 §6 |
| Canonical Rich Menu publication saga | `domains/line/rich_menu.py`; `subsystems/line/rich_menu_application.py`; `rich_menu_worker.py`; `infrastructure/line/rich_menu_api_adapter.py`; `line_rich_menu_publication_*` | LINE | LINE | intrinsic | keep-owner | canonical worker與step receipts已存在 |
| Legacy Rich Menu publication workflow | `subsystems/line/rich_menu_publication_workflow.py`; legacy branches in `api/routes/line_rich_menus.py`; `line/worker.py` | LINE legacy | canonical Rich Menu application／worker | duplicated-business | rewrite | 同一 publication family 同時有 canonical application與direct provider workflow；public routes需保留 contract但改接 canonical path |
| Rich Menu provider calls | `infrastructure/line/rich_menu_api_adapter.py` plus direct calls in `rich_menu_publication_workflow.py` | canonical＋legacy | LINE provider adapter | adapter | rewrite | direct `api.line.me` calls不得留在 subsystem workflow |
| Order-group binding／participants | `domains/line/order_group.py`; `line_order_group_*`; `subsystems/line/order_group_application.py` | LINE | LINE | intrinsic | keep-owner | group identity、membership、invitation delivery因 LINE 才存在 |
| Orders `line_group_id` projection writer | `infrastructure/mysql/line_order_group_adapters.py::set_group_projection`; `orders.line_group_id` | LINE adapter writing Orders | LINE order-group root；Orders query只可投影 | duplicated-business | rewrite | canonical `line_order_group_bindings` 已保存 group root；停止 LINE 對 Orders table direct UPDATE，schema retention另列 blocker |
| Matching LINE interaction tokens | `matching_line_interactions`; `matching_schedule_line_interactions`; `subsystems/line/matching_postback_application.py` | Scheduling＋LINE adapter | Scheduling owns match decision；LINE owns recipient token／delivery | transient | keep-adapter | formal postback path呼叫 Scheduling application；不得保存 matching final lifecycle |
| Customer Service tickets／escalation | `subsystems/line/service_help_application.py`; `runtime_human_escalation_source.py`; Customer Service tables | Customer Service through LINE ingress | Customer Service | adapter | keep-adapter | LINE只解析 intent並呼叫 Customer Service application；ticket status不屬 LINE |
| Baby Log media／text ingress | `subsystems/line/liff_media_upload.py`; `media_application.py`; `media_archive.py`; `line_media_records` | LINE media＋Scheduling/owner linkage | source Domain owns log；LINE owns provider media receipt／digest | adapter | keep-adapter | 保留 verified ingress、provider metadata與controlled-file port；不另建 service-day business state |
| Deterministic routing／approved knowledge interaction | `deterministic_ai_router.py`; `knowledge_question_application.py`; Knowledge tables | LINE adapter／Knowledge | Knowledge owns approved content；LINE owns presentation interaction | adapter | keep-adapter | 正式規格 20 Phase 1；不得升格為 business mutation owner |
| Full/rejected AI speculative paths | unused confidence／LLM／autonomous branches（若 caller inventory確認） | none／legacy | none | dead/legacy | delete | full autonomous AI正式 REJECT；current deterministic routing與cited Knowledge不刪 |
| Runtime heartbeats／alerts／targets | `line_worker_heartbeats`; `line_alert_*`; runtime applications | LINE operations | LINE technical operations；Customer Service owns human case | intrinsic | keep-owner | health／target CAS為 technical state；escalation經 Customer Service boundary |
| Config-file stores | `config/line_menu.json`; `rich_menu_ids.json`; LIFF/message config plus `configuration_store.py` | mixed legacy bootstrap | LINE configuration bootstrap／compatibility | adapter | rewrite | MySQL current revision為正式 SSOT時，file只能 bootstrap，不得形成平行 current state |
| Public compatibility entries | guarded `/api/line/**`, legacy LIFF pages, webhook aliases | LINE transport | canonical applications | adapter | keep-adapter | entry queue仍有 active／retired_410混合；caller evidence不足者不得刪 route，只能移除 unreachable implementation |
| Schema／migration/history | all LINE schema parts, release manifests, provider／identity／audit history | release governance | release governance／LINE historical evidence | intrinsic | keep-owner | 本任務不得 drop／rewrite migration chain；停止新寫後仍保留，逐項等 retention Authority |

## Current measurable baseline

- Cross-domain direct write sites requiring slimming：2 families—Orders `line_group_id` projection，以及 legacy client binding/review direct writes。
- Formal identity owner-projection adapter family：1；依正式規格保留為 typed adapter，不計為 LINE business ownership。
- Production-capable messaging provider send paths：2（canonical `LineMessagingApiAdapter`、legacy `line/worker.py`）。
- Rich Menu provider implementations：2（canonical adapter、legacy publication workflow）。
- Canonical public webhook path：1；`line/line_bot.py` 內另有一段 unreachable direct-writer source。

## Task 97 overlap checkpoint

S0／S1 已完成，但 S2～S9 production refactor 暫停。Task 97 current checkpoint仍有 repository writer
classification、raw-dict API、entry governance、legacy retirement與 fresh-clone global acceptance 未完成；
任何 LINE writer／route／worker修改都會使其 candidate、entry queue及驗證 evidence失效。依 2026-08-29
最新人工裁決，固定先完成 Task 97，再以其 final baseline重新計數並執行本 write set。

## Retention blockers

- `DESTRUCTIVE_RETENTION_DECISION`：`line_tasks`／`line_task_attempts`、legacy webhook tables、`orders.line_group_id`、legacy identity/review tables及其歷史資料不得在本任務自行 drop／delete。
- `DESTRUCTIVE_RETENTION_DECISION`：public compatibility entries只有在 item-level caller evidence完整後才能移除；目前預設保留 route並回 canonical result或明確 410。

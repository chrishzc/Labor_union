---
doc_type: resolved-write-set
task_id: CUR-LINE-BACKEND-SLIMMING-01
declared_status: blocked
owner: LINE / Integration
date: 2026-08-30
current_blocker: awaiting_user_resume_and_current_head_refresh
---

# LINE Backend Resolved Write Set

Production 修改只限下表。發現新 dependency 時，先補 evidence 與本表，再修改；三種正式 blocker 只停止受影響子項。
Task 97 final baseline已存在，但本表仍是pre-refresh write set。任何row在使用者恢復本計畫並完成current-head
caller／owner／replacement／gate refresh前都不得施工；Task 97已吸收的row必須從本表移除而非重做。

| path | action | owner | target responsibility | dependency | gate |
|---|---|---|---|---|---|
| `line/line_bot.py` | rewrite | LINE transport | 刪 unreachable direct-writer source與不再使用的 imports；保留 canonical webhook及未裁決 public compatibility routes | `api/line_webhook_boundary.py` | internal dead-code gate |
| `api/routes/line_system_config.py` | rewrite | LINE transport | worker wakeup改用 canonical wakeup publisher，不 import legacy worker | `api.dependencies.line_runtime` | focused route tests |
| `line/worker.py` | rewrite／retain-restricted | LINE legacy compatibility | 不再被 canonical API import；僅 legacy runtime mode可動態載入 | runtime cutover contract | legacy runtime仍 registered，不可 delete |
| `subsystems/line/client_binding_application.py` | delete candidate | LINE Identity legacy | 移除 duplicate binding transaction | canonical identity application | public entry保留 410；module caller gate |
| `subsystems/line/identity_review_workflow.py` | delete candidate | LINE Identity legacy | 移除 direct clients write與legacy review state machine | `identity_review_application.py` | caller／entry／test gate |
| `subsystems/line/user_lifecycle.py` | rewrite | LINE Identity | 只保留 platform follow/unfollow adapter所需部分；移除單一 business role authority | canonical platform user／identity binding | legacy runtime caller gate |
| `subsystems/line/delivery_task_workflow.py` | delete candidate | LINE Delivery legacy | 停止建立 `line_tasks`；所有 current caller改為 canonical delivery repository | canonical `LineDeliveryTaskRepositoryPort` | caller inventory＋focused regression |
| `subsystems/line/webhook_inbox.py` | delete candidate | LINE Ingress legacy | 移除 duplicate legacy inbox implementation | canonical webhook intake／repository | schema/history retain |
| `infrastructure/mysql/line_order_group_adapters.py` | rewrite | LINE Order Group | 只讀 Orders audience；停止更新 `orders.line_group_id` | `line_order_group_bindings` | focused order-group regression |
| `subsystems/line/order_group_application.py` | rewrite | LINE Order Group | 只寫 LINE-owned binding／participants／delivery | Orders audience query port | no Orders direct write |
| `subsystems/line/ports.py` | rewrite | LINE | 移除 Orders projection mutation method；保留 query port | order-group application | static protocol tests |
| Orders detail query adapters／schemas as needed | rewrite | Orders query | `line_group_id` 顯示改由 LINE binding query projection取得，保持 public field | `line_order_group_bindings` | public response compatibility |
| `subsystems/line/rich_menu_publication_workflow.py` | rewrite／delete candidate | LINE Rich Menu legacy | public compatible operations改接 canonical application；移除 direct provider calls | canonical Rich Menu application／worker | route caller＋publication regression |
| `api/routes/line_rich_menus.py` | rewrite | LINE transport | publication routes只接一套 canonical lifecycle | canonical Rich Menu application | public schema保持不變 |
| `infrastructure/line/messaging_api_adapter.py` | keep-adapter | LINE Delivery | 唯一 messaging provider send adapter | canonical delivery worker | provider adapter tests |
| `infrastructure/line/rich_menu_api_adapter.py` | keep-adapter | LINE Rich Menu | 唯一 Rich Menu provider adapter | canonical Rich Menu worker | saga tests |
| `subsystems/line/deterministic_ai_router.py`、Knowledge adapter | keep-adapter | LINE／Knowledge | 保留 deterministic／cited current behavior | Customer Service／Knowledge applications | current regression only |
| unused AI／legacy modules discovered by import＋registration proof | delete | none | 清除 speculative framework | none | delete gate；不得碰 current deterministic／Knowledge |
| affected tests／config／registrations | rewrite／delete | owning package | 只驗 current architecture；不為 obsolete test保留 legacy path | corresponding production change | focused regression |

## Explicitly excluded write set

- `db/schema_parts/**`、`db/schema.sql`、migration／cutover release chain。
- provider／identity／review／audit／reconciliation historical rows。
- `union_db`、production、provider sandbox、deployment、entry switch。
- Task 96 M1～M4 未完成功能。

## Current stop condition

`BLOCKED / AWAITING_USER_RESUME_AND_CURRENT_HEAD_REFRESH`：Task 97 repository-local writer、entry、transaction
與retirement evidence已完成；production／DB／external acceptance仍未執行。S2～S9所有rows維持未施工；只有
使用者另行恢復LINE計畫後，才可從Task 97 final artifacts重新盤點受影響rows，不能沿用本表stale count直接修改。

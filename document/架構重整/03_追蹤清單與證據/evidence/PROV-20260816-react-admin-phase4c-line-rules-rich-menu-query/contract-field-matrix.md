# Phase 4C-Q contract field matrix

## Request allowlist

| Surface | Method／path | Auth | Budget | Disposition |
|---|---|---|---|---|
| Rules catalog | `GET /api/v1/line/notification-rules` | fresh memory bearer／`line.config.read` | tab activation 1 | `CLIENT_STRICT_DECODE` |
| Rich menu config | `GET /api/v1/line/configurations/rich_menus` | same | tab activation 1 | `CLIENT_STRICT_DECODE` |
| Publications | `GET /api/v1/line/rich-menus/publications?page=1&page_size=100` | same | tab activation 1 | `CLIENT_STRICT_DECODE_LOADED_SCOPE` |
| Publication detail | `GET /api/v1/line/rich-menus/publications/{id}` | same | explicit selection 1 | `CLIENT_STRICT_DECODE` |

所有 POST／PUT／DELETE 固定 `LOCKED_OUT_OF_SCOPE`。`publish-preview` 會 INSERT＋commit，不是零寫入 Preview。

## Notification rules

| JSON path | Type／constraint | UI disposition |
|---|---|---|
| `data.revision` | integer `>=0` | display |
| `data.definition` | strict `{}` or `{rules: strict rule[]}` | empty/catalog |
| `rules[].id/template_id` | domain identifier | display |
| `rules[].event_code` | `order_lifecycle_transition | service_time_checkpoint | beclass_completion_changed | deposit_confirmed` | display label |
| `rules[].recipient_selector` | `client | assigned_caregiver | case_group` | display label |
| `rules[].enabled` | optional boolean；缺省依Domain為`false` | adapter materialize/display |
| `rules[].schedule` | immediate／relative_service_time／service_end；relative requires nonnegative offset | summary |
| `rules[].frequency` | optional；缺省`once`；recurring_bounded需positive maximum/interval | adapter materialize/summary |
| `rules[].predicates[]` | optional；缺省`[]`；registered literal only | adapter materialize/summary |

No active revision／empty rules 是真 empty；missing/wrong/extra/unknown literal 是 unavailable。

## Rich menu configuration

Envelope：`kind=rich_menus`、revision integer `>=0`、strict definition。revision 0＋`{}`為empty；非空definition
對齊 `LineMenusConfig`。Pydantic有default的version/menu flags/size/appearance/button colors/border/action uri_source
可optional，由adapter依正式default materialize；required結構與所有出現欄位仍strict decode。

Render allowlist：menu id/name/audience role/enabled/selected/default/chat-bar、button label與bounds。禁止 render
literal URI、postback data、rich-menu alias、image path/provider asset identity。

## Publication

List：strict `items/page/page_size/total/total_pages`，但route只先取100筆，本波只作loaded-scope display，
不宣稱完整total；detail與item同 schema：positive id、menu definition id、
nonnegative configuration revision及 status enum：`draft|queued|publishing|published|publish_retryable_failed|failed|
rollback_queued|delete_queued|rollback_retryable_failed|delete_retryable_failed|rolled_back|deleted`。

Unknown status、extra/missing/null violation一律 schema mismatch，不可當 published。

Publication detail ID由client先驗positive integer；live route尚未transport-level `ge=1`，記錄backend gap。

## Known backend gap

Routes仍以 `BaseResponse[dict]` 宣告且errors未完全Global typed；本波只建立fail-closed bounded client，不修改
public API。後續 Phase4C-H 才處理 typed Pydantic views、correlation與Rich Menu Preview寫入邊界。

---
doc_type: implementation-specification
declared_status: approved
identity: PROV-20260816-react-admin-phase4c-line-rules-rich-menu-query
date: 2026-08-16
owner: LINE Configuration / React Integration
domain: LINE Configuration
subsystem: Notification Rules Catalog / Rich Menu Snapshot / Publication History
authority: user-approved-autonomous-phase-progression-2026-08-16
---

# React 管理端 Phase 4C-Q：LINE Rules／Rich Menu Query-only 規格

## 0. 合法完成邊界

保留 `LineManagementPage` 六個 tabs、既有客服與身分管理真實流程，只把通知規則目錄、Rich Menu
設定快照與發布歷史改成 authenticated GET 真資料。所有 Save／Delete／Manual Replay／Publish Preview／
Publish／Retry／Upload／Delete Image 固定 native disabled。

本波不主張 backend raw response model 已完成 hardening；React bounded client 必須將 envelope 與完整
definition 嚴格驗證成封閉型別，任何 unknown/missing/extra/enum drift 一律顯示 unavailable，不得把 raw
`dict` 傳到 adapter 或 render。

## 1. Business scenario

具有 `line.config.read` 的已登入管理員開啟 LINE 管理頁後，只有切到對應 tab 才查詢：

1. current notification-rule revision／catalog；沒有 revision 或 rules 時顯示真實空狀態，不顯示 mock 規則。
2. current rich-menu configuration，依 server audience role 顯示 phone preview。
3. rich-menu publication history，顯示 server id、configuration revision 與狀態，不推導 provider 成功。

## 2. 唯一允許的 HTTP contract

- `GET /api/v1/line/notification-rules`
- `GET /api/v1/line/configurations/rich_menus`
- `GET /api/v1/line/rich-menus/publications?page=1&page_size=100`
- `GET /api/v1/line/rich-menus/publications/{publication_id}`（只在人工開啟 detail 時）

每次 request 即時取得 memory bearer；不得 token in URL/storage/log。tab 首次載入各最多一個 GET；detail
每次人工選擇最多一個 GET；0 polling、0 N+1。支援 AbortSignal 與 generation guard。

## 3. Strict local public views

Notification rules：revision 非負整數；definition 只允許 `{}` 或 strict `{rules: [...]}`。rule 必須包含
`id/event_code/recipient_selector/template_id/schedule`；`enabled/frequency/predicates` 依 Domain 可省略，client
不得使用 Zod `.default()`，由 adapter 明確 materialize `false/{kind:"once"}/[]`。event、recipient、schedule、
frequency、predicate 皆使用現行 Domain allowlist literal。

Rich Menu configuration：`kind=rich_menus`、revision 非負整數；revision 0／`definition={}` 顯示真實空狀態。
非空 definition strict 對齊 `LineMenusConfig`；Pydantic 有 default 的 `version/enabled/selected/set_as_default/
size/appearance` 與button appearance可省略，adapter只依正式 Pydantic default materialize，不使用Zod default。
menu/button/bounds/action的存在欄位仍嚴格驗證。transport schema可驗證合法URI/image/alias欄位，但adapter與
UI不得 render literal URI、postback data、provider IDs、alias或 image path，只顯示安全label／role／layout。

Publication：item strict decode；status 只接受 Domain 12 個 enum。未知 status fail closed，不能歸類為成功。
route目前最多先載入100筆再做in-memory filter／pagination，本波固定 `page=1&page_size=100` 並只稱
`loaded-scope history`，不得把 `total/total_pages` 宣稱為全量。detail與list item schema一致；client在發送前
拒絕非正整數publication ID。

## 4. UI preservation／stable IDs

必須保留 `line.tab.richmenu`、`line.tab.push-queue`、六 tabs、phone preview、rule list／Drawer與既有
客服／identity surfaces。新增或固定：

- `line.notification-rules.refresh`
- `line.notification-rules.list`
- `line.notification-rules.empty`
- `line.notification-rules.unavailable`
- `line.notification-rule.detail`
- `line.notification-rule.create`／`.save`（disabled）
- `line.richmenu.refresh`
- `line.richmenu.configuration`
- `line.richmenu.publications`
- `line.richmenu.publication-detail`
- `line.richmenu.unavailable`
- `line.richmenu.publish`（disabled）

## 5. Safety／out of scope

- 禁止任何非 GET、provider call、wakeup、DB mutation、fake alert/confirm、mock RULES／menu literals。
- `publish-preview` 雖名 Preview 但會 INSERT＋commit，明確禁止。
- 不修改 backend、DB、shared transport、Auth、App、package、其他頁面。
- Delivery Tasks／Knowledge FAQ 另受 Phase4C public-query hardening gaps 阻擋。

## 6. Completion semantics

focused/full React tests、build/lint及 static scans 通過後最高為
`completed-local-validated-query-only`；沒有真 browser controlled session/data evidence時不得稱 cutover ready。

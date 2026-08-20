---
doc_type: implementation-specification
declared_status: approved
identity: PROV-20260816-react-admin-phase3a-line-customer-service-identity
date: 2026-08-16
owner: Customer Service / LINE Identity Management / React Integration
domain: Customer Service / LINE Identity Management
subsystem: Ticket Handling / Identity Revocation / React Presentation
authority: human-approved-exact-package-2026-08-16
---

# React 管理端 Phase 3A：LINE 客服結案與身分解除規格

## 0. 目的與成功邊界

保留現有 `LineManagementPage` 六個 tab、表格、手機預覽及 rule Drawer 的視覺結構，只把下列
既有可見區塊改成真實資料與受控 action：

1. 客服 ticket summary／list／detail；
2. 客服 ticket 的「結案」Preview → Apply → receipt-equivalent detail → re-query；
3. LINE identity binding list／detail；
4. identity revocation Preview → Apply → durable saga status re-query。

本波不是 LINE 全功能上線。Rich Menu publication、delivery queue control、notification rules、FAQ／
Knowledge lifecycle、綁定邀請、order-group create/cancel、replacement、retry 及 manual-complete 固定留在
Phase 4 或後續專用 Work Package，控制位置保留且原生 disabled。

## 1. Business scenarios

### 1.1 客服結案

已完成帳密 Challenge 與 TOTP 的工會人員查看等待／處理中 tickets，打開 detail，確認 current version、
事件與去敏身分後，輸入 internal note（可空）並預覽 `handling|resolved` transition。Apply 必須 fresh-read、
驗證 expected version、使用 idempotency key，收到 server 結果並重新查詢後才顯示成功。

現行 backend 的 `PATCH /api/v1/customer-service/tickets/{ticket_id}` 沒有 Preview endpoint，與 Global
mutation contract 不閉合。本規格要求新增 purpose-specific Preview／Apply pair；Phase 3A React 不呼叫、
不修改也不退役既有 PATCH。新 pair 通過 route/application tests 前，「結案」固定 unavailable。
`reply` 不是現有可見 UI 的結案 action，本波不新增回覆編輯器。

### 1.2 身分解除

工會人員在 binding 表格選擇仍為 `bound` 的身分，開啟既有操作位置的預覽 Drawer，看到 subject、
binding version、default menu publication、provider menu ID 與 blockers，填寫非空原因後 Apply。
成功只代表 revocation request 已提交且 binding 立即不再授權；不得顯示 owner projection 已清除或 saga
已完成。UI re-query 顯示 `revocation_pending`／request status；provider 成功後才可能成為 `revoked`。

## 2. 權威與不變量

- Global：`01_規格基線/00_Global_共同契約.md`。
- Customer Service：`01_規格基線/20_LINE客服與月嫂自助服務正式規格.md`。
- LINE Identity：`01_規格基線/23_LINE身分管理與解除正式規格.md`。
- React 主計畫：`document/功能開發計畫/React管理端遷移與UI真實業務流程驗收計畫.md`。

不可破壞的不變量：

1. Customer Service ticket status／version 由 Customer Service 擁有；React 不從 event 文案推 transition。
2. LINE binding／revocation saga 由 LINE Identity Management 擁有；React 不直接寫 owner projection。
3. Query 唯讀；Preview 零寫入；Apply fresh-read、expected version、idempotency、單一 UoW 與 receipt。
4. 客服 reply／identity revocation 造成的 LINE 外部效果只能由 committed durable task／worker 執行。
5. provider timeout 或失敗不回滾已提交的 ticket／revocation root，也不得在 UI 偽造成完成。
6. 任何成功必須由 typed server result 加 re-query observation 證明；不得 optimistic update。
7. `line_user_id`、client phone、internal note、provider ID 依 matrix 分為 masked、restricted 或 internal-only；
   不得進 log、URL、hash route、snapshot 或 evidence receipt。
8. 所有 enabled internal users 的業務能力相同；本波不得依 prototype role 字串隱藏功能。

## 3. HTTP allowlist

### 3.1 Customer Service

已存在且允許：

- `GET /api/v1/customer-service/tickets/summary`
- `GET /api/v1/customer-service/tickets`
- `GET /api/v1/customer-service/tickets/{ticket_id}`
- `POST /api/v1/customer-service/tickets/{ticket_id}/update/preview`
- `POST /api/v1/customer-service/tickets/{ticket_id}/update/apply`

Preview request 必須只包含 proposed status、nullable internal note、expected version 與 correlation ID；
Preview view 至少包含 before/after status、current/expected version、blockers、candidate fingerprint 與
apply readiness。Apply request必須帶expected version、preview fingerprint、idempotency key、correlation
ID與proposed status/note。精確欄位由G1 Pydantic matrix凍結，不得由writer自創。若新增pair會改變
既有Domain transition或UoW語意，固定停止並回`PUBLIC_CONTRACT_SCOPE_EXPANSION_REQUIRED`，不得在
React模擬Preview，也不得破壞legacy PATCH caller。

`POST /{ticket_id}/reply` 本波禁止。

### 3.2 LINE Identity Management

- `GET /api/v1/line/identity-bindings`
- `GET /api/v1/line/identity-bindings/{line_user_id}`
- `POST /api/v1/line/identity-bindings/{line_user_id}/revocation/preview`
- `POST /api/v1/line/identity-bindings/{line_user_id}/revocation/apply`

replacement、retry、manual-complete 全部禁止。Preview 不帶 idempotency；Apply 帶 expected version、trim
後 1..1000 reason、idempotency key 與 correlation ID。request ID 是 saga identity，不等於完成 receipt。

## 4. Frontend state machines

兩條 mutation 均使用 discriminated union，不得使用互相矛盾的 loading/success/error booleans：

```text
idle → query_loading → query_ready → preview_loading → preview_ready
     → apply_pending → result_received → requery_loading → observed
                         └ timeout/503 → outcome_unknown → same-key retry
```

- stale/version conflict：保留輸入但移除舊 preview，要求 re-query＋重新 Preview。
- schema mismatch：fail closed，顯示 contract error，不 render Apply。
- apply pending／outcome unknown：Drawer 不得由 Escape、backdrop、X 或 footer 關閉。
- Apply 單一飛行；重試只能使用已保存的同一 payload 與 idempotency key。
- 新 Preview 必須建立新 idempotency key；不得重用上一筆 observed command key。
- 客服 observed 以 detail version/status 為準；identity observed 以 binding/request query 為準。

## 5. UI preservation 與 control inventory

必須保留六個 tab 與既有 tickets、Rich Menu、binding、rules、FAQ、groups surface。至少新增／固定：

- `line.page`
- `line.tab.tickets`
- `line.ticket.table`
- `line.ticket.detail`
- `line.ticket.resolve.preview`
- `line.ticket.resolve.apply`
- `line.tab.binding`
- `line.identity.table`
- `line.identity.revocation.drawer`
- `line.identity.revocation.reason`
- `line.identity.revocation.preview`
- `line.identity.revocation.apply`

其餘 mutation controls（Open LINE、publish、invite、replacement、retry、manual-complete、rule save、FAQ、
groups）必須列入 locked inventory，原生 disabled、無 fake handler、無 non-GET request。不得用
`display:none`、刪除 tab、刪除按鈕或空白頁冒充處理缺口。

## 6. Strict decoder 與 errors

- Zod 必須 `.strict()`；後端 required 不得 optional/default。
- 禁止 `z.any`、`z.unknown`、`z.record`、`.passthrough()`、`.catch()`、`.default()`、`.coerce()`、
  `.preprocess()`、`.transform()` 及 `as any`／`unknown as`。
- nullable 與 optional 必須依 Pydantic 精確區分。
- 每個 DTO 至少測 missing required、wrong primitive、unknown key、null violation、enum drift、invalid range。
- errors 不能靠 message substring branching；HTTP status、`detail.code` 與已凍結 typed payload分層處理。
- 401 回登入入口；403 顯示不可用；404 清除 selection；409 顯示 stale/blocker；422 schema/request error；
  429/503 只在 server retryable 或 transport outcome unknown 時提供安全重試。
- 每次 request 即時取得 current memory session token；不得 module-load快取或寫入browser storage。

## 7. Out of scope

- DB schema／migration／seed／backfill；
- 真人 LINE publish/send；只驗證 committed durable task／request；
- customer reply editor、native LINE app deep-link；
- identity replacement、retry、manual override；
- Rich Menu、delivery tasks、notification rules、FAQ／Knowledge、order groups；
- App router、Auth、shared transport、package／lockfile、其他 10 頁；
- Streamlit retirement、entry cutover、deployment。

## 8. Completion semantics

最高狀態只有在 G0–G8 全 PASS 時為 `completed-local-validated`。缺 controlled ticket/binding 或真 browser
證據時固定 `blocked`；backend Preview contract 尚未閉合時 Customer Service mutation 固定
`blocked-backend-contract`，不得以 identity flow 完成替代整包完成。

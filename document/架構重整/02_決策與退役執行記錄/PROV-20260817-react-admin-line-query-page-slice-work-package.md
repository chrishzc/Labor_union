---
doc_type: work-package
declared_status: approved
identity: PROV-20260817-react-admin-line-query-page-slice
date: 2026-08-17
owner: LINE React Page Integration Owner
domain: Customer Service / LINE Identity / LINE Configuration
subsystem: line-management-query-page-slice
authority: PROV-20260817-react-admin-page-slice-migration-execution-decision
approval_required: 核准此 exact React LINE Query Page-Slice Work Package
approval_evidence: user-replied-核准此-exact-React-LINE-Query-Page-Slice-Work-Package
evidence_directory: document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-line-query-page-slice/
completion_ceiling: query-real-data-validated
ui_execution_mode: browser-required
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: LineManagementPage、四組query client/adapter或相關route drift時重新凍結
---

# React LINE 管理：逐頁精簡 query page-slice 工作包

## 1. Scope

本包讓 `LineManagementPage` 成為單一 query-only 管理頁，只使用已存在且經 strict client驗證的四組 GET：

1. Customer Service summary/list/detail。
2. LINE Identity binding list/detail。
3. Notification Rules current catalog。
4. Rich Menu configuration/publication list/detail。

頁面保留六個 tab與現有視覺階層；Delivery、FAQ／Knowledge、Order Groups三組未達本包typed/redacted門檻的
surface原位顯示 `unavailable`，不另拆欄位gap，也不得以其他route存在或HTTP 200冒充已接線。

現有客服結案、身分解除、Rich Menu發布／重試等 mutation code即使已有client、tests或可操作畫面，均不是本包query完成證據。
本包執行後 `LineManagementPage` 不得呼叫任何 non-GET；mutation successor仍依既有Phase 3A／4C文件處理。

## 2. Existing query contracts

### 2.1 Customer Service

- `GET /api/v1/customer-service/tickets/summary`
- `GET /api/v1/customer-service/tickets?page=<n>&page_size=<1..100>...`
- `GET /api/v1/customer-service/tickets/{ticket_id}`
- 重用 `customer_service_client/schemas/errors` 與 adapter；summary/list/detail success與nested views strict。
- Page只能import/query interface，不得呼叫 update/reply/resolve Preview／Apply。

### 2.2 LINE Identity

- `GET /api/v1/line/identity-bindings`
- `GET /api/v1/line/identity-bindings/{line_user_id}`
- 重用 `line_identity_client/schemas/errors` 與 adapter；只render masked LINE user id與核准subject/status/version欄位。
- revocation Preview／Apply、invite、replacement、manual complete與retry全部排除。

### 2.3 Notification Rules

- `GET /api/v1/line/notification-rules`
- 重用 completed Phase 4C query client／adapter的strict decoded catalog；raw route dict不得直接進page。
- current revision、event/recipient/template、schedule/frequency、enabled只依server值顯示；若現行已核准的
  Pydantic contract 明確宣告可省略欄位，adapter 只能物化該正式 default（例如 `enabled=false`、`frequency=once`、
  `predicates=[]`），不得新增業務推導或前端猜測；create/save/delete/manual replay排除。

### 2.4 Rich Menu

- `GET /api/v1/line/configurations/rich_menus`
- `GET /api/v1/line/rich-menus/publications?page=1&page_size=100`
- `GET /api/v1/line/rich-menus/publications/{publication_id}`
- 重用 completed Phase 4C strict client／adapter；configuration與publication history分開載入並各自呈現error/empty。
- publish-preview/publish/image upload/delete/retry與provider side effect排除。

四組 query 每次request讀取fresh memory bearer、使用AbortSignal與Global typed errors。UI不得render action URI、postback data、
image path、provider id、correlation、raw error、payload JSON或完整LINE user identity。

## 3. Unavailable surfaces

以下tab保留但0 GET、0 fixture fallback、0 hard-coded business content：

- `line.tab.delivery`／現有push queue若指向delivery task：顯示後端typed redacted query尚未納入本包。
- `line.tab.faq`：不顯示硬編FAQ文章；只顯示catalog未開放。
- `line.tab.order-groups`：不使用現有raw／非本包契約route；顯示unavailable。

若live六tab命名仍為`tickets/richmenu/binding/push_queue/faq/order_groups`，`push_queue`在本包只承載Notification Rules catalog；
不得混入delivery queue。Delivery另設 unavailable slot或在tab內清楚分區。

## 4. All mutation controls native disabled

至少鎖定：

- `line.ticket.resolve.preview|apply|retry`、update、reply、open-LINE。
- `line.identity.revocation.preview|apply|observe`、invite、replacement、retry、manual-complete。
- `line.notification-rule.create|save|delete|replay`。
- `line.richmenu.publish|retry|upload|delete`。
- `line.delivery.retry|replay|cancel|run-now`。
- `line.faq.create|save|publish|retire|reindex`。
- `line.order-group.create|bind|unbind|replay`。

Unavailable slots 必須使用穩定 ID `line.delivery.unavailable`、`line.faq.unavailable`、
`line.order-groups.unavailable`；不得以靜態 FAQ、空白成功或 delivery/order-group HTTP 200 代替。

上述 mutation controls 必須原生`disabled`且不得掛 handler；query tab、detail、refresh、pagination 等唯讀控制仍可操作，
但只能觸發本包列出的 GET。全頁 0 local business mutation、0 `alert/confirm/prompt`、0 POST/PUT/PATCH/DELETE。

## 5. Exact write set

### 5.1 Production

- `ui_react/src/pages/LineManagementPage.tsx`
- `ui_react/src/pages/LineManagementPage.css`

現有 query-only artifacts只讀重用，預設不修改：

- `ui_react/src/api/customer_service/**`、`adapters/customer_service/**`
- `ui_react/src/api/line_identity/**`、`adapters/line_identity/**`
- `ui_react/src/api/line_configuration/**`、`adapters/line_configuration/**`

若fresh final matrix發現query decoder缺required/nullability/extra closure，允許在對應client/schema/adapter做最小query修正；不得修改或測試
mutation methods。Backend route/schema預設0 write；任何route raw/security問題只使該surface unavailable，不擴張本包。

### 5.2 Tests／evidence

- `ui_react/src/tests/line_management_query_page.test.tsx`
- `ui_react/src/tests/line_management_query_request_budget.test.tsx`
- `ui_react/src/tests/line_management_query_no_fake_mutation.test.tsx`
- 現有 customer service／identity／configuration／rich-menu client與adapter focused regression。
- 本包 evidence directory。

不得修改backend、DB、provider、worker、shared transport/Auth、package/lockfile、其他pages、README、main plan或shared matrix。
`LineManagementPage.tsx/.css`只有本包一位writer。

## 6. Request budget／state

| Active surface | Budget | Lazy detail |
|---|---:|---:|
| Tickets | summary 1 + list 1 | selected ticket detail 1 |
| Identity | list 1 | selected binding detail 1 |
| Notification Rules | catalog 1 | detail local from decoded catalog，0 GET |
| Rich Menu | configuration 1 + publications 1 | selected publication detail 1 |
| Delivery／FAQ／Order Groups | 0 | 0 |

Runtime只載入active tab，不預抓其他tab；0 polling、0 StrictMode duplicate、0 unbounded pagination。tab/detail/retry切換需abort舊request、
generation discard stale response。每條query各自loading／empty／typed error／retry，不以另一條成功掩蓋失敗。

無token零fetch；401/403/404/409/422/503/timeout/network顯示typed code與安全message，不renderraw response。Schema drift顯示
unavailable；server empty顯示empty，兩者不得混同。

## 7. Gates

1. G0：exact approval、fresh baseline、LineManagementPage唯一writer、0 backend/DB/provider。
2. G1：四組GET final field/redaction/error/request matrix；三組unavailable surface固定。
3. G2：現有strict clients negative cases與fresh token/abort regression通過。
4. G3：page只呼叫query interface；source/network test證明non-GET=0。
5. G4：所有mutation controls native disabled，無resolve/revoke/publish/save/retry/replay handler。
6. G5：loading/empty/error/retry/stale/deep-link、loaded scope、Drawer query tests。
7. G6：focused/full React、build/lint、UTF-8/header/diff/secret/PII/write-set/skip scans。
8. G7：真FastAPI + Vite + TOTP browser，existing DB只做四組GET Network→DOM；0 provider call。

完成上限為`query-real-data-validated`。不得宣稱mutation、delivery、FAQ、order-group、entry cutover或Streamlit retirement完成。

## 8. Existing Work Package disposition

- Phase 3A的query artifacts可重用；其resolve/revocation mutation與browser blocker不作本包PASS證據。
- completed Phase 4C Rules／Rich Menu query artifacts作候選輸入，仍須本包fresh regression與browser GET。
- Delivery、Knowledge與Order Groups相關WPs不因本包啟動；其surface保持unavailable。
- 不改舊WP status或shared index；由Integration Owner後續裁決successor關係。

## 9. DB gate

| Gate | Status | Reason |
|---|---|---|
| Scope gate | BLOCKED | proposed；exact approval前不改production |
| Change inventory | PASS | 0 schema/seed/backfill/destructive；React query-only |
| Static release gate | NOT_RUN | 無schema release |
| Descriptor gate | NOT_RUN | 無owned-object變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不建立DB；existing DB只GET browser |
| Developer acceptance gate | NOT_RUN | 不操作既有DB |

結論：`DB_CHANGE_NOT_READY`。

---
doc_type: evidence-matrix-draft
declared_status: draft
identity: PROV-20260817-react-admin-line-query-page-slice-evidence-matrix
date: 2026-08-17
owner: LINE React Page Integration Owner
not_a_receipt: true
---

# LINE Management Query Page-Slice Evidence Matrix（Draft）

本草案不是contract freeze、人工核准或implementation receipt。

## 1. Query surface matrix

| Tab | GET／client | Allowed display | Disposition |
|---|---|---|---|
| Customer Service | summary/list/detail | safe counts、ticket id、masked subject、case/category/summary/time/status/version/events | wired candidate |
| LINE Identity | binding list/detail | masked LINE user id、subject name/type、status/version/updated/revocation status | wired candidate |
| Notification Rules | configuration catalog | revision、rule id、event/recipient/template、schedule/frequency/enabled | wired candidate |
| Rich Menu | menu configuration、publication list/detail | menu safe label/revision、publication id/status/loaded scope | wired candidate |
| Delivery | none in page-slice | unavailable only | 0 GET |
| FAQ／Knowledge | none in page-slice | unavailable only；0 static FAQ article | 0 GET |
| Order Groups | none in page-slice | unavailable only | 0 GET |

## 2. Mutation exclusion matrix

| Family | Controls | Required state |
|---|---|---|
| Ticket | resolve preview/apply/retry、update、reply | native disabled；0 non-GET |
| Identity | revoke preview/apply/observe、invite/replacement/manual | native disabled；0 non-GET |
| Rules | create/save/delete/replay | native disabled |
| Rich Menu | publish/retry/upload/delete | native disabled；0 provider |
| Delivery | retry/replay/cancel/run-now | native disabled |
| FAQ | create/save/publish/retire/reindex | native disabled |
| Groups | create/bind/unbind/replay | native disabled |

## 3. Evidence cases

- active-tab-only request budget與no StrictMode duplicate。
- fresh memory bearer；caller Authorization不能覆蓋。
- list/summary/detail success、empty、401/403/404、schema mismatch、timeout/abort/stale。
- response/DOM deny list：raw LINE user id、action URI、postback、image path、provider id、payload、correlation、raw error。
- source/network scan證明0 POST/PUT/PATCH/DELETE與0 fake mutation。
- existing DB只做真browser GET；不得呼叫LINE provider。

## 4. Known live distinction

- Current page含客服resolve與identity revocation state machines；它們必須從query-only page移除或全部鎖定，不能當作本包完成證據。
- Rules／Rich Menu已存在strict frontend decoder；backend route標示raw dict不允許穿透renderer，只能經既有verified client。
- FAQ目前含hard-coded文章，final page必須改為unavailable，不得保留為production fallback。

## 5. Forbidden substitutions

- Mutation tests、HTTP 200、mock、static FAQ、delivery/task route存在都不能證明query page完成。
- 不為raw delivery／FAQ／order-groups拆欄位gap；原位unavailable。
- 不修改DB、provider、worker、backend或shared Auth。

Final matrix由Integration Owner在production施工前依live client/schema/route重新凍結。

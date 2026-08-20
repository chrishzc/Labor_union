---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-contract-signing-public-query-redaction-contract-gap
date: 2026-08-17
owner: Orders Contract Signing / Access Integration Owner
domain: Contract Signing
production_mutation_authorized: false
---

# Contract Signing public Query／redaction contract缺口

## 現況與風險

`GET /api/v1/orders/{case_no}/contract-signing`目前為`BaseResponse[dict]`，同route family另有文件下載與多個
mutation。React Orders 曾直接呼叫此 raw Query，導致 UI 可能把未凍結欄位、文件identity或簽署/送達狀態當成
正式契約。Phase 2A remediation必須先移除此呼叫並保留 unavailable slot。

## 待人工裁決

1. Public Query只可回哪些 staff/client signing milestones、document version metadata與delivery evidence。
2. 契約已產生、已寄送、provider delivered、已簽回、commitment完成必須是不同facts；何者由哪個owner提供。
3. 文件metadata的PII class、masked filename/MIME/size/digest/version；不得暴露storage path、provider payload或原始簽署資料。
4. Preview/download authorization、capability、security audit、retention與一次性下載語意。
5. Contract Signing view與Orders terms／contract-completion的重疊欄位由誰canonical ownership，禁止雙重推導。
6. not-found／forbidden／stale／document-unavailable的Global typed errors及correlation policy。

## 本gap exact write set

- 本文件
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-contract-signing-public-query-redaction-contract-gap/contract-query-field-owner-matrix.md`（new）
- `02/README.md`與正式規格索引只由Integration Owner late-bind。

0 production code、0 API/schema、0 React、0 DB。人工裁決完成後另立backend public-query hardening與React
successor exact WPs；不得直接擴張本gap。

## DB gate

| Gate | 狀態 | 理由 |
|---|---|---|
| Scope gate | PASS | docs-only public contract decision |
| Change inventory | PASS | 0 schema/seed/backfill/destructive |
| Static release gate | NOT_RUN | 無DB變更 |
| Descriptor gate | NOT_RUN | 無DB變更 |
| Read-only plan gate | NOT_RUN | 無DB變更 |
| Engine verification gate | NOT_RUN | 無DB變更 |
| Developer acceptance gate | NOT_RUN | 無DB變更 |

總結：`DB_CHANGE_NOT_READY`。
